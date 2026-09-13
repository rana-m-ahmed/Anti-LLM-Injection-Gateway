"""Browser QA for the responsive precision-instrument security cockpit."""

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
SCREENSHOT_ROOT = PROJECT_ROOT / "test-results" / "precision-ui"


def _free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture(scope="session")
def base_url():
    port = _free_port()
    url = f"http://127.0.0.1:{port}"
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)],
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
        instance = runtime.chromium.launch(channel="chromium", headless=True)
        yield instance
        instance.close()


@pytest.fixture
def page(browser):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    instance = context.new_page()
    yield instance
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
    risk_by_action = {"Allow": "none", "Mask": "medium", "Warn": "medium", "Block": "critical"}
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
    page.route(pattern, lambda route: route.fulfill(status=status, content_type="application/json", body=json.dumps(body)))


def _submit(page, prompt="Browser test prompt"):
    page.get_by_label("Prompt payload").fill(prompt)
    page.get_by_role("button", name="Inspect prompt without model inference").click()


def test_health_presets_and_character_count(page, base_url):
    _mock_health(page)
    page.goto(base_url)
    expect(page.get_by_test_id("health-status")).to_contain_text("Gateway healthy")
    expect(page.get_by_text("test/model", exact=True)).to_be_visible()
    page.get_by_role("button", name="Clean question").click()
    expect(page.get_by_label("Prompt payload")).to_have_value(
        "Can you explain the difference between symmetric and asymmetric encryption in simple terms?"
    )
    expect(page.locator("#charCount")).to_have_text("91 / 50,000")
    expect(page.get_by_role("button", name="Clean question")).to_have_attribute("aria-pressed", "true")


def test_empty_validation_and_keyboard_submission(page, base_url):
    _mock_health(page)
    _mock_json(page, "**/api/v1/gateway/process", _result())
    page.goto(base_url)
    page.get_by_role("button", name="Inspect prompt without model inference").click()
    expect(page.locator("#formError")).to_have_text("Enter a prompt before starting an inspection.")
    expect(page.get_by_label("Prompt payload")).to_have_attribute("aria-invalid", "true")
    page.get_by_label("Prompt payload").fill("Browser test prompt")
    page.get_by_label("Prompt payload").press("Control+Enter")
    expect(page.get_by_role("heading", name="Request allowed")).to_be_visible()
    expect(page.get_by_text("req-browser-01", exact=True)).to_be_visible()


def test_loading_state_and_controls(page, base_url):
    _mock_health(page)
    pending_routes = []
    page.route("**/api/v1/gateway/process", lambda route: pending_routes.append(route))
    page.goto(base_url)
    page.get_by_label("Prompt payload").fill("Browser test prompt")
    page.get_by_role("button", name="Inspect prompt without model inference").click()
    expect(page.get_by_test_id("loading-state")).to_be_visible()
    expect(page.locator(".results-shell")).to_have_attribute("aria-busy", "true")
    expect(page.get_by_role("button", name="Inspect prompt without model inference")).to_be_disabled()
    pending_routes[0].fulfill(status=200, content_type="application/json", body=json.dumps(_result()))
    expect(page.get_by_role("heading", name="Request allowed")).to_be_visible()
    expect(page.locator(".results-shell")).to_have_attribute("aria-busy", "false")
    expect(page.get_by_role("button", name="Inspect prompt without model inference")).to_be_enabled()


@pytest.mark.parametrize(
    ("action", "heading"),
    [("Allow", "Request allowed"), ("Mask", "Sensitive data masked"), ("Warn", "Review recommended"), ("Block", "Request blocked")],
)
def test_policy_states_render(page, base_url, action, heading):
    _mock_health(page)
    overrides = {}
    if action == "Mask":
        overrides = {
            "sanitized_prompt": "Email <EMAIL_ADDRESS>",
            "pii_entities": [
                {"entity_type": "EMAIL_ADDRESS", "start": 6, "end": 23, "score": 0.95, "sensitivity": "medium"}
            ],
        }
    _mock_json(page, "**/api/v1/gateway/process", _result(action, **overrides))
    page.goto(base_url)
    _submit(page)
    expect(page.get_by_role("heading", name=heading)).to_be_visible()
    expect(page.get_by_test_id("results-container")).to_be_visible()
    expect(page.locator("#verdictCard")).to_have_attribute("data-action", action)
    if action == "Mask":
        page.get_by_role("tab", name="Signals 1").click()
        expect(page.get_by_text("EMAIL_ADDRESS", exact=True)).to_be_visible()
        page.get_by_role("tab", name="Payload").click()
        expect(page.get_by_text("Email <EMAIL_ADDRESS>", exact=True)).to_be_visible()
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
    page.get_by_text("Security + model", exact=True).click()
    page.get_by_label("Prompt payload").fill("Browser test prompt")
    page.get_by_role("button", name="Inspect prompt and send allowed content to the model").click()
    expect(page.get_by_text("Protected model output", exact=True)).to_be_visible()
    expect(page.locator("#llmCode")).to_contain_text("Safe response")
    expect(page.locator("#llmCode img")).to_have_count(0)
    assert page.evaluate("window.__unsafe") is None


