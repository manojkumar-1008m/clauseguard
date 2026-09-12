/**
 * DarkShield Phase B4.4 — Cross-Container Semantic Action Pairing Engine
 *
 * Identifies and evaluates semantically competing decision actions that reside
 * in different DOM containers within the same decision context.
 *
 * Core Concept:
 * DOM CANDIDATE ACTIONS -> SEMANTIC NORMALIZATION -> DECISION CONTEXT -> CROSS-CONTAINER PAIRING -> VISUAL/STATE COMPARISON -> DOM EVIDENCE
 *
 * Observational Evidence Only:
 * - Does NOT calculate final risk scores or manipulation probabilities.
 * - Does NOT declare legal violations or confirmed dark patterns.
 * - Produces objective observable facts and traceable evidence records.
 */

(function (root) {
	"use strict";

// =========================================================
// SELF-CONTAINED VISUAL PROMINENCE & CONTRAST HELPERS
// =========================================================

function parseRgbColor(colorStr) {
	if (!colorStr || typeof colorStr !== "string") return null;
	const str = colorStr.trim().toLowerCase();
	if (str === "transparent" || str.includes("var(") || str.includes("gradient")) return null;

	const rgbaMatch = str.match(/rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)(?:\s*,\s*([\d.]+))?\s*\)/);
	if (rgbaMatch) {
		const r = parseFloat(rgbaMatch[1]);
		const g = parseFloat(rgbaMatch[2]);
		const b = parseFloat(rgbaMatch[3]);
		const a = rgbaMatch[4] !== undefined ? parseFloat(rgbaMatch[4]) : 1.0;
		if (a < 0.1) return null;
		return { r, g, b, a };
	}

	const hexMatch = str.match(/^#([0-9a-f]{3,8})$/i);
	if (hexMatch) {
		const hex = hexMatch[1];
		if (hex.length === 3) {
			return {
				r: parseInt(hex[0] + hex[0], 16),
				g: parseInt(hex[1] + hex[1], 16),
				b: parseInt(hex[2] + hex[2], 16),
				a: 1.0
			};
		}
		if (hex.length === 6) {
			return {
				r: parseInt(hex.slice(0, 2), 16),
				g: parseInt(hex.slice(2, 4), 16),
				b: parseInt(hex.slice(4, 6), 16),
				a: 1.0
			};
		}
	}
	return null;
}

function getRelativeLuminance(rgb) {
	if (!rgb) return null;
	const sRGB = [rgb.r / 255, rgb.g / 255, rgb.b / 255];
	const [r, g, b] = sRGB.map(val => (val <= 0.03928 ? val / 12.92 : Math.pow((val + 0.055) / 1.055, 2.4)));
	return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function calculateContrastRatio(colorStr, bgStr) {
	const cRgb = parseRgbColor(colorStr);
	const bgRgb = parseRgbColor(bgStr);
	if (!cRgb || !bgRgb) return null;

	const l1 = getRelativeLuminance(cRgb);
	const l2 = getRelativeLuminance(bgRgb);
	if (l1 === null || l2 === null) return null;

	const lighter = Math.max(l1, l2);
	const darker = Math.min(l1, l2);
	return Number(((lighter + 0.05) / (darker + 0.05)).toFixed(2));
}

function computeProminenceMetrics(metricsA, metricsB) {
	const areaA = metricsA?.area || 0;
	const areaB = metricsB?.area || 0;
	const area_ratio = (areaA > 0 && areaB > 0) ? Number((areaA / areaB).toFixed(2)) : null;

	const fsA = metricsA?.font_size_px;
	const fsB = metricsB?.font_size_px;
	const font_size_ratio = (typeof fsA === "number" && typeof fsB === "number" && fsB > 0) ? Number((fsA / fsB).toFixed(2)) : null;

	const fwA = metricsA?.font_weight || 400;
	const fwB = metricsB?.font_weight || 400;
	const font_weight_difference = Math.abs(fwA - fwB);

	const opA = typeof metricsA?.opacity === "number" ? metricsA.opacity : 1.0;
	const opB = typeof metricsB?.opacity === "number" ? metricsB.opacity : 1.0;
	const opacity_difference = Number(Math.abs(opA - opB).toFixed(2));

	const crA = metricsA?.contrast;
	const crB = metricsB?.contrast;
	const contrast_difference = (typeof crA === "number" && typeof crB === "number") ? Number(Math.abs(crA - crB).toFixed(2)) : null;

	return {
		area_ratio,
		font_size_ratio,
		font_weight_difference,
		opacity_difference,
		contrast_difference
	};
}

function getEffectiveOpacity(data) {
	if (data && typeof data.effective_opacity === "number") return data.effective_opacity;
	if (data && typeof data.opacity === "number") return data.opacity;
	return 1.0;
}

// =========================================================
// 1. ACTION NORMALIZATION LEXICONS & CATEGORIES
// =========================================================

const ACTION_CATEGORIES = {
	CANCELLATION: "CANCELLATION",
	RETENTION: "RETENTION",
	ACCEPT: "ACCEPT",
	REJECT: "REJECT",
	ALLOW: "ALLOW",
	DECLINE: "DECLINE",
	SUBSCRIBE: "SUBSCRIBE",
	SKIP: "SKIP",
	UPGRADE: "UPGRADE",
	DOWNGRADE: "DOWNGRADE",
	KEEP: "KEEP",
	REMOVE: "REMOVE",
	DELETE: "DELETE",
	OPT_OUT: "OPT_OUT",
	OPT_IN: "OPT_IN"
};

const EXCLUDED_NON_COMPETING_PAIRS = [
	["continue", "back"],
	["next", "previous"],
	["open", "close"],
	["expand", "collapse"],
	["menu", "close"],
	["help", "faq"]
];

const NON_COMPETING_KEYWORDS = [
	"continue",
	"back",
	"next",
	"previous",
	"open",
	"close",
	"expand",
	"collapse",
	"menu",
	"help",
	"faq",
	"search",
	"explore more",
	"read less"
];

function normalizeText(value) {
	return String(value || "").toLowerCase().replace(/\s+/g, " ").trim();
}

function containsAny(text, keywords) {
	if (!text || !keywords) return false;
	const norm = normalizeText(text);
	return keywords.some(k => norm.includes(k));
}

/**
 * Normalizes an element's text / aria-label / role into a canonical semantic action category.
 *
 * @param {Object|string} element - Element descriptor or raw text string.
 * @param {string} [contextHint] - Optional context hint.
 * @returns {string|null} Canonical category or null if non-competing / unrecognized.
 */
function normalizeAction(element, contextHint = "") {
	if (!element) return null;

	let text = "";
	let aria = "";
	let role = "";
	let tag = "";

	if (typeof element === "string") {
		text = element;
	} else if (typeof element === "object") {
		text = element.visible_text || element.text || "";
		aria = element.aria_label || "";
		role = element.role || "";
		tag = String(element.tag || "").toUpperCase();
	}

	const normText = normalizeText(text);
	const normAria = normalizeText(aria);
	const combined = `${normText} ${normAria}`.trim();
	const normRole = normalizeText(role);
	const context = normalizeText(contextHint);

	if (!combined) return null;

	// Check non-competing exclusions
	if (combined === "back" || combined === "continue" || combined === "next" || combined === "previous" || combined === "close") {
		return null;
	}
	if (combined.startsWith("step ") || combined.includes("page ")) {
		return null;
	}
	// "Save" vs "Cancel" in ordinary non-cancellation settings is non-competing
	if ((combined === "save" || combined === "save settings" || combined === "save changes") && context !== "cancellation" && context !== "subscription") {
		return null;
	}

	// 1. CANCELLATION
	if (
		containsAny(combined, [
			"cancel subscription",
			"cancel my subscription",
			"cancel plan",
			"cancel my plan",
			"cancel membership",
			"end membership",
			"stop renewal",
			"cancel account",
			"proceed with cancellation",
			"continue with cancellation",
			"confirm cancellation",
			"cancel service",
			"cancel benefits",
			"end subscription",
			"terminate membership",
			"cancel order"
		]) || ((combined === "cancel" || combined.includes("cancel")) && (context === "cancellation" || context === "subscription" || context === "membership" || combined.includes("membership") || combined.includes("plan")))
	) {
		return ACTION_CATEGORIES.CANCELLATION;
	}

	// 2. RETENTION
	if (
		containsAny(combined, [
			"keep my subscription",
			"stay subscribed",
			"keep benefits",
			"continue membership",
			"keep plan",
			"stay member",
			"keep my plan",
			"stay on plan",
			"remain subscribed",
			"pause subscription",
			"keep subscription",
			"keep my membership",
			"stay with us",
			"keep service",
			"keep account",
			"stay on current tier"
		])
	) {
		return ACTION_CATEGORIES.RETENTION;
	}

	// 3. DELETE (Account / Data)
	if (
		containsAny(combined, [
			"delete account",
			"delete my account",
			"delete profile",
			"permanently delete",
			"delete my data"
		])
	) {
		return ACTION_CATEGORIES.DELETE;
	}

	// 4. ACCEPT / ALLOW
	if (
		containsAny(combined, [
			"accept all",
			"accept cookies",
			"accept all tracking",
			"accept and continue",
			"i agree",
			"agree and continue"
		]) || combined === "accept" || combined === "agree"
	) {
		return ACTION_CATEGORIES.ACCEPT;
	}
	if (
		containsAny(combined, [
			"allow all",
			"allow tracking",
			"allow selection",
			"enable all"
		]) || combined === "allow"
	) {
		return ACTION_CATEGORIES.ALLOW;
	}

	// 5. REJECT / DECLINE
	if (
		containsAny(combined, [
			"reject all",
			"reject non-essential",
			"reject cookies",
			"reject tracking"
		]) || combined === "reject"
	) {
		return ACTION_CATEGORIES.REJECT;
	}
	if (
		containsAny(combined, [
			"don't allow",
			"do not allow",
			"decline all",
			"decline coverage",
			"decline offer",
			"decline protection"
		]) || combined === "decline"
	) {
		return ACTION_CATEGORIES.DECLINE;
	}

	// 6. SUBSCRIBE
	if (
		containsAny(combined, [
			"subscribe now",
			"subscribe to newsletter",
			"subscribe"
		]) || (combined === "sign up" && context.includes("subscri"))
	) {
		return ACTION_CATEGORIES.SUBSCRIBE;
	}

	// 7. SKIP
	if (
		containsAny(combined, [
			"skip this step",
			"skip offer",
			"skip for now",
			"no thanks",
			"maybe later",
			"not now"
		]) || combined === "skip"
	) {
		return ACTION_CATEGORIES.SKIP;
	}

	// 8. UPGRADE / DOWNGRADE
	if (
		containsAny(combined, [
			"upgrade plan",
			"upgrade to pro",
			"upgrade now",
			"get premium",
			"upgrade to premium"
		]) || (combined === "upgrade" && (context === "subscription" || context === "billing"))
	) {
		return ACTION_CATEGORIES.UPGRADE;
	}
	if (
		containsAny(combined, [
			"downgrade plan",
			"downgrade to free",
			"stay basic",
			"stay on basic"
		]) || (combined === "downgrade" && (context === "subscription" || context === "billing"))
	) {
		return ACTION_CATEGORIES.DOWNGRADE;
	}

	// 9. OPT_IN / OPT_OUT
	if (combined.includes("opt in") || combined.includes("opt-in") || combined.includes("enable sharing")) {
		return ACTION_CATEGORIES.OPT_IN;
	}
	if (combined.includes("opt out") || combined.includes("opt-out") || combined.includes("disable sharing")) {
		return ACTION_CATEGORIES.OPT_OUT;
	}

	// 10. KEEP / REMOVE
	if (containsAny(combined, ["keep item", "keep file", "keep selection", "keep changes"])) {
		return ACTION_CATEGORIES.KEEP;
	}
	if (containsAny(combined, ["remove item", "remove file", "remove from cart"])) {
		return ACTION_CATEGORIES.REMOVE;
	}

	return null;
}

// =========================================================
// 2. SEMANTIC COMPETING RELATIONSHIPS
// =========================================================

const VALID_COMPETING_PAIRS = new Set([
	// Retention ↔ Cancellation
	"CANCELLATION::RETENTION",
	"RETENTION::CANCELLATION",

	// Retention ↔ Delete
	"DELETE::RETENTION",
	"RETENTION::DELETE",
	"CANCELLATION::KEEP",
	"KEEP::CANCELLATION",
	"DELETE::KEEP",
	"KEEP::DELETE",

	// Accept ↔ Reject
	"ACCEPT::REJECT",
	"REJECT::ACCEPT",

	// Allow ↔ Decline
	"ALLOW::DECLINE",
	"DECLINE::ALLOW",
	"ACCEPT::DECLINE",
	"DECLINE::ACCEPT",
	"ALLOW::REJECT",
	"REJECT::ALLOW",

	// Subscribe ↔ Skip / Decline
	"SUBSCRIBE::SKIP",
	"SKIP::SUBSCRIBE",
	"SUBSCRIBE::DECLINE",
	"DECLINE::SUBSCRIBE",
	"SUBSCRIBE::REJECT",
	"REJECT::SUBSCRIBE",

	// Upgrade ↔ Downgrade
	"UPGRADE::DOWNGRADE",
	"DOWNGRADE::UPGRADE",

	// Opt_In ↔ Opt_Out
	"OPT_IN::OPT_OUT",
	"OPT_OUT::OPT_IN",

	// Keep ↔ Remove
	"KEEP::REMOVE",
	"REMOVE::KEEP"
]);

/**
 * Checks if two normalized action categories form a valid competing decision relationship.
 */
function isCompetingAction(catA, catB) {
	if (!catA || !catB || catA === catB) return false;
	const pairKey = `${catA}::${catB}`;
	return VALID_COMPETING_PAIRS.has(pairKey);
}

// =========================================================
// 3. DECISION CONTEXT RESOLUTION & SHARING
// =========================================================

const VALID_DECISION_CONTEXTS = [
	"cancellation",
	"subscription",
	"checkout",
	"billing",
	"consent",
	"purchase",
	"account_deletion",
	"membership",
	"renewal"
];

/**
 * Resolves the decision context for an element from route, container, and text.
 */
function getDecisionContext(element, route = "", containerType = "") {
	const r = normalizeText(route || element?.route || "");
	const t = normalizeText(element?.visible_text || element?.text || element?.aria_label || "");
	const c = normalizeText(containerType || element?.container_type || element?.container || "");

	if (r.includes("cancel") || t.includes("cancel") || r.includes("unsubscribe") || t.includes("unsubscribe") || c.includes("cancel")) {
		return "cancellation";
	}
	if (r.includes("delete") || t.includes("delete account") || c.includes("delete")) {
		return "account_deletion";
	}
	if (r.includes("cookie") || r.includes("consent") || t.includes("cookie") || t.includes("consent") || c.includes("consent") || c.includes("cookie")) {
		return "consent";
	}
	if (r.includes("checkout") || r.includes("cart") || r.includes("order") || t.includes("protection") || t.includes("checkout") || c.includes("checkout")) {
		return "checkout";
	}
	if (r.includes("subscri") || r.includes("membership") || r.includes("renewal") || t.includes("subscri") || t.includes("membership") || t.includes("renewal")) {
		return "subscription";
	}
	if (r.includes("billing") || r.includes("plan") || t.includes("plan") || t.includes("billing") || c.includes("billing")) {
		return "billing";
	}
	if (c === "dialog" || c === "modal") {
		return "dialog";
	}

	return null;
}

/**
 * Determines whether two contexts are compatible or belong to the same decision flow.
 */
function isSharedDecisionContext(ctxA, ctxB) {
	if (!ctxA || !ctxB) return false;
	if (ctxA === ctxB) return true;

	// Cross-compatible context clusters
	const isCancelCluster = (ctx) => ctx === "cancellation" || ctx === "subscription" || ctx === "membership" || ctx === "renewal" || ctx === "account_deletion";
	if (isCancelCluster(ctxA) && isCancelCluster(ctxB)) return true;

	const isCommerceCluster = (ctx) => ctx === "checkout" || ctx === "billing" || ctx === "purchase";
	if (isCommerceCluster(ctxA) && isCommerceCluster(ctxB)) return true;

	// Dialogs inherit caller context
	if (ctxA === "dialog" || ctxB === "dialog") return true;

	return false;
}

// =========================================================
// 4. CONTEXT LOCALITY & VIEWPORT PROXIMITY
// =========================================================

/**
 * Checks whether two elements satisfy locality and viewport proximity.
 */
function isWithinLocalityAndProximity(elA, elB) {
	if (!elA || !elB) return false;

	const cA = normalizeText(elA.container_type || elA.container || "page");
	const cB = normalizeText(elB.container_type || elB.container || "page");

	// Locality Level 1: Same dialog or modal container
	if ((cA === "modal" || cA === "dialog") && (cB === "modal" || cB === "dialog")) {
		return true;
	}

	// Locality Level 2: Same form or section
	if (cA === cB && cA !== "page" && cA !== "none") {
		return true;
	}

	// Locality Level 3: Viewport Proximity check via bounding geometry
	const gA = elA.geometry || {};
	const gB = elB.geometry || {};

	// If coordinates exist, check vertical delta
	if (typeof gA.y === "number" && typeof gB.y === "number") {
		const deltaY = Math.abs(gA.y - gB.y);
		// If vertical distance exceeds 900px, they are in distant unrelated page sections
		if (deltaY > 900) return false;
	}

	// Locality Level 4: Actions within the same route / view
	return true;
}

// =========================================================
// 5. CROSS-CONTAINER PAIR MATCHING
// =========================================================

/**
 * Finds valid semantic competing action pairs across DOM containers.
 *
 * @param {Array<Object>} candidates - List of candidate elements (up to 25).
 * @param {Object} [options] - Options including route and container hints.
 * @returns {Array<Object>} List of matched canonical pairs.
 */
function findSemanticPairs(candidates = [], options = {}) {
	const safeCandidates = Array.isArray(candidates) ? candidates.slice(0, 25) : [];
	const route = options.route || "/";
	const pairs = [];
	const seenPairKeys = new Set();
	const maxPairs = options.maxPairs || 20;

	// Extract normalized actions for candidates
	const actions = safeCandidates.map((el, idx) => {
		const ctx = el.decision_context || getDecisionContext(el, route, el.container_type || el.container);
		const category = normalizeAction(el, ctx);
		const ref = el.element_ref || `${el.tag || "ELEMENT"}::role(${el.role || "none"})::ord(${idx + 1})`;
		return {
			element: el,
			ref,
			category,
			context: ctx,
			container: el.container_type || el.container || "page"
		};
	}).filter(item => Boolean(item.category));

	// Pairwise evaluation with locality and context gating
	for (let i = 0; i < actions.length && pairs.length < maxPairs; i++) {
		const a = actions[i];

		for (let j = i + 1; j < actions.length && pairs.length < maxPairs; j++) {
			const b = actions[j];

			// 1. Same element or identical ref cannot pair with itself
			if (a.ref === b.ref) continue;

			// 2. Competing Category Check
			if (!isCompetingAction(a.category, b.category)) continue;

			// 3. Shared Decision Context Gate
			if (!isSharedDecisionContext(a.context, b.context)) continue;

			// 4. Locality & Viewport Proximity Gate
			if (!isWithinLocalityAndProximity(a.element, b.element)) continue;

			// 5. Canonicalize pair key using sorted references to prevent A<->B and B<->A duplicates
			const pairKey = [a.ref, b.ref].sort().join("::competing::");
			if (seenPairKeys.has(pairKey)) continue;
			seenPairKeys.add(pairKey);

			pairs.push({
				action_a: a,
				action_b: b,
				context: a.context || b.context || "decision",
				pair_key: pairKey
			});
		}
	}

	return pairs;
}

// =========================================================
// 6. ACTION ROLE DETERMINATION & VISUAL COMPARISON
// =========================================================

/**
 * Determines primary and secondary action roles and computes prominence disparity metrics.
 *
 * @param {Object} pair - Matched semantic pair object.
 * @param {Object} [options] - Comparison options.
 * @returns {Object} Comparison result with metrics, primary/secondary elements, and visual flags.
 */
function comparePair(pair, options = {}) {
	const computeProminence = computeProminenceMetrics;
	const calcContrast = calculateContrastRatio;
	const getEffectiveOp = getEffectiveOpacity;

	const elA = pair.action_a.element;
	const elB = pair.action_b.element;

	const areaA = elA.geometry?.area || ((elA.geometry?.width || 0) * (elA.geometry?.height || 0)) || 0;
	const areaB = elB.geometry?.area || ((elB.geometry?.width || 0) * (elB.geometry?.height || 0)) || 0;

	const fsA = typeof elA.font_size_px === "number" ? elA.font_size_px : (elA.fontSize ? parseFloat(elA.fontSize) : null);
	const fsB = typeof elB.font_size_px === "number" ? elB.font_size_px : (elB.fontSize ? parseFloat(elB.fontSize) : null);

	const fwA = typeof elA.font_weight === "number" ? elA.font_weight : 400;
	const fwB = typeof elB.font_weight === "number" ? elB.font_weight : 400;

	const opA = getEffectiveOp(elA);
	const opB = getEffectiveOp(elB);

	const crA = typeof elA.contrast_ratio === "number" ? elA.contrast_ratio : calcContrast(elA.color, elA.background_color);
	const crB = typeof elB.contrast_ratio === "number" ? elB.contrast_ratio : calcContrast(elB.color, elB.background_color);

	const isDisA = Boolean(elA.is_disabled || elA.disabled);
	const isDisB = Boolean(elB.is_disabled || elB.disabled);

	const isVisA = elA.is_visible !== false && elA.visible !== false;
	const isVisB = elB.is_visible !== false && elB.visible !== false;

	const metrics = computeProminence({
		area: areaA,
		font_size_px: fsA,
		font_weight: fwA,
		opacity: opA,
		contrast: crA
	}, {
		area: areaB,
		font_size_px: fsB,
		font_weight: fwB,
		opacity: opB,
		contrast: crB
	});

	// Determine primary vs secondary strictly from observable evidence
	let primary = null;
	let secondary = null;

	// Is A retention/affirmative and B cancellation/decline?
	const aIsAffirm = ["RETENTION", "ACCEPT", "ALLOW", "SUBSCRIBE", "UPGRADE", "OPT_IN", "KEEP"].includes(pair.action_a.category);
	const bIsAffirm = ["RETENTION", "ACCEPT", "ALLOW", "SUBSCRIBE", "UPGRADE", "OPT_IN", "KEEP"].includes(pair.action_b.category);
	const aIsDecline = ["CANCELLATION", "REJECT", "DECLINE", "SKIP", "DOWNGRADE", "OPT_OUT", "REMOVE", "DELETE"].includes(pair.action_a.category);
	const bIsDecline = ["CANCELLATION", "REJECT", "DECLINE", "SKIP", "DOWNGRADE", "OPT_OUT", "REMOVE", "DELETE"].includes(pair.action_b.category);

	// Check if meaningful visual/state distinction exists
	const hasMeaningfulDistinction = Boolean(
		(areaA > 0 && areaB > 0 && (areaA >= areaB * 1.5 || areaB >= areaA * 1.5))
		|| Math.abs(opA - opB) >= 0.20
		|| (typeof crA === "number" && typeof crB === "number" && Math.abs(crA - crB) >= 2.0)
		|| (typeof fsA === "number" && typeof fsB === "number" && (fsA >= fsB * 1.5 || fsB >= fsA * 1.5))
		|| isDisA !== isDisB
		|| isVisA !== isVisB
	);

	if (hasMeaningfulDistinction) {
		if (aIsAffirm && bIsDecline) {
			primary = pair.action_a;
			secondary = pair.action_b;
		} else if (bIsAffirm && aIsDecline) {
			primary = pair.action_b;
			secondary = pair.action_a;
		} else if (areaA >= areaB) {
			primary = pair.action_a;
			secondary = pair.action_b;
		} else {
			primary = pair.action_b;
			secondary = pair.action_a;
		}
	}

	return {
		pair,
		primary,
		secondary,
		metrics,
		values: {
			areaA, areaB,
			fsA, fsB,
			fwA, fwB,
			opA, opB,
			crA, crB,
			isDisA, isDisB,
			isVisA, isVisB
		}
	};
}

// =========================================================
// 7. EVIDENCE GENERATION
// =========================================================

/**
 * Builds observable evidence signals for a compared semantic pair.
 *
 * @param {Object} comparison - Result of comparePair.
 * @param {Object} [options] - Context and provenance options.
 * @returns {Array<Object>} List of DOM evidence signals.
 */
function buildPairEvidence(comparison, options = {}) {
	const signals = [];
	const { pair, primary, secondary, metrics, values } = comparison;
	const route = options.route || pair.action_a.element.route || "/";
	const eventIndices = Array.isArray(options.event_indices) ? options.event_indices : [0];

	const labelA = pair.action_a.element.visible_text || pair.action_a.element.text || pair.action_a.element.aria_label || "";
	const labelB = pair.action_b.element.visible_text || pair.action_b.element.text || pair.action_b.element.aria_label || "";
	const refA = pair.action_a.ref;
	const refB = pair.action_b.ref;

	// 1. Primary semantic evidence signal: SEMANTIC_COMPETING_ACTIONS
	signals.push({
		type: "semantic_competing_actions",
		detected: true,
		strength: "moderate",
		reason: `${pair.action_a.category} and ${pair.action_b.category} presented as competing choices across containers.`,
		element_ref: refA,
		event_indices: eventIndices,
		route,
		dom_properties: {
			action_a: {
				semantic_role: pair.action_a.category,
				text: labelA,
				container: pair.action_a.container,
				element_ref: refA
			},
			action_b: {
				semantic_role: pair.action_b.category,
				text: labelB,
				container: pair.action_b.container,
				element_ref: refB
			},
			primary_element: primary ? primary.ref : null,
			secondary_element: secondary ? secondary.ref : null,
			decision_context: pair.context,
			metrics
		},
		paired_elements: [refA, refB]
	});

	// If primary and secondary are identified, check visual disparities
	if (primary && secondary) {
		const primEl = primary.element;
		const secEl = secondary.element;
		const isSecA = secondary.ref === refA;
		const primArea = isSecA ? values.areaB : values.areaA;
		const secArea = isSecA ? values.areaA : values.areaB;
		const secOp = isSecA ? values.opA : values.opB;
		const primOp = isSecA ? values.opB : values.opA;
		const secCr = isSecA ? values.crA : values.crB;
		const primCr = isSecA ? values.crB : values.crA;
		const secFs = isSecA ? values.fsA : values.fsB;
		const primFs = isSecA ? values.fsB : values.fsA;
		const secFw = isSecA ? values.fwA : values.fwB;
		const primFw = isSecA ? values.fwB : values.fwA;
		const secDis = isSecA ? values.isDisA : values.isDisB;
		const primDis = isSecA ? values.isDisB : values.isDisA;
		const secVis = isSecA ? values.isVisA : values.isVisB;
		const primVis = isSecA ? values.isVisB : values.isVisA;

		// A. ACTION_SIZE_ASYMMETRY
		if (primArea > 0 && secArea > 0) {
			const ratio = Number((primArea / secArea).toFixed(2));
			if (ratio >= 3.0) {
				signals.push({
					type: "action_size_asymmetry",
					detected: true,
					strength: ratio >= 5.0 ? "strong" : "moderate",
					reason: `Cross-container competing choice "${secEl.visible_text || secEl.text}" is significantly smaller (${ratio}x area disparity).`,
					element_ref: secondary.ref,
					event_indices: eventIndices,
					route,
					dom_properties: {
						primary_action: primEl.visible_text || primEl.text,
						secondary_action: secEl.visible_text || secEl.text,
						area_ratio: ratio,
						metrics,
						cross_container: true
					},
					paired_elements: [primary.ref, secondary.ref]
				});
			}
		}

		// B. ACTION_VISUAL_DEEMPHASIS (Low Opacity or Tiny Font)
		if (secOp <= 0.50 && primOp >= 0.80) {
			signals.push({
				type: "action_visual_deemphasis",
				detected: true,
				strength: secOp <= 0.20 ? "strong" : "moderate",
				reason: `Cross-container decline option "${secEl.visible_text || secEl.text}" rendered with reduced opacity (${secOp}).`,
				element_ref: secondary.ref,
				event_indices: eventIndices,
				route,
				dom_properties: {
					secondary_action: secEl.visible_text || secEl.text,
					effective_opacity: secOp,
					primary_opacity: primOp,
					metrics,
					cross_container: true
				},
				paired_elements: [primary.ref, secondary.ref]
			});
		} else if (typeof secFs === "number" && secFs > 0 && secFs <= 8) {
			signals.push({
				type: "action_visual_deemphasis",
				detected: true,
				strength: "strong",
				reason: `Cross-container decline option "${secEl.visible_text || secEl.text}" rendered with tiny font size (${secFs}px).`,
				element_ref: secondary.ref,
				event_indices: eventIndices,
				route,
				dom_properties: {
					secondary_action: secEl.visible_text || secEl.text,
					font_size_px: secFs,
					cross_container: true
				},
				paired_elements: [primary.ref, secondary.ref]
			});
		}

		// C. CONTRAST_ASYMMETRY
		if (typeof primCr === "number" && typeof secCr === "number" && primCr >= 3.5 && (secCr < 3.0 || (primCr - secCr) >= 3.0)) {
			signals.push({
				type: "contrast_asymmetry",
				detected: true,
				strength: (secCr < 2.5 || (primCr - secCr) >= 4.0) ? "strong" : "moderate",
				reason: `Cross-container decline option rendered with lower contrast (${secCr}:1 vs ${primCr}:1).`,
				element_ref: secondary.ref,
				event_indices: eventIndices,
				route,
				dom_properties: {
					secondary_contrast: secCr,
					primary_contrast: primCr,
					contrast_difference: Number(Math.abs(primCr - secCr).toFixed(2)),
					metrics,
					cross_container: true
				},
				paired_elements: [primary.ref, secondary.ref]
			});
		}

		// D. TYPOGRAPHY_ASYMMETRY
		if (typeof primFs === "number" && typeof secFs === "number" && secFs > 0) {
			const fsRatio = Number((primFs / secFs).toFixed(2));
			const fwDiff = Math.abs(primFw - secFw);
			if ((fsRatio >= 1.5 && fwDiff >= 300) || fsRatio >= 2.0) {
				signals.push({
					type: "typography_asymmetry",
					detected: true,
					strength: fsRatio >= 2.0 ? "strong" : "moderate",
					reason: `Cross-container typographic hierarchy disparity observed (${fsRatio}x font size ratio).`,
					element_ref: secondary.ref,
					event_indices: eventIndices,
					route,
					dom_properties: {
						font_size_ratio: fsRatio,
						font_weight_difference: fwDiff,
						metrics,
						cross_container: true
					},
					paired_elements: [primary.ref, secondary.ref]
				});
			}
		}

		// E. DISABLED_ACTION (Decline disabled while retention active)
		if (secDis && !primDis) {
			signals.push({
				type: "disabled_action",
				detected: true,
				strength: "strong",
				reason: `Cross-container decline option "${secEl.visible_text || secEl.text}" is disabled while retention choice is active.`,
				element_ref: secondary.ref,
				event_indices: eventIndices,
				route,
				dom_properties: {
					disabled_text: secEl.visible_text || secEl.text,
					active_text: primEl.visible_text || primEl.text,
					cross_container: true
				},
				paired_elements: [primary.ref, secondary.ref]
			});
		}

		// F. HIDDEN_ALTERNATIVE
		if (!secVis && primVis) {
			signals.push({
				type: "hidden_alternative",
				detected: true,
				strength: "strong",
				reason: `Cross-container decline option "${secEl.visible_text || secEl.text}" exists in DOM but is hidden from visual rendering.`,
				element_ref: secondary.ref,
				event_indices: eventIndices,
				route,
				dom_properties: {
					hidden_text: secEl.visible_text || secEl.text,
					primary_text: primEl.visible_text || primEl.text,
					cross_container: true
				},
				paired_elements: [primary.ref, secondary.ref]
			});
		}
	}

	return signals;
}

// =========================================================
// 8. HIGH-LEVEL ORCHESTRATOR
// =========================================================

/**
 * Analyzes candidate elements across DOM containers, finding competing pairs and generating evidence.
 *
 * @param {Array<Object>} candidates - Array of candidate elements.
 * @param {Object} [options] - Options (route, event_indices, etc.).
 * @returns {{ dom_signals: Array<Object>, evidence: Array<Object>, pairs: Array<Object> }}
 */
function analyzeSemanticPairs(candidates = [], options = {}) {
	const safeCandidates = Array.isArray(candidates) ? candidates : [];
	const pairs = findSemanticPairs(safeCandidates, options);
	const signals = [];

	pairs.forEach(pair => {
		const comparison = comparePair(pair, options);
		const pairSignals = buildPairEvidence(comparison, options);
		pairSignals.forEach(sig => signals.push(sig));
	});

	// Deduplicate signals by type + element_ref + route
	const uniqueSignals = [];
	const seenKeys = new Set();

	signals.forEach(sig => {
		const key = `${sig.type}::${sig.element_ref}::${sig.route}`;
		if (!seenKeys.has(key)) {
			seenKeys.add(key);
			uniqueSignals.push(sig);
		}
	});

	const evidence = uniqueSignals.map(sig => ({
		signal_type: sig.type,
		strength: sig.strength,
		description: sig.reason,
		element_ref: sig.element_ref,
		event_indices: sig.event_indices,
		route: sig.route,
		dom_properties: sig.dom_properties
	}));

	return {
		dom_signals: uniqueSignals,
		evidence,
		pairs
	};
}

// =========================================================
// EXPORTS
// =========================================================

if (typeof module !== "undefined" && module.exports) {
	module.exports = {
		ACTION_CATEGORIES,
		normalizeAction,
		isCompetingAction,
		getDecisionContext,
		isSharedDecisionContext,
		findSemanticPairs,
		comparePair,
		buildPairEvidence,
		analyzeSemanticPairs
	};
}

root.normalizeAction = normalizeAction;
root.isCompetingAction = isCompetingAction;
root.findSemanticPairs = findSemanticPairs;
root.analyzeSemanticPairs = analyzeSemanticPairs;
})(globalThis);
