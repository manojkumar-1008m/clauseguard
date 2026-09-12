/**
 * DarkShield Phase B2 - Behavioral Feature Extraction
 *
 * Extracts measurable behavioral facts and signals from ordered event sequences.
 * Sequence-aware: uses timestamps, routes, actions, element text, element metadata,
 * and navigation history.
 *
 * NOTE: This module strictly produces behavioral features and observable signals.
 * It does NOT compute final risk scores, classify dark patterns, or declare legal violations.
 */

/* global ANALYZER_RULES */

(function (root) {
	"use strict";

const analyzerRules = root.analyzerRules || root.ANALYZER_RULES;

const INFORMATIVE_CANCEL_PHRASES = [
	"policy",
	"terms",
	"orders",
	"history",
	"receipt",
	"how to cancel",
	"cancellation policy",
	"cancelled orders",
	"view cancelled"
];

function normalizeText(value) {
	return String(value || "").toLowerCase().replace(/\s+/g, " ").trim();
}

function getAction(event) {
	return String(event?.action || "OTHER").toUpperCase();
}

function getRoute(event) {
	if (!event) return "/";
	if (event.route) return String(event.route);
	if (event.url) {
		try {
			if (event.url.startsWith("http://") || event.url.startsWith("https://")) {
				const parsed = new URL(event.url);
				return `${parsed.pathname}${parsed.search || ""}${parsed.hash || ""}` || "/";
			}
		} catch {
			return String(event.url);
		}
		return String(event.url);
	}
	return "/";
}

function getScreenPath(route) {
	const str = String(route || "/");
	const withoutQuery = str.split("?")[0];
	return withoutQuery.endsWith("/") && withoutQuery.length > 1
		? withoutQuery.slice(0, -1)
		: withoutQuery;
}

function getText(event) {
	if (!event) return "";
	if (event.element && typeof event.element === "object") {
		const tag = String(event.element.tag || "").toUpperCase();
		if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") {
			return "";
		}
		return normalizeText(event.element.text || event.element.aria_label || event.text || "");
	}
	return normalizeText(event.text || "");
}

function getTimestamp(event) {
	if (!event?.timestamp) return null;
	const time = new Date(event.timestamp).getTime();
	return Number.isFinite(time) ? time : null;
}

function containsKeyword(text, keywords) {
	if (!text || !keywords) return false;
	return keywords.some(keyword => text.includes(keyword));
}

function isCompletionEvent(event) {
	const text = getText(event);
	const route = getRoute(event).toLowerCase();

	const hasCompletionKeyword = analyzerRules?.keywords?.completion
		? containsKeyword(text, analyzerRules.keywords.completion)
		: ["cancellation complete", "cancelled successfully", "canceled successfully"].some(k => text.includes(k));

	const isExplicitConfirm = text === "confirm cancellation"
		|| text === "yes, cancel"
		|| text === "finish cancellation"
		|| text === "cancel subscription confirmation";

	const hasSuccessRoute = ["#success", "/success", "#completed", "/completed", "#cancelled", "/cancelled"].some(k => route.includes(k));

	return hasCompletionKeyword || isExplicitConfirm || hasSuccessRoute;
}

function isDeclineEvent(event) {
	const text = getText(event);
	if (!text) return false;
	const declineKeywords = analyzerRules?.keywords?.decline || ["no thanks", "decline", "continue cancelling", "maybe later", "skip", "not interested"];
	return containsKeyword(text, declineKeywords);
}

function isCancellationIntent(event) {
	if (isCompletionEvent(event)) {
		return false;
	}

	const text = getText(event);
	const route = getRoute(event).toLowerCase();

	if (text && INFORMATIVE_CANCEL_PHRASES.some(phrase => text.includes(phrase))) {
		return false;
	}

	const hasCancelKeyword = analyzerRules?.keywords?.cancellation
		? containsKeyword(text, analyzerRules.keywords.cancellation)
		: ["cancel", "unsubscribe", "terminate", "end subscription", "stop subscription"].some(k => text.includes(k));

	const hasCancelRoute = ["#cancel", "/cancel", "cancel-subscription", "cancellation"].some(k => route.includes(k));

	return hasCancelKeyword || (hasCancelRoute && getAction(event) === "CLICK" && !text.includes("confirm"));
}

function isSurveyEvent(event) {
	const text = getText(event);
	const route = getRoute(event).toLowerCase();

	const hasSurveyKeyword = analyzerRules?.keywords?.survey
		? containsKeyword(text, analyzerRules.keywords.survey)
		: ["survey", "feedback", "questionnaire", "reason", "why are you leaving"].some(k => text.includes(k));

	const hasSurveyRoute = ["survey", "feedback", "questionnaire", "reason"].some(k => route.includes(k));

	return hasSurveyKeyword || hasSurveyRoute;
}

function isRetentionEvent(event, inCancellationFlow = false) {
	if (isDeclineEvent(event) || isCompletionEvent(event)) {
		return false;
	}

	const text = getText(event);
	const route = getRoute(event).toLowerCase();

	if (!text && !route) return false;

	const hasRetentionKeyword = analyzerRules?.keywords?.retention
		? containsKeyword(text, analyzerRules.keywords.retention)
		: ["discount", "offer", "save", "stay", "keep", "pause", "deal"].some(k => text.includes(k));

	const hasRetentionRoute = ["offer", "retention", "save-offer", "discount"].some(k => route.includes(k));

	if (inCancellationFlow) {
		return hasRetentionKeyword || (hasRetentionRoute && text.length > 0 && !text.includes("confirm"));
	}

	return hasRetentionRoute || (hasRetentionKeyword && (route.includes("account") || route.includes("subscription")));
}

function classifyRetentionType(event) {
	const text = getText(event);
	if (text.includes("%") || text.includes("discount") || text.includes("save ₹") || text.includes("save $") || text.includes("price cut")) {
		return "DISCOUNT";
	}
	if (text.includes("pause") || text.includes("hold")) {
		return "PAUSE_PLAN";
	}
	if (text.includes("free month") || text.includes("free days") || text.includes("free trial") || text.includes("bonus")) {
		return "FREE_EXTENSION";
	}
	if (text.includes("switch") || text.includes("downgrade") || text.includes("basic") || text.includes("lower plan")) {
		return "PLAN_DOWNGRADE";
	}
	return "RETENTION_OFFER";
}

function isPromptEvent(event) {
	const text = getText(event);
	if (!text) return false;

	const hasPromptKeyword = analyzerRules?.keywords?.prompt
		? containsKeyword(text, analyzerRules.keywords.prompt)
		: ["are you sure", "wait", "don't leave", "before you go", "last chance"].some(k => text.includes(k));

	return hasPromptKeyword || (text.endsWith("?") && text.length > 5);
}

function isAlternativeChoice(event, inCancellationFlow) {
	if (!inCancellationFlow) return false;
	const text = getText(event);
	if (!text) return false;

	return text.includes("keep subscription")
		|| text.includes("stay with us")
		|| text.includes("pause instead")
		|| text.includes("change plan instead")
		|| text.includes("switch to basic")
		|| text.includes("maybe later");
}

function extractBehaviorFeatures(events = []) {
	const safeEvents = Array.isArray(events) ? events : [];
	const totalEvents = safeEvents.length;

	let totalClicks = 0;
	let totalNavigations = 0;
	let totalInputChanges = 0;
	const clickIndices = [];
	const navIndices = [];
	const inputChangeIndices = [];

	const uniqueRoutesSet = new Set();
	const uniqueScreensSet = new Set();
	const routeHistory = [];
	const compressedRoutes = [];
	const compressedRouteIndices = [];

	let cancellationStartIndex = -1;
	const cancelAttemptIndices = [];

	safeEvents.forEach((event, index) => {
		const action = getAction(event);
		if (action === "CLICK") {
			totalClicks++;
			clickIndices.push(index);
		} else if (action === "NAVIGATION") {
			totalNavigations++;
			navIndices.push(index);
		} else if (action === "INPUT_CHANGE") {
			totalInputChanges++;
			inputChangeIndices.push(index);
		}

		const route = getRoute(event);
		uniqueRoutesSet.add(route);
		uniqueScreensSet.add(getScreenPath(route));
		routeHistory.push(route);

		if (compressedRoutes.length === 0 || compressedRoutes[compressedRoutes.length - 1] !== route) {
			compressedRoutes.push(route);
			compressedRouteIndices.push(index);
		}

		if (isCancellationIntent(event)) {
			cancelAttemptIndices.push(index);
			if (cancellationStartIndex === -1) {
				cancellationStartIndex = index;
			}
		}
	});

	let cancellationDetected = cancellationStartIndex !== -1;
	let cancellationSteps = 0;
	const cancellationRoutesSet = new Set();
	const cancellationEventIndices = [];
	let completionIndex = -1;
	let abandonmentDetected = false;

	if (cancellationDetected) {
		for (let index = cancellationStartIndex; index < totalEvents; index++) {
			const event = safeEvents[index];
			const route = getRoute(event);
			cancellationRoutesSet.add(route);
			cancellationEventIndices.push(index);

			if (getAction(event) === "CLICK" || getAction(event) === "NAVIGATION") {
				cancellationSteps++;
			}

			if (index > cancellationStartIndex && isCompletionEvent(event)) {
				completionIndex = index;
				break;
			}

			if (index > cancellationStartIndex) {
				const lowerRoute = route.toLowerCase();
				const isAbandonPath = ["#home", "/home", "#pricing", "/pricing", "#account", "/account", "#dashboard", "/dashboard"]
					.some(p => lowerRoute === p || lowerRoute.endsWith(p));
				const isCancelText = isCancellationIntent(event);
				if (isAbandonPath && !isCancelText) {
					abandonmentDetected = true;
					break;
				}
			}
		}

		if (completionIndex === -1 && !abandonmentDetected && totalEvents > cancellationStartIndex + 1) {
			const lastRoute = getRoute(safeEvents[totalEvents - 1]).toLowerCase();
			if (!["#cancel", "/cancel", "#confirm", "/confirm"].some(p => lastRoute.includes(p))) {
				abandonmentDetected = true;
			}
		}
	}

	const promptMap = new Map();
	const promptIndicesMap = new Map();
	safeEvents.forEach((event, index) => {
		if (isPromptEvent(event)) {
			const textKey = getText(event).replace(/[.!?,:;]+/g, "").trim();
			if (textKey.length > 0) {
				promptMap.set(textKey, (promptMap.get(textKey) || 0) + 1);
				if (!promptIndicesMap.has(textKey)) promptIndicesMap.set(textKey, []);
				promptIndicesMap.get(textKey).push(index);
			}
		}
	});

	let repeatedPromptCount = 0;
	const repeatedPromptTexts = [];
	const repeatedPromptIndices = [];
	promptMap.forEach((count, text) => {
		if (count > 1) {
			repeatedPromptCount += (count - 1);
			repeatedPromptTexts.push(text);
			repeatedPromptIndices.push(...(promptIndicesMap.get(text) || []));
		}
	});

	let retentionOfferCount = 0;
	const retentionOfferTypesSet = new Set();
	const retentionOfferIndices = [];
	safeEvents.forEach((event, index) => {
		const inCancel = cancellationDetected && index >= cancellationStartIndex;
		if (isRetentionEvent(event, inCancel)) {
			retentionOfferCount++;
			retentionOfferTypesSet.add(classifyRetentionType(event));
			retentionOfferIndices.push(index);
		}
	});

	let confirmationScreenCount = 0;
	const confirmationIndices = [];
	safeEvents.forEach((event, index) => {
		const text = getText(event);
		const route = getRoute(event).toLowerCase();
		const isConfirmation = containsKeyword(text, analyzerRules?.keywords?.confirmation || ["confirm"])
			|| text.includes("confirm cancellation")
			|| text.includes("are you sure")
			|| route.endsWith("#confirm")
			|| route.endsWith("/confirm");

		if (isConfirmation && (getAction(event) === "CLICK" || getAction(event) === "NAVIGATION")) {
			confirmationScreenCount++;
			confirmationIndices.push(index);
		}
	});
	const repeatedConfirmationCount = Math.max(0, confirmationScreenCount - 1);

	let backtrackingCount = 0;
	const backtrackedRoutesSet = new Set();
	const backtrackingIndices = [];
	const seenRoutesSet = new Set();

	compressedRoutes.forEach((route, cIndex) => {
		if (seenRoutesSet.has(route)) {
			backtrackingCount++;
			backtrackedRoutesSet.add(route);
			backtrackingIndices.push(compressedRouteIndices[cIndex]);
		}
		seenRoutesSet.add(route);
	});

	let deadEndCount = 0;
	const deadEndRoutesSet = new Set();
	const deadEndIndices = [];

	for (let i = 0; i < compressedRoutes.length - 3; i++) {
		if (compressedRoutes[i] === compressedRoutes[i + 2] && compressedRoutes[i + 1] === compressedRoutes[i + 3]) {
			deadEndCount++;
			deadEndRoutesSet.add(compressedRoutes[i]);
			deadEndIndices.push(compressedRouteIndices[i + 2]);
		}
	}

	safeEvents.forEach((event, index) => {
		if (event?.element && typeof event.element === "object") {
			if (event.element.disabled || event.element.aria_disabled === "true") {
				const text = getText(event);
				if (text.includes("continue") || text.includes("cancel") || text.includes("confirm") || text.includes("next")) {
					deadEndCount++;
					deadEndRoutesSet.add(getRoute(event));
					deadEndIndices.push(index);
				}
			}
		}
	});

	let surveyDetected = false;
	let surveyRequired = false;
	const surveyIndices = [];

	safeEvents.forEach((event, index) => {
		if (isSurveyEvent(event)) {
			surveyDetected = true;
			surveyIndices.push(index);
			if (cancellationDetected && index > cancellationStartIndex) {
				if (completionIndex === -1 || index < completionIndex) {
					surveyRequired = true;
				}
			}
		}
	});

	let forcedActionCount = 0;
	const forcedActionTypesSet = new Set();
	const forcedActionIndices = [];

	if (surveyRequired) {
		forcedActionCount++;
		forcedActionTypesSet.add("REQUIRED_SURVEY");
		forcedActionIndices.push(...surveyIndices);
	}

	safeEvents.forEach((event, index) => {
		const text = getText(event);
		if (text.includes("call customer support") || text.includes("call 1-800") || text.includes("contact support to cancel")) {
			forcedActionCount++;
			forcedActionTypesSet.add("REQUIRED_SUPPORT_CONTACT");
			forcedActionIndices.push(index);
		}
	});

	let alternativeChoiceCount = 0;
	const alternativeChoicesList = [];
	const alternativeChoiceIndices = [];

	safeEvents.forEach((event, index) => {
		const inCancel = cancellationDetected && index >= cancellationStartIndex;
		if (isAlternativeChoice(event, inCancel)) {
			alternativeChoiceCount++;
			alternativeChoicesList.push(getText(event));
			alternativeChoiceIndices.push(index);
		}
	});

	let flowDurationSeconds = 0;
	if (totalEvents >= 2) {
		const tStart = getTimestamp(safeEvents[0]);
		const tEnd = getTimestamp(safeEvents[totalEvents - 1]);
		if (tStart != null && tEnd != null && tEnd >= tStart) {
			flowDurationSeconds = Math.round((tEnd - tStart) / 1000);
		}
	}

	let routeChangeCount = 0;
	let repeatedRouteCount = 0;
	for (let i = 1; i < totalEvents; i++) {
		if (getRoute(safeEvents[i]) !== getRoute(safeEvents[i - 1])) {
			routeChangeCount++;
		} else {
			repeatedRouteCount++;
		}
	}

	const behaviorFeatures = {
		total_events: totalEvents,
		total_clicks: totalClicks,
		total_navigation_events: totalNavigations,
		total_input_changes: totalInputChanges,
		unique_routes: uniqueRoutesSet.size,
		unique_screens: uniqueScreensSet.size,
		cancellation_detected: cancellationDetected,
		cancellation_steps: cancellationSteps,
		cancellation_routes: [...cancellationRoutesSet],
		cancel_attempt_count: cancelAttemptIndices.length,
		repeated_prompt_count: repeatedPromptCount,
		repeated_prompt_texts: repeatedPromptTexts,
		retention_offer_count: retentionOfferCount,
		retention_offer_types: [...retentionOfferTypesSet],
		confirmation_screen_count: confirmationScreenCount,
		repeated_confirmation_count: repeatedConfirmationCount,
		backtracking_count: backtrackingCount,
		backtracked_routes: [...backtrackedRoutesSet],
		dead_end_count: deadEndCount,
		dead_end_routes: [...deadEndRoutesSet],
		forced_action_count: forcedActionCount,
		forced_action_types: [...forcedActionTypesSet],
		alternative_choice_count: alternativeChoiceCount,
		alternative_choices: alternativeChoicesList,
		survey_detected: surveyDetected,
		survey_required: surveyRequired,
		abandonment_detected: abandonmentDetected,
		flow_duration_seconds: flowDurationSeconds,
		route_change_count: routeChangeCount,
		repeated_route_count: repeatedRouteCount
	};

	const evidence = [
		{ feature: "total_events", value: totalEvents, event_indices: safeEvents.map((_, i) => i) },
		{ feature: "total_clicks", value: totalClicks, event_indices: clickIndices },
		{ feature: "total_navigation_events", value: totalNavigations, event_indices: navIndices },
		{ feature: "total_input_changes", value: totalInputChanges, event_indices: inputChangeIndices },
		{ feature: "cancellation_detected", value: cancellationDetected, event_indices: cancelAttemptIndices },
		{ feature: "cancellation_steps", value: cancellationSteps, event_indices: cancellationEventIndices },
		{ feature: "cancel_attempt_count", value: cancelAttemptIndices.length, event_indices: cancelAttemptIndices },
		{ feature: "repeated_prompt_count", value: repeatedPromptCount, event_indices: repeatedPromptIndices },
		{ feature: "retention_offer_count", value: retentionOfferCount, event_indices: retentionOfferIndices },
		{ feature: "confirmation_screen_count", value: confirmationScreenCount, event_indices: confirmationIndices },
		{ feature: "backtracking_count", value: backtrackingCount, event_indices: backtrackingIndices },
		{ feature: "dead_end_count", value: deadEndCount, event_indices: deadEndIndices },
		{ feature: "survey_detected", value: surveyDetected, event_indices: surveyIndices },
		{ feature: "forced_action_count", value: forcedActionCount, event_indices: forcedActionIndices },
		{ feature: "alternative_choice_count", value: alternativeChoiceCount, event_indices: alternativeChoiceIndices }
	];

	return {
		behavior_features: behaviorFeatures,
		evidence
	};
}

if (typeof module !== "undefined" && module.exports) {
	module.exports = {
		extractBehaviorFeatures
	};
}

root.extractBehaviorFeatures = extractBehaviorFeatures;
})(globalThis);
