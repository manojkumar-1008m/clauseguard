/* global ANALYZER_RULES */

(function (root) {
	"use strict";

const analyzerRules = typeof root.ANALYZER_RULES !== "undefined"
	? root.ANALYZER_RULES
	: (typeof require === "function" ? require("./rules.js").ANALYZER_RULES : null);
const datasetMatcher = typeof require === "function" ? require("./datasetMatcher.js") : null;

root.analyzerRules = analyzerRules;

if (!analyzerRules) {
	throw new Error("ANALYZER_RULES is required before analyzer.js");
}

const PRIVATE_ELEMENT_NAMES = new Set(["input", "textarea", "select"]);

function normalizeText(value) {
	return String(value || "").toLowerCase().replace(/\s+/g, " ").trim();
}

function elementName(event) {
	if (!event) return "";
	if (event.element && typeof event.element === "object") return String(event.element.tag || "").toLowerCase();
	return String(event.element || "").toLowerCase();
}

function textOf(event) {
	if (!event || PRIVATE_ELEMENT_NAMES.has(elementName(event))) return "";
	if (event.element && typeof event.element === "object") {
		return normalizeText(event.element.text || event.element.aria_label || event.text);
	}
	return normalizeText(event.text);
}

function routeOf(url) {
	if (url && typeof url === "object" && url.route) return String(url.route);
	try {
		const parsed = new URL(url);
		return `${parsed.pathname}${parsed.hash}` || parsed.pathname;
	} catch {
		const value = String(url || "");
		const hashPosition = value.indexOf("#");
		return hashPosition >= 0 ? value.slice(hashPosition) : value;
	}
}

function searchableText(event) {
	return `${textOf(event)} ${routeOf(event)}`.toLowerCase();
}

function containsKeyword(value, keywords) {
	return keywords.some(keyword => value.includes(keyword));
}

function classifyAction(event) {
	if (!event) return "UNKNOWN";
	const rawAction = String(event.action || "").toUpperCase();
	if (rawAction === "NAVIGATION") return "NAVIGATION";
	if (rawAction === "INPUT_CHANGE") return "INPUT_CHANGE";
	if (rawAction === "PAGE_INIT") return "PAGE_INIT";
	if (rawAction === "CLICK" || (!rawAction && textOf(event))) {
		const text = textOf(event);
		if (!text) return "CLICK";
		if (containsKeyword(text, analyzerRules.keywords.confirmation)) return "CONFIRM";
		if (containsKeyword(text, analyzerRules.keywords.survey)) return "SURVEY";
		if (text.includes("continue cancelling") || text.includes("no thanks")) return "DECLINE";
		if (text === "continue" || text.startsWith("continue ")) return "CONTINUE";
		if (containsKeyword(text, analyzerRules.keywords.decline)) return "DECLINE";
		if (containsKeyword(text, analyzerRules.keywords.confirmShaming)) return "DECLINE";
		if (containsKeyword(text, analyzerRules.keywords.retention)) return "RETENTION";
		if (containsKeyword(text, analyzerRules.keywords.deleteAccount)) return "DELETE_ACCOUNT";
		if (containsKeyword(text, analyzerRules.keywords.optOut)) return "OPT_OUT";
		if (containsKeyword(text, analyzerRules.keywords.cancellation)) return "CANCEL";
		if (containsKeyword(text, analyzerRules.keywords.subscribe)) return "SUBSCRIBE";
		if (containsKeyword(text, analyzerRules.keywords.purchase)) return "PURCHASE";
		if (containsKeyword(text, analyzerRules.keywords.changePlan)) return "CHANGE_PLAN";
		if (containsKeyword(text, analyzerRules.keywords.subscription)) return "SUBSCRIPTION";
		return "CLICK";
	}
	return rawAction || "UNKNOWN";
}

function isMeaningfulAction(event) {
	return event
		&& String(event.action || "").toUpperCase() === "CLICK"
		&& textOf(event).length > 0
		&& !PRIVATE_ELEMENT_NAMES.has(elementName(event));
}

function isCompletionEvent(event) {
	const value = searchableText(event);
	return classifyAction(event) === "CONFIRM"
		|| containsKeyword(value, analyzerRules.keywords.completion);
}

function isAbandonmentEvent(event) {
	const route = routeOf(event).toLowerCase();
	return ["#home", "#pricing", "#account", "#subscription"].some(path => route.endsWith(path))
		&& !containsKeyword(textOf(event).toLowerCase(), analyzerRules.keywords.cancellation);
}

function findCancellationStart(events) {
	return events.findIndex(event => classifyAction(event) === "CANCEL");
}

function getCancellationSegment(events, cancellationStartIndex) {
	if (cancellationStartIndex < 0) return [];

	const segment = [];
	for (let index = cancellationStartIndex; index < events.length; index += 1) {
		if (index > cancellationStartIndex && isAbandonmentEvent(events[index])) break;
		segment.push(events[index]);
		if (index > cancellationStartIndex && isCompletionEvent(events[index])) break;
	}
	return segment;
}

function normalizePrompt(text) {
	const value = normalizeText(text).replace(/[.!?,:;]+/g, "");
	if (containsKeyword(value, analyzerRules.keywords.prompt)) return "prompt";
	if (containsKeyword(value, analyzerRules.keywords.retention)) return "retention";
	if (containsKeyword(value, analyzerRules.keywords.decline)) return "decline";
	if (containsKeyword(value, analyzerRules.keywords.confirmation)) return "confirmation";
	return "";
}

function getRepeatedPromptCount(segment) {
	const promptGroups = new Map();
	segment.filter(isMeaningfulAction).forEach(event => {
		const category = normalizePrompt(textOf(event));
		if (!category) return;
		promptGroups.set(category, (promptGroups.get(category) || 0) + 1);
	});

	return [...promptGroups.values()]
		.filter(count => count > 1)
		.reduce((total, count) => total + count, 0);
}

function getRetentionInterference(segment) {
	const clickOffers = segment.filter(event => classifyAction(event) === "RETENTION");
	if (clickOffers.length > 0) {
		return { detected: true, count: clickOffers.length };
	}

	const retentionEvents = [];
	let previousRetentionRoute = "";
	let previousRoute = "";
	segment.forEach(event => {
		const text = textOf(event).toLowerCase();
		const route = routeOf(event).toLowerCase();
		if (route !== previousRoute) previousRetentionRoute = "";
		previousRoute = route;
		const isDecline = containsKeyword(text, analyzerRules.keywords.decline);
		const isShaming = containsKeyword(text, analyzerRules.keywords.confirmShaming);
		const isRetention = !isDecline && !isShaming && (containsKeyword(text, analyzerRules.keywords.retention)
			|| (!text && route.includes("offer")));
		if (!isRetention || route === previousRetentionRoute) return;
		retentionEvents.push(event);
		previousRetentionRoute = route;
	});

	return {
		detected: retentionEvents.length > 0,
		count: retentionEvents.length
	};
}

function getForcedAction(segment) {
	const completionIndex = segment.findIndex((event, index) => index > 0 && isCompletionEvent(event));
	const beforeCompletion = completionIndex >= 0 ? segment.slice(0, completionIndex) : segment;
	const requiredIndex = beforeCompletion.findIndex(event => {
		const text = textOf(event).toLowerCase();
		const route = routeOf(event).toLowerCase();
		return containsKeyword(text, analyzerRules.keywords.survey)
			|| (!text && (route.includes("survey") || route.includes("feedback") || route.includes("questionnaire")));
	});

	if (requiredIndex >= 0 && requiredIndex < beforeCompletion.length - 1) {
		const requiredAction = beforeCompletion[requiredIndex];
		const value = searchableText(requiredAction);
		if (containsKeyword(value, analyzerRules.keywords.survey) || value.includes("survey")) {
			return { detected: true, type: "SURVEY" };
		}
	}

	const retentionIndex = beforeCompletion.findIndex(event =>
		containsKeyword(textOf(event).toLowerCase(), analyzerRules.keywords.retention)
	);
	const declinedAfterOffer = retentionIndex >= 0 && beforeCompletion.slice(retentionIndex + 1).some(event =>
		containsKeyword(textOf(event).toLowerCase(), analyzerRules.keywords.decline)
	);
	if (retentionIndex >= 0 && declinedAfterOffer && completionIndex >= 0) {
		return { detected: true, type: "RETENTION_OFFER" };
	}
	return { detected: false, type: null };
}

function getMeaningfulBacktracking(segment) {
	const routeHistory = [];

	// Rendering can emit the same route repeatedly. Compress those duplicates
	// before looking for a return to a route after forward movement.
	segment.forEach(event => {
		const route = routeOf(event);
		if (!route || route === routeHistory[routeHistory.length - 1]) return;
		routeHistory.push(route);
	});

	let backtracking = 0;
	for (let index = 1; index < routeHistory.length; index += 1) {
		if (routeHistory.slice(0, index - 1).includes(routeHistory[index])) backtracking += 1;
	}
	return backtracking;
}

function getGeneralIntent(events) {
	const intentTypes = new Set(["CANCEL", "DELETE_ACCOUNT", "OPT_OUT", "SUBSCRIBE", "PURCHASE", "CONTINUE", "CHANGE_PLAN"]);
	const startIndex = events.findIndex(event => intentTypes.has(classifyAction(event)));
	if (startIndex < 0) return { detected: false, type: null, startIndex: -1 };
	return { detected: true, type: classifyAction(events[startIndex]), startIndex };
}

function matchingClickEvents(events, keywords) {
	return events.filter(isMeaningfulAction)
		.filter(event => containsKeyword(textOf(event), keywords));
}

function getForcedContinuity(events) {
	const clicks = events.filter(isMeaningfulAction);
	const freeTrial = matchingClickEvents(clicks, analyzerRules.keywords.freeTrial);
	const paidAfterTrial = matchingClickEvents(clicks, analyzerRules.keywords.paidAfterTrial);
	const autoRenewal = matchingClickEvents(clicks, analyzerRules.keywords.autoRenewal);
	const detected = [freeTrial.length > 0, paidAfterTrial.length > 0, autoRenewal.length > 0]
		.filter(Boolean).length >= 2;
	return {
		detected,
		freeTrial: freeTrial.map(displayEventText),
		paidAfterTrial: paidAfterTrial.map(displayEventText),
		autoRenewal: autoRenewal.map(displayEventText)
	};
}

function getPressureSignals(events, keywords) {
	return matchingClickEvents(events, keywords).map(displayEventText);
}

function getScarcitySignals(events) {
	const signals = getPressureSignals(events, analyzerRules.keywords.scarcity);
	return signals.concat(events.filter(isMeaningfulAction)
		.filter(event => /only\s+\d+\s+(left|remaining|available)/i.test(textOf(event)))
		.map(displayEventText))
		.filter((value, index, values) => values.indexOf(value) === index);
}

function getConfirmShamingEvents(events) {
	return matchingClickEvents(events, analyzerRules.keywords.confirmShaming);
}

function getObstructionDetected(features, intent, segment) {
	if (!intent.detected) return false;
	if (intent.type === "DELETE_ACCOUNT") return features.totalSteps - intent.startIndex >= analyzerRules.thresholds.obstructionSteps;
	return intent.type === "CANCEL"
		&& features.cancellationSteps >= analyzerRules.thresholds.obstructionSteps
		&& features.cancellationSteps < analyzerRules.thresholds.cancellationStepsHigh;
}

function getUnclearChoiceDetected(events, intent) {
	if (!intent.detected) return false;
	const meaningful = events.filter(isMeaningfulAction);
	const primaryIndex = meaningful.findIndex(event => containsKeyword(textOf(event), analyzerRules.keywords.primary));
	if (primaryIndex < 0) return false;
	const alternativeIndex = meaningful.findIndex((event, index) => index > primaryIndex
		&& containsKeyword(textOf(event), analyzerRules.keywords.alternative));
	return alternativeIndex - primaryIndex >= analyzerRules.thresholds.unclearChoiceGap;
}

function getRepeatedRetentionDetected(features) {
	return features.cancellationDetected && features.retentionInterference.count >= 2;
}

function extractFeatures(events = []) {
	const safeEvents = Array.isArray(events) ? events : [];
	const meaningfulEvents = safeEvents.filter(isMeaningfulAction);
	const intent = getGeneralIntent(safeEvents);
	const cancellationStartIndex = findCancellationStart(safeEvents);
	const cancellationSegment = getCancellationSegment(safeEvents, cancellationStartIndex);
	const cancellationSteps = cancellationSegment.filter(isMeaningfulAction).length;
	const retentionInterference = getRetentionInterference(cancellationSegment);
	const forcedAction = getForcedAction(cancellationSegment);
	const baseFeatures = {
		totalSteps: meaningfulEvents.length,
		actionTypes: meaningfulEvents.map(classifyAction),
		cancellationSteps,
		repeatedPromptCount: getRepeatedPromptCount(cancellationSegment),
		retentionInterference,
		forcedActionDetected: forcedAction.detected,
		forcedActionType: forcedAction.type,
		meaningfulBacktracking: getMeaningfulBacktracking(cancellationSegment),
		cancellationDetected: cancellationStartIndex >= 0
	};
	const forcedContinuity = getForcedContinuity(safeEvents);

	return {
		...baseFeatures,
		generalIntent: intent,
		forcedContinuity,
		confirmShaming: getConfirmShamingEvents(safeEvents).map(displayEventText),
		urgencySignals: getPressureSignals(safeEvents, analyzerRules.keywords.urgency),
		scarcitySignals: getScarcitySignals(safeEvents),
		obstructionDetected: getObstructionDetected(baseFeatures, intent, cancellationSegment),
		unclearChoiceDetected: getUnclearChoiceDetected(safeEvents, intent),
		repeatedRetentionDetected: getRepeatedRetentionDetected(baseFeatures)
	};
}

function severityForSteps(cancellationSteps) {
	return cancellationSteps >= analyzerRules.thresholds.cancellationStepsHigh ? "HIGH" : "MEDIUM";
}

function severityForRepeatedPrompts(count) {
	return count >= analyzerRules.thresholds.repeatedPromptsHigh ? "HIGH" : "MEDIUM";
}

function severityForBacktracking(count) {
	return count >= analyzerRules.thresholds.backtrackingHigh ? "HIGH" : "MEDIUM";
}

function addBehavior(behaviors, type, severity, evidence) {
	behaviors.push({ type, severity, evidence });
}

function displayEventText(event) {
	const text = String(event && event.text || "").replace(/\s+/g, " ").trim();
	if (text && !PRIVATE_ELEMENT_NAMES.has(elementName(event))) return text.slice(0, 120);
	const route = routeOf(event);
	const hashIndex = route.indexOf("#");
	return hashIndex >= 0 ? route.slice(hashIndex) : "Navigation";
}

function meaningfulLabels(events) {
	return events.filter(isMeaningfulAction).map(displayEventText);
}

function routeHistoryFor(segment) {
	const routes = [];
	segment.forEach(event => {
		const route = routeOf(event);
		if (!route || route === routes[routes.length - 1]) return;
		routes.push(route);
	});
	return routes;
}

function evidenceEventsFor(type, segment, features, allEvents) {
	const source = segment.length > 0
		? segment
		: allEvents.slice(Math.max(features.generalIntent.startIndex, 0));
	if (type === "RETENTION_INTERFERENCE") {
		const clickOffers = source.filter(event => classifyAction(event) === "RETENTION");
		const retentionEvents = clickOffers.length > 0 ? clickOffers : source.filter(event =>
			!textOf(event) && routeOf(event).toLowerCase().includes("offer")
		);
		return retentionEvents
			.map(displayEventText)
			.filter((label, index, labels) => index === 0 || label !== labels[index - 1]);
	}
	if (type === "FORCED_ACTION") {
		const start = source.findIndex(event => classifyAction(event) === "SURVEY"
			|| routeOf(event).toLowerCase().includes("survey"));
		const end = source.findIndex((event, index) => index > start && isCompletionEvent(event));
		return meaningfulLabels(source.slice(Math.max(start, 0), end >= 0 ? end + 1 : source.length));
	}
	if (type === "BACKTRACKING") {
		return routeHistoryFor(source).map(route => {
			const hashIndex = route.indexOf("#");
			return hashIndex >= 0 ? route.slice(hashIndex) : route;
		});
	}
	if (type === "REPEATED_PROMPTS") {
		return source.filter(isMeaningfulAction)
			.filter(event => normalizePrompt(textOf(event)))
			.map(displayEventText);
	}
	if (type === "EXCESSIVE_STEPS") return meaningfulLabels(segment);
	if (type === "DIFFICULT_CANCELLATION") return meaningfulLabels(segment);
	if (type === "CONFIRM_SHAMING") return features.confirmShaming;
	if (type === "FORCED_CONTINUITY") return [
		...features.forcedContinuity.freeTrial,
		...features.forcedContinuity.paidAfterTrial,
		...features.forcedContinuity.autoRenewal
	];
	if (type === "URGENCY_PRESSURE") return features.urgencySignals;
	if (type === "SCARCITY_PRESSURE") return features.scarcitySignals;
	if (type === "OBSTRUCTION" || type === "UNCLEAR_CHOICE") return meaningfulLabels(source);
	if (type === "REPEATED_RETENTION") return source.filter(event => classifyAction(event) === "RETENTION").map(displayEventText);
	return [];
}

function presentationFor(type, features, segment) {
	const retentionCount = features.retentionInterference.count;
	const signals = [];
	if (features.cancellationSteps >= analyzerRules.thresholds.cancellationStepsMedium) {
		signals.push(`${features.cancellationSteps} cancellation steps`);
	}
	if (features.retentionInterference.detected) signals.push(`${retentionCount} retention offer${retentionCount === 1 ? "" : "s"}`);
	if (features.forcedActionDetected) signals.push("survey");
	if (features.repeatedPromptCount >= analyzerRules.thresholds.repeatedPromptsMedium) {
		signals.push(`${features.repeatedPromptCount} repeated prompts`);
	}
	if (features.meaningfulBacktracking > 0) signals.push(`${features.meaningfulBacktracking} route reversal${features.meaningfulBacktracking === 1 ? "" : "s"}`);

	const presentations = {
		EXCESSIVE_STEPS: {
			title: "Excessive Steps",
			explanation: "Several additional actions were required after you started cancellation.",
			whyItMatters: "Extra steps can make an intended action harder to complete.",
			evidence: `${features.cancellationSteps} meaningful actions were required after cancellation was initiated.`
		},
		REPEATED_PROMPTS: {
			title: "Repeated Prompts",
			explanation: "The website presented multiple prompts or retention messages during your cancellation attempt.",
			whyItMatters: "Repeated prompts may pressure you to reconsider or make the intended action harder to complete.",
			evidence: `${features.repeatedPromptCount} cancellation or retention prompts were encountered.`
		},
		FORCED_ACTION: {
			title: "Forced Action",
			explanation: "A survey or additional action appeared before you could complete cancellation.",
			whyItMatters: "This adds an additional step between your decision and completing the requested action.",
			evidence: "A cancellation survey was encountered before final cancellation."
		},
		DIFFICULT_CANCELLATION: {
			title: "Difficult Cancellation",
			explanation: "Multiple friction signals were detected during the cancellation process.",
			whyItMatters: "The website may be making cancellation more difficult than necessary.",
			evidence: `${signals.join(" + ")} detected.`
		},
		BACKTRACKING: {
			title: "Repeated Navigation",
			explanation: "The cancellation flow returned to earlier stages instead of progressing directly.",
			whyItMatters: "Returning to earlier stages can make the process longer and harder to complete.",
			evidence: "Earlier cancellation stages were revisited."
		},
		RETENTION_INTERFERENCE: {
			title: "Retention Offer",
			explanation: "A promotional offer appeared after you started cancellation.",
			whyItMatters: "This may encourage you to stay instead of completing your original action.",
			evidence: `${retentionCount} retention offer${retentionCount === 1 ? "" : "s"} appeared after cancellation was initiated.`
		},
		CONFIRM_SHAMING: {
			title: "Confirm Shaming",
			explanation: "The decline option used wording that may make saying no feel negative.",
			whyItMatters: "This type of language can pressure users into accepting an option they did not intend to choose.",
			evidence: "A decline option used language implying a negative choice."
		},
		FORCED_CONTINUITY: {
			title: "Automatic Renewal",
			explanation: "The trial appears to transition into a paid subscription automatically.",
			whyItMatters: "You may be charged after the trial unless you cancel before renewal.",
			evidence: "Free trial, paid-after-trial, and renewal messages appeared together."
		},
		OBSTRUCTION: {
			title: "Obstructed Action",
			explanation: "The requested action required several additional steps before completion.",
			whyItMatters: "Extra friction can make it harder to complete the action you intended.",
			evidence: `${features.totalSteps - features.generalIntent.startIndex} meaningful steps followed the detected intent.`
		},
		URGENCY_PRESSURE: {
			title: "Urgency Pressure",
			explanation: "The website used time-sensitive language to encourage a quick decision.",
			whyItMatters: "Urgency can pressure users to act before evaluating the decision carefully.",
			evidence: `Potential urgency pressure: ${features.urgencySignals.join("; ")}`
		},
		SCARCITY_PRESSURE: {
			title: "Scarcity Pressure",
			explanation: "The website indicated that availability may be limited.",
			whyItMatters: "Scarcity messaging can encourage rushed decisions.",
			evidence: `Potential scarcity pressure: ${features.scarcitySignals.join("; ")}`
		},
		UNCLEAR_CHOICE: {
			title: "Unclear Choice",
			explanation: "The alternative to the primary action may be harder to find.",
			whyItMatters: "Users may overlook an alternative because of how choices are presented.",
			evidence: "A primary action appeared before the alternative choice."
		},
		REPEATED_RETENTION: {
			title: "Repeated Retention Offers",
			explanation: "Multiple retention offers appeared after cancellation was initiated.",
			whyItMatters: "Repeated offers can make the requested action harder to complete.",
			evidence: `${retentionCount} retention attempts occurred during cancellation.`
		}
	};
	return presentations[type];
}

function summaryForRisk(riskScore) {
	if (riskScore >= 60) return {
		title: "High Risk Behavior",
		message: "Multiple behavioral signals were detected that may make the requested action difficult or encourage you to change your decision."
	};
	if (riskScore >= 30) return {
		title: "Potentially Manipulative",
		message: "Some behaviors may be making the requested action harder or more confusing to complete."
	};
	return {
		title: "Low Risk",
		message: "No significant behavioral manipulation signals were detected."
	};
}

function whatHappenedFor(features, segment) {
	if (!features.cancellationDetected) {
		if (features.forcedContinuity.detected) return "You started a trial and encountered messages about paid renewal or automatic subscription continuation.";
		if (features.urgencySignals.length > 0 || features.scarcitySignals.length > 0) return "You encountered time-sensitive or limited-availability messaging during the interaction.";
		return "No cancellation flow was detected in the recorded interactions.";
	}
	let summary = "You started a subscription cancellation";
	if (features.retentionInterference.detected) summary += " and encountered a retention offer";
	if (features.forcedActionDetected) summary += " and an additional survey";
	if (features.meaningfulBacktracking > 0) summary += " and returned to earlier cancellation stages";
	if (summary === "You started a subscription cancellation") return `${summary} without significant behavioral friction.`;
	return `${summary} before reaching confirmation.`;
}

function whyThisMattersFor(riskScore) {
	if (riskScore >= 60) return "Multiple friction and persuasion signals were detected during the interaction.";
	if (riskScore >= 30) return "Some friction or persuasive behavior was detected during the interaction.";
	return "Normal navigation was detected without significant behavioral friction.";
}

function enrichBehaviors(behaviors, features, segment, allEvents) {
	return behaviors.map(behavior => {
		const presentation = presentationFor(behavior.type, features, segment);
		const trail = evidenceEventsFor(behavior.type, segment, features, allEvents);
		const category = Object.keys(analyzerRules.categories).find(name => analyzerRules.categories[name].includes(behavior.type)) || "OTHER";
		return {
			type: behavior.type,
			category,
			title: presentation.title,
			severity: behavior.severity,
			explanation: presentation.explanation,
			evidence: presentation.evidence,
			whyItMatters: presentation.whyItMatters,
			evidenceEvents: trail
		};
	});
}

function analyzeBehavior(events = []) {
	const safeEvents = Array.isArray(events) ? events : [];
	const features = extractFeatures(safeEvents);
	const cancellationStartIndex = findCancellationStart(safeEvents);
	const cancellationSegment = getCancellationSegment(safeEvents, cancellationStartIndex);
	const behaviors = [];

	if (features.cancellationSteps >= analyzerRules.thresholds.cancellationStepsHigh) {
		addBehavior(behaviors, "EXCESSIVE_STEPS", severityForSteps(features.cancellationSteps),
			`${features.cancellationSteps} steps were required after cancellation was initiated.`);
	}
	if (features.repeatedPromptCount >= analyzerRules.thresholds.repeatedPromptsMedium) {
		addBehavior(behaviors, "REPEATED_PROMPTS", severityForRepeatedPrompts(features.repeatedPromptCount),
			`${features.repeatedPromptCount} repeated cancellation or retention prompts detected.`);
	}
	if (features.retentionInterference.detected) {
		addBehavior(behaviors, "RETENTION_INTERFERENCE", "MEDIUM",
			`${features.retentionInterference.count} retention offer${features.retentionInterference.count === 1 ? "" : "s"} appeared after cancellation was initiated.`);
	}
	if (features.forcedActionDetected) {
		const label = features.forcedActionType === "SURVEY" ? "cancellation survey" : "required action";
		addBehavior(behaviors, "FORCED_ACTION", "HIGH",
			`A ${label} appeared before cancellation could be completed.`);
	}
	if (features.meaningfulBacktracking >= analyzerRules.thresholds.backtrackingMedium) {
		addBehavior(behaviors, "BACKTRACKING", severityForBacktracking(features.meaningfulBacktracking),
			`${features.meaningfulBacktracking} meaningful route reversal${features.meaningfulBacktracking === 1 ? "" : "s"} detected during cancellation.`);
	}
	if (features.confirmShaming.length > 0) {
		addBehavior(behaviors, "CONFIRM_SHAMING", "MEDIUM",
			"The decline option used wording implying a negative choice.");
	}
	if (features.forcedContinuity.detected) {
		addBehavior(behaviors, "FORCED_CONTINUITY", "HIGH",
			"Free-trial and paid-renewal messages appeared together in the interaction.");
	}
	if (features.obstructionDetected) {
		addBehavior(behaviors, "OBSTRUCTION", "MEDIUM",
			"The requested action required several additional steps before completion.");
	}
	if (features.urgencySignals.length > 0) {
		addBehavior(behaviors, "URGENCY_PRESSURE", "MEDIUM",
			"Potential urgency pressure was detected in the interaction wording.");
	}
	if (features.scarcitySignals.length > 0) {
		addBehavior(behaviors, "SCARCITY_PRESSURE", "MEDIUM",
			"Potential scarcity pressure was detected in the interaction wording.");
	}
	if (features.unclearChoiceDetected) {
		addBehavior(behaviors, "UNCLEAR_CHOICE", "LOW",
			"The alternative to a primary action appeared after additional navigation.");
	}
	if (features.repeatedRetentionDetected) {
		addBehavior(behaviors, "REPEATED_RETENTION", "HIGH",
			"Multiple retention offers appeared after cancellation was initiated.");
	}

	const frictionSignals = [
		features.cancellationSteps >= analyzerRules.thresholds.cancellationStepsMedium,
		features.repeatedPromptCount >= analyzerRules.thresholds.repeatedPromptsMedium,
		features.retentionInterference.detected,
		features.forcedActionDetected,
		features.meaningfulBacktracking > 0
	].filter(Boolean).length;
	const difficultCancellation = features.cancellationDetected
		&& (features.cancellationSteps >= analyzerRules.thresholds.cancellationStepsHigh
			|| frictionSignals >= analyzerRules.thresholds.difficultSignalCount);

	if (difficultCancellation) {
		addBehavior(behaviors, "DIFFICULT_CANCELLATION", "HIGH",
			"Multiple friction signals were detected during cancellation.");
	}

	const supportingEvidenceByType = new Map();
	const addSupportingEvidence = (type, source, evidence) => {
		if (!evidence) return;
		if (!supportingEvidenceByType.has(type)) supportingEvidenceByType.set(type, []);
		supportingEvidenceByType.get(type).push({ source, ...evidence });
	};
	const existingBehaviorTypes = new Set(behaviors.map(behavior => behavior.type));
	const addCorroboratedBehavior = (type, severity, evidence, source, support) => {
		addSupportingEvidence(type, source, support);
		if (existingBehaviorTypes.has(type)) return;
		addBehavior(behaviors, type, severity, evidence);
		existingBehaviorTypes.add(type);
	};

	let b2Result = null;
	let b3Result = null;
	try {
		if (typeof root.extractBehaviorFeatures === "function") {
			b2Result = root.extractBehaviorFeatures(safeEvents);
		}
	} catch {}

	try {
		if (typeof root.analyzeBehaviorSequence === "function") {
			b3Result = root.analyzeBehaviorSequence(safeEvents, b2Result);
		}
	} catch {}

	const b2Features = b2Result?.behavior_features;
	if (features.cancellationDetected && b2Features) {
		const b2Evidence = Array.isArray(b2Result.evidence) ? b2Result.evidence : [];
		const evidenceFor = feature => b2Evidence.find(item => item.feature === feature);
		if (b2Features.cancellation_steps >= analyzerRules.thresholds.cancellationStepsHigh) {
			addCorroboratedBehavior("EXCESSIVE_STEPS", "HIGH",
				"B2 confirmed excessive cancellation steps.", "b2", evidenceFor("cancellation_steps"));
		}
		if (b2Features.repeated_prompt_count >= analyzerRules.thresholds.repeatedPromptsMedium) {
			addCorroboratedBehavior("REPEATED_PROMPTS", severityForRepeatedPrompts(b2Features.repeated_prompt_count),
				"B2 confirmed repeated cancellation prompts.", "b2", evidenceFor("repeated_prompt_count"));
		}
		if (b2Features.retention_offer_count > 0) {
			addCorroboratedBehavior("RETENTION_INTERFERENCE", "MEDIUM",
				"B2 confirmed retention offers during cancellation.", "b2", evidenceFor("retention_offer_count"));
		}
		if (b2Features.retention_offer_count >= 2) {
			addCorroboratedBehavior("REPEATED_RETENTION", "HIGH",
				"B2 confirmed repeated retention offers during cancellation.", "b2", evidenceFor("retention_offer_count"));
		}
		if (b2Features.forced_action_count > 0 && b2Features.survey_required === true) {
			addCorroboratedBehavior("FORCED_ACTION", "HIGH",
				"B2 confirmed a mandatory action during cancellation.", "b2", evidenceFor("forced_action_count"));
		}
		if (b2Features.backtracking_count > 0) {
			addCorroboratedBehavior("BACKTRACKING", severityForBacktracking(b2Features.backtracking_count),
				"B2 confirmed cancellation-flow backtracking.", "b2", evidenceFor("backtracking_count"));
		}
	}

	const b3Signals = Array.isArray(b3Result?.behavior_signals) ? b3Result.behavior_signals : [];
	for (const signal of features.cancellationDetected ? b3Signals : []) {
		const support = {
			signal_type: signal.type,
			strength: signal.strength,
			event_indices: signal.event_indices,
			route_sequence: signal.route_sequence
		};
		if (signal.type === "repeated_retention_interference") {
			addCorroboratedBehavior("REPEATED_RETENTION", "HIGH", signal.reason, "b3", support);
		} else if (signal.type === "required_survey" || signal.type === "forced_action_sequence") {
			addCorroboratedBehavior("FORCED_ACTION", "HIGH", signal.reason, "b3", support);
		} else if (signal.type === "backtracking_loop" && signal.strength !== "weak") {
			addCorroboratedBehavior("BACKTRACKING", severityForBacktracking(features.meaningfulBacktracking || 2), signal.reason, "b3", support);
		} else if (signal.type === "cancellation_obstruction") {
			addCorroboratedBehavior("DIFFICULT_CANCELLATION", "HIGH", signal.reason, "b3", support);
		} else if (signal.type === "dead_end_behavior" && signal.strength === "strong") {
			addCorroboratedBehavior("OBSTRUCTION", "MEDIUM", signal.reason, "b3", support);
		}
	}

	const hasRepeatedRetention = behaviors.some(behavior => behavior.type === "REPEATED_RETENTION");
	const riskScore = Math.min(100, behaviors.reduce((score, behavior) => {
		// Repeated retention is the stronger version of the same offer signal;
		// count its weight once instead of adding both retention weights.
		if (hasRepeatedRetention && behavior.type === "RETENTION_INTERFERENCE") return score;
		return score + analyzerRules.weights[behavior.type];
	}, 0));
	const friendlyBehaviors = enrichBehaviors(behaviors, features, cancellationSegment, safeEvents)
		.map(behavior => ({
			...behavior,
			...(supportingEvidenceByType.has(behavior.type)
				? { supportingEvidence: supportingEvidenceByType.get(behavior.type) }
				: {})
		}));
	const summary = summaryForRisk(riskScore);
	const matchDataset = typeof root.matchBehaviorToDataset === "function"
		? root.matchBehaviorToDataset
		: datasetMatcher?.matchBehaviorToDataset;
	const datasetMatches = matchDataset ? matchDataset(features) : [];

	const result = {
		riskScore,
		overallSeverity: riskScore >= 60 ? "HIGH" : riskScore >= 30 ? "MEDIUM" : "LOW",
		summary,
		summaryText: summary.message,
		whatHappened: whatHappenedFor(features, cancellationSegment),
		whyThisMatters: whyThisMattersFor(riskScore),
		intent: {
			detected: features.generalIntent.detected,
			type: features.generalIntent.type,
			startIndex: features.generalIntent.startIndex,
			cancellationDetected: features.cancellationDetected,
			cancellationStartIndex
		},
		behaviors: friendlyBehaviors,
		features,
		dataset_matches: datasetMatches,
		evidence: friendlyBehaviors.map(behavior => ({
			behavior: behavior.type,
			events: behavior.evidenceEvents
		}))
	};
	console.log("BEHAVIOR FEATURES:", features);
	console.log("BEHAVIOR RESULT:", result);
	return result;
}

if (typeof module !== "undefined" && module.exports) {
	module.exports = { normalizeText, classifyAction, extractFeatures, analyzeBehavior };
}

root.analyzeBehavior = analyzeBehavior;
})(globalThis);
