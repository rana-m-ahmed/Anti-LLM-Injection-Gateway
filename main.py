import time

import requests
from fastapi import FastAPI, HTTPException

from injection_detector import InjectionDetector
from llm_connector import OllamaConnector
from pii_analyzer import PIIAnalyzer
from policy_engine import PolicyEngine

app = FastAPI(title="Presidio LLM Security Mini-Gateway", version="1.0.0")

injection_detector = InjectionDetector(threshold=0.55)
pii_analyzer = PIIAnalyzer()
policy_engine = PolicyEngine(injection_block_threshold=0.55)
ollama_connector = OllamaConnector()


def extract_prompt(payload):
    # Pull the prompt from the request and validate it
    prompt = payload.get("prompt", "")
    if not isinstance(prompt, str) or not prompt.strip():
        raise HTTPException(status_code=400, detail="Payload must include non-empty 'prompt'.")
    return prompt


def run_gateway_pipeline(prompt):
    # Core pipeline: injection check -> PII scan -> policy decision
    gateway_start = time.time()

    is_injection, injection_score, matched_keywords = injection_detector.analyze(prompt)

    pii_findings = pii_analyzer.analyze(prompt)
    pii_entities = [
        {
            "entity_type": item.entity_type,
            "start": item.start,
            "end": item.end,
            "score": round(item.score, 4),
        }
        for item in pii_findings
    ]

    decision = policy_engine.evaluate(
        prompt=prompt,
        injection_score=injection_score,
        pii_findings=pii_findings,
        pii_analyzer=pii_analyzer,
    )

    gateway_latency_ms = round((time.time() - gateway_start) * 1000.0, 2)

    return {
        "original_prompt": prompt,
        "sanitized_prompt": decision["sanitized_prompt"],
        "policy_action": decision["policy_action"],
        "injection_detected": is_injection,
        "injection_score": injection_score,
        "injection_matched_keywords": matched_keywords,
        "pii_detected": decision["pii_detected"],
        "pii_entities": pii_entities,
        "gateway_latency_ms": gateway_latency_ms,
    }


@app.post("/api/v1/gateway/process")
def process_gateway(payload: dict):
    # Run the security pipeline and return results
    try:
        prompt = extract_prompt(payload)
        return run_gateway_pipeline(prompt)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Gateway processing failed: {exc}")


@app.post("/api/v1/gateway/chat")
def chat_gateway(payload: dict):
    # Run security pipeline, then query Ollama if allowed
    try:
        prompt = extract_prompt(payload)
        gateway_result = run_gateway_pipeline(prompt)

        if gateway_result["policy_action"] == "Block":
            gateway_result["llm_inference_latency_ms"] = 0.0
            gateway_result["llm_response"] = ""
            return gateway_result

        llm_start = time.time()
        llm_response = ollama_connector.generate(prompt=gateway_result["sanitized_prompt"])
        llm_latency_ms = round((time.time() - llm_start) * 1000.0, 2)

        gateway_result["llm_inference_latency_ms"] = llm_latency_ms
        gateway_result["llm_response"] = llm_response
        return gateway_result

    except HTTPException:
        raise
    except requests.ConnectionError as exc:
        raise HTTPException(status_code=503, detail=f"Ollama connection error: {exc}")
    except requests.HTTPError as exc:
        raise HTTPException(status_code=503, detail=f"Ollama HTTP error: {exc}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Gateway chat failed: {exc}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