def test_execution_route_switcher_updates_route_and_selected_state(page, base_url):
    _mock_health(page)
    page.goto(base_url)
    page.get_by_text("Security + model", exact=True).click()
    expect(page.get_by_label("Security + model")).to_be_checked()
    expect(page.locator("#routeValue")).to_have_text("/chat")
    expect(page.get_by_role("button", name="Inspect prompt and send allowed content to the model")).to_be_visible()
    expect(page.locator(".mode-track")).to_have_attribute("data-mode", "chat")
    page.wait_for_timeout(500)
    position = page.evaluate("""(() => {
      const track = document.querySelector('.mode-track').getBoundingClientRect();
      const indicator = document.querySelector('.mode-indicator').getBoundingClientRect();
      return { track: track.toJSON(), indicator: indicator.toJSON(), transform: getComputedStyle(document.querySelector('.mode-indicator')).transform };
    })()""")
    assert position["indicator"]["left"] > position["track"]["left"] + position["track"]["width"] / 2 - 10, position
    page.get_by_text("Security only", exact=True).click()
    expect(page.get_by_label("Security only")).to_be_checked()
    expect(page.locator("#routeValue")).to_have_text("/process")
    page.wait_for_timeout(320)
    assert page.evaluate("""(() => {
      const track = document.querySelector('.mode-track').getBoundingClientRect();
      const indicator = document.querySelector('.mode-indicator').getBoundingClientRect();
      return indicator.left < track.left + track.width / 2;
    })()""")


@pytest.mark.parametrize("status", [422, 401, 429, 500, 503])
def test_http_errors_are_inline_and_controls_recover(page, base_url, status):
    _mock_health(page)
    _mock_json(page, "**/api/v1/gateway/process", {"detail": "Controlled failure"}, status=status)
    page.goto(base_url)
    _submit(page)
    expect(page.get_by_test_id("request-error")).to_have_text(f"Gateway error {status}: Controlled failure")
    expect(page.get_by_role("button", name="Inspect prompt without model inference")).to_be_enabled()
    expect(page.locator(".results-shell")).to_have_attribute("aria-busy", "false")


def test_malformed_and_network_errors_are_inline(page, base_url):
    _mock_health(page)
    page.route("**/api/v1/gateway/process", lambda route: route.fulfill(status=200, content_type="application/json", body="{not-json"))
    page.goto(base_url)
    _submit(page)
    expect(page.get_by_test_id("request-error")).to_have_text("The gateway returned malformed JSON.")
    page.unroute("**/api/v1/gateway/process")
    page.route("**/api/v1/gateway/process", lambda route: route.abort("connectionfailed"))
    page.get_by_role("button", name="Inspect prompt without model inference").click()
    expect(page.get_by_test_id("request-error")).to_have_text("The gateway could not be reached. Check the connection and try again.")


def test_timeout_is_inline_and_controls_recover(browser, base_url):
    context = browser.new_context(viewport={"width": 1024, "height": 768})
    page = context.new_page()
    page.add_init_script(
        """const nativeTimeout = window.setTimeout;
        window.setTimeout = (callback, delay, ...args) =>
          nativeTimeout(callback, delay === 30000 ? 60 : delay, ...args);"""
    )
    _mock_health(page)
    page.route("**/api/v1/gateway/process", lambda route: None)
    page.goto(base_url)
    _submit(page)
    expect(page.get_by_test_id("request-error")).to_have_text("The gateway timed out after 30 seconds. Try again.")
    expect(page.get_by_role("button", name="Inspect prompt without model inference")).to_be_enabled()
    context.close()


