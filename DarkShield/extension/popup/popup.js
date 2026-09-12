const EVENTS_KEY = "behaviorEvents";
const ANALYSIS_KEY = "behaviorAnalysis";
const SESSIONS_KEY = "behaviorSessions";
const FUSION_ENDPOINT = "http://127.0.0.1:8000/fuse-evidence";
const VISION_ENDPOINT = "http://127.0.0.1:8000/vision/predict";
const eventCount = document.getElementById("event-count");
const eventList = document.getElementById("event-list");
const emptyState = document.getElementById("empty-state");
const clearEventsButton = document.getElementById("clear-events");
const riskScore = document.getElementById("risk-score");
const analysisSeverity = document.getElementById("analysis-severity");
const behaviorList = document.getElementById("behavior-list");
const noRisks = document.getElementById("no-risks");
const summaryTitle = document.getElementById("summary-title");
const summaryMessage = document.getElementById("summary-message");
const whatHappened = document.getElementById("what-happened");
const whyThisMatters = document.getElementById("why-this-matters");
const datasetMatchList = document.getElementById("dataset-match-list");
const datasetEmpty = document.getElementById("dataset-empty");
const behaviorScoreLabel = document.querySelector(".risk-summary span");
let riskEnginePanel;

const EMPTY_ANALYSIS = {
	riskScore: 0,
	overallSeverity: "LOW",
	summary: {
		title: "Low Risk",
		message: "No significant behavioral manipulation signals were detected."
	},
	whatHappened: "No interaction data is available yet.",
	whyThisMatters: "Normal navigation was detected without significant behavioral friction.",
	intent: {
		cancellationDetected: false,
		cancellationStartIndex: -1
	},
	behaviors: [],
	dataset_matches: [],
	evidence: []
};

