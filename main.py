import os
import time
import uuid
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

import groq
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel, Field
from typing import Optional

from injection_detector import InjectionDetector
from llm_connector import GroqConnector
from pii_analyzer import PIIAnalyzer
from policy_engine import PolicyEngine
from ui import GATEWAY_HTML_UI

# ── App Version ──
APP_VERSION = "2.0.0"
MAX_PROMPT_LENGTH = 50_000


# ── Pydantic Models ──

class GatewayRequest(BaseModel):
    """Request body for gateway endpoints."""
    prompt: str = Field(
        ...,
        min_length=1,
        max_length=MAX_PROMPT_LENGTH,
        description="The prompt text to analyze and optionally forward to the LLM.",
        examples=["Summarize the history of public key cryptography"],
    )


class PIIEntity(BaseModel):
    """A detected PII entity."""
    entity_type: str
    start: int
    end: int
    score: float
    sensitivity: Optional[str] = None


class InjectionDetail(BaseModel):
    """Detailed injection analysis breakdown."""
    severity: str
    threat_categories: list[str] = []
    total_indicators: int = 0
    encoding_attacks: list[dict] = []
    structural_anomalies: list[dict] = []


class GatewayResponse(BaseModel):
    """Response from the security gateway pipeline."""
    request_id: str = Field(description="Unique request identifier for tracing")
    original_prompt: str
    sanitized_prompt: str
    policy_action: str = Field(description="Block | Warn | Mask | Allow")
    risk_level: str = Field(description="critical | high | medium | low | none")
    injection_detected: bool
    injection_score: float
    injection_severity: str
    injection_matched_keywords: list[str] = []
    injection_details: Optional[InjectionDetail] = None
    threat_categories: list[str] = []
    block_reasons: list[str] = []
    pii_detected: bool
    pii_entities: list[PIIEntity] = []
    pii_sensitivity: Optional[str] = None
    gateway_latency_ms: float
    warning: Optional[str] = None


class ChatResponse(GatewayResponse):
    """Response from the chat endpoint (gateway + LLM inference)."""
    llm_inference_latency_ms: float = 0.0
    llm_response: str = ""
    llm_model: Optional[str] = None


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    gateway: str
    model_info: dict
    capabilities: list[str]


class ErrorResponse(BaseModel):
    """Standardized error response."""
    request_id: str
    error: str
    detail: str
    status_code: int


# ── App Initialization ──

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    print(f"🛡️  Anti-LLM Injection Gateway v{APP_VERSION} starting...")
    print(f"🤖 Model: {groq_connector.model}")
    print(f"🔍 Injection threshold: {injection_detector.threshold}")
    print(f"📡 Gateway ready.")
    yield
    print("🛑 Gateway shutting down.")


app = FastAPI(
    title="Anti-LLM Injection Gateway",
    description=(
        "A production-grade security gateway for LLM applications. "
        "Detects prompt injection attacks (50+ patterns, encoding attacks, structural anomalies), "
        "identifies and masks PII including developer secrets, "
        "and enforces policy decisions before forwarding to Groq-hosted models."
    ),
    version=APP_VERSION,
    lifespan=lifespan,
)

# ── CORS Middleware ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)




# ── Component Initialization ──
injection_detector = InjectionDetector(threshold=0.55)
pii_analyzer = PIIAnalyzer()
policy_engine = PolicyEngine(injection_block_threshold=0.55, injection_warn_threshold=0.30)
groq_connector = GroqConnector()


# ── Helper Functions ──

def generate_request_id():
    """Generate a unique request ID."""
    return str(uuid.uuid4())[:12]


def run_gateway_pipeline(prompt, request_id):
    """Core pipeline: injection check → PII scan → policy decision."""
    gateway_start = time.time()

    # Step 1: Injection analysis (now returns 4 values with details)
    is_injection, injection_score, matched_keywords, injection_details = (
        injection_detector.analyze(prompt)
    )

    # Step 2: PII analysis
    pii_findings = pii_analyzer.analyze(prompt)
    pii_entities = [
        PIIEntity(
            entity_type=item.entity_type,
            start=item.start,
            end=item.end,
            score=round(item.score, 4),
            sensitivity=PIIAnalyzer.get_entity_sensitivity(item.entity_type),
        )
        for item in pii_findings
    ]

    # Step 3: Policy decision
    decision = policy_engine.evaluate(
        prompt=prompt,
        injection_score=injection_score,
        pii_findings=pii_findings,
        pii_analyzer=pii_analyzer,
        injection_details=injection_details,
    )

    gateway_latency_ms = round((time.time() - gateway_start) * 1000.0, 2)

    result = GatewayResponse(
        request_id=request_id,
        original_prompt=prompt,
        sanitized_prompt=decision["sanitized_prompt"],
        policy_action=decision["policy_action"],
        risk_level=decision.get("risk_level", "none"),
        injection_detected=is_injection,
        injection_score=injection_score,
        injection_severity=injection_details.get("severity", "none"),
        injection_matched_keywords=matched_keywords,
        injection_details=InjectionDetail(
            severity=injection_details.get("severity", "none"),
            threat_categories=injection_details.get("threat_categories", []),
            total_indicators=injection_details.get("total_indicators", 0),
            encoding_attacks=injection_details.get("encoding_attacks", []),
            structural_anomalies=injection_details.get("structural_anomalies", []),
        ),
        threat_categories=decision.get("threat_categories", []),
        block_reasons=decision.get("block_reasons", []),
        pii_detected=decision["pii_detected"],
        pii_entities=pii_entities,
        pii_sensitivity=decision.get("pii_sensitivity"),
        gateway_latency_ms=gateway_latency_ms,
        warning=decision.get("warning"),
    )

    return result, decision