def test_health_failure_has_offline_state(page, base_url):
    _mock_health(page, status=503)
    page.goto(base_url)
    expect(page.get_by_test_id("health-status")).to_contain_text("Gateway offline")
    expect(page.get_by_test_id("health-status")).to_have_attribute("data-state", "offline")


def test_unknown_policy_is_rendered_defensively(page, base_url):
    _mock_health(page)
    _mock_json(page, "**/api/v1/gateway/process", _result("Escalate"))
    page.goto(base_url)
    _submit(page)
    expect(page.get_by_role("heading", name="Unknown decision")).to_be_visible()
    expect(page.get_by_text("Unknown value: Escalate", exact=True)).to_be_visible()


def test_mobile_two_step_workflow_preserves_prompt_and_focus(browser, base_url):
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    _mock_health(page)
    _mock_json(page, "**/api/v1/gateway/process", _result())
    page.goto(base_url)
    expect(page.get_by_role("heading", name="Compose")).to_be_visible()
    expect(page.get_by_role("heading", name="Evidence")).to_be_hidden()
    page.get_by_label("Prompt payload").fill("Keep this payload intact")
    page.get_by_role("button", name="Inspect prompt without model inference").click()
    expect(page.get_by_role("heading", name="Request allowed")).to_be_visible()
    expect(page.locator("#verdictTitle")).to_be_focused()
    page.get_by_role("button", name="Back to prompt").click()
    expect(page.get_by_label("Prompt payload")).to_have_value("Keep this payload intact")
    expect(page.get_by_role("heading", name="Compose")).to_be_visible()
    context.close()


def test_mobile_api_error_returns_to_compose(browser, base_url):
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    _mock_health(page)
    _mock_json(page, "**/api/v1/gateway/process", {"detail": "Policy unavailable"}, status=503)
    page.goto(base_url)
    _submit(page)
    expect(page.get_by_role("heading", name="Compose")).to_be_visible()
    expect(page.locator("#formError")).to_contain_text("Gateway error 503")
    expect(page.get_by_role("button", name="Inspect prompt without model inference")).to_be_enabled()
    context.close()


@pytest.mark.parametrize("viewport", [(320, 720), (390, 844), (768, 1024), (900, 760), (1024, 768), (1440, 900), (1920, 1080)])
def test_responsive_layout_has_no_horizontal_overflow(browser, base_url, viewport):
    context = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]})
    page = context.new_page()
    _mock_health(page)
    page.goto(base_url)
    expect(page.get_by_role("heading", name="Compose")).to_be_visible()
    overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
    assert overflow is False
    if viewport[0] < 900:
        expect(page.locator(".mobile-steps")).to_be_visible()
        expect(page.get_by_role("heading", name="Evidence")).to_be_hidden()
    else:
        expect(page.locator(".mobile-steps")).to_be_hidden()
        expect(page.get_by_role("heading", name="Evidence")).to_be_visible()
    context.close()


def test_reduced_motion_keeps_functionality(browser, base_url):
    context = browser.new_context(viewport={"width": 1024, "height": 768}, reduced_motion="reduce")
    page = context.new_page()
    _mock_health(page)
    _mock_json(page, "**/api/v1/gateway/process", _result("Block"))
    page.goto(base_url)
    _submit(page)
    expect(page.get_by_role("heading", name="Request blocked")).to_be_visible()
    duration = page.evaluate("getComputedStyle(document.querySelector('.preset')).transitionDuration")
    assert duration in {"1e-06s", "0.001ms", "0s"}
    context.close()


def test_anime_failure_keeps_workbench_functional(browser, base_url):
    context = browser.new_context(viewport={"width": 1024, "height": 768})
    page = context.new_page()
    _mock_health(page)
    page.route("**/assets/vendor/anime.esm.min.js", lambda route: route.abort("failed"))
    _mock_json(page, "**/api/v1/gateway/process", _result())
    page.goto(base_url)
    _submit(page)
    expect(page.get_by_role("heading", name="Request allowed")).to_be_visible()
    expect(page.get_by_test_id("results-container")).to_be_visible()
    context.close()


def test_keyboard_tab_navigation(page, base_url):
    _mock_health(page)
    _mock_json(page, "**/api/v1/gateway/process", _result("Block"))
    page.goto(base_url)
    _submit(page)
    page.get_by_role("tab", name="Overview").focus()
    page.keyboard.press("ArrowRight")
    expect(page.get_by_role("tab", name="Signals 2")).to_be_focused()
    expect(page.locator("#signalsPanel")).to_be_visible()


