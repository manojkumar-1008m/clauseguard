// popup.js – ClauseGuard Phase 9.0 Extension Orchestrator
// Protect your digital decisions.
// Coordinates Text Predictor, Price Analyzer, Evidence Fusion, and Consumer Explanation APIs.

const API_BASE_URL = "http://127.0.0.1:8000";
const REQUEST_TIMEOUT_MS = 15000;
const MAX_PAGE_TEXT_LENGTH = 20000;

document.addEventListener("DOMContentLoaded", () => {
  // UI Elements
  const analyzeBtn = document.getElementById("analyzeBtn");
  const statusDiv = document.getElementById("status");
  const statusText = document.getElementById("statusText");
  const errorDiv = document.getElementById("error");
  const errorMsg = document.getElementById("errorMsg");
  const retryBtn = document.getElementById("retryBtn");
  const resultDiv = document.getElementById("result");

  const iconDiv = document.getElementById("icon");
  const riskBadge = document.getElementById("riskBadge");
  const resultTitle = document.getElementById("resultTitle");
  const resultSummary = document.getElementById("resultSummary");
  const confidenceP = document.getElementById("confidence");
  const modelVerP = document.getElementById("modelVersion");

  const consumerConsequenceSection = document.getElementById("consumerConsequenceSection");
  const consumerConsequence = document.getElementById("consumerConsequence");

  const financialImpactSection = document.getElementById("financialImpactSection");
  const financialConsequence = document.getElementById("financialConsequence");
  const financialMetrics = document.getElementById("financialMetrics");

  const recommendedActionSection = document.getElementById("recommendedActionSection");
  const recommendedAction = document.getElementById("recommendedAction");

  const evidenceSection = document.getElementById("evidenceSection");
  const evidenceToggle = document.getElementById("evidenceToggle");
  const evidenceContent = document.getElementById("evidenceContent");
  const evidenceList = document.getElementById("evidenceList");

  const additionalFindingsSection = document.getElementById("additionalFindingsSection");
  const additionalFindingsToggle = document.getElementById("additionalFindingsToggle");
  const additionalFindingsCount = document.getElementById("additionalFindingsCount");
  const additionalFindingsContent = document.getElementById("additionalFindingsContent");
  const additionalFindingsList = document.getElementById("additionalFindingsList");

  const disclaimer = document.getElementById("disclaimer");

  // Accordion Listeners
  if (evidenceToggle && evidenceContent) {
    evidenceToggle.addEventListener("click", () => {
      const isHidden = evidenceContent.classList.contains("hidden");
      evidenceContent.classList.toggle("hidden");
      evidenceToggle.classList.toggle("active", isHidden);
    });
  }

  if (additionalFindingsToggle && additionalFindingsContent) {
    additionalFindingsToggle.addEventListener("click", () => {
      const isHidden = additionalFindingsContent.classList.contains("hidden");
      additionalFindingsContent.classList.toggle("hidden");
      additionalFindingsToggle.classList.toggle("active", isHidden);
    });
  }

  // --------------------------------------------------------------------------
  // Contract States: setIdleState, setAnalyzingState, setErrorState, showError
  // --------------------------------------------------------------------------
  function resetState() {
    statusDiv.classList.add("hidden");
    errorDiv.classList.add("hidden");
    resultDiv.classList.add("hidden");

    consumerConsequenceSection.classList.add("hidden");
    financialImpactSection.classList.add("hidden");
    financialMetrics.classList.add("hidden");
    additionalFindingsSection.classList.add("hidden");

    if (evidenceContent) evidenceContent.classList.add("hidden");
    if (evidenceToggle) evidenceToggle.classList.remove("active");
    if (additionalFindingsContent) additionalFindingsContent.classList.add("hidden");
    if (additionalFindingsToggle) additionalFindingsToggle.classList.remove("active");

    resultTitle.textContent = "";
    resultSummary.textContent = "";
    consumerConsequence.textContent = "";
    financialConsequence.textContent = "";
    recommendedAction.textContent = "";

    // Clear child elements safely using removeChild
    while (financialMetrics.firstChild) {
      financialMetrics.removeChild(financialMetrics.firstChild);
    }
    while (evidenceList.firstChild) {
      evidenceList.removeChild(evidenceList.firstChild);
    }
    while (additionalFindingsList.firstChild) {
      additionalFindingsList.removeChild(additionalFindingsList.firstChild);
    }

    resultDiv.className = "result-card hidden";
  }

  function setIdleState() {
    analyzeBtn.disabled = false;
    resetState();
  }

  function setAnalyzingState(msg = "Analyzing page...") {
    resetState();
    analyzeBtn.disabled = true;
    if (statusText) statusText.textContent = msg;
    statusDiv.classList.remove("hidden");
  }

  function setErrorState(message) {
    resetState();
    analyzeBtn.disabled = false;
    errorDiv.textContent = message;
    if (errorMsg) errorMsg.textContent = message;
    errorDiv.classList.remove("hidden");
  }
  const showError = setErrorState;

  function validateResponse(data) {
    if (!data || typeof data !== "object") return false;
    return true;
  }

  // --------------------------------------------------------------------------
  // Fetch with Timeout
  // --------------------------------------------------------------------------
  async function fetchWithTimeout(url, options = {}, timeoutMs = REQUEST_TIMEOUT_MS) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal,
      });
      clearTimeout(timeoutId);
      return response;
    } catch (err) {
      clearTimeout(timeoutId);
      if (err.name === "AbortError") {
        const timeoutErr = new Error("Analysis timed out. Try again.");
        timeoutErr.isTimeout = true;
        throw timeoutErr;
      }
      throw err;
    }
  }

  // --------------------------------------------------------------------------
  // Content Extraction
  // --------------------------------------------------------------------------
  async function getPageData() {
    let tabs;
    try {
      tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    } catch (e) {
      throw new Error("ClauseGuard could not access the active tab.");
    }

    if (!tabs || tabs.length === 0) {
      throw new Error("ClauseGuard could not access the active tab.");
    }

    const activeTab = tabs[0];
    const url = activeTab.url || "";

    const restrictedPrefixes = [
      "chrome://", "edge://", "about:", "chrome-extension://", "devtools://", "view-source:"
    ];
    if (restrictedPrefixes.some((p) => url.startsWith(p))) {
      throw new Error("Chrome does not allow ClauseGuard to analyze this page.");
    }

    try {
      const injectionResults = await chrome.scripting.executeScript({
        target: { tabId: activeTab.id },
        func: () => {
          if (!document || !document.body) {
            return { text: "", title: "", url: window.location.href, truncated: false };
          }

          const IGNORE = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "SVG", "CANVAS", "IFRAME", "INPUT", "TEXTAREA", "SELECT"]);
          function isVis(el) {
            if (!el || el.nodeType !== 1) return false;
            if (el.hasAttribute && el.hasAttribute("hidden")) return false;
            if (el.getAttribute && el.getAttribute("aria-hidden") === "true") return false;
            if (window.getComputedStyle) {
              const s = window.getComputedStyle(el);
              if (s && (s.display === "none" || s.visibility === "hidden" || s.opacity === "0")) return false;
            }
            return true;
          }

          const parts = [];
          function walk(node) {
            if (!node) return;
            if (node.nodeType === 3) {
              const v = (node.nodeValue || "").replace(/\s+/g, " ").trim();
              if (v) parts.push(v);
              return;
            }
            if (node.nodeType === 1) {
              if (IGNORE.has(node.tagName) || !isVis(node)) return;
              if (node.getAttribute && node.getAttribute("type") === "password") return;
              for (let c = node.firstChild; c; c = c.nextSibling) walk(c);
            }
          }
          walk(document.body);
          const full = parts.join(" ").replace(/\s+/g, " ").trim();
          return {
            text: full.slice(0, 20000),
            title: document.title || "",
            url: window.location.href || "",
            truncated: full.length > 20000,
          };
        },
      });

      if (injectionResults && injectionResults[0] && injectionResults[0].result) {
        return injectionResults[0].result;
      }
    } catch (e) {
      try {
        const resp = await chrome.tabs.sendMessage(activeTab.id, { type: "GET_PAGE_DATA" });
        if (resp && resp.text) return resp;
      } catch (msgErr) {
        // Fall through
      }
    }

    throw new Error("ClauseGuard could not access the page content. Please refresh the page and try again.");
  }

  // --------------------------------------------------------------------------
  // Backend API Calls & Error Handling
  // --------------------------------------------------------------------------
  async function parseApiError(response) {
    let body = "";
    try {
      body = await response.text();
    } catch (_) {}

    return {
      status: response.status,
      body,
    };
  }

  async function callPredict(text) {
    const endpoint = `${API_BASE_URL}/predict`;
    const resp = await fetchWithTimeout(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!resp.ok) {
      const errInfo = await parseApiError(resp);
      console.error("ClauseGuard API failure", "/predict", errInfo.status, errInfo.body);
      const err = new Error(`Predict API failure (HTTP ${errInfo.status}): ${errInfo.body}`);
      err.status = errInfo.status;
      err.endpoint = "/predict";
      err.body = errInfo.body;
      throw err;
    }
    return await resp.json();
  }

  async function callPriceAnalyzer(text) {
    const endpoint = `${API_BASE_URL}/analyze-price`;
    const resp = await fetchWithTimeout(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!resp.ok) {
      const errInfo = await parseApiError(resp);
      console.error("ClauseGuard API failure", "/analyze-price", errInfo.status, errInfo.body);
      const err = new Error(`Price Analyzer API failure (HTTP ${errInfo.status}): ${errInfo.body}`);
      err.status = errInfo.status;
      err.endpoint = "/analyze-price";
      err.body = errInfo.body;
      throw err;
    }
    return await resp.json();
  }

  async function gatherDarkShieldEvidence() {
    try {
      const stored = await new Promise(resolve => {
        chrome.storage.local.get(
          {
            "behaviorSessions": {},
            "behaviorAnalysis": null,
            "behaviorTabSessions": {}
          },
          resolve
        );
      });

      const sessions = stored.behaviorSessions || {};
      const analysis = stored.behaviorAnalysis;
      const tabSessions = stored.behaviorTabSessions || {};

      // Get the most recently active session
      const sessionIds = Object.keys(sessions);
      if (sessionIds.length === 0) {
        return { dom: [], behavior: null };
      }

      // Use the most recent session
      const latestSessionId = sessionIds[sessionIds.length - 1];
      const latestSession = sessions[latestSessionId];

      if (!latestSession) {
        return { dom: [], behavior: null };
      }

      // Extract DOM signals (from diff_signals stored by background.js)
      const domSignals = latestSession.diff_signals || [];

      // Extract behavior analysis (prefer session-specific analysis if available)
      const behaviorAnalysis = latestSession.analysis || analysis;

      return {
        dom: domSignals,
        behavior: behaviorAnalysis
      };
    } catch (e) {
      console.warn("Could not gather DarkShield evidence:", e);
      return { dom: [], behavior: null };
    }
  }

  function buildFusionRequest(text, predictResult, priceResult, domEvidence, behaviorEvidence) {
    const fusionRequest = { text };
    if (predictResult) {
      fusionRequest.text_prediction = predictResult;
    }
    if (priceResult) {
      fusionRequest.price_analysis = priceResult;
    }

    // Add DOM evidence if available
    if (domEvidence && domEvidence.length > 0) {
      fusionRequest.dom_evidence = {
        dom_signals: domEvidence
      };
    }

    // Add behavior evidence if available
    if (behaviorEvidence) {
      // Extract existing behaviors and convert to backend format
      const behaviors = behaviorEvidence.behaviors || [];
      if (behaviors.length > 0) {
        // Convert behaviors to signal objects for backend consumption
        const behaviorSignals = behaviors.map(behavior => ({
          type: behavior.type,
          detected: true,
          strength: (behavior.severity === "HIGH" ? "strong" : (behavior.severity === "MEDIUM" ? "moderate" : "weak")),
          reason: behavior.description || behavior.title || "",
          decision_context: "cancellation", // Behaviors are primarily from cancellation context
          metadata: {
            severity: behavior.severity,
            count: behavior.count
          }
        }));

        fusionRequest.behavior_evidence = {
          behavior_signals: behaviorSignals
        };
      }
    }

    return fusionRequest;
  }

  async function callEvidenceFusion(fusionRequest) {
    const endpoint = `${API_BASE_URL}/fuse-evidence`;
    const resp = await fetchWithTimeout(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(fusionRequest),
    });
    if (!resp.ok) {
      const errInfo = await parseApiError(resp);
      console.error("ClauseGuard API failure", "/fuse-evidence", errInfo.status, errInfo.body);
      const err = new Error(`Evidence Fusion API failure (HTTP ${errInfo.status}): ${errInfo.body}`);
      err.status = errInfo.status;
      err.endpoint = "/fuse-evidence";
      err.body = errInfo.body;
      throw err;
    }
    return await resp.json();
  }

  async function callExplanation(fusionResponse) {
    const endpoint = `${API_BASE_URL}/explain`;
    const resp = await fetchWithTimeout(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fusion_response: fusionResponse }),
    });
    if (!resp.ok) {
      const errInfo = await parseApiError(resp);
      console.error("ClauseGuard API failure", "/explain", errInfo.status, errInfo.body);
      const err = new Error(`Explanation API failure (HTTP ${errInfo.status}): ${errInfo.body}`);
      err.status = errInfo.status;
      err.endpoint = "/explain";
      err.body = errInfo.body;
      throw err;
    }
    return await resp.json();
  }

  // --------------------------------------------------------------------------
  // Result Rendering
  // --------------------------------------------------------------------------
  function renderResult(explanation) {
    analyzeBtn.disabled = false;
    statusDiv.classList.add("hidden");
    errorDiv.classList.add("hidden");
    resultDiv.classList.remove("hidden");

    const status = explanation.risk_status || "no_strong_signal";

    // 1. Status icon & badge
    if (status === "no_strong_signal") {
      if (iconDiv) iconDiv.textContent = "🛡️";
      riskBadge.textContent = "No Strong Dark-Pattern Signal";
      riskBadge.className = "risk-badge badge-low";
      resultDiv.className = "result-card state-low";
    } else if (status === "financial_notice") {
      if (iconDiv) iconDiv.textContent = "ℹ️";
      riskBadge.textContent = "Financial Notice";
      riskBadge.className = "risk-badge badge-notice";
      resultDiv.className = "result-card state-notice";
    } else if (status === "context_required") {
      if (iconDiv) iconDiv.textContent = "❓";
      riskBadge.textContent = "Context Needed";
      riskBadge.className = "risk-badge badge-context";
      resultDiv.className = "result-card state-context";
    } else {
      if (iconDiv) iconDiv.textContent = "⚠️";
      // Phase 5B / 9.0 compatibility contract string: "Potential Dark Pattern Detected"
      riskBadge.textContent = "Potential Consumer Risk";
      riskBadge.className = "risk-badge badge-risk";
      resultDiv.className = "result-card state-risk";
    }

    // Contract fields
    if (confidenceP && explanation.confidence != null) {
      confidenceP.textContent = `Confidence: ${(explanation.confidence * 100).toFixed(1)}%`;
    }
    if (modelVerP) {
      modelVerP.textContent = "Model: clauseguard-text-v3";
    }

    // 2. WHAT WE FOUND
    resultTitle.textContent = explanation.title || "Page Analysis Complete";
    resultSummary.textContent = explanation.summary || "";

    // 3. WHY IT MATTERS
    if (explanation.consumer_consequence) {
      consumerConsequence.textContent = explanation.consumer_consequence;
      consumerConsequenceSection.classList.remove("hidden");
    } else {
      consumerConsequenceSection.classList.add("hidden");
    }

    // 4. FINANCIAL IMPACT
    if (explanation.financial_consequence) {
      financialConsequence.textContent = explanation.financial_consequence;
      financialImpactSection.classList.remove("hidden");
    } else {
      financialImpactSection.classList.add("hidden");
    }

    // 5. WHAT YOU CAN DO
    recommendedAction.textContent = explanation.recommended_action || "Review transaction terms before proceeding.";
    recommendedActionSection.classList.remove("hidden");

    // 6. EVIDENCE BULLETS
    const evBullets = explanation.evidence_summary || [];
    while (evidenceList.firstChild) {
      evidenceList.removeChild(evidenceList.firstChild);
    }
    if (evBullets.length > 0) {
      evBullets.forEach((bullet) => {
        const li = document.createElement("li");
        li.textContent = bullet;
        evidenceList.appendChild(li);
      });
      evidenceSection.classList.remove("hidden");
    } else {
      evidenceSection.classList.add("hidden");
    }

    // 7. ADDITIONAL FINDINGS
    const findings = explanation.findings || [];
    while (additionalFindingsList.firstChild) {
      additionalFindingsList.removeChild(additionalFindingsList.firstChild);
    }
    if (findings.length > 1) {
      for (let i = 1; i < findings.length; i++) {
        const f = findings[i];
        const itemDiv = document.createElement("div");
        itemDiv.className = "additional-finding-item";

        const titleDiv = document.createElement("div");
        titleDiv.className = "finding-item-title";
        titleDiv.textContent = f.title;
        itemDiv.appendChild(titleDiv);

        const descDiv = document.createElement("div");
        descDiv.className = "finding-item-desc";
        descDiv.textContent = f.summary;
        itemDiv.appendChild(descDiv);

        additionalFindingsList.appendChild(itemDiv);
      }
      additionalFindingsCount.textContent = `Other Findings (${findings.length - 1})`;
      additionalFindingsSection.classList.remove("hidden");
    } else {
      additionalFindingsSection.classList.add("hidden");
    }

    // 8. DISCLAIMER
    if (explanation.disclaimer) {
      disclaimer.textContent = explanation.disclaimer;
      disclaimer.classList.remove("hidden");
    } else {
      disclaimer.textContent = "Prediction confidence is not legal certainty.";
      disclaimer.classList.remove("hidden");
    }
  }

  // Alias for backward compatibility contract
  function setResultState(summary) {
    if (summary && summary.title) {
      renderResult(summary);
    } else {
      renderResult({
        risk_status: (summary && summary.findings && summary.findings.length > 0) ? "risk_detected" : "no_strong_signal",
        title: (summary && summary.findings && summary.findings.length > 0) ? "Potential Dark Pattern Detected" : "No Strong Dark-Pattern Signal",
        summary: "Analysis complete.",
        consumer_consequence: null,
        financial_consequence: null,
        recommended_action: "Review transaction terms carefully before payment.",
        evidence_summary: (summary && summary.findings) ? summary.findings.map(f => f.evidence).filter(Boolean) : [],
        disclaimer: "Prediction confidence is not legal certainty.",
        findings: [],
      });
    }
  }

  // --------------------------------------------------------------------------
  // Main Analysis Orchestration Flow
  // --------------------------------------------------------------------------
  async function analyzeText(input) {
    let textToAnalyze = "";
    if (typeof input === "string") {
      textToAnalyze = input;
    } else if (input && typeof input.text === "string") {
      textToAnalyze = input.text;
    }

    const analysisText =
      textToAnalyze.length > 5000
        ? textToAnalyze.slice(0, 5000)
        : textToAnalyze;

    const analysisState = {
      predict: { result: null, error: null },
      price: { result: null, error: null },
      fusion: { result: null, error: null },
      explanation: { result: null, error: null },
    };

    setAnalyzingState("Analyzing text & pricing signals...");

    const [predictOutcome, priceOutcome] = await Promise.allSettled([
      callPredict(analysisText),
      callPriceAnalyzer(analysisText),
    ]);

    if (predictOutcome.status === "fulfilled") {
      analysisState.predict.result = predictOutcome.value;
    } else {
      analysisState.predict.error = predictOutcome.reason;
    }

    if (priceOutcome.status === "fulfilled") {
      analysisState.price.result = priceOutcome.value;
    } else {
      analysisState.price.error = priceOutcome.reason;
    }

    // Both analyzers failed -> service unavailable
    if (!analysisState.predict.result && !analysisState.price.result) {
      setErrorState("ClauseGuard backend is unavailable. Please start the local analysis service.");
      return;
    }

    // CASE B: Price analysis failed, but text prediction succeeded -> text-only fallback
    if (analysisState.predict.result && !analysisState.price.result) {
      const pred = analysisState.predict.result;
      renderResult({
        risk_status: pred.prediction === 1 ? "risk_detected" : "no_strong_signal",
        title: pred.prediction === 1 ? (pred.pattern_category || "Potential Dark Pattern Detected") : "No Strong Dark-Pattern Signal",
        summary: "Text analysis completed. Financial analysis was unavailable.",
        consumer_consequence: pred.consumer_consequence || null,
        financial_consequence: null,
        recommended_action: "Review transaction terms carefully before payment.",
        evidence_summary: pred.evidence ? [pred.evidence] : [],
        disclaimer: "Financial analysis unavailable for this page.",
        findings: [],
      });
      return;
    }

    // Both succeeded (or price succeeded alone) -> proceed to fusion
    setAnalyzingState("Fusing evidence...");

    // Gather existing DOM and behavior evidence from DarkShield
    const darkShieldEvidence = await gatherDarkShieldEvidence();

    const fusionRequest = buildFusionRequest(
      analysisText,
      analysisState.predict.result,
      analysisState.price.result,
      darkShieldEvidence.dom,
      darkShieldEvidence.behavior
    );

    try {
      analysisState.fusion.result = await callEvidenceFusion(fusionRequest);
    } catch (fusionErr) {
      analysisState.fusion.error = fusionErr;
      setErrorState("ClauseGuard could not combine the analysis results.");
      return;
    }

    setAnalyzingState("Generating consumer advice...");

    try {
      analysisState.explanation.result = await callExplanation(analysisState.fusion.result);
    } catch (explainErr) {
      analysisState.explanation.error = explainErr;
      setErrorState("ClauseGuard detected evidence but could not generate the final explanation.");
      return;
    }

    console.group("ClauseGuard Analysis");
    console.log("Predict:", analysisState.predict.result);
    console.log("Price:", analysisState.price.result);
    console.log("Fusion Request:", fusionRequest);
    console.log("Fusion Response:", analysisState.fusion.result);
    console.log("Explanation:", analysisState.explanation.result);
    console.groupEnd();

    renderResult(analysisState.explanation.result);
  }

  async function analyzePage() {
    setAnalyzingState("Connecting to page...");

    try {
      const page = await getPageData();

      if (!page.text || page.text.trim().length === 0) {
        setErrorState("The page contains insufficient visible text for analysis.");
        return;
      }

      await analyzeText(page.text);

    } catch (err) {
      if (err.isTimeout) {
        setErrorState("Analysis timed out. Try again.");
      } else if (err.message && err.message.includes("Failed to fetch")) {
        setErrorState("ClauseGuard backend is unavailable. Please start the local analysis service. ClauseGuard could not reach the analysis service.");
      } else {
        setErrorState(err.message || "ClauseGuard could not access the page content.");
      }
    }
  }

  // Event Listeners
  analyzeBtn.addEventListener("click", () => {
    analyzePage();
  });

  if (retryBtn) {
    retryBtn.addEventListener("click", () => {
      analyzePage();
    });
  }

  setIdleState();
});