# ── API Endpoints ──

@app.get("/", response_class=HTMLResponse, tags=["UI"])
def root(request: Request):
    """Serve the interactive Web UI for browsers, or JSON info for API clients."""
    accept = request.headers.get("accept", "")
    if "application/json" in accept and "text/html" not in accept:
        return JSONResponse(content={
            "service": "Anti-LLM Injection Gateway",
            "version": APP_VERSION,
            "docs": "/docs",
            "ui": "/",
            "endpoints": {
                "process": "POST /api/v1/gateway/process — Security analysis only",
                "chat": "POST /api/v1/gateway/chat — Security analysis + LLM inference",
                "health": "GET /api/v1/gateway/health — Service health check",
            },
        })
    return HTMLResponse(content=GATEWAY_HTML_UI)


@app.get("/ui", response_class=HTMLResponse, tags=["UI"])
def ui():
    """Direct route to the interactive Web UI."""
    return HTMLResponse(content=GATEWAY_HTML_UI)


@app.get("/api/v1/gateway/health", response_model=HealthResponse, tags=["Health"])
def health_check():
    """Service health check with model info and capabilities."""
    return HealthResponse(
        status="healthy",
        version=APP_VERSION,
        gateway="Anti-LLM Injection Gateway",
        model_info=groq_connector.get_model_info(),
        capabilities=[
            "prompt_injection_detection",
            "encoding_attack_detection",
            "structural_anomaly_analysis",
            "pii_detection",
            "developer_secret_detection",
            "pii_anonymization",
            "risk_scoring",
            "threat_classification",
            "groq_llm_inference",
        ],
    )


@app.post(
    "/api/v1/gateway/process",
    response_model=GatewayResponse,
    tags=["Gateway"],
    summary="Analyze prompt security",
    description="Run the full security pipeline (injection detection, PII scanning, policy evaluation) without calling the LLM.",
)
def process_gateway(payload: GatewayRequest):
    """Run the security pipeline and return results."""
    request_id = generate_request_id()
    try:
        result, _ = run_gateway_pipeline(payload.prompt, request_id)
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Gateway processing failed: {exc}",
        )


@app.post(
    "/api/v1/gateway/chat",
    response_model=ChatResponse,
    tags=["Gateway"],
    summary="Analyze and chat",
    description="Run the security pipeline, then forward safe prompts to the Groq LLM for inference.",
)
def chat_gateway(payload: GatewayRequest):
    """Run security pipeline, then query Groq if allowed."""
    request_id = generate_request_id()
    try:
        gateway_result, decision = run_gateway_pipeline(payload.prompt, request_id)

        chat_result = ChatResponse(**gateway_result.model_dump())

        if decision["policy_action"] == "Block":
            chat_result.llm_inference_latency_ms = 0.0
            chat_result.llm_response = ""
            chat_result.llm_model = groq_connector.model
            return chat_result

        llm_start = time.time()
        llm_response = groq_connector.generate(
            prompt=gateway_result.sanitized_prompt
        )
        llm_latency_ms = round((time.time() - llm_start) * 1000.0, 2)

        chat_result.llm_inference_latency_ms = llm_latency_ms
        chat_result.llm_response = llm_response
        chat_result.llm_model = groq_connector.model
        return chat_result

    except HTTPException:
        raise
    except groq.AuthenticationError as exc:
        raise HTTPException(status_code=401, detail=f"Groq API authentication failed: {exc}")
    except groq.RateLimitError as exc:
        raise HTTPException(status_code=429, detail=f"Groq API rate limit exceeded: {exc}")
    except groq.APIConnectionError as exc:
        raise HTTPException(status_code=503, detail=f"Groq API connection error: {exc}")
    except groq.APIStatusError as exc:
        raise HTTPException(status_code=503, detail=f"Groq API error: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Gateway chat failed: {exc}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
