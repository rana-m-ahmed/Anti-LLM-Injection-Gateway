"""Semantic HTML shell for the zero-build gateway workbench."""

GATEWAY_HTML_UI = r"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="color-scheme" content="dark">
  <meta name="theme-color" content="#090b0d">
  <title>Anti-LLM Injection Gateway</title>
  <link rel="stylesheet" href="/assets/ui.css">
  <script type="module" src="/assets/app.js"></script>
</head>
<body>
  <a class="skip-link" href="#promptInput">Skip to prompt</a>
  <div class="atmosphere" aria-hidden="true">
    <div class="grid-plane"></div>
    <div class="signal-line"></div>
  </div>

  <div id="appFrame" class="app-frame" data-view="compose" data-state="idle">
    <header class="command-bar" data-motion="command">
      <a class="identity" href="/" aria-label="Anti-LLM Injection Gateway home">
        <span class="identity-mark" aria-hidden="true">
          <svg viewBox="0 0 32 32" fill="none">
            <path d="M16 3.5 27 8v7.4c0 6.2-3.8 10.7-11 13.1C8.8 26.1 5 21.6 5 15.4V8l11-4.5Z" stroke="currentColor" stroke-width="1.5"/>
            <path d="M10 16h3l2-5 3 10 2-5h3" stroke="currentColor" stroke-width="1.5"/>
          </svg>
        </span>
        <span class="identity-copy">
          <strong>Injection Gateway</strong>
          <small>Pre-inference security</small>
        </span>
      </a>

      <div class="command-context" aria-label="Current gateway route">
        <span class="context-label">Route</span>
        <span id="routeValue" class="context-value">/process</span>
      </div>

      <div class="runtime-cluster">
        <div class="runtime-data runtime-model">
          <span>Model</span>
          <strong id="modelValue">Resolving</strong>
        </div>
        <div class="runtime-data runtime-version">
          <span>Gateway</span>
          <strong id="versionValue">v--</strong>
        </div>
        <div id="healthStatus" class="health-status" data-state="checking" role="status" aria-live="polite" data-testid="health-status">
          <span class="health-orbit" aria-hidden="true"><i></i></span>
          <span id="healthText">Checking</span>
        </div>
        <nav class="resource-links" aria-label="Gateway resources">
          <a href="/docs" target="_blank" rel="noopener noreferrer">Docs<span aria-hidden="true">↗</span></a>
          <a href="/api/v1/gateway/health" target="_blank" rel="noopener noreferrer">Health<span aria-hidden="true">↗</span></a>
        </nav>
      </div>
    </header>

    <nav class="mobile-steps" aria-label="Workbench steps" data-motion="mobile-nav">
      <button type="button" data-mobile-view="compose" aria-current="step">
        <span>01</span> Compose
      </button>
      <i aria-hidden="true"></i>
      <button type="button" data-mobile-view="evidence">
        <span>02</span> Evidence
      </button>
    </nav>

    <main class="workbench">
      <section class="compose-panel instrument-panel" data-mobile-panel="compose" data-motion="compose" aria-labelledby="composeTitle">
        <header class="panel-header">
          <div>
            <p class="section-index">01 / Prompt intake</p>
            <h1 id="composeTitle" tabindex="-1">Compose</h1>
          </div>
          <span class="panel-code">INPUT::UTF-8</span>
        </header>

        <form id="promptForm" class="compose-form" novalidate data-testid="prompt-form">
          <div class="preset-section">
            <div class="field-heading">
              <span>Test vectors</span>
              <small>Choose a known pattern</small>
            </div>
            <div class="preset-grid" aria-label="Prompt test cases">
              <button type="button" class="preset" data-preset="clean" aria-label="Clean question" aria-pressed="false"><span>01</span>Clean query</button>
              <button type="button" class="preset" data-preset="injection" aria-label="Prompt injection" aria-pressed="false"><span>02</span>Injection</button>
              <button type="button" class="preset" data-preset="dan" aria-label="Jailbreak attempt" aria-pressed="false"><span>03</span>Jailbreak</button>
              <button type="button" class="preset" data-preset="base64" aria-label="Encoded attack" aria-pressed="false"><span>04</span>Encoded</button>
              <button type="button" class="preset" data-preset="aws" aria-label="AWS key leak" aria-pressed="false"><span>05</span>Key leak</button>
              <button type="button" class="preset" data-preset="db" aria-label="Database secret" aria-pressed="false"><span>06</span>DB secret</button>
            </div>
          </div>

          <div class="editor-section">
            <div class="field-heading">
              <label for="promptInput">Prompt payload</label>
              <small id="charCount" aria-live="polite">0 / 50,000</small>
            </div>
            <div class="editor-shell">
              <div class="editor-gutter" aria-hidden="true"><span>01</span><span>02</span><span>03</span><span>04</span><span>05</span><span>06</span></div>
              <textarea id="promptInput" name="prompt" maxlength="50000" spellcheck="false" aria-describedby="charCount formError" placeholder="Enter a prompt to inspect..." data-testid="prompt-input"></textarea>
              <div class="editor-corner" aria-hidden="true"></div>
            </div>
            <p id="formError" class="form-error" role="alert" hidden></p>
          </div>

          <fieldset class="mode-control">
            <legend>Execution route</legend>
            <div class="mode-track">
              <span id="modeIndicator" class="mode-indicator" aria-hidden="true"></span>
              <label><input type="radio" name="mode" value="process" checked><span>Security only</span></label>
              <label><input type="radio" name="mode" value="chat"><span>Security + model</span></label>
            </div>
          </fieldset>

          <div class="compose-actions">
            <p><kbd>Ctrl</kbd><span>+</span><kbd>Enter</kbd> to execute</p>
            <button id="submitButton" class="execute-button" type="submit" aria-label="Inspect prompt without model inference" data-testid="submit-button">
              <span class="button-signal" aria-hidden="true"></span>
              <span id="submitLabel">Run inspection</span>
              <svg viewBox="0 0 20 20" fill="none" aria-hidden="true"><path d="M4 10h11M11 6l4 4-4 4" stroke="currentColor" stroke-width="1.5"/></svg>
            </button>
          </div>
        </form>
      </section>

      <section class="evidence-panel instrument-panel results-shell" data-mobile-panel="evidence" data-motion="evidence" aria-labelledby="evidenceTitle" aria-busy="false">
        <header class="panel-header evidence-header">
          <div>
            <p class="section-index">02 / Policy output</p>
            <h2 id="evidenceTitle" tabindex="-1">Evidence</h2>
          </div>
          <div class="evidence-tools">
            <span id="resultStatus" class="panel-code" role="status" aria-live="polite">STANDBY</span>
            <button id="backToPrompt" class="back-button" type="button"><span aria-hidden="true">←</span> Back to prompt</button>
          </div>
        </header>

        <div id="emptyState" class="empty-state" data-testid="empty-state">
          <div class="empty-copy" data-motion="empty-copy">
            <span class="overline">Four-stage defense</span>
            <h3>Trace every decision<br>before inference.</h3>
            <p>The gateway inspects instruction integrity and sensitive data, then resolves a policy before any model receives the prompt.</p>
          </div>
          <div class="defense-map" aria-label="Gateway stages: injection scan, privacy scan, policy decision, model inference" data-motion="map">
            <svg class="map-lines" viewBox="0 0 640 290" preserveAspectRatio="none" aria-hidden="true">
              <path class="path-base" d="M70 145H570"/>
              <path id="pathSignal" class="path-signal" d="M70 145H570"/>
            </svg>
            <div class="stage-node node-1"><span>01</span><strong>Injectionless</strong><small>Injection scan</small></div>
            <div class="stage-node node-2"><span>02</span><strong>Private</strong><small>PII + secrets</small></div>
            <div class="stage-node node-3"><span>03</span><strong>Decide</strong><small>Policy engine</small></div>
            <div class="stage-node node-4"><span>04</span><strong>Forward</strong><small>Model route</small></div>
            <div class="map-core" aria-hidden="true"><span></span><i></i></div>
          </div>
          <button id="emptyAction" class="quiet-action" type="button">Load a clean test vector <span aria-hidden="true">→</span></button>
        </div>

        <div id="loadingState" class="loading-state" role="status" aria-live="polite" hidden data-testid="loading-state">
          <div class="scan-visual" aria-hidden="true">
            <div class="scan-ring ring-a"></div><div class="scan-ring ring-b"></div>
            <div class="scan-axis axis-x"></div><div class="scan-axis axis-y"></div>
            <div id="scanSignal" class="scan-signal"></div>
            <span>SEC</span>
          </div>
          <div class="loading-copy">
            <p>INSPECTION ACTIVE</p>
            <h3>Resolving policy path</h3>
            <span>No content is forwarded until the gateway completes.</span>
          </div>
          <ol class="loading-stages" aria-hidden="true">
            <li><i></i>Instruction integrity</li><li><i></i>Privacy surface</li><li><i></i>Policy resolution</li><li><i></i>Inference route</li>
          </ol>
        </div>

        <div id="requestError" class="request-error" role="alert" tabindex="-1" hidden data-testid="request-error"></div>

        <div id="resultsContainer" class="results-container" hidden data-testid="results-container">
          <div class="result-summary" data-motion="result-summary">
            <div id="verdictCard" class="verdict-block" data-action="Unknown">
              <div class="verdict-copy">
                <p>POLICY VERDICT</p>
                <h3 id="verdictTitle" tabindex="-1">Unknown decision</h3>
                <span id="verdictSubtitle">The returned policy action is not recognized.</span>
              </div>
              <div class="risk-instrument">
                <svg viewBox="0 0 120 120" aria-hidden="true">
                  <circle class="gauge-track" cx="60" cy="60" r="48"/>
                  <circle id="gaugeValue" class="gauge-value" cx="60" cy="60" r="48"/>
                  <path class="gauge-tick" d="M60 8v9M60 103v9M8 60h9M103 60h9"/>
                </svg>
                <div><strong id="scoreValue">0.000</strong><span id="riskBadge" data-risk="unknown">UNKNOWN</span></div>
              </div>
            </div>

            <dl class="telemetry" data-motion="telemetry">
              <div><dt>Gateway latency</dt><dd id="latencyValue">--</dd></div>
              <div><dt>Request trace</dt><dd id="requestId">--</dd></div>
              <div><dt>Indicators</dt><dd id="indicatorCount">0</dd></div>
              <div><dt>PII entities</dt><dd id="piiMetric">0</dd></div>
            </dl>
          </div>

          <div class="evidence-tabs" role="tablist" aria-label="Evidence views">
            <button id="overviewTab" role="tab" aria-selected="true" aria-controls="overviewPanel" data-tab="overview">Overview</button>
            <button id="signalsTab" role="tab" aria-selected="false" aria-controls="signalsPanel" data-tab="signals">Signals <span id="signalTabCount">0</span></button>
            <button id="payloadTab" role="tab" aria-selected="false" aria-controls="payloadPanel" data-tab="payload">Payload</button>
          </div>

          <div id="overviewPanel" class="tab-panel" role="tabpanel" aria-labelledby="overviewTab" data-tab-panel="overview">
            <ol class="policy-path" aria-label="Policy path">
              <li data-stage="injection"><span>01</span><i></i><div><strong>Injection scan</strong><small id="injectionStage">--</small></div></li>
              <li data-stage="privacy"><span>02</span><i></i><div><strong>Privacy scan</strong><small id="privacyStage">--</small></div></li>
              <li data-stage="policy"><span>03</span><i></i><div><strong>Policy engine</strong><small id="policyStage">--</small></div></li>
              <li data-stage="model"><span>04</span><i></i><div><strong>Model inference</strong><small id="modelStage">Not requested</small></div></li>
            </ol>
            <div id="overviewResponse" class="response-extract" hidden>
              <div class="content-heading"><span>Protected model output</span><button type="button" data-copy-target="llmCode">Copy</button></div>
              <pre id="llmCode"></pre>
              <small id="llmMeta"></small>
            </div>
          </div>

          <div id="signalsPanel" class="tab-panel" role="tabpanel" aria-labelledby="signalsTab" data-tab-panel="signals" hidden>
            <div id="noEvidence" class="no-findings"><span>00</span><div><strong>No suspicious signals</strong><p>The gateway returned no injection indicators or privacy findings.</p></div></div>
            <div id="threatGroup" class="signal-group" hidden><h4>Threat categories</h4><div id="threatTags" class="signal-tags"></div></div>
            <div id="keywordGroup" class="signal-group" hidden><h4>Matched indicators</h4><div id="keywordTags" class="signal-tags"></div></div>
            <div id="encodingGroup" class="signal-group" hidden><h4>Encoding attacks</h4><pre id="encodingCode" class="code-surface"></pre></div>
            <div id="anomalyGroup" class="signal-group" hidden><h4>Structural anomalies</h4><pre id="anomalyCode" class="code-surface"></pre></div>
            <div id="piiDetails" class="signal-group" hidden>
              <h4>PII and developer secrets <span id="piiCount">0 findings</span></h4>
              <div class="table-wrap"><table><thead><tr><th>Entity</th><th>Sensitivity</th><th>Confidence</th><th>Span</th></tr></thead><tbody id="piiTableBody"></tbody></table></div>
            </div>
          </div>

          <div id="payloadPanel" class="tab-panel" role="tabpanel" aria-labelledby="payloadTab" data-tab-panel="payload" hidden>
            <div id="sanitizedDetails" class="payload-group" hidden>
              <div class="content-heading"><span>Forwarded prompt</span><button type="button" data-copy-target="sanitizedCode">Copy</button></div>
              <pre id="sanitizedCode" class="code-surface"></pre>
            </div>
            <div class="payload-group">
              <div class="content-heading"><span>Raw gateway response</span><button type="button" data-copy-target="rawCode">Copy</button></div>
              <pre id="rawCode" class="code-surface"></pre>
            </div>
          </div>

          <p id="copyStatus" class="copy-status" role="status" aria-live="polite"></p>
        </div>
      </section>
    </main>
  </div>
</body>
</html>
"""
