const EVENTS_KEY = "behaviorEvents";
const ANALYSIS_KEY = "behaviorAnalysis";
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

function renderAnalysis(analysis) {
	const result = { ...EMPTY_ANALYSIS, ...(analysis || {}) };
	const behaviors = Array.isArray(result.behaviors) ? result.behaviors : [];
	const summary = result.summary || EMPTY_ANALYSIS.summary;
	riskScore.textContent = result.riskScore || 0;
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

function loadEvents() {
	chrome.storage.local.get({ [EVENTS_KEY]: [], [ANALYSIS_KEY]: null }, stored => {
		renderEvents(stored[EVENTS_KEY]);
		renderAnalysis(stored[ANALYSIS_KEY]);
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
});

loadEvents();
