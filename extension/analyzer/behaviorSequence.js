/**
 * DarkShield Phase B3 — Sequence-Based Behavior Analysis
 *
 * Transforms B1 structured events + B2 behavioral features into
 * deterministic behavioral signals and traceable evidence.
 *
 * Sequence-aware reasoning:
 * - Evaluates event ordering, route transitions, and interaction relationships
 * - Strictly does NOT calculate final dark-pattern risk or risk scores
 * - Strictly does NOT declare legal violations or use ML/LLMs
 * - Signal 'strength' is behavioral evidence strength ('weak' | 'moderate' | 'strong'), NOT probability
 */

/* global ANALYZER_RULES */

(function (root) {
	"use strict";

const analyzerRules = root.analyzerRules || root.ANALYZER_RULES;

const b2Module = typeof root.extractBehaviorFeatures === "function"
	? { extractBehaviorFeatures: root.extractBehaviorFeatures }
	: (typeof require === "function" ? require("./behaviorFeatures.js") : null);

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

function containsKeyword(text, keywords) {
	if (!text || !keywords) return false;
	return keywords.some(keyword => text.includes(keyword));
}

function isCompletionEvent(event) {
	const text = getText(event);
	const route = getRoute(event).toLowerCase();

	const hasCompletionKeyword = analyzerRules?.keywords?.completion
		? containsKeyword(text, analyzerRules.keywords.completion)
		: ["cancellation complete", "cancelled successfully", "canceled successfully", "subscription ended", "account deleted successfully"].some(k => text.includes(k));

	const isExplicitConfirm = text === "confirm cancellation"
		|| text === "yes, cancel"
		|| text === "finish cancellation"
		|| text === "confirm deletion"
		|| text === "cancel subscription confirmation";

	const hasSuccessRoute = ["#success", "/success", "#completed", "/completed", "#cancelled", "/cancelled", "/done"].some(k => route.includes(k));

	return hasCompletionKeyword || isExplicitConfirm || hasSuccessRoute;
}

function isDeclineEvent(event) {
	const text = getText(event);
	if (!text) return false;
	const declineKeywords = analyzerRules?.keywords?.decline || [
		"no thanks",
		"decline",
		"continue cancelling",
		"continue cancellation",
		"maybe later",
		"skip",
		"not interested",
		"no, continue to cancel",
		"keep cancelling",
		"proceed to cancel",
		"no,"
	];
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
		: ["cancel", "unsubscribe", "terminate", "end subscription", "stop subscription", "delete account"].some(k => text.includes(k));

	const hasCancelRoute = ["#cancel", "/cancel", "cancel-subscription", "cancellation", "delete"].some(k => route.includes(k));

	return hasCancelKeyword || (hasCancelRoute && getAction(event) === "CLICK" && !text.includes("confirm"));
}

function isRetentionEvent(event, inCancellationFlow = false) {
	if (isDeclineEvent(event) || isCompletionEvent(event)) {
		return false;
	}

	const text = getText(event);
	const route = getRoute(event).toLowerCase();

	if (!text && !route) return false;

	// Exclude compliance / privacy "data retention"
	if (route.includes("data-retention") || text.includes("data retention") || text.includes("retention info") || text.includes("retention policy")) {
		return false;
	}

	const hasRetentionKeyword = analyzerRules?.keywords?.retention
		? containsKeyword(text, analyzerRules.keywords.retention)
		: ["discount", "offer", "save", "stay", "keep", "pause", "deal"].some(k => text.includes(k));

	const hasRetentionRoute = ["offer", "retention", "save-offer", "discount"].some(k => route.includes(k));

	if (inCancellationFlow) {
		const hasAltKeyword = [
			"switch to basic",
			"switch to",
			"downgrade",
			"pause instead",
			"change plan instead",
			"keep subscription",
			"stay with us",
			"free month",
			"free extension"
		].some(k => text.includes(k));

		return hasRetentionKeyword || hasAltKeyword || (hasRetentionRoute && text.length > 0 && !text.includes("confirm"));
	}

	return hasRetentionRoute || (hasRetentionKeyword && (route.includes("account") || route.includes("subscription")));
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

function isConfirmationPrompt(event, inCancellationFlow) {
	if (!inCancellationFlow || isCompletionEvent(event)) return false;
	const text = getText(event);
	const route = getRoute(event).toLowerCase();

	const hasConfirmKeyword = [
		"are you sure",
		"really want to cancel",
		"lose all benefits",
		"final warning",
		"warning: data loss"
	].some(k => text.includes(k));

	const isConfirmRoute = route.includes("confirm") || route.includes("review");

	return hasConfirmKeyword || (isConfirmRoute && text.includes("confirm"));
}

/**
 * Extracts distinct route sequence given an array of event indices.
 */
function getRouteSequence(events, indices) {
	const routes = [];
	indices.forEach(idx => {
		if (events[idx]) {
			const r = getRoute(events[idx]);
			if (routes.length === 0 || routes[routes.length - 1] !== r) {
				routes.push(r);
			}
		}
	});
	return routes;
}

/**
 * Analyzes event sequences and B2 features to produce deterministic behavior signals.
 *
 * @param {Array<Object>} events - Ordered array of B1 event objects.
 * @param {Object} [behaviorFeatures] - Pre-extracted B2 features (optional).
 * @returns {{ behavior_signals: Array<Object>, evidence: Array<Object> }}
 */
function analyzeBehaviorSequence(events = [], behaviorFeatures = null) {
	const safeEvents = Array.isArray(events) ? events : [];

	if (safeEvents.length === 0) {
		return {
			behavior_signals: [],
			evidence: []
		};
	}

	// Resolve B2 features if missing or wrapped
	let features = behaviorFeatures?.behavior_features || behaviorFeatures;
	if (!features && b2Module?.extractBehaviorFeatures) {
		const extracted = b2Module.extractBehaviorFeatures(safeEvents);
		features = extracted.behavior_features;
	}

	const signals = [];

	// Track cancellation lifecycle across ordered events
	let cancellationStartIndex = -1;
	const cancelIndices = [];
	let cancellationCompleted = false;
	let completionIndex = -1;

	safeEvents.forEach((ev, idx) => {
		if (isCancellationIntent(ev)) {
			if (cancellationStartIndex === -1) {
				cancellationStartIndex = idx;
			}
			cancelIndices.push(idx);
		}
		if (isCompletionEvent(ev)) {
			cancellationCompleted = true;
			if (completionIndex === -1) {
				completionIndex = idx;
			}
		}
	});

	const inCancellation = cancellationStartIndex !== -1;

	// Build compressed route timeline for sequence transitions
	const compressedRoutes = [];
	const compressedRouteIndices = [];
	safeEvents.forEach((ev, idx) => {
		const screen = getScreenPath(getRoute(ev));
		if (compressedRoutes.length === 0 || compressedRoutes[compressedRoutes.length - 1] !== screen) {
			compressedRoutes.push(screen);
			compressedRouteIndices.push(idx);
		}
	});

	// Check if survey was optional via explicit skip button or optional label
	const hasOptionalSurveyIndicator = safeEvents.slice(Math.max(0, cancellationStartIndex)).some(ev => {
		const t = getText(ev);
		return t === "skip" || t.includes("skip survey") || t.includes("optional") || ev.metadata?.required === false;
	});

	// ==========================================
	// PATTERN A: Repeated Retention Interference
	// ==========================================
	// Sequence: CANCEL -> RETENTION OFFER -> DECLINE -> RETENTION OFFER -> DECLINE
	if (inCancellation) {
		const retentionOfferIndices = [];
		const declineIndices = [];

		for (let i = cancellationStartIndex; i < safeEvents.length; i++) {
			const ev = safeEvents[i];
			if (isRetentionEvent(ev, true)) {
				retentionOfferIndices.push(i);
			} else if (isDeclineEvent(ev) && retentionOfferIndices.length > 0) {
				declineIndices.push(i);
			}
		}

		// Distinct retention screens / unique offers
		const distinctOfferScreens = new Set(
			retentionOfferIndices.map(idx => getScreenPath(getRoute(safeEvents[idx])))
		);
		const distinctOfferTexts = new Set(
			retentionOfferIndices.map(idx => getText(safeEvents[idx]))
		);
		const effectiveOfferCount = Math.max(distinctOfferScreens.size, distinctOfferTexts.size);

		// Trigger only if 2 or more retention offers occurred after cancellation intent
		if (effectiveOfferCount >= 2 && retentionOfferIndices.length >= 2) {
			const strength = effectiveOfferCount >= 3 ? "strong" : "moderate";
			const allIndices = [cancellationStartIndex, ...retentionOfferIndices, ...declineIndices]
				.filter((v, i, a) => a.indexOf(v) === i)
				.sort((a, b) => a - b);

			signals.push({
				type: "repeated_retention_interference",
				detected: true,
				strength,
				reason: `${effectiveOfferCount} retention offers appeared after cancellation was initiated and were declined or bypassed.`,
				event_indices: allIndices,
				route_sequence: getRouteSequence(safeEvents, allIndices)
			});
		}
	}

	// ==========================================
	// PATTERN C: Required Survey During Cancellation
	// ==========================================
	// Sequence: CANCEL -> SURVEY -> SUBMIT/CONTINUE -> CANCELLATION
	if (inCancellation) {
		const surveyIndices = [];
		let surveyRequired = false;
		let submitIndex = -1;

		for (let i = cancellationStartIndex; i < safeEvents.length; i++) {
			const ev = safeEvents[i];
			if (isSurveyEvent(ev)) {
				surveyIndices.push(i);
				if (ev.element?.required === true || ev.metadata?.required === true || ev.required === true) {
					surveyRequired = true;
				}
				const text = getText(ev);
				if (text.includes("required") || text.includes("must select") || text.includes("mandatory")) {
					surveyRequired = true;
				}
			} else if (surveyIndices.length > 0 && (getAction(ev) === "CLICK" || getAction(ev) === "INPUT_CHANGE")) {
				const text = getText(ev);
				if (text.includes("submit") || text.includes("next") || text.includes("continue") || text.includes("save response")) {
					if (submitIndex === -1) submitIndex = i;
				}
			}
		}

		if (features?.survey_required === true && !hasOptionalSurveyIndicator) {
			surveyRequired = true;
		}

		if (surveyRequired && !hasOptionalSurveyIndicator && surveyIndices.length > 0) {
			const allIndices = [cancellationStartIndex, ...surveyIndices];
			if (submitIndex !== -1) allIndices.push(submitIndex);
			const uniqueIndices = allIndices.filter((v, i, a) => a.indexOf(v) === i).sort((a, b) => a - b);

			signals.push({
				type: "required_survey",
				detected: true,
				strength: "moderate",
				reason: "A survey was required to progress through the cancellation flow.",
				event_indices: uniqueIndices,
				route_sequence: getRouteSequence(safeEvents, uniqueIndices)
			});
		}
	}

	// ==========================================
	// PATTERN D: Repeated Confirmation Pressure
	// ==========================================
	// Sequence: CANCEL -> CONFIRMATION 1 -> DECLINE/CONTINUE -> CONFIRMATION 2 -> ...
	// Hard negative: exactly 1 normal confirmation screen must NOT trigger.
	if (inCancellation) {
		const promptIndices = [];
		const distinctPromptScreens = new Set();
		const distinctPromptTexts = new Set();

		for (let i = cancellationStartIndex; i < safeEvents.length; i++) {
			const ev = safeEvents[i];
			if (isConfirmationPrompt(ev, true)) {
				promptIndices.push(i);
				distinctPromptScreens.add(getScreenPath(getRoute(ev)));
				const t = getText(ev);
				if (t) distinctPromptTexts.add(t);
			}
		}

		// Distinct confirmation dialogs/screens across the cancellation flow
		// Multiple clicks on the same screen (e.g. view screen + click confirm) do NOT count as repeated confirmations
		const effectiveConfirmationCount = Math.max(distinctPromptScreens.size, distinctPromptTexts.size);

		if (effectiveConfirmationCount >= 2 && promptIndices.length >= 2) {
			const strength = effectiveConfirmationCount >= 3 ? "strong" : "moderate";
			const uniqueIndices = [cancellationStartIndex, ...promptIndices]
				.filter((v, i, a) => a.indexOf(v) === i)
				.sort((a, b) => a - b);

			signals.push({
				type: "repeated_confirmation_pressure",
				detected: true,
				strength,
				reason: `${effectiveConfirmationCount} confirmation screens were presented during the cancellation flow.`,
				event_indices: uniqueIndices,
				route_sequence: getRouteSequence(safeEvents, uniqueIndices)
			});
		}
	}

	// ==========================================
	// PATTERN E: Backtracking / Loop Behavior
	// ==========================================
	// Sequence: A -> B -> C -> B (meaningful backtrack) or A -> B -> A -> B -> A (oscillation)
	// Hard negative: clicks on same page A -> A -> A do NOT count.
	const visitedRoutes = [];
	const backtrackedIndices = [];
	let routeOscillationCount = 0;

	for (let i = 0; i < compressedRoutes.length; i++) {
		const route = compressedRoutes[i];
		const firstIdx = visitedRoutes.indexOf(route);
		if (firstIdx !== -1 && firstIdx < visitedRoutes.length - 1) {
			// Backtrack to an earlier route
			backtrackedIndices.push(compressedRouteIndices[i]);

			// Check for 2-step oscillation: A -> B -> A -> B
			if (i >= 3 && compressedRoutes[i] === compressedRoutes[i - 2] && compressedRoutes[i - 1] === compressedRoutes[i - 3]) {
				routeOscillationCount++;
			}
		}
		visitedRoutes.push(route);
	}

	if (routeOscillationCount >= 1 || backtrackedIndices.length >= 1) {
		const isStrongOscillation = routeOscillationCount >= 1 || backtrackedIndices.length >= 3;
		const isModerate = backtrackedIndices.length >= 2;
		const strength = isStrongOscillation ? "strong" : (isModerate ? "moderate" : "weak");

		const allIndices = backtrackedIndices.slice();
		const routeSeq = compressedRoutes;

		signals.push({
			type: "backtracking_loop",
			detected: true,
			strength,
			reason: isStrongOscillation
				? "Navigation repeatedly oscillated between routes in a loop."
				: "Navigation sequence returned to a previously visited route after visiting intervening screens.",
			event_indices: allIndices,
			route_sequence: routeSeq
		});
	}

	// ==========================================
	// PATTERN F: Dead-End Behavior
	// ==========================================
	// Conservative:
	// 1. Loop oscillation where user cannot advance: A -> B -> A -> B -> A
	// 2. Disabled/blocked progression with repeated attempts and no exit route
	let deadEndDetected = false;
	let deadEndStrength = "moderate";
	const deadEndIndices = [];
	let deadEndReason = "";

	// Check disabled/blocked progression attempts
	let consecutiveDisabledClicks = 0;
	const disabledClickIndices = [];
	safeEvents.forEach((ev, idx) => {
		const isDisabled = ev.element?.disabled === true || ev.metadata?.disabled === true || ev.disabled === true;
		if (getAction(ev) === "CLICK" && isDisabled) {
			consecutiveDisabledClicks++;
			disabledClickIndices.push(idx);
		} else if (getAction(ev) === "NAVIGATION") {
			consecutiveDisabledClicks = 0;
		}
	});

	if (consecutiveDisabledClicks >= 2) {
		deadEndDetected = true;
		deadEndStrength = "strong";
		deadEndReason = "User encountered blocked/disabled progression with repeated attempts and no forward navigation.";
		deadEndIndices.push(...disabledClickIndices);
	} else if (routeOscillationCount >= 2) {
		deadEndDetected = true;
		deadEndStrength = "moderate";
		deadEndReason = "Navigation loop repeatedly returned the user to previous states without progression.";
		deadEndIndices.push(...backtrackedIndices);
	} else if (features?.dead_end_count > 0) {
		deadEndDetected = true;
		deadEndStrength = "moderate";
		deadEndReason = "Observable navigation dead-end pattern detected.";
		deadEndIndices.push(...compressedRouteIndices.slice(-3));
	}

	if (deadEndDetected) {
		const uniqueIndices = deadEndIndices.filter((v, i, a) => a.indexOf(v) === i).sort((a, b) => a - b);
		signals.push({
			type: "dead_end_behavior",
			detected: true,
			strength: deadEndStrength,
			reason: deadEndReason,
			event_indices: uniqueIndices,
			route_sequence: getRouteSequence(safeEvents, uniqueIndices)
		});
	}

	// ==========================================
	// PATTERN G: Forced-Action Sequence
	// ==========================================
	// Sequence: CANCEL -> mandatory action -> action completion -> cancellation can continue
	// Hard negative: ordinary optional form with skip does not trigger.
	if (inCancellation) {
		const forcedIndices = [];
		const forcedTypes = new Set();

		safeEvents.forEach((ev, idx) => {
			if (idx < cancellationStartIndex) return;
			const isReq = ev.element?.required === true || ev.metadata?.required === true || ev.required === true;
			const text = getText(ev);
			const isMandatoryText = text.includes("mandatory") || text.includes("required to proceed") || text.includes("must select");

			if (isReq || isMandatoryText) {
				forcedIndices.push(idx);
				if (isSurveyEvent(ev)) forcedTypes.add("mandatory survey");
				else if (text.includes("feedback")) forcedTypes.add("mandatory feedback");
				else if (text.includes("reason")) forcedTypes.add("mandatory reason");
				else forcedTypes.add("mandatory requirement");
			}
		});

		if (features?.forced_action_count > 0 && !hasOptionalSurveyIndicator) {
			features.forced_action_types?.forEach(t => {
				if (t === "REQUIRED_SURVEY" && hasOptionalSurveyIndicator) return;
				forcedTypes.add(t);
			});
		}

		if (forcedTypes.size > 0 || forcedIndices.length > 0) {
			const typeList = [...forcedTypes];
			const strength = typeList.length >= 2 || forcedIndices.length >= 2 ? "strong" : "moderate";
			const allIndices = [cancellationStartIndex, ...forcedIndices]
				.filter((v, i, a) => a.indexOf(v) === i)
				.sort((a, b) => a - b);

			signals.push({
				type: "forced_action_sequence",
				detected: true,
				strength,
				reason: `A mandatory action (${typeList.join(", ") || "required action"}) gated cancellation progression.`,
				event_indices: allIndices,
				route_sequence: getRouteSequence(safeEvents, allIndices)
			});
		}
	}

	// ==========================================
	// PATTERN B: Cancellation Obstruction
	// ==========================================
	// Multi-signal combination during cancellation flow.
	// Combines retention interference, forced actions / required survey, repeated confirmations, and backtracking loops.
	// Hard negative: legitimate 5-step cancellation flow must NOT trigger obstruction.
	if (inCancellation) {
		const obstructionSources = [];
		const obstructionIndices = [cancellationStartIndex];

		const retentionSignal = signals.find(s => s.type === "repeated_retention_interference");
		if (retentionSignal) {
			obstructionSources.push("retention interference");
			obstructionIndices.push(...retentionSignal.event_indices);
		} else if (features?.retention_offer_count >= 2) {
			obstructionSources.push("multiple retention offers");
		}

		const surveySignal = signals.find(s => s.type === "required_survey");
		const forcedSignal = signals.find(s => s.type === "forced_action_sequence");
		if (surveySignal) {
			obstructionSources.push("required survey gating");
			obstructionIndices.push(...surveySignal.event_indices);
		} else if (forcedSignal) {
			obstructionSources.push("forced action gating");
			obstructionIndices.push(...forcedSignal.event_indices);
		}

		const confirmSignal = signals.find(s => s.type === "repeated_confirmation_pressure");
		if (confirmSignal) {
			obstructionSources.push("repeated confirmation pressure");
			obstructionIndices.push(...confirmSignal.event_indices);
		}

		const backtrackSignal = signals.find(s => s.type === "backtracking_loop" && s.strength !== "weak");
		const deadEndSignal = signals.find(s => s.type === "dead_end_behavior");
		if (deadEndSignal) {
			obstructionSources.push("dead end navigation");
			obstructionIndices.push(...deadEndSignal.event_indices);
		} else if (backtrackSignal) {
			obstructionSources.push("navigation backtracking");
			obstructionIndices.push(...backtrackSignal.event_indices);
		}

		// Require at least 2 distinct friction types to trigger cancellation obstruction
		if (obstructionSources.length >= 2) {
			const strength = obstructionSources.length >= 3 ? "strong" : "moderate";
			const uniqueIndices = obstructionIndices
				.filter((v, i, a) => a.indexOf(v) === i)
				.sort((a, b) => a - b);

			signals.push({
				type: "cancellation_obstruction",
				detected: true,
				strength,
				reason: `Cancellation flow combined multiple obstruction signals: ${obstructionSources.join(", ")}.`,
				event_indices: uniqueIndices,
				route_sequence: getRouteSequence(safeEvents, uniqueIndices)
			});
		}
	}

	// ==========================================
	// PATTERN H: Cancellation Abandonment Context
	// ==========================================
	// Sequence: CANCEL STARTED -> friction/retention interaction -> user leaves cancellation flow -> cancellation NOT confirmed.
	// Observable fact only: do NOT claim the website caused abandonment.
	if (inCancellation && !cancellationCompleted) {
		const frictionSignals = signals.filter(s => s.type !== "backtracking_loop" || s.strength !== "weak");
		const hasFriction = frictionSignals.length > 0
			|| (features?.retention_offer_count > 0)
			|| (features?.repeated_confirmation_count > 0)
			|| (features?.forced_action_count > 0);

		// Check if user exited cancellation flow to other routes or stopped before completion
		const lastRoute = getRoute(safeEvents[safeEvents.length - 1]).toLowerCase();
		const isCancelRoute = lastRoute.includes("cancel");
		const nonCancelRoutes = ["/home", "/dashboard", "/shop", "/products", "/account", "/overview", "/browse"];
		const exitedToNonCancel = nonCancelRoutes.some(r => lastRoute.includes(r)) || (!isCancelRoute && safeEvents.length - 1 > cancellationStartIndex);

		if (hasFriction && (exitedToNonCancel || !cancellationCompleted)) {
			const exitIndex = safeEvents.length - 1;
			const frictionIndices = frictionSignals.flatMap(s => s.event_indices);
			const allIndices = [cancellationStartIndex, ...frictionIndices, exitIndex]
				.filter((v, i, a) => a.indexOf(v) === i)
				.sort((a, b) => a - b);

			const strength = frictionSignals.length >= 2 ? "strong" : "moderate";

			signals.push({
				type: "cancellation_abandonment",
				detected: true,
				strength,
				reason: "Cancellation was initiated and friction was encountered, but the session exited the cancellation flow without confirmation.",
				event_indices: allIndices,
				route_sequence: getRouteSequence(safeEvents, allIndices)
			});
		}
	}

	// Format traceable evidence list
	const evidence = signals.map(sig => ({
		signal_type: sig.type,
		strength: sig.strength,
		description: sig.reason,
		event_indices: sig.event_indices,
		route_sequence: sig.route_sequence
	}));

	return {
		behavior_signals: signals,
		evidence
	};
}

if (typeof module !== "undefined" && module.exports) {
	module.exports = {
		analyzeBehaviorSequence
	};
}

root.analyzeBehaviorSequence = analyzeBehaviorSequence;
})(globalThis);