def test_copy_control_reports_success(browser, base_url):
    context = browser.new_context(viewport={"width": 1024, "height": 768}, permissions=["clipboard-read", "clipboard-write"])
    page = context.new_page()
    _mock_health(page)
    _mock_json(page, "**/api/v1/gateway/process", _result())
    page.goto(base_url)
    _submit(page)
    page.get_by_role("tab", name="Payload").click()
    page.locator('[data-copy-target="rawCode"]').click()
    expect(page.locator("#copyStatus")).to_have_text("Copied to clipboard.")
    assert "req-browser-01" in page.evaluate("navigator.clipboard.readText()")
    context.close()


def test_orientation_change_preserves_compose_state(browser, base_url):
    context = browser.new_context(viewport={"width": 390, "height": 844})
    page = context.new_page()
    _mock_health(page)
    page.goto(base_url)
    page.get_by_label("Prompt payload").fill("Preserve through rotation")
    page.set_viewport_size({"width": 844, "height": 390})
    expect(page.get_by_label("Prompt payload")).to_have_value("Preserve through rotation")
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    page.set_viewport_size({"width": 390, "height": 844})
    expect(page.get_by_label("Prompt payload")).to_have_value("Preserve through rotation")
    context.close()


def test_long_evidence_is_contained_at_320px(browser, base_url):
    context = browser.new_context(viewport={"width": 320, "height": 720})
    page = context.new_page()
    _mock_health(page)
    long_value = "<script>never-render-as-html</script> " * 90
    result = _result(
        "Mask",
        request_id="request-" + "x" * 120,
        sanitized_prompt=long_value,
        threat_categories=[long_value],
        injection_matched_keywords=[long_value],
        pii_entities=[
            {"entity_type": "VERY_LONG_SECRET_ENTITY_NAME", "start": 2, "end": 49999, "score": 0.999, "sensitivity": "critical"}
        ],
    )
    _mock_json(page, "**/api/v1/gateway/process", result)
    page.goto(base_url)
    _submit(page, "A" * 2000)
    page.get_by_role("tab", name="Signals 3").click()
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    assert page.evaluate("document.querySelector('.table-wrap').scrollWidth > document.querySelector('.table-wrap').clientWidth")
    page.get_by_role("tab", name="Payload").click()
    expect(page.locator("#sanitizedCode script")).to_have_count(0)
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    context.close()


def test_visual_snapshots_cover_all_workbench_states(browser, base_url):
    SCREENSHOT_ROOT.mkdir(parents=True, exist_ok=True)
    viewports = {"desktop": (1440, 900), "mobile": (390, 844)}
    result_states = {
        "allowed": _result("Allow"),
        "masked": _result("Mask", sanitized_prompt="Email <EMAIL_ADDRESS>"),
        "warned": _result("Warn"),
        "blocked": _result("Block"),
    }

    for device, viewport in viewports.items():
        for visual_state in ["idle", "scanning", *result_states, "error"]:
            context = browser.new_context(viewport={"width": viewport[0], "height": viewport[1]})
            page = context.new_page()
            _mock_health(page)
            pending_routes = []
            if visual_state == "scanning":
                page.route("**/api/v1/gateway/process", lambda route: pending_routes.append(route))
            elif visual_state == "error":
                _mock_json(page, "**/api/v1/gateway/process", {"detail": "Gateway temporarily unavailable"}, status=503)
            elif visual_state in result_states:
                _mock_json(page, "**/api/v1/gateway/process", result_states[visual_state])

            page.goto(base_url)
            page.wait_for_timeout(600)
            if visual_state != "idle":
                _submit(page)
                if visual_state == "scanning":
                    expect(page.get_by_test_id("loading-state")).to_be_visible()
                elif visual_state == "error":
                    expect(page.locator("#formError") if device == "mobile" else page.get_by_test_id("request-error")).to_contain_text("503")
                    page.wait_for_timeout(450)
                else:
                    expect(page.get_by_test_id("results-container")).to_be_visible()
                    page.wait_for_timeout(750)
            page.screenshot(path=SCREENSHOT_ROOT / f"{device}-{visual_state}.png", full_page=False)
            context.close()