function formatTime(timestamp) {
	const date = new Date(timestamp);
	return Number.isNaN(date.getTime()) ? "Unknown time" : date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function renderEvents(events) {
	const recentEvents = [...events].reverse().slice(0, 50);
	eventCount.textContent = events.length;
	eventList.replaceChildren();
	emptyState.hidden = recentEvents.length > 0;

	recentEvents.forEach(event => {
		const item = document.createElement("li");
		item.className = "event-item";

		const topline = document.createElement("div");
		topline.className = "event-topline";
		const action = document.createElement("span");
		action.className = "event-action";
		action.textContent = event.action || "EVENT";
		const time = document.createElement("span");
		time.className = "event-time";
		time.textContent = formatTime(event.timestamp);
		topline.append(action, time);

		const elementTag = (typeof event.element === "object" && event.element !== null)
			? (event.element.tag || "ELEMENT")
			: (event.element || "document");
		const eventText = (typeof event.element === "object" && event.element !== null)
			? (event.element.text || event.text || "")
			: (event.text || "");
		const text = document.createElement("p");
		text.className = "event-text";
		text.textContent = `${elementTag}${eventText ? ` · ${eventText}` : ""}`;
		const url = document.createElement("p");
		url.className = "event-url";
		url.textContent = event.url || "";

		item.append(topline, text, url);
		eventList.appendChild(item);
	});
}

function renderAnalysis(behaviorAnalysis) {
	const result = { ...EMPTY_ANALYSIS, ...(behaviorAnalysis || {}) };
	const behaviors = Array.isArray(result.behaviors) ? result.behaviors : [];
	const summary = result.summary || EMPTY_ANALYSIS.summary;
	const behaviorScore = Number.isFinite(Number(behaviorAnalysis?.riskScore)) ? Number(behaviorAnalysis.riskScore) : 0;
	if (behaviorScoreLabel) behaviorScoreLabel.textContent = "Behavior score";
	riskScore.textContent = behaviorScore;
	analysisSeverity.textContent = result.overallSeverity || "LOW";
	analysisSeverity.className = `severity-badge ${(result.overallSeverity || "LOW").toLowerCase()}`;
	summaryTitle.textContent = summary.title;
	summaryMessage.textContent = summary.message;
	whatHappened.textContent = result.whatHappened || EMPTY_ANALYSIS.whatHappened;
	whyThisMatters.textContent = result.whyThisMatters || EMPTY_ANALYSIS.whyThisMatters;
	datasetMatchList.replaceChildren();
	const datasetMatches = Array.isArray(result.dataset_matches) ? result.dataset_matches : [];
	datasetEmpty.hidden = datasetMatches.length > 0;
	datasetMatches.forEach(match => {
		const item = document.createElement("li");
		item.className = "dataset-match-item";
		item.textContent = `✓ ${match.type.replace(/_/g, " ")}`;
		item.title = match.description || match.dataset_category || "Rule-based dataset taxonomy match";
		datasetMatchList.appendChild(item);
	});
	behaviorList.replaceChildren();
	noRisks.hidden = behaviors.length > 0;

	behaviors.forEach(behavior => {
		const item = document.createElement("li");
		item.className = "behavior-item";

		const title = document.createElement("strong");
		title.textContent = behavior.title || behavior.type.replace(/_/g, " ");
		const severity = document.createElement("span");
		severity.className = "behavior-severity";
		severity.textContent = behavior.severity;
		const explanation = document.createElement("p");
		explanation.className = "behavior-explanation";
		explanation.textContent = behavior.explanation || behavior.evidence || "";
		const why = document.createElement("p");
		why.className = "behavior-why";
		why.textContent = `Why this matters: ${behavior.whyItMatters || "This may add friction to the requested action."}`;
		const evidenceButton = document.createElement("button");
		evidenceButton.className = "evidence-button";
		evidenceButton.type = "button";
		evidenceButton.textContent = "Show evidence";
		const evidence = document.createElement("p");
		evidence.className = "behavior-evidence";
		evidence.hidden = true;
		evidence.textContent = (behavior.evidenceEvents || []).join(" → ") || behavior.evidence || "No event details available.";
		evidenceButton.addEventListener("click", () => {
			evidence.hidden = !evidence.hidden;
			evidenceButton.textContent = evidence.hidden ? "Show evidence" : "Hide evidence";
		});

		item.append(title, severity, explanation, why, evidenceButton, evidence);
		behaviorList.appendChild(item);
	});
}

function ensureRiskEnginePanel() {
	if (riskEnginePanel) return riskEnginePanel;
	const analysisSection = document.querySelector(".analysis-section");
	if (!analysisSection) return null;

	riskEnginePanel = document.createElement("section");
	riskEnginePanel.className = "analysis-section risk-engine-section";
	riskEnginePanel.innerHTML = `
		<div class="section-heading">
			<h2>Risk Engine</h2>
			<span data-risk-engine-level class="severity-badge unavailable">Unavailable</span>
		</div>
		<div class="risk-summary">
			<span>Overall risk</span>
			<strong><span data-risk-engine-score>Unavailable</span> / 100</strong>
		</div>
		<ul data-risk-engine-components class="dataset-match-list"></ul>
	`;
	analysisSection.insertAdjacentElement("afterend", riskEnginePanel);
	return riskEnginePanel;
}

function renderRiskEngineUnavailable() {
	const panel = ensureRiskEnginePanel();
	if (!panel) return;
	panel.querySelector("[data-risk-engine-score]").textContent = "Unavailable";
	const level = panel.querySelector("[data-risk-engine-level]");
	level.textContent = "Unavailable";
	level.className = "severity-badge unavailable";
	panel.querySelector("[data-risk-engine-components]").replaceChildren();
}

function renderRiskEngine(fusionResponse, overallRisk) {
	const panel = ensureRiskEnginePanel();
	if (!panel) return;
	const score = overallRisk?.overall_score;
	const level = overallRisk?.risk_level;
	panel.querySelector("[data-risk-engine-score]").textContent = typeof score === "number" && Number.isFinite(score) ? score : "Unavailable";
	const levelElement = panel.querySelector("[data-risk-engine-level]");
	levelElement.textContent = level || "Unavailable";
	levelElement.className = `severity-badge ${(level || "unavailable").toLowerCase()}`;

	const componentLabels = {
		dark_pattern_risk: "Dark Pattern Risk",
		financial_risk: "Financial Risk",
		transparency_risk: "Transparency Risk",
		regulatory_risk: "Regulatory Risk",
		historical_risk: "Historical Risk"
	};
	const componentScores = {
		dark_pattern_risk: fusionResponse?.risk_analysis?.dark_pattern_risk?.risk_score,
		financial_risk: fusionResponse?.risk_analysis?.financial_risk?.risk_score,
		transparency_risk: fusionResponse?.risk_analysis?.transparency_risk?.risk_score,
		regulatory_risk: fusionResponse?.risk_analysis?.regulatory_risk?.risk_score,
		historical_risk: fusionResponse?.risk_analysis?.historical_risk?.risk_score
	};
	const list = panel.querySelector("[data-risk-engine-components]");
	list.replaceChildren();
	Object.entries(componentLabels).forEach(([key, label]) => {
		const item = document.createElement("li");
		const componentScore = typeof componentScores[key] === "number"
			? componentScores[key]
			: "Unavailable";
		item.textContent = `${label}: ${componentScore}`;
		list.appendChild(item);
	});
}

function buildFusionRequest(events, analysis, sessions, pageText = "", imageEvidence = []) {
	const fallbackText = events
		.map(event => event.text || event.element?.text || "")
		.filter(Boolean)
		.join(" ")
		.slice(0, 20000);
	const text = pageText.trim().slice(0, 20000) || fallbackText;
	const sessionList = Object.values(sessions || {});
	const latestSession = sessionList.sort(
		(a, b) => Number(b?.last_activity || 0) - Number(a?.last_activity || 0)
	)[0];
	const domSignals = latestSession?.diff_signals || [];
	const behaviors = analysis?.behaviors || latestSession?.analysis?.behaviors || [];
	const behaviorSignals = behaviors.map(behavior => ({
		type: behavior.type,
		detected: true,
		strength: behavior.severity === "HIGH" ? "strong" : (behavior.severity === "MEDIUM" ? "moderate" : "weak"),
		description: behavior.explanation || behavior.evidence || behavior.title || "",
		decision_context: "cancellation",
		metadata: { severity: behavior.severity }
	}));

	const fusionRequest = { text };
	if (domSignals.length > 0) fusionRequest.dom_evidence = { dom_signals: domSignals };
	if (behaviorSignals.length > 0) fusionRequest.behavior_evidence = { behavior_signals: behaviorSignals };
	if (Array.isArray(imageEvidence) && imageEvidence.length > 0) {
		fusionRequest.image_evidence = imageEvidence;
	}
	return fusionRequest;
}

async function getActivePageText() {
	try {
		const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
		const activeTab = tabs?.[0];
		if (!activeTab?.id) return "";
		const response = await chrome.tabs.sendMessage(activeTab.id, { type: "GET_PAGE_DATA" });
		return typeof response?.text === "string" ? response.text : "";
	} catch {
		return "";
	}
}

async function getVisionEvidence() {
	try {
		const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
		const activeTab = tabs?.[0];
		if (!activeTab?.windowId) throw new Error("Active tab is unavailable");
		const screenshotDataUrl = await chrome.tabs.captureVisibleTab(activeTab.windowId, { format: "png" });
		const imageResponse = await fetch(screenshotDataUrl);
		if (!imageResponse.ok) throw new Error("Screenshot payload could not be read");
		const imageBytes = await imageResponse.arrayBuffer();
		const visionResponse = await fetch(VISION_ENDPOINT, {
			method: "POST",
			headers: { "Content-Type": "image/png" },
			body: imageBytes
		});
		if (!visionResponse.ok) throw new Error(`Vision request failed with HTTP ${visionResponse.status}`);
		const visionResult = await visionResponse.json();
		const imageEvidence = Array.isArray(visionResult?.image_evidence)
			? visionResult.image_evidence
			: [];
		console.log("[ClauseGuard] Vision response:", {
			model: visionResult?.model,
			version: visionResult?.version,
			predictionCount: Object.keys(visionResult?.predictions || {}).length,
			imageEvidenceCount: imageEvidence.length
		});
		return imageEvidence;
	} catch (error) {
		console.warn("[ClauseGuard] Vision capture failed:", error?.message || error);
		console.warn("[ClauseGuard] Vision unavailable; continuing without image evidence.");
		return [];
	}
}

async function loadRiskEngineScore(events, analysis, sessions) {
	const pageText = await getActivePageText();
	const imageEvidence = await getVisionEvidence();
	const fusionRequest = buildFusionRequest(events, analysis, sessions, pageText, imageEvidence);
	console.log("[ClauseGuard] Fusion request:", fusionRequest);
	try {
		const response = await fetch(FUSION_ENDPOINT, {
			method: "POST",
			headers: { "Content-Type": "application/json" },
			body: JSON.stringify(fusionRequest)
		});
		if (!response.ok) throw new Error(`Fusion request failed with HTTP ${response.status}`);
		const fusionResponse = await response.json();
		console.log("[ClauseGuard] Fusion response:", fusionResponse);
		const overallRisk = fusionResponse?.risk_analysis?.overall_risk;
		const score = overallRisk?.overall_score;
		console.log("[ClauseGuard] Risk Engine score:", score);
		if (typeof score !== "number" || !Number.isFinite(score)) {
			renderRiskEngineUnavailable();
			return;
		}
		renderRiskEngine(fusionResponse, overallRisk);
	} catch (error) {
		console.warn("[ClauseGuard] Risk Engine unavailable:", error);
		renderRiskEngineUnavailable();
	}
}

function loadEvents() {
	chrome.storage.local.get({ [EVENTS_KEY]: [], [ANALYSIS_KEY]: null, [SESSIONS_KEY]: {} }, stored => {
		const events = Array.isArray(stored[EVENTS_KEY]) ? stored[EVENTS_KEY] : [];
		renderEvents(events);
		renderAnalysis(stored[ANALYSIS_KEY]);
		loadRiskEngineScore(events, stored[ANALYSIS_KEY], stored[SESSIONS_KEY]);
	});
}

clearEventsButton.addEventListener("click", () => {
	chrome.storage.local.set({
		[EVENTS_KEY]: [],
		[ANALYSIS_KEY]: EMPTY_ANALYSIS
	});
});

chrome.storage.onChanged.addListener((changes, areaName) => {
	if (areaName !== "local") return;
	if (changes[EVENTS_KEY]) renderEvents(changes[EVENTS_KEY].newValue || []);
	if (changes[ANALYSIS_KEY]) renderAnalysis(changes[ANALYSIS_KEY].newValue);
	if (changes[EVENTS_KEY] || changes[ANALYSIS_KEY] || changes[SESSIONS_KEY]) {
		loadEvents();
	}
});

loadEvents();
