"""Browser-level QA for the embedded editorial security workbench."""

import json
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

playwright = pytest.importorskip("playwright.sync_api")
from playwright.sync_api import expect, sync_playwright


PROJECT_ROOT = Path(__file__).resolve().parent


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def base_url():
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=PROJECT_ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("The test server stopped before becoming ready.")
        try:
            with urllib.request.urlopen(f"{url}/api/v1/gateway/health", timeout=2) as response:
                if response.status == 200:
                    break
        except OSError:
            time.sleep(0.2)
    else:
        process.terminate()
        raise RuntimeError("Timed out waiting for the test server.")

    yield url

    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as runtime:
        # Use the full Chromium channel so CI does not also require the optional
        # headless-shell download.
        browser_instance = runtime.chromium.launch(channel="chromium", headless=True)
        yield browser_instance
        browser_instance.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page_instance = context.new_page()
    yield page_instance
    context.close()


def _mock_health(page, status=200):
    body = {
        "status": "healthy",
        "version": "2.0.0",
        "gateway": "Anti-LLM Injection Gateway",
        "model_info": {"model": "test/model"},
        "capabilities": [],
    }
    page.route(
        "**/api/v1/gateway/health",
        lambda route: route.fulfill(
            status=status,
            content_type="application/json",
            body=json.dumps(body if status == 200 else {"detail": "Unavailable"}),
        ),
    )


def _result(action="Allow", **overrides):
    risk_by_action = {
        "Allow": "none",
        "Mask": "medium",
        "Warn": "medium",
        "Block": "critical",
    }
    result = {
        "request_id": "req-browser-01",
        "original_prompt": "Browser test prompt",
        "sanitized_prompt": "Browser test prompt",
        "policy_action": action,
        "risk_level": risk_by_action.get(action, "none"),
        "injection_detected": action == "Block",
        "injection_score": 0.78 if action == "Block" else 0.0,
        "injection_severity": "critical" if action == "Block" else "none",
        "injection_matched_keywords": ["ignore previous instructions"] if action == "Block" else [],
        "injection_details": {
            "severity": "critical" if action == "Block" else "none",
            "threat_categories": ["instruction_override"] if action == "Block" else [],
            "total_indicators": 1 if action == "Block" else 0,
            "encoding_attacks": [],
            "structural_anomalies": [],
        },
        "threat_categories": ["instruction_override"] if action == "Block" else [],
        "block_reasons": ["Instruction override detected"] if action == "Block" else [],
        "pii_detected": action == "Mask",
        "pii_entities": [],
        "pii_sensitivity": None,
        "gateway_latency_ms": 8.42,
        "warning": "Elevated signals require review" if action == "Warn" else None,
    }
    result.update(overrides)
    return result


def _mock_json(page, pattern, body, status=200):
    page.route(
        pattern,
        lambda route: route.fulfill(
            status=status,
            content_type="application/json",
            body=json.dumps(body),
        ),
    )


def test_health_presets_and_character_count(page, base_url):
    _mock_health(page)
    page.goto(base_url)

    expect(page.get_by_test_id("health-status")).to_contain_text("Gateway healthy")
    expect(page.get_by_text("test/model", exact=True)).to_be_visible()
    page.get_by_role("button", name="Clean question").click()
    expect(page.get_by_label("Prompt to evaluate")).to_have_value("Can you explain the difference between symmetric and asymmetric encryption in simple terms?")
    expect(page.locator("#charCount")).to_have_text("91 / 50,000")
    expect(page.get_by_role("button", name="Clean question")).to_have_attribute("aria-pressed", "true")


def test_empty_validation_and_keyboard_submission(page, base_url):
    _mock_health(page)
    _mock_json(page, "**/api/v1/gateway/process", _result())
    page.goto(base_url)

    page.get_by_role("button", name="Inspect prompt without model inference").click()
    expect(page.get_by_role("alert")).to_have_text("Enter a prompt before starting an inspection.")
    expect(page.get_by_label("Prompt to evaluate")).to_have_attribute("aria-invalid", "true")

    page.get_by_label("Prompt to evaluate").fill("Browser test prompt")
    page.get_by_label("Prompt to evaluate").press("Control+Enter")
    expect(page.get_by_role("heading", name="Request allowed")).to_be_visible()
    expect(page.get_by_text("req-browser-01", exact=True)).to_be_visible()


def test_loading_state_is_explicit(page, base_url):
    _mock_health(page)
    page.goto(base_url)
    expect(page.get_by_test_id("health-status")).to_contain_text("Gateway healthy")
    page.evaluate("setBusy(true); setView('loading')")
    expect(page.get_by_test_id("loading-state")).to_be_visible()
    expect(page.get_by_role("button", name="Inspect prompt without model inference")).to_be_disabled()
    expect(page.locator(".results-shell")).to_have_attribute("aria-busy", "true")


