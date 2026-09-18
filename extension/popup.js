// ClauseGuard unified consumer-protection popup.

const API_BASE_URL = "http://127.0.0.1:8000";
const REQUEST_TIMEOUT_MS = 30000;
const MAX_PAGE_TEXT_LENGTH = 20000;
const STORAGE_KEYS = {
  sessions: "behaviorSessions",
  tabSessions: "behaviorTabSessions",
  canonicalAnalysis: "canonical_analysis"
};
const ASK_ENDPOINT = `${API_BASE_URL}/ask`;
const ASK_REQUEST_ID_HEADER = "X-Request-ID";
const MAX_CONVERSATION_MESSAGES = 10;

// Compatibility labels retained while the UI is driven only by /analyze.
const LEGACY_CLEAR_LABEL = "No Strong Dark-Pattern Signal";
const LEGACY_RISK_LABEL = "Potential Dark Pattern Detected";

document.addEventListener("DOMContentLoaded", () => {
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
  const scoreBreakdownSection = document.getElementById("scoreBreakdownSection");
  const scoreBreakdownToggle = document.getElementById("scoreBreakdownToggle");
  const scoreBreakdownContent = document.getElementById("scoreBreakdownContent");
  const scoreBreakdownDetails = document.getElementById("scoreBreakdownDetails");
  const riskScoreValue = document.getElementById("riskScoreValue");
  const confidenceP = document.getElementById("confidence");
  const modelVerP = document.getElementById("modelVersion");
  const consumerConsequenceSection = document.getElementById("consumerConsequenceSection");
  const consumerConsequence = document.getElementById("consumerConsequence");
  const financialImpactSection = document.getElementById("financialImpactSection");
  const financialConsequence = document.getElementById("financialConsequence");
  const recommendedActionSection = document.getElementById("recommendedActionSection");
  const recommendedAction = document.getElementById("recommendedAction");
  const evidenceSection = document.getElementById("evidenceSection");
  const evidenceToggle = document.getElementById("evidenceToggle");
  const evidenceContent = document.getElementById("evidenceContent");
  const evidenceList = document.getElementById("evidenceList");
  const additionalFindingsSection = document.getElementById("additionalFindingsSection");
  const additionalFindingsToggle = document.getElementById("additionalFindingsToggle");
  const additionalFindingsContent = document.getElementById("additionalFindingsContent");
  const additionalFindingsList = document.getElementById("additionalFindingsList");
  const additionalFindingsCount = document.getElementById("additionalFindingsCount");
  const disclaimer = document.getElementById("disclaimer");
  const currentPage = document.getElementById("currentPage");
  const journeyStage = document.getElementById("journeyStage");
  const eventCount = document.getElementById("eventCount");
  const askForm = document.getElementById("askForm");
  const askQuestion = document.getElementById("askQuestion");
  const askButton = document.getElementById("askButton");
  const askConversation = document.getElementById("askConversation");
  const askError = document.getElementById("askError");
  const quickQuestions = document.getElementById("quickQuestions");
  const headerRiskBadge = document.getElementById("headerRiskBadge");
  const headerRiskScore = document.getElementById("headerRiskScore");
  const headerRiskLevel = document.getElementById("headerRiskLevel");

  // Feature 3: Decision Snapshot elements
  const decisionSnapshotSection = document.getElementById("decisionSnapshotSection");
  const snapshotCost = document.getElementById("snapshotCost");
  const snapshotRenewal = document.getElementById("snapshotRenewal");
  const snapshotPrivacy = document.getElementById("snapshotPrivacy");
  const snapshotInterface = document.getElementById("snapshotInterface");
  const snapshotChecklist = document.getElementById("snapshotChecklist");

  // Feature 2: What Happens If I Continue? elements
  const consequenceSection = document.getElementById("consequenceSection");
  const consequenceToggle = document.getElementById("consequenceToggle");
  const consequenceContent = document.getElementById("consequenceContent");
  const consequenceFlowBlock = document.getElementById("consequenceFlowBlock");
  const consequenceSteps = document.getElementById("consequenceSteps");
  const consequenceAdvisories = document.getElementById("consequenceAdvisories");
  const consequenceAdviceText = document.getElementById("consequenceAdviceText");
  const consequenceViewEvidenceBtn = document.getElementById("consequenceViewEvidenceBtn");
  const consequenceFallback = document.getElementById("consequenceFallback");
  const consequenceFallbackText = document.getElementById("consequenceFallbackText");

  // Feature 1: Agreement Memory elements
  const agreementMemorySection = document.getElementById("agreementMemorySection");
  const memoryLastAnalyzed = document.getElementById("memoryLastAnalyzed");
  const memoryStatusBadge = document.getElementById("memoryStatusBadge");
  const memoryToggleBtn = document.getElementById("memoryToggleBtn");
  const memoryToggleLabel = document.getElementById("memoryToggleLabel");
  const memoryContent = document.getElementById("memoryContent");
  const memoryDetailsList = document.getElementById("memoryDetailsList");

  let latestAnalysis = null;
  let latestSession = null;
  let latestTab = null;
  let latestPageText = "";
  let latestAnalysisGeneratedAt = null;
  let askHistory = [];
  let askContextKey = null;

  function toggleSection(toggle, content) {
    if (!toggle || !content) return;
    toggle.addEventListener("click", () => {
      const hidden = content.classList.toggle("hidden");
      toggle.classList.toggle("active", !hidden);
      toggle.setAttribute("aria-expanded", String(!hidden));
    });
  }

  toggleSection(evidenceToggle, evidenceContent);
  toggleSection(additionalFindingsToggle, additionalFindingsContent);
  toggleSection(scoreBreakdownToggle, scoreBreakdownContent);
  toggleSection(consequenceToggle, consequenceContent);
  toggleSection(memoryToggleBtn, memoryContent);

  consequenceViewEvidenceBtn?.addEventListener("click", () => {
    if (evidenceSection && evidenceContent) {
      evidenceSection.classList.remove("hidden");
      evidenceContent.classList.remove("hidden");
      evidenceToggle?.classList.add("active");
      evidenceToggle?.setAttribute("aria-expanded", "true");
      evidenceSection.scrollIntoView({ behavior: "smooth" });
    }
  });

  function resetState() {
    statusDiv.classList.add("hidden");
    errorDiv.classList.add("hidden");
    resultDiv.classList.add("hidden");
    consumerConsequenceSection.classList.add("hidden");
    financialImpactSection.classList.add("hidden");
    recommendedActionSection.classList.add("hidden");
    evidenceSection.classList.add("hidden");
    additionalFindingsSection.classList.add("hidden");
    scoreBreakdownSection?.classList.add("hidden");
    headerRiskBadge?.classList.add("hidden");
    evidenceContent?.classList.add("hidden");
    additionalFindingsContent?.classList.add("hidden");
    evidenceList?.replaceChildren();
    additionalFindingsList?.replaceChildren();
    scoreBreakdownDetails?.replaceChildren();
    scoreBreakdownContent?.classList.add("hidden");
    scoreBreakdownToggle?.classList.remove("active");
    scoreBreakdownToggle?.setAttribute("aria-expanded", "false");

    // Clear and hide new feature sections
    decisionSnapshotSection?.classList.add("hidden");
    snapshotChecklist?.replaceChildren();
    consequenceSection?.classList.add("hidden");
    consequenceContent?.classList.add("hidden");
    consequenceToggle?.classList.remove("active");
    consequenceToggle?.setAttribute("aria-expanded", "false");
    consequenceSteps?.replaceChildren();
    consequenceAdvisories?.replaceChildren();
    agreementMemorySection?.classList.add("hidden");
    memoryContent?.classList.add("hidden");
    memoryToggleBtn?.classList.remove("active");
    memoryToggleBtn?.setAttribute("aria-expanded", "false");
    memoryDetailsList?.replaceChildren();
  }

  function renderHeaderRiskScore(data) {
    const finalScore = data?.score_breakdown?.final_score;
    if (typeof finalScore !== "number" || !Number.isFinite(finalScore) || !headerRiskBadge) return;
    headerRiskScore.textContent = `${finalScore} / 10`;
    headerRiskLevel.textContent = data.risk_level || data.consumer_gate?.risk_level || "";
    headerRiskBadge.className = `header-risk-badge ${String(data.risk_level || "LOW").toLowerCase()}`;
  }

  function addScoreRow(container, label, value) {
    if (!container || value === null || value === undefined) return;
    const row = document.createElement("div");
    row.className = "score-breakdown-row";
    const name = document.createElement("span");
    name.textContent = label;
    const amount = document.createElement("strong");
    amount.textContent = value;
    row.append(name, amount);
    container.appendChild(row);
  }

  function formatScore(value) {
    return typeof value === "number" && Number.isFinite(value) ? String(value) : "";
  }

  function renderScoreBreakdown(data) {
    const breakdown = data?.score_breakdown;
    if (!breakdown || typeof breakdown !== "object" || !scoreBreakdownSection) return;
    const finalScore = formatScore(breakdown.final_score);
    if (!finalScore) return;
    riskScoreValue.textContent = `${finalScore} / 10`;
    scoreBreakdownDetails.replaceChildren();

    const addGroup = (title, rows) => {
      const group = document.createElement("section");
      group.className = "score-breakdown-group";
      const heading = document.createElement("h4");
      heading.textContent = title;
      group.appendChild(heading);
      rows.forEach(row => addScoreRow(group, row[0], row[1]));
      scoreBreakdownDetails.appendChild(group);
    };

    addGroup("Evidence contributions", [
      ["Weak evidence", `+${formatScore(breakdown.weak_contribution)}`],
      ["Moderate evidence", `+${formatScore(breakdown.moderate_contribution)}`],
      ["Strong evidence", `+${formatScore(breakdown.strong_contribution)}`]
    ]);
    addGroup("Context contributions", [
      ["DOM contribution", `+${formatScore(breakdown.dom_contribution)} / ${formatScore(breakdown.dom_cap)}`],
      ["Behavior contribution", `+${formatScore(breakdown.behavior_contribution)} / ${formatScore(breakdown.behavior_cap)}`]
    ]);
    addGroup("Bonuses", [
      ["Corroboration", `+${formatScore(breakdown.corroboration_bonus)}`],
      ["Multiple sources", `+${formatScore(breakdown.multi_source_bonus)}`]
    ]);
    addGroup("Adjustments", [
      ["Contradiction escalation", `+${formatScore(breakdown.contradiction_escalation)}`],
      ["Conflict penalty", `-${formatScore(breakdown.conflict_penalty)}`]
    ]);
    addGroup("Score calculation", [
      ["Pre-ceiling score", formatScore(breakdown.pre_ceiling_score)],
      ["Global ceiling", formatScore(breakdown.global_score_ceiling)],
      ["Ceiling applied", breakdown.ceiling_applied === true ? "Yes" : "No"],
      ["Final score", `${finalScore} / 10`]
    ]);

    const sources = Array.isArray(breakdown.evidence_sources)
      ? breakdown.evidence_sources.filter(source => typeof source === "string" && source.trim())
      : Array.isArray(breakdown.contributing_evidence_sources)
        ? breakdown.contributing_evidence_sources.filter(source => typeof source === "string" && source.trim())
        : [];
    if (sources.length) addGroup("Contributing sources", sources.map(source => [source, ""]));
    scoreBreakdownSection.classList.remove("hidden");
  }

  function setIdleState() {
    analyzeBtn.disabled = false;
    resetState();
  }

  function currentAskContextKey() {
    return `${latestSession?.active_page_load_id || latestSession?.session_id || "page"}:${latestSession?.journey_id || "journey"}`;
  }

  function resetAskConversation() {
    askHistory = [];
    askConversation?.replaceChildren();
  }

  function setAnalyzingState(message = "Analyzing page...") {
    resetState();
    analyzeBtn.disabled = true;
    statusText.textContent = message;
    statusDiv.classList.remove("hidden");
  }

  function setErrorState(message) {
    resetState();
    analyzeBtn.disabled = false;
    errorDiv.textContent = message;
    errorMsg.textContent = message;
    errorDiv.classList.remove("hidden");
  }

  const showError = setErrorState;

  function validateResponse(data) {
    return Boolean(data && typeof data === "object" && typeof data.risk_level === "string" && data.consumer_gate);
  }

  async function fetchWithTimeout(url, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
      const response = await fetch(url, { ...options, signal: controller.signal });
      clearTimeout(timeout);
      return response;
    } catch (error) {
      clearTimeout(timeout);
      if (error.name === "AbortError") error.isTimeout = true;
      throw error;
    }
  }

  async function getActiveTab() {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const tab = tabs?.[0];
    if (!tab?.id || !tab.url) throw new Error("ClauseGuard could not access the active tab.");
    const restricted = ["chrome://", "edge://", "about:", "chrome-extension://", "devtools://", "view-source:"];
    if (restricted.some(prefix => tab.url.startsWith(prefix))) {
      throw new Error("Chrome does not allow ClauseGuard to analyze this page.");
    }
    return tab;
  }

  async function getPageData(tab) {
    try {
      const response = await chrome.tabs.sendMessage(tab.id, { type: "GET_PAGE_DATA" });
      if (response && typeof response.text === "string") return response;
    } catch (_) {
      const injected = await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: () => ({
          text: document.body?.innerText?.replace(/\s+/g, " ").trim().slice(0, 20000) || "",
          title: document.title || "",
          url: window.location.href || ""
        })
      });
      if (injected?.[0]?.result) return injected[0].result;
    }
    throw new Error("ClauseGuard could not access the page content. Please refresh the page and try again.");
  }

  function currentSession(stored, tab) {
    const storage = stored && typeof stored === "object" ? stored : {};
    const tabSessions = storage[STORAGE_KEYS.tabSessions] && typeof storage[STORAGE_KEYS.tabSessions] === "object"
      ? storage[STORAGE_KEYS.tabSessions]
      : {};
    const sessions = storage[STORAGE_KEYS.sessions] && typeof storage[STORAGE_KEYS.sessions] === "object"
      ? storage[STORAGE_KEYS.sessions]
      : {};
    const sessionId = tabSessions[String(tab.id)];
    return sessionId ? sessions[sessionId] || null : null;
  }

  function buildAnalyzeRequest(text, session) {
    const behaviorSignals = Array.isArray(session?.analysis?.behaviors)
      ? session.analysis.behaviors.map(behavior => ({
        type: behavior.type,
        detected: true,
        strength: behavior.severity === "HIGH" ? "strong" : behavior.severity === "MEDIUM" ? "moderate" : "weak",
        reason: behavior.explanation || behavior.evidence || behavior.title || "",
        decision_context: behavior.decision_context || session?.decision_context || "unknown",
        journey_id: session?.journey_id || null,
        journey_stage: session?.journey_stage || null,
        route: behavior.route || session?.route || null,
        route_sequence: behavior.route_sequence || session?.route_sequence || [],
        event_indices: behavior.eventIndices || behavior.event_indices || []
      }))
      : [];
    const request = { text: text.slice(0, MAX_PAGE_TEXT_LENGTH) };
    if (session?.diff_signals?.length) request.dom_evidence = { dom_signals: session.diff_signals.slice(-100) };
    if (behaviorSignals.length) request.behavior_evidence = { behavior_signals: behaviorSignals.slice(-200) };
    return request;
  }

  async function callAnalyze(request) {
    const response = await fetchWithTimeout(`${API_BASE_URL}/analyze`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request)
    });
    if (!response.ok) throw new Error(`ClauseGuard analysis failed (HTTP ${response.status}).`);
    const data = await response.json();
    if (!validateResponse(data)) throw new Error("ClauseGuard returned an incomplete analysis.");
    return data;
  }

  function addTextItem(list, text, prefix = "") {
    if (!text || !list) return;
    const item = document.createElement("li");
    item.textContent = `${prefix}${text}`;
    list.appendChild(item);
  }

  function appendAskMessage(text, kind) {
    const message = document.createElement("p");
    message.className = `ask-message ${kind}`;
    message.textContent = text;
    askConversation.appendChild(message);
    askConversation.scrollTop = askConversation.scrollHeight;
  }

  function renderQuickQuestions(data) {
    quickQuestions.replaceChildren();
    const questions = ["Why am I seeing this warning?", "What evidence did you find?", "What should I check before continuing?"];
    const types = (data?.evidence || []).map(item => `${item.type} ${item.pattern || ""}`.toLowerCase()).join(" ");
    if (types.includes("renewal") || types.includes("trial") || types.includes("subscription")) questions.splice(1, 0, "Could I be charged later?");
    if (types.includes("fee") || types.includes("cost") || types.includes("price")) questions.splice(2, 0, "How much could this cost me?");
    if (types.includes("obstruction") || types.includes("cancel")) questions.splice(2, 0, "Why is cancellation difficult?");
    if (!data?.risk_detected && !data?.consumer_gate?.actionable) {
      questions.splice(0, 1, "What did ClauseGuard check?");
    }
    [...new Set(questions)].slice(0, 5).forEach(question => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "quick-question";
      button.textContent = question;
      button.addEventListener("click", () => askQuestionAndRender(question));
      quickQuestions.appendChild(button);
    });
  }

  function normalizedPattern(value) {
    return String(value || "").toUpperCase().replace(/[^A-Z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  }

  function extractCanonicalPattern(context) {
    const explanation = context?.explanation || {};
    const findings = Array.isArray(explanation.findings) ? explanation.findings : [];
    return explanation.pattern
      || findings.find(item => item?.pattern)?.pattern
      || context?.explanation_context?.pattern
      || context?.primary_pattern
      || context?.potential_pattern
      || context?.dark_pattern
      || null;
  }

  function buildActiveFinding(context, activePattern) {
    if (!activePattern) return null;
    const findings = Array.isArray(context.explanation?.findings) ? context.explanation.findings : [];
    const matchingFinding = findings.find(item => normalizedPattern(item.pattern || item.type) === normalizedPattern(activePattern));
    const evidence = Array.isArray(context.evidence) ? context.evidence : [];
    const evidenceIds = Array.isArray(matchingFinding?.evidence_ids)
      ? matchingFinding.evidence_ids.slice(0, 20)
      : evidence.filter(item => normalizedPattern(item.pattern) === normalizedPattern(activePattern)).map(item => item.evidence_id).filter(Boolean).slice(0, 20);
    return {
      pattern: matchingFinding?.pattern || activePattern,
      status: context.consumer_gate?.decision || null,
      description: matchingFinding?.summary || context.explanation?.summary || null,
      why_it_matters: matchingFinding?.consumer_consequence || context.explanation?.consumer_consequence || null,
      recommended_action: matchingFinding?.recommended_action || context.explanation?.recommended_action || null,
      evidence_ids: evidenceIds
    };
  }

  function buildAskContext() {
    const context = latestAnalysis || {};
    const gate = context.consumer_gate || {};
    const explanationContext = context.explanation_context || {};
    const activePattern = extractCanonicalPattern(context);
    return {
      page_id: latestSession?.active_page_load_id || latestSession?.session_id || null,
      journey_id: latestSession?.journey_id || null,
      route: latestSession?.route || null,
      decision_context: explanationContext.decision_context || null,
      risk_level: context.risk_level || "LOW",
      risk_score: typeof context.risk_score === "number" ? context.risk_score : 0,
      gate_decision: gate.decision || "CLEAR",
      actionable: gate.actionable === true,
      requires_context: context.context_requirements?.requires_context === true || context.explanation?.requires_context === true,
      risk_detected: context.risk_detected === true,
      primary_pattern: activePattern,
      active_finding: buildActiveFinding(context, activePattern),
      detected_patterns: [activePattern, context.primary_pattern, context.potential_pattern, context.dark_pattern].filter(Boolean),
      evidence: (Array.isArray(context.evidence) ? context.evidence : []).slice(0, 20).map(item => ({
        evidence_id: item.evidence_id,
        source: item.source,
        type: item.type,
        pattern: item.pattern,
        description: item.description || "",
        strength: item.strength,
        model_confidence: item.model_confidence,
        provenance: typeof item.provenance === "string" ? item.provenance : null,
        route: item.route,
        decision_context: item.decision_context,
        temporal_position: item.temporal_position,
        event_indices: item.event_indices || [],
        element_ref: item.element_ref,
        bounding_box: item.bounding_box,
        frame_id: item.frame_id,
        value: item.value,
        currency: item.currency
      })),
      consequences: [context.consumer_consequence?.description, context.explanation?.consumer_consequence].filter(Boolean).slice(0, 10),
      financial_exposure: context.financial_impact?.known_total ?? null,
      consumer_effort: explanationContext.consumer_effort || null,
      recommended_action: context.explanation?.recommended_action || null,
      regulatory_context: summarizeRegulatoryContext(context.regulatory_assessment || explanationContext.regulatory_assessment),
      temporal_context: (context.temporal_relationships || []).map(item => item.reason).filter(Boolean).slice(0, 20),
      contradiction_context: (context.contradictions || []).map(item => item.description || item.reason).filter(Boolean).slice(0, 20),
      provenance: explanationContext.provenance || [],
      generated_at: latestAnalysisGeneratedAt || new Date().toISOString()
    };
  }

  function createRequestId() {
    if (globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") return globalThis.crypto.randomUUID();
    return `ask-${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }

  async function parseAskResponse(response) {
    const text = await response.text();
    if (!text) return {};
    try {
      return JSON.parse(text);
    } catch (_) {
      return { error: { code: "ASK_INVALID_RESPONSE", message: "Ask ClauseGuard returned invalid JSON." } };
    }
  }

  function mapAskError(error) {
    if (error?.name === "AbortError" || error?.isTimeout) {
      return { code: "ASK_TIMEOUT", message: "Ask ClauseGuard took too long to respond. Please try again." };
    }
    if (error?.code && error?.message) return error;
    if (error?.status === 400) return { code: "ASK_BAD_REQUEST", message: "ClauseGuard could not understand the request. Please refresh the page analysis and try again." };
    if (error?.status === 409) return { code: "ASK_CONTEXT_STALE", message: "The page analysis has changed. Refresh the current ClauseGuard analysis before asking this question." };
    if (error?.status === 422) return { code: "ASK_CONTEXT_INVALID", message: "The current ClauseGuard analysis context could not be validated. Please refresh the analysis and try again." };
    if (error?.status === 429) return { code: "ASK_RATE_LIMITED", message: "Ask ClauseGuard is temporarily rate limited. Please try again shortly." };
    if (error?.status === 503) return { code: "ASK_PROVIDER_UNAVAILABLE", message: "Ask ClauseGuard's answer service is temporarily unavailable." };
    if (error?.status >= 500) return { code: "ASK_SERVER_ERROR", message: "Ask ClauseGuard could not complete the request. Please try again." };
    if (error?.name === "TypeError" || error?.message?.includes("Failed to fetch")) {
      return { code: "ASK_BACKEND_UNAVAILABLE", message: "ClauseGuard backend is unavailable. Make sure the ClauseGuard backend is running and try again." };
    }
    return { code: "ASK_UNKNOWN_ERROR", message: "Ask ClauseGuard could not complete the request. Please try again." };
  }

  function summarizeRegulatoryContext(value) {
    if (!value || typeof value !== "object") return null;
    const assessments = Array.isArray(value.pattern_assessments) ? value.pattern_assessments : [];
    const findings = Array.isArray(value.findings) ? value.findings : [];
    return {
      status: typeof value.status === "string" ? value.status.slice(0, 80) : null,
      jurisdiction: typeof value.jurisdiction === "string" ? value.jurisdiction.slice(0, 80) : null,
      pattern_assessments: assessments.slice(0, 10).map(item => ({
        pattern: typeof item.pattern === "string" ? item.pattern.slice(0, 100) : null,
        status: typeof item.status === "string" ? item.status.slice(0, 40) : null,
        reason: typeof item.reason === "string" ? item.reason.slice(0, 500) : null
      })),
      findings: findings.slice(0, 10).map(item => ({
        status: typeof item.status === "string" ? item.status.slice(0, 40) : null,
        summary: typeof item.summary === "string" ? item.summary.slice(0, 500) : null
      }))
    };
  }

  async function askQuestionAndRender(question) {
    if (!latestAnalysis) {
      askError.textContent = "Analyze the current page before asking about it.";
      askError.classList.remove("hidden");
      return;
    }
    const normalizedQuestion = String(question || "").trim();
    if (!normalizedQuestion) {
      askError.textContent = "Enter a question about the current ClauseGuard analysis.";
      askError.classList.remove("hidden");
      askQuestion.focus();
      return;
    }
    askError.classList.add("hidden");
    askButton.disabled = true;
    askButton.textContent = "Analyzing...";
    appendAskMessage(normalizedQuestion, "question");
    const requestId = createRequestId();
    try {
      const payload = {
          request_id: requestId,
          question: normalizedQuestion,
          context: buildAskContext(),
          context_generated_at: latestAnalysisGeneratedAt || new Date().toISOString(),
          current_page_id: latestSession?.active_page_load_id || latestSession?.session_id || null,
          current_journey_id: latestSession?.journey_id || null,
          conversation_history: askHistory.slice(-MAX_CONVERSATION_MESSAGES),
          prefer_local_llm: true
      };
      console.debug("[ClauseGuard Ask] request", {
        request_id: requestId,
        question: payload.question,
        page_id: payload.current_page_id,
        journey_id: payload.current_journey_id,
        active_finding: payload.context.active_finding,
        evidence_ids: payload.context.evidence.map(item => item.evidence_id).filter(Boolean),
        decision_context: payload.context.decision_context
      });
      const response = await new Promise((resolve, reject) => {
        const runtime = globalThis.chrome?.runtime;
        if (!runtime?.sendMessage) {
          reject({ code: "ASK_EXTENSION_CONTEXT", message: "Open ClauseGuard from the Chrome extension menu before asking a question." });
          return;
        }
        let settled = false;
        let messageTimeout;
        const finish = callback => value => {
          if (settled) return;
          settled = true;
          clearTimeout(messageTimeout);
          callback(value);
        };
        const resolveMessage = finish(resolve);
        const rejectMessage = finish(reject);
        messageTimeout = setTimeout(() => {
          rejectMessage({ code: "ASK_EXTENSION_TIMEOUT", message: "ClauseGuard did not receive a response from its background service. Reload the extension and try again." });
        }, REQUEST_TIMEOUT_MS + 1000);
        try {
          runtime.sendMessage({ type: "ASK_CLAUSEGUARD", payload }, result => {
            if (runtime.lastError) rejectMessage({ code: "ASK_EXTENSION_TRANSPORT", message: runtime.lastError.message });
            else resolveMessage(result);
          });
        } catch (error) {
          rejectMessage({ code: "ASK_EXTENSION_TRANSPORT", message: error?.message || "ClauseGuard could not contact its background service." });
        }
      });
      const body = response?.body || {};
      if (!response?.ok) {
        const backendError = body?.error || {};
        throw { status: response?.status, code: backendError.code, message: backendError.message };
      }
      const result = body;
      if (!result || typeof result.answer !== "string" || typeof result.request_id !== "string" || !Array.isArray(result.evidence_ids) || typeof result.grounded !== "boolean" || typeof result.response_mode !== "string") {
        throw { code: "ASK_INVALID_RESPONSE", message: "Ask ClauseGuard returned an incomplete answer." };
      }
      if (result.request_id !== requestId) {
        throw { code: "ASK_INVALID_RESPONSE", message: "Ask ClauseGuard returned a mismatched request." };
      }
      if (!result.grounded || result.error_code === "ASK_GROUNDING_FAILURE") {
        throw { code: "ASK_GROUNDING_FAILURE", message: "ClauseGuard could not produce a sufficiently evidence-grounded answer." };
      }
      console.debug("[ClauseGuard Ask] response", {
        request_id: result.request_id,
        intent: result.intent,
        response_mode: result.response_mode,
        evidence_ids: result.evidence_ids,
        provider: result.provider,
        fallback_used: result.fallback_used
      });
      appendAskMessage(result.answer || "ClauseGuard does not have enough verified evidence to answer that.", "answer");
      askHistory = [...askHistory, normalizedQuestion, result.answer].slice(-MAX_CONVERSATION_MESSAGES);
    } catch (error) {
      const mapped = mapAskError(error);
      askError.textContent = `${mapped.message} (Request ID: ${requestId.slice(0, 8)})`;
      askError.classList.remove("hidden");
    } finally {
      askButton.disabled = false;
      askButton.textContent = "Ask";
    }
  }

  function renderResult(data) {
    const nextContextKey = currentAskContextKey();
    if (askContextKey !== null && askContextKey !== nextContextKey) resetAskConversation();
    askContextKey = nextContextKey;
    latestAnalysis = data;
    latestAnalysisGeneratedAt = data.generated_at || new Date().toISOString();
    const gate = data.consumer_gate || {};
    const contextRequired = Boolean(data.context_requirements?.requires_context || gate.requires_context);
    const actionable = !contextRequired && gate.actionable === true;
    const signal = !actionable && !contextRequired && gate.decision === "POTENTIAL";
    const explanation = data.explanation || {};
    const title = contextRequired ? "Context required" : (explanation.title || data.potential_pattern || data.dark_pattern || (actionable ? "Potential Consumer Risk" : signal ? "Potential signal" : "No strong consumer-risk signal"));
    const summary = explanation.summary || gate.message || (contextRequired ? "ClauseGuard needs more information before it can classify this page." : "Analysis completed using the canonical ClauseGuard pipeline.");

    resetState();
    resultDiv.className = `result-card ${actionable ? "state-risk" : signal ? "state-notice" : "state-low"}`;
    resultDiv.classList.remove("hidden");
    iconDiv.textContent = contextRequired ? "?" : actionable ? "!" : signal ? "i" : "OK";
    riskBadge.textContent = contextRequired ? "Context Required" : actionable ? "Actionable Consumer Risk" : signal ? "Potential Signal" : "Clear";
    riskBadge.className = `risk-badge ${actionable ? "badge-risk" : signal ? "badge-notice" : contextRequired ? "badge-context" : "badge-low"}`;
    resultTitle.textContent = title;
    resultSummary.textContent = summary;
    renderHeaderRiskScore(data);
    renderScoreBreakdown(data);
    confidenceP.textContent = typeof data.confidence === "number" ? `Confidence: ${(data.confidence * 100).toFixed(1)}%` : "";
    modelVerP.textContent = "Canonical ClauseGuard analysis";

    if (explanation.consumer_consequence) {
      consumerConsequence.textContent = explanation.consumer_consequence;
      consumerConsequenceSection.classList.remove("hidden");
    }
    if (explanation.financial_consequence) {
      financialConsequence.textContent = explanation.financial_consequence;
      financialImpactSection.classList.remove("hidden");
    }
    if (!contextRequired) {
      recommendedAction.textContent = explanation.recommended_action || (actionable ? "Review the terms before continuing." : "Continue normally and review important terms before committing.");
      recommendedActionSection.classList.remove("hidden");
    }

    const evidence = Array.isArray(data.evidence) ? data.evidence : [];
    const evidenceSummary = Array.isArray(explanation.evidence_summary) ? explanation.evidence_summary : [];
    evidence.forEach(item => addTextItem(evidenceList, item.description || item.evidence || item.text || item.source, "Evidence: "));
    evidenceSummary.forEach(item => addTextItem(evidenceList, item));
    if (evidenceList.children.length) evidenceSection.classList.remove("hidden");

    const findings = Array.isArray(explanation.findings) ? explanation.findings : [];
    findings.forEach(finding => {
      const item = document.createElement("div");
      item.className = "additional-finding-item";
      item.textContent = `${finding.title || "Finding"}: ${finding.summary || finding.evidence || ""}`;
      additionalFindingsList.appendChild(item);
    });
    if (additionalFindingsList.children.length) {
      additionalFindingsCount.textContent = `Other Findings (${additionalFindingsList.children.length})`;
      additionalFindingsSection.classList.remove("hidden");
    }
    disclaimer.textContent = "ClauseGuard provides consumer information, not legal advice.";
    disclaimer.classList.remove("hidden");
    renderQuickQuestions(data);
    renderDecisionFeatures(data);
    return actionable;
  }

  async function renderDecisionFeatures(data) {
    if (!data) return;
    const domain = latestTab?.url ? (new URL(latestTab.url).hostname || "Current page") : "Current page";
    const pageText = latestPageText || "";

    // 1. Decision Snapshot
    const snapshot = globalThis.DecisionSnapshot
      ? globalThis.DecisionSnapshot.extractDecisionSnapshot(data, pageText, latestSession)
      : null;

    if (snapshot && decisionSnapshotSection) {
      if (snapshotCost) snapshotCost.textContent = snapshot.cost.detected ? snapshot.cost.text : "Not detected";
      if (snapshotRenewal) snapshotRenewal.textContent = snapshot.renewal.detected ? snapshot.renewal.text : "Not detected";
      if (snapshotPrivacy) snapshotPrivacy.textContent = snapshot.privacy.detected ? snapshot.privacy.text : "No relevant signal";
      if (snapshotInterface) snapshotInterface.textContent = snapshot.interface.detected ? snapshot.interface.text : "Standard interface";

      snapshotChecklist?.replaceChildren();
      (snapshot.checklist || []).forEach(itemText => {
        const li = document.createElement("li");
        li.textContent = itemText;
        snapshotChecklist.appendChild(li);
      });
      decisionSnapshotSection.classList.remove("hidden");
    }

    // 2. What Happens If I Continue?
    const consequence = globalThis.ConsequenceEngine
      ? globalThis.ConsequenceEngine.buildConsequenceFlow(data, snapshot, pageText, latestSession)
      : null;

    if (consequence && consequenceSection) {
      if (consequence.hasFlow) {
        consequenceSteps?.replaceChildren();
        (consequence.steps || []).forEach((stepText, idx, arr) => {
          const stepItem = document.createElement("div");
          stepItem.className = "step-item";

          const stepBadge = document.createElement("span");
          stepBadge.className = "step-badge";
          stepBadge.textContent = String(idx + 1);

          const stepLabel = document.createElement("span");
          stepLabel.className = "step-label";
          stepLabel.textContent = stepText;

          stepItem.appendChild(stepBadge);
          stepItem.appendChild(stepLabel);
          consequenceSteps.appendChild(stepItem);

          if (idx < arr.length - 1) {
            const arrow = document.createElement("div");
            arrow.className = "step-arrow";
            arrow.textContent = "↓";
            consequenceSteps.appendChild(arrow);
          }
        });

        consequenceAdvisories?.replaceChildren();
        (consequence.advisories || []).forEach(advText => {
          const adv = document.createElement("p");
          adv.className = "consequence-advisory-item";
          adv.textContent = advText;
          consequenceAdvisories.appendChild(adv);
        });

        if (consequenceAdviceText) {
          consequenceAdviceText.textContent = consequence.actionAdvice || "Check the renewal price and cancellation terms.";
        }
        consequenceFlowBlock?.classList.remove("hidden");
        consequenceFallback?.classList.add("hidden");
      } else {
        consequenceFlowBlock?.classList.add("hidden");
        if (consequenceFallbackText) {
          consequenceFallbackText.textContent = consequence.fallbackMessage || "ClauseGuard does not have enough information to determine the next steps.";
        }
        consequenceFallback?.classList.remove("hidden");
      }
      consequenceSection.classList.remove("hidden");
    }

    // 3. Agreement Memory
    if (globalThis.AgreementMemory && agreementMemorySection) {
      try {
        const currentRecord = globalThis.AgreementMemory.buildMemoryRecord(domain, latestTab?.url, data, snapshot, consequence);
        const previousMemory = await globalThis.AgreementMemory.getDomainMemory(domain);
        const diff = globalThis.AgreementMemory.compareWithPrevious(currentRecord, previousMemory?.latest);

        memoryDetailsList?.replaceChildren();

        if (diff.isFirstAnalysis) {
          if (memoryLastAnalyzed) memoryLastAnalyzed.textContent = "First analysis";
          if (memoryStatusBadge) {
            memoryStatusBadge.textContent = "First analysis for this website";
            memoryStatusBadge.className = "memory-badge badge-neutral";
          }
          if (memoryToggleLabel) memoryToggleLabel.textContent = "View current record";

          const item = document.createElement("div");
          item.className = "memory-detail-item";
          const desc = document.createElement("p");
          desc.textContent = "Baseline recorded. Future changes to price, renewal terms, or cancellation policies will be flagged here.";
          item.appendChild(desc);
          memoryDetailsList.appendChild(item);
        } else if (diff.hasChanged) {
          if (memoryLastAnalyzed) memoryLastAnalyzed.textContent = `Last analyzed: ${globalThis.AgreementMemory.formatChangeDate(diff.previousRecord?.analyzedAt)}`;
          if (memoryStatusBadge) {
            memoryStatusBadge.textContent = "⚠ Something changed";
            memoryStatusBadge.className = "memory-badge badge-warning";
          }
          if (memoryToggleLabel) memoryToggleLabel.textContent = "View changes";

          diff.changes.forEach(chg => {
            const item = document.createElement("div");
            item.className = "memory-change-item";

            const title = document.createElement("strong");
            title.className = "change-title";
            title.textContent = chg.title;

            const detail = document.createElement("span");
            detail.className = "change-detail";
            detail.textContent = chg.detail;

            item.appendChild(title);
            item.appendChild(detail);

            if (chg.extra) {
              const extra = document.createElement("span");
              extra.className = "change-extra";
              extra.textContent = chg.extra;
              item.appendChild(extra);
            }

            memoryDetailsList.appendChild(item);
          });
        } else {
          if (memoryLastAnalyzed) memoryLastAnalyzed.textContent = `Last analyzed: ${globalThis.AgreementMemory.formatChangeDate(diff.previousRecord?.analyzedAt)}`;
          if (memoryStatusBadge) {
            memoryStatusBadge.textContent = "✓ No major changes detected";
            memoryStatusBadge.className = "memory-badge badge-success";
          }
          if (memoryToggleLabel) memoryToggleLabel.textContent = "View history";

          const item = document.createElement("div");
          item.className = "memory-detail-item";
          const p1 = document.createElement("p");
          p1.textContent = `Previous assessment was identical. Price (${diff.previousRecord?.price || "none recorded"}), renewal terms, and risk levels remain consistent.`;
          item.appendChild(p1);
          memoryDetailsList.appendChild(item);
        }

        await globalThis.AgreementMemory.saveDomainMemory(domain, currentRecord);
        agreementMemorySection.classList.remove("hidden");
      } catch (err) {
        console.warn("[ClauseGuard] Memory error:", err);
      }
    }
  }

  async function showPageAlert(data) {
    const gate = data?.consumer_gate || {};
    const contextRequired = Boolean(data?.context_requirements?.requires_context || gate.requires_context);
    if (contextRequired || gate.actionable !== true) return;
    try {
      const tab = await getActiveTab();
      await chrome.tabs.sendMessage(tab.id, {
        type: "CLAUSEGUARD_ALERT",
        title: data.explanation?.title || data.potential_pattern || "Potential Consumer Risk",
        message: data.explanation?.summary || gate.message || "Review the terms before continuing."
      });
    } catch (_) {}
  }

  async function analyzePage() {
    setAnalyzingState("Reading page and journey evidence...");
    try {
      const tab = await getActiveTab();
      const page = await getPageData(tab);
      if (!page.text?.trim()) throw new Error("The page contains insufficient visible text for analysis.");
      const stored = await new Promise(resolve => chrome.storage.local.get({ [STORAGE_KEYS.sessions]: {}, [STORAGE_KEYS.tabSessions]: {} }, result => resolve(result || {})));
      const session = currentSession(stored, tab);
      latestTab = tab;
      latestSession = session;
      latestPageText = page.text;
      currentPage.textContent = new URL(tab.url).hostname || "Current page";
      eventCount.textContent = String(session?.events?.length || 0);
      journeyStage.textContent = session?.journey_stage || "Page";
      setAnalyzingState("Sending evidence to ClauseGuard...");
      const result = await callAnalyze(buildAnalyzeRequest(page.text, session));
      if (session) {
        session.canonical_analysis = result;
      }
      renderResult(result);
      await showPageAlert(result);
    } catch (error) {
      const message = error.isTimeout
        ? "Analysis timed out. Try again."
        : error.message?.includes("Failed to fetch")
          ? "ClauseGuard backend is unavailable. Please start the local analysis service. ClauseGuard could not reach the analysis service."
          : error.message || "ClauseGuard could not complete this analysis.";
      setErrorState(message);
    }
  }

  async function analyzeText(input) {
  const text = typeof input === "string" ? input : input?.text;
  if (!text) return;
  latestPageText = text;
  const result = await callAnalyze({ text: text.slice(0, MAX_PAGE_TEXT_LENGTH) });
  renderResult(result);
  }

  function setResultState(summary) {
    if (summary && summary.risk_level) renderResult(summary);
  }

  analyzeBtn.addEventListener("click", analyzePage);
  retryBtn?.addEventListener("click", analyzePage);
  askForm?.addEventListener("submit", event => {
    event.preventDefault();
    const question = askQuestion.value.trim();
    if (!question) {
      askError.textContent = "Enter a question about the current ClauseGuard analysis.";
      askError.classList.remove("hidden");
      askQuestion.focus();
      return;
    }
    askQuestion.value = "";
    askQuestionAndRender(question);
  });
  setIdleState();
});