@pytest.mark.parametrize(
    ("action", "heading"),
    [
        ("Allow", "Request allowed"),
        ("Mask", "Sensitive data masked"),
        ("Warn", "Request allowed with warning"),
        ("Block", "Request blocked"),
    ],
)
def test_policy_states_render(page, base_url, action, heading):
    _mock_health(page)
    overrides = {}
    if action == "Mask":
        overrides = {
            "sanitized_prompt": "Email <EMAIL_ADDRESS>",
            "pii_entities": [
                {
                    "entity_type": "EMAIL_ADDRESS",
                    "start": 6,
                    "end": 23,
                    "score": 0.95,
                    "sensitivity": "medium",
                }
            ],
        }
    _mock_json(page, "**/api/v1/gateway/process", _result(action, **overrides))
    page.goto(base_url)
    page.get_by_label("Prompt to evaluate").fill("Browser test prompt")
    page.get_by_role("button", name="Inspect prompt without model inference").click()

    expect(page.get_by_role("heading", name=heading)).to_be_visible()
    expect(page.get_by_test_id("results-container")).to_be_visible()
    expect(page.get_by_text(action, exact=True)).to_be_visible()
    if action == "Mask":
        expect(page.get_by_text("EMAIL_ADDRESS", exact=True)).to_be_attached()
        expect(page.get_by_text("Email <EMAIL_ADDRESS>", exact=True)).to_be_attached()
    if action == "Block":
        expect(page.get_by_text("Stopped by policy", exact=True)).to_be_visible()


def test_chat_response_is_rendered_as_text(page, base_url):
    _mock_health(page)
    response = _result(
        llm_inference_latency_ms=123.0,
        llm_response='<img src=x onerror="window.__unsafe=true"> Safe response',
        llm_model="test/model",
    )
    _mock_json(page, "**/api/v1/gateway/chat", response)
    page.goto(base_url)
    page.get_by_label("Security + model").check()
    page.get_by_label("Prompt to evaluate").fill("Browser test prompt")
    page.get_by_role("button", name="Inspect prompt and send allowed content to the model").click()

    expect(page.get_by_text("Protected model output", exact=True)).to_be_visible()
    expect(page.locator("#llmCode")).to_contain_text("Safe response")
    expect(page.locator("#llmCode img")).to_have_count(0)
    assert page.evaluate("window.__unsafe") is None


@pytest.mark.parametrize("status", [422, 401, 429, 500, 503])
def test_http_errors_are_inline_and_controls_recover(page, base_url, status):
    _mock_health(page)
    _mock_json(page, "**/api/v1/gateway/process", {"detail": "Controlled failure"}, status=status)
    page.goto(base_url)
    page.get_by_label("Prompt to evaluate").fill("Browser test prompt")
    page.get_by_role("button", name="Inspect prompt without model inference").click()

    expect(page.get_by_test_id("request-error")).to_have_text(f"Gateway error {status}: Controlled failure")
    expect(page.get_by_role("button", name="Inspect prompt without model inference")).to_be_enabled()
    expect(page.locator(".results-shell")).to_have_attribute("aria-busy", "false")


def test_malformed_and_network_errors_are_inline(page, base_url):
    _mock_health(page)
    page.route(
        "**/api/v1/gateway/process",
        lambda route: route.fulfill(status=200, content_type="application/json", body="{not-json"),
    )
    page.goto(base_url)
    page.get_by_label("Prompt to evaluate").fill("Browser test prompt")
    page.get_by_role("button", name="Inspect prompt without model inference").click()
    expect(page.get_by_test_id("request-error")).to_have_text("The gateway returned malformed JSON.")

    page.unroute("**/api/v1/gateway/process")
    page.route("**/api/v1/gateway/process", lambda route: route.abort("connectionfailed"))
    page.get_by_role("button", name="Inspect prompt without model inference").click()
    expect(page.get_by_test_id("request-error")).to_have_text("The gateway could not be reached. Check the connection and try again.")


def test_health_failure_has_degraded_state(page, base_url):
    _mock_health(page, status=503)
    page.goto(base_url)
    expect(page.get_by_test_id("health-status")).to_contain_text("Health unavailable")
    expect(page.get_by_test_id("health-status")).to_have_attribute("data-state", "degraded")


@pytest.mark.parametrize("viewport", [(1440, 900), (768, 900), (390, 844)])
def test_responsive_layout_has_no_horizontal_overflow(page, base_url, viewport):
    _mock_health(page)
    page.set_viewport_size({"width": viewport[0], "height": viewport[1]})
    page.goto(base_url)
    expect(page.get_by_role("heading", name="Inspect what reaches your model.")).to_be_visible()
    overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
    assert overflow is False
