/**
 * DarkShield Phase B4.1 — DOM / Interaction Context Analyzer
 *
 * Evaluates privacy-safe, targeted DOM context and UI element properties
 * to produce deterministic, observable DOM signals and traceable evidence.
 *
 * Core Principle:
 * OBSERVABLE DOM FACT -> DOM SIGNAL -> EVIDENCE
 *
 * Strictly observational:
 * - Does NOT calculate final risk scores or dark-pattern classifications.
 * - Does NOT make legal claims or use ML/LLMs.
 * - Signal 'strength' represents evidence strength ('weak' | 'moderate' | 'strong'), NOT risk probability.
 * - Performance benchmark note: performance benchmark not independently established.
 */

let domDiffModule = null;
try {
	domDiffModule = require("./domDiff.js");
} catch {}

let semanticPairingModule = null;
try {
	semanticPairingModule = require("./semanticPairing.js");
} catch {}

function getDiffSnapshotsFn() {
	if (typeof diffSnapshots === "function") return diffSnapshots;
	if (domDiffModule && typeof domDiffModule.diffSnapshots === "function") return domDiffModule.diffSnapshots;
	return null;
}

function getSemanticPairsFn() {
	if (typeof analyzeSemanticPairs === "function") return analyzeSemanticPairs;
	if (semanticPairingModule && typeof semanticPairingModule.analyzeSemanticPairs === "function") return semanticPairingModule.analyzeSemanticPairs;
	return null;
}

const COMMERCIAL_PRESELECT_KEYWORDS = [
	"protection",
	"warranty",
	"insurance",
	"recurring",
	"donation",
	"add-on",
	"addon",
	"priority",
	"annual",
	"annually",
	"auto-renew",
	"autorenew",
	"monthly donation",
	"partner offers",
	"expedited",
	"tip",
	"extra coverage",
	"service plan"
];

const HARD_NEGATIVE_PRESELECT_KEYWORDS = [
	"remember me",
	"keep me logged in",
	"country",
	"language",
	"standard shipping",
	"standard delivery",
	"ground shipping",
	"free shipping",
	"current plan",
	"terms",
	"privacy policy"
];

function normalizeText(value) {
	return String(value || "").toLowerCase().replace(/\s+/g, " ").trim();
}

function containsAny(text, keywords) {
	if (!text || !keywords) return false;
	return keywords.some(k => text.includes(k));
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

function isCancellationContext(event, route) {
	const text = normalizeText(event?.text || event?.element?.text || event?.dom_context?.visible_text || "");
	const r = normalizeText(route || getRoute(event));

	const hasCancelRoute = ["cancel", "unsubscribe", "delete", "terminate", "membership", "billing"].some(k => r.includes(k));
	const hasCancelText = ["cancel", "unsubscribe", "end subscription", "stop subscription", "delete account"].some(k => text.includes(k));

	return hasCancelRoute || hasCancelText;
}

function getDecisionContext(event, route, containerType) {
	const r = normalizeText(route || getRoute(event));
	const t = normalizeText(event?.text || event?.element?.text || event?.dom_context?.visible_text || "");
	const c = normalizeText(containerType || "");

	if (r.includes("cancel") || t.includes("cancel") || r.includes("unsubscribe") || t.includes("unsubscribe")) return "cancellation";
	if (r.includes("subscri") || t.includes("subscri") || r.includes("membership")) return "subscription";
	if (r.includes("billing") || r.includes("checkout") || r.includes("payment") || r.includes("donate") || r.includes("order")) return "checkout";
	if (r.includes("consent") || r.includes("cookie") || r.includes("privacy") || c.includes("consent") || c.includes("cookie")) return "consent";
	if (c === "dialog" || c === "modal") return "dialog";
	return null;
}

function parseRgbColor(colorStr) {
	if (!colorStr || typeof colorStr !== "string") return null;
	const str = colorStr.trim().toLowerCase();
	if (str === "transparent" || str.includes("var(") || str.includes("gradient")) return null;

	const rgbaMatch = str.match(/rgba?\(\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)(?:\s*,\s*([\d.]+))?\s*\)/);
	if (rgbaMatch) {
		const r = parseFloat(rgbaMatch[1]);
		const g = parseFloat(rgbaMatch[2]);
		const b = parseFloat(rgbaMatch[3]);
		const a = rgbaMatch[4] !== undefined ? parseFloat(rgbaMatch[4]) : 1;
		if (a < 0.1) return null;
		return { r, g, b, a };
	}

	const hexMatch = str.match(/^#([0-9a-f]{3,8})$/);
	if (hexMatch) {
		let hex = hexMatch[1];
		if (hex.length === 3 || hex.length === 4) {
			hex = hex.split("").map(c => c + c).join("");
		}
		const r = parseInt(hex.slice(0, 2), 16);
		const g = parseInt(hex.slice(2, 4), 16);
		const b = parseInt(hex.slice(4, 6), 16);
		const a = hex.length === 8 ? parseInt(hex.slice(6, 8), 16) / 255 : 1;
		if (a < 0.1) return null;
		return { r, g, b, a };
	}

	return null;
}

function getRelativeLuminance(rgb) {
	if (!rgb) return null;
	const [r, g, b] = [rgb.r / 255, rgb.g / 255, rgb.b / 255].map(val => {
		return val <= 0.03928 ? val / 12.92 : Math.pow((val + 0.055) / 1.055, 2.4);
	});
	return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function calculateContrastRatio(fgColor, bgColor) {
	const fg = parseRgbColor(fgColor);
	const bg = parseRgbColor(bgColor);
	if (!fg || !bg) return null;
	const l1 = getRelativeLuminance(fg);
	const l2 = getRelativeLuminance(bg);
	if (l1 === null || l2 === null) return null;
	const lighter = Math.max(l1, l2);
	const darker = Math.min(l1, l2);
	return Number(((lighter + 0.05) / (darker + 0.05)).toFixed(2));
}

function parseComputedWeight(val) {
	if (typeof val === "number") return val;
	if (!val) return 400;
	if (val === "bold") return 700;
	if (val === "normal") return 400;
	const n = parseInt(val, 10);
	return isNaN(n) ? 400 : n;
}

/**
 * Computes an effective rendering opacity approximation by inspecting
 * the element and up to 3 bounded ancestors.
 * Note: CSS opacity creates a stacking context rather than being inherited,
 * but visually scales the composite alpha of descendants.
 */
function getEffectiveOpacity(elData) {
	if (!elData || typeof elData !== "object") return 1.0;
	if (typeof elData.effective_opacity === "number") return elData.effective_opacity;
	let eff = typeof elData.opacity === "number" ? elData.opacity : 1.0;
	if (Array.isArray(elData.parent_opacities)) {
		const bounded = elData.parent_opacities.slice(0, 3);
		for (const pOp of bounded) {
			if (typeof pOp === "number") {
				eff *= pOp;
			}
		}
	}
	return Number(Math.max(0, Math.min(1, eff)).toFixed(2));
}

function computeProminenceMetrics(prim, sec) {
	const areaRatio = (prim.area > 0 && sec.area > 0) ? Number((prim.area / sec.area).toFixed(2)) : null;
	const fontSizeRatio = (prim.font_size_px > 0 && sec.font_size_px > 0) ? Number((prim.font_size_px / sec.font_size_px).toFixed(2)) : null;
	const fontWeightDiff = (typeof prim.font_weight === "number" && typeof sec.font_weight === "number") ? prim.font_weight - sec.font_weight : null;
	const opacityDiff = (typeof prim.opacity === "number" && typeof sec.opacity === "number") ? Number((prim.opacity - sec.opacity).toFixed(2)) : null;
	const contrastDiff = (typeof prim.contrast === "number" && typeof sec.contrast === "number") ? Number((prim.contrast - sec.contrast).toFixed(2)) : null;

	return {
		area_ratio: areaRatio,
		font_size_ratio: fontSizeRatio,
		font_weight_difference: fontWeightDiff,
		opacity_difference: opacityDiff,
		contrast_difference: contrastDiff
	};
}

const NON_COMPETING_PAIRS = [
	["continue", "back"],
	["next", "previous"],
	["next", "back"],
	["submit", "reset"],
	["learn more", "continue"],
	["learn more", "next"],
	["help", "continue"],
	["help", "buy"],
	["close", "next"],
	["close", "continue"],
	["save", "cancel"], // Ordinary form settings: Save vs Cancel is standard design
	["open", "close"],
	["expand", "collapse"],
	["menu", "close"]
];

const AFFIRMATIVE_KEYWORDS = [
	"keep", "stay", "continue plan", "keep subscription", "keep plan",
	"stay subscribed", "accept", "accept all", "agree", "upgrade",
	"renew", "save with discount", "keep my subscription", "continue with plan",
	"allow", "subscribe", "add protection", "protect", "start trial"
];

const DECLINE_KEYWORDS = [
	"cancel", "decline", "reject", "opt out", "stop subscription",
	"end subscription", "delete account", "proceed with cancel",
	"cancel plan", "continue to cancel", "cancel subscription", "no thanks",
	"don't allow", "skip", "continue without trial"
];

function isAffirmativeKeyword(text) {
	return containsAny(normalizeText(text), AFFIRMATIVE_KEYWORDS);
}

function isDeclineKeyword(text) {
	return containsAny(normalizeText(text), DECLINE_KEYWORDS);
}

function isAlternativeDecisionPair(textA, textB) {
	const a = normalizeText(textA);
	const b = normalizeText(textB);

	if (!a || !b || a === b) return false;

	for (const [nc1, nc2] of NON_COMPETING_PAIRS) {
		if ((a.includes(nc1) && b.includes(nc2)) || (a.includes(nc2) && b.includes(nc1))) {
			return false;
		}
	}

	const aIsAffirmative = isAffirmativeKeyword(a);
	const aIsDecline = isDeclineKeyword(a);
	const bIsAffirmative = isAffirmativeKeyword(b);
	const bIsDecline = isDeclineKeyword(b);

	return (aIsAffirmative && bIsDecline) || (bIsAffirmative && aIsDecline);
}

function classifyCommercialReason(text) {
	const t = normalizeText(text);
	if (t.includes("warranty")) return "paid_warranty";
	if (t.includes("insurance")) return "insurance";
	if (t.includes("protection") || t.includes("coverage")) return "paid_protection";
	if (t.includes("donation") && (t.includes("recurring") || t.includes("monthly"))) return "recurring_donation";
	if (t.includes("annual") || t.includes("auto-renew") || t.includes("autorenew")) return "annual_auto_renew";
	if (t.includes("expedited") || t.includes("priority shipping")) return "expedited_shipping_fee";
	if (t.includes("marketing") || t.includes("partner offers")) return "marketing_consent";
	if (t.includes("add-on") || t.includes("addon") || t.includes("extra")) return "paid_add_on";
	return "commercial_option";
}

/**
 * Produces a deterministic semantic fingerprint for an element.
 */
function makeElementRef(tag, role, label, containerType, order = 1) {
	const cleanTag = String(tag || "ELEMENT").toUpperCase();
	const cleanRole = role ? `::role(${normalizeText(role)})` : "";
	const cleanText = label ? `::text(${normalizeText(label).slice(0, 30)})` : "";
	const cleanContainer = containerType ? `::ctx(${normalizeText(containerType)})` : "";
	const cleanOrder = `::ord(${Number(order) || 1})`;
	return `${cleanTag}${cleanRole}${cleanText}${cleanContainer}${cleanOrder}`;
}

/**
 * Analyzes event array and attached DOM contexts to extract observable DOM signals and traceable evidence.
 *
 * @param {Array<Object>} events - Array of normalized B1 events with optional dom_context.
 * @param {Object} [options] - Optional analysis parameters.
 * @returns {{ dom_signals: Array<Object>, evidence: Array<Object> }}
 */
function analyzeDomContext(events = [], options = {}) {
	const safeEvents = Array.isArray(events) ? events : [];
	const signals = [];

	if (safeEvents.length === 0) {
		return {
			dom_signals: [],
			evidence: []
		};
	}

	let cancellationSeen = false;

	safeEvents.forEach((ev, idx) => {
		if (!ev || typeof ev !== "object") return;

		const route = getRoute(ev);
		if (isCancellationContext(ev, route)) {
			cancellationSeen = true;
		}
		// Dynamic DOM Diff (B4.3)
		const diffFn = getDiffSnapshotsFn();
		if (diffFn && ev.snapshot_before && ev.snapshot_after) {
			const diffRes = diffFn(ev.snapshot_before, ev.snapshot_after, {
				route,
				event_indices: [idx],
				provenance: {
					event_id: ev.event_id,
					session_id: ev.session_id,
					tab_id: ev.tab_id,
					page_load_id: ev.page_load_id,
					timestamp: ev.timestamp
				}
			});
			if (diffRes && Array.isArray(diffRes.diff_signals)) {
				diffRes.diff_signals.forEach(s => signals.push(s));
			}
		} else if (Array.isArray(ev.diff_signals)) {
			ev.diff_signals.forEach(s => signals.push(s));
		} else if (ev.dom_diff && Array.isArray(ev.dom_diff.diff_signals)) {
			ev.dom_diff.diff_signals.forEach(s => signals.push(s));
		}

		// Cross-Container Semantic Pairing (B4.4)
		const pairFn = getSemanticPairsFn();
		const candidateActions = ev.candidate_actions || ev.cross_container_actions || ev.candidate_elements || ev.dom_context?.candidate_actions;
		if (pairFn && Array.isArray(candidateActions) && candidateActions.length >= 2) {
			const pairRes = pairFn(candidateActions, {
				route,
				event_indices: [idx]
			});
			if (pairRes && Array.isArray(pairRes.dom_signals)) {
				pairRes.dom_signals.forEach(s => signals.push(s));
			}
		}

		const dom = ev.dom_context || ev.element_context || null;
		if (!dom || typeof dom !== "object") return;

		const elementRef = dom.element_ref || makeElementRef(dom.tag, dom.role, dom.visible_text || dom.aria_label, dom.container_type);
		const tag = String(dom.tag || "").toUpperCase();
		const visibleText = normalizeText(dom.visible_text || ev.text || "");
		const ariaLabel = normalizeText(dom.aria_label || "");
		const labelText = visibleText || ariaLabel;
		const containerType = dom.container_type || "page";
		const geometry = dom.geometry || { width: 0, height: 0, area: 0 };
		const competing = Array.isArray(dom.competing_actions) ? dom.competing_actions : [];
		const decisionContext = getDecisionContext(ev, route, containerType);

		// =========================================================
		// SIGNAL 1: PRESELECTED_OPTION
		// =========================================================
		const checkables = [];
		if (dom.checked_state === true || dom.is_preselected === true) {
			checkables.push({
				label: labelText,
				type: dom.type || "checkbox",
				ref: elementRef,
				required: Boolean(dom.is_required)
			});
		}

		if (Array.isArray(dom.preselected_options)) {
			dom.preselected_options.forEach((opt, optIdx) => {
				if (opt && opt.checked === true) {
					checkables.push({
						label: normalizeText(opt.text || opt.label || ""),
						type: opt.type || "checkbox",
						ref: opt.element_ref || makeElementRef(opt.tag || "INPUT", "checkbox", opt.text || opt.label, containerType, optIdx + 1),
						required: Boolean(opt.required)
					});
				}
			});
		}

		checkables.forEach(chk => {
			const text = chk.label;
			const isHardNegative = containsAny(text, HARD_NEGATIVE_PRESELECT_KEYWORDS);
			const isCommercial = containsAny(text, COMMERCIAL_PRESELECT_KEYWORDS)
				|| (cancellationSeen && containsAny(text, ["stay", "keep", "offer", "discount", "pause", "renew", "upgrade"]));

			if (!isHardNegative && isCommercial) {
				const reasonKey = classifyCommercialReason(text);
				const isHighImpact = containsAny(text, ["recurring", "donation", "monthly", "annual", "insurance", "warranty", "paid", "auto-renew", "expedited"]);
				const strength = isHighImpact ? "strong" : "moderate";

				signals.push({
					type: "preselected_option",
					detected: true,
					strength,
					reason: `Preselected option observed for commercial choice: "${chk.label}".`,
					element_ref: chk.ref,
					event_indices: [idx],
					route,
					dom_properties: {
						label: chk.label,
						type: chk.type,
						is_preselected: true,
						commercial_context: true,
						commercial_reason: reasonKey,
						container_type: containerType
					}
				});
			}
		});

		// =========================================================
		// SIGNAL 2: DISABLED_ACTION
		// =========================================================
		// Detects when cancellation or decline option is disabled while competing affirmative action is enabled
		if (dom.is_disabled === true || dom.disabled === true) {
			const isCancelAction = containsAny(labelText, ["cancel", "decline", "delete", "unsubscribe", "stop", "no thanks"]);
			const enabledCompeting = competing.find(c => c.disabled !== true && c.is_disabled !== true && c.visible !== false);

			if (isCancelAction && enabledCompeting && (cancellationSeen || isCancellationContext(ev, route))) {
				signals.push({
					type: "disabled_action",
					detected: true,
					strength: "strong",
					reason: `Cancellation/decline action "${labelText}" was disabled while alternative "${normalizeText(enabledCompeting.text)}" remained active.`,
					element_ref: elementRef,
					event_indices: [idx],
					route,
					dom_properties: {
						disabled_element: labelText,
						enabled_competing: normalizeText(enabledCompeting.text),
						container_type: containerType
					}
				});
			}
		}

		// Also inspect competing actions if clicked element was enabled but competing cancel action was disabled
		competing.forEach((comp, cIdx) => {
			const compText = normalizeText(comp.text || "");
			const compDisabled = comp.disabled === true || comp.is_disabled === true;
			const isCompCancel = containsAny(compText, ["cancel", "decline", "delete", "unsubscribe", "no thanks"]);

			if (compDisabled && isCompCancel && !dom.is_disabled && (cancellationSeen || isCancellationContext(ev, route))) {
				const compRef = comp.element_ref || makeElementRef(comp.tag || "BUTTON", comp.role || "button", compText, containerType, cIdx + 1);
				signals.push({
					type: "disabled_action",
					detected: true,
					strength: "strong",
					reason: `Cancellation/decline action "${compText}" was disabled while primary action "${labelText}" remained active.`,
					element_ref: compRef,
					event_indices: [idx],
					route,
					dom_properties: {
						disabled_element: compText,
						enabled_competing: labelText,
						container_type: containerType
					}
				});
			}
		});

		// =========================================================
		// SIGNAL 3: HIDDEN_ALTERNATIVE
		// =========================================================
		// Only triggers within relevant decision context when a semantically related alternative is hidden
		competing.forEach((comp, cIdx) => {
			const compText = normalizeText(comp.text || "");
			const isAriaHidden = comp.aria_hidden === true || comp.aria_hidden === "true";
			const isSrOnly = comp.is_sr_only === true || comp.class_name?.includes("sr-only");
			const isHidden = comp.is_visible === false || comp.visible === false || comp.display === "none" || comp.visibility === "hidden" || comp.opacity === 0 || comp.opacity === "0";
			const isDeclineChoice = containsAny(compText, ["cancel", "decline", "opt out", "no thanks", "skip", "delete", "proceed with cancellation"]);

			// Non-competing informational content (FAQ, privacy policy, help) must NOT trigger hidden_alternative
			const isInformational = containsAny(compText, ["privacy policy", "terms", "faq", "help", "cookie policy"]);

			if (isHidden && !isAriaHidden && !isSrOnly && isDeclineChoice && !isInformational && (cancellationSeen || decisionContext === "cancellation" || decisionContext === "dialog")) {
				const compRef = comp.element_ref || makeElementRef(comp.tag || "A", comp.role || "link", compText, containerType, cIdx + 1);
				signals.push({
					type: "hidden_alternative",
					detected: true,
					strength: "strong",
					reason: `Cancellation/decline option "${compText}" exists in container DOM but is hidden from visual rendering.`,
					element_ref: compRef,
					event_indices: [idx],
					route,
					dom_properties: {
						hidden_text: compText,
						primary_text: labelText,
						container_type: containerType
					}
				});
			}
		});

		// =========================================================
		// SIGNAL 4: VISUAL PROMINENCE & CONTRAST ENGINE
		// =========================================================
		// Evaluates semantically competing alternative decision actions in relevant decision contexts
		// Produces deterministic evidence signals:
		// - action_size_asymmetry
		// - action_visual_deemphasis
		// - contrast_asymmetry
		// - typography_asymmetry
		// - covered_action
		if (competing.length > 0 && decisionContext) {
			competing.forEach((comp, cIdx) => {
				const compText = normalizeText(comp.text || "");
				if (!compText || comp.visible === false) return;

				if (isAlternativeDecisionPair(labelText, compText)) {
					const compRef = comp.element_ref || makeElementRef(comp.tag || "BUTTON", comp.role || "button", compText, containerType, cIdx + 1);

					const aIsAffirm = isAffirmativeKeyword(labelText);
					const aIsDec = isDeclineKeyword(labelText);
					const bIsAffirm = isAffirmativeKeyword(compText);
					const bIsDec = isDeclineKeyword(compText);

					let primaryNode, secondaryNode;
					if (aIsAffirm && bIsDec) {
						primaryNode = { text: labelText, ref: elementRef, isClicked: true, data: dom, area: geometry.area };
						secondaryNode = { text: compText, ref: compRef, isClicked: false, data: comp, area: comp.area || (comp.width && comp.height ? comp.width * comp.height : 0) };
					} else if (bIsAffirm && aIsDec) {
						primaryNode = { text: compText, ref: compRef, isClicked: false, data: comp, area: comp.area || (comp.width && comp.height ? comp.width * comp.height : 0) };
						secondaryNode = { text: labelText, ref: elementRef, isClicked: true, data: dom, area: geometry.area };
					} else {
						const compArea = comp.area || (comp.width && comp.height ? comp.width * comp.height : 0);
						if (geometry.area >= compArea) {
							primaryNode = { text: labelText, ref: elementRef, isClicked: true, data: dom, area: geometry.area };
							secondaryNode = { text: compText, ref: compRef, isClicked: false, data: comp, area: compArea };
						} else {
							primaryNode = { text: compText, ref: compRef, isClicked: false, data: comp, area: compArea };
							secondaryNode = { text: labelText, ref: elementRef, isClicked: true, data: dom, area: geometry.area };
						}
					}

					const primArea = primaryNode.area || 0;
					const secArea = secondaryNode.area || 0;
					const primFontSize = typeof primaryNode.data.font_size_px === "number" ? primaryNode.data.font_size_px : (primaryNode.data.fontSize ? parseFloat(primaryNode.data.fontSize) : null);
					const secFontSize = typeof secondaryNode.data.font_size_px === "number" ? secondaryNode.data.font_size_px : (secondaryNode.data.fontSize ? parseFloat(secondaryNode.data.fontSize) : null);
					const primFontWeight = parseComputedWeight(primaryNode.data.font_weight);
					const secFontWeight = parseComputedWeight(secondaryNode.data.font_weight);
					const primOpacity = getEffectiveOpacity(primaryNode.data);
					const secOpacity = getEffectiveOpacity(secondaryNode.data);

					let primContrast = typeof primaryNode.data.contrast_ratio === "number" ? primaryNode.data.contrast_ratio : calculateContrastRatio(primaryNode.data.color, primaryNode.data.background_color);
					let secContrast = typeof secondaryNode.data.contrast_ratio === "number" ? secondaryNode.data.contrast_ratio : calculateContrastRatio(secondaryNode.data.color, secondaryNode.data.background_color);

					const secIsDisabled = Boolean(secondaryNode.data.disabled || secondaryNode.data.is_disabled);
					const secIsAnimating = Boolean(secondaryNode.data.is_animating);
					const secIsCovered = Boolean(secondaryNode.data.is_covered || (secondaryNode.data.pointer_events === "none" && !secIsDisabled));

					const metrics = computeProminenceMetrics({
						area: primArea,
						font_size_px: primFontSize,
						font_weight: primFontWeight,
						opacity: primOpacity,
						contrast: primContrast
					}, {
						area: secArea,
						font_size_px: secFontSize,
						font_weight: secFontWeight,
						opacity: secOpacity,
						contrast: secContrast
					});

					// 4A. ACTION_SIZE_ASYMMETRY
					if (primArea > 0 && secArea > 0) {
						const ratio = Number((primArea / secArea).toFixed(2));
						if (ratio >= 3.0) {
							const strength = ratio >= 5.0 ? "strong" : "moderate";
							signals.push({
								type: "action_size_asymmetry",
								detected: true,
								strength,
								reason: `Primary action "${primaryNode.text}" (${primArea}px²) is ${ratio}x larger than secondary action "${secondaryNode.text}" (${secArea}px²).`,
								element_ref: primaryNode.ref,
								event_indices: [idx],
								route,
								dom_properties: {
									ratio,
									area_ratio: ratio,
									primary_area: primArea,
									secondary_area: secArea,
									primary_element_ref: primaryNode.ref,
									secondary_element_ref: secondaryNode.ref,
									primary_text: primaryNode.text,
									secondary_text: secondaryNode.text,
									context: decisionContext,
									metrics
								}
							});
						}
					}

					// 4B. ACTION_VISUAL_DEEMPHASIS (Opacity or severe visual dimming)
					if (!secIsDisabled && !secIsAnimating) {
						if (primOpacity >= 0.80 && secOpacity <= 0.50) {
							const opacityDiff = Number((primOpacity - secOpacity).toFixed(2));
							const strength = (secOpacity <= 0.20 || opacityDiff >= 0.75) ? "strong" : "moderate";
							signals.push({
								type: "action_visual_deemphasis",
								detected: true,
								strength,
								reason: `Secondary alternative "${secondaryNode.text}" rendered with visual deemphasis (effective opacity: ${secOpacity} vs primary: ${primOpacity}).`,
								element_ref: secondaryNode.ref,
								event_indices: [idx],
								route,
								dom_properties: {
									deemphasis_type: "opacity",
									primary_opacity: primOpacity,
									secondary_opacity: secOpacity,
									opacity_difference: Number((primOpacity - secOpacity).toFixed(2)),
									primary_element_ref: primaryNode.ref,
									secondary_element_ref: secondaryNode.ref,
									primary_text: primaryNode.text,
									secondary_text: secondaryNode.text,
									context: decisionContext,
									metrics
								}
							});
						} else if (secFontSize && secFontSize <= 8 && primFontSize && primFontSize >= 14) {
							signals.push({
								type: "action_visual_deemphasis",
								detected: true,
								strength: "strong",
								reason: `Secondary alternative "${secondaryNode.text}" rendered with severe font deemphasis (${secFontSize}px vs primary: ${primFontSize}px).`,
								element_ref: secondaryNode.ref,
								event_indices: [idx],
								route,
								dom_properties: {
									deemphasis_type: "typography",
									primary_font_size: primFontSize,
									secondary_font_size: secFontSize,
									primary_element_ref: primaryNode.ref,
									secondary_element_ref: secondaryNode.ref,
									primary_text: primaryNode.text,
									secondary_text: secondaryNode.text,
									context: decisionContext,
									metrics
								}
							});
						}
					}

					// 4C. CONTRAST_ASYMMETRY
					if (!secIsDisabled && typeof primContrast === "number" && typeof secContrast === "number") {
						if (primContrast >= 3.5 && (secContrast < 3.0 || (primContrast - secContrast) >= 3.0)) {
							const strength = (secContrast <= 2.5 && primContrast >= 4.5) ? "strong" : "moderate";
							signals.push({
								type: "contrast_asymmetry",
								detected: true,
								strength,
								reason: `Primary action "${primaryNode.text}" has ${primContrast}:1 contrast while secondary alternative "${secondaryNode.text}" has low ${secContrast}:1 contrast against background.`,
								element_ref: secondaryNode.ref,
								event_indices: [idx],
								route,
								dom_properties: {
									primary_contrast: primContrast,
									secondary_contrast: secContrast,
									contrast_difference: Number((primContrast - secContrast).toFixed(2)),
									primary_element_ref: primaryNode.ref,
									secondary_element_ref: secondaryNode.ref,
									primary_text: primaryNode.text,
									secondary_text: secondaryNode.text,
									context: decisionContext,
									metrics
								}
							});
						}
					}

					// 4D. TYPOGRAPHY_ASYMMETRY
					if (!secIsDisabled && primFontSize && secFontSize) {
						const fontRatio = primFontSize / secFontSize;
						const weightDiff = primFontWeight - secFontWeight;
						if (fontRatio >= 2.0 && weightDiff >= 200) {
							signals.push({
								type: "typography_asymmetry",
								detected: true,
								strength: "strong",
								reason: `Primary action "${primaryNode.text}" uses ${primFontSize}px (weight: ${primFontWeight}) typography while secondary alternative "${secondaryNode.text}" uses ${secFontSize}px (weight: ${secFontWeight}).`,
								element_ref: secondaryNode.ref,
								event_indices: [idx],
								route,
								dom_properties: {
									primary_font_size: primFontSize,
									secondary_font_size: secFontSize,
									font_size_ratio: Number(fontRatio.toFixed(2)),
									primary_font_weight: primFontWeight,
									secondary_font_weight: secFontWeight,
									font_weight_difference: weightDiff,
									primary_element_ref: primaryNode.ref,
									secondary_element_ref: secondaryNode.ref,
									primary_text: primaryNode.text,
									secondary_text: secondaryNode.text,
									context: decisionContext,
									metrics
								}
							});
						} else if ((fontRatio >= 1.5 && weightDiff >= 300) || fontRatio >= 2.0) {
							signals.push({
								type: "typography_asymmetry",
								detected: true,
								strength: "moderate",
								reason: `Primary action "${primaryNode.text}" uses ${primFontSize}px (weight: ${primFontWeight}) typography while secondary alternative "${secondaryNode.text}" uses ${secFontSize}px (weight: ${secFontWeight}).`,
								element_ref: secondaryNode.ref,
								event_indices: [idx],
								route,
								dom_properties: {
									primary_font_size: primFontSize,
									secondary_font_size: secFontSize,
									font_size_ratio: Number(fontRatio.toFixed(2)),
									primary_font_weight: primFontWeight,
									secondary_font_weight: secFontWeight,
									font_weight_difference: weightDiff,
									primary_element_ref: primaryNode.ref,
									secondary_element_ref: secondaryNode.ref,
									primary_text: primaryNode.text,
									secondary_text: secondaryNode.text,
									context: decisionContext,
									metrics
								}
							});
						}
					}

					// 4E. COVERED_ACTION
					if (secIsCovered && !secIsDisabled) {
						signals.push({
							type: "covered_action",
							detected: true,
							strength: "strong",
							reason: `Secondary decision alternative "${secondaryNode.text}" is covered or pointer-events are blocked while appearing active.`,
							element_ref: secondaryNode.ref,
							event_indices: [idx],
							route,
							dom_properties: {
								primary_element_ref: primaryNode.ref,
								secondary_element_ref: secondaryNode.ref,
								primary_text: primaryNode.text,
								secondary_text: secondaryNode.text,
								context: decisionContext,
								metrics
							}
						});
					}
				}
			});
		}

		// =========================================================
		// SIGNAL 5: REQUIRED_OPTION
		// =========================================================
		// Detects required inputs/surveys gating cancellation progression
		const isRequired = dom.is_required === true || dom.required === true || dom.aria_required === true || dom.aria_required === "true";
		if (isRequired && (cancellationSeen || isCancellationContext(ev, route))) {
			const isSurveyOrFeedback = containsAny(labelText, ["survey", "feedback", "reason", "why are you leaving", "tell us why", "select a reason"])
				|| containsAny(route, ["survey", "feedback", "reason", "cancel"]);

			if (isSurveyOrFeedback) {
				signals.push({
					type: "required_option",
					detected: true,
					strength: "moderate",
					reason: `Required form field "${labelText || "survey field"}" gates cancellation progression.`,
					element_ref: elementRef,
					event_indices: [idx],
					route,
					dom_properties: {
						label: labelText,
						tag,
						is_required: true,
						container_type: containerType
					}
				});
			}
		}

		// Check multiple required acknowledgement checkboxes gating cancellation
		if (Array.isArray(dom.required_acknowledgements) && dom.required_acknowledgements.length >= 2 && cancellationSeen) {
			signals.push({
				type: "required_option",
				detected: true,
				strength: "strong",
				reason: `${dom.required_acknowledgements.length} required acknowledgement checkboxes gate cancellation.`,
				element_ref: elementRef,
				event_indices: [idx],
				route,
				dom_properties: {
					count: dom.required_acknowledgements.length,
					container_type: containerType
				}
			});
		}

		// =========================================================
		// SIGNAL 6: SMALL_SECONDARY_ACTION
		// =========================================================
		// Requirements:
		// 1. Semantic competing action.
		// 2. Relevant cancellation/decline/consent context.
		// 3. Secondary action is actually visible.
		// 4. Size difference is meaningful.
		// Font size or dimensions alone on general page must never create a strong signal.
		const fontSize = Number(dom.font_size_px) || (dom.font_size ? parseFloat(dom.font_size) : null);
		const isCancelSecondary = containsAny(labelText, ["cancel", "decline", "no thanks", "opt out", "stop subscription", "continue to cancel"]);
		const nonCompetingNavigation = containsAny(labelText, ["back", "previous", "close", "learn more", "help", "save"]);

		if (isCancelSecondary && !nonCompetingNavigation && (cancellationSeen || decisionContext === "cancellation" || decisionContext === "dialog")) {
			let isSmall = false;
			let smallReason = "";
			let strength = "moderate";
			let primaryComp = competing.find(c => isAlternativeDecisionPair(labelText, c.text));

			if (primaryComp) {
				const primaryArea = primaryComp.area || (primaryComp.width && primaryComp.height ? primaryComp.width * primaryComp.height : 0);
				const hasMeaningfulAreaDiff = primaryArea > 0 && geometry.area > 0 && (geometry.area / primaryArea) <= 0.25;
				if (hasMeaningfulAreaDiff) {
					isSmall = true;
					smallReason = `Cancellation action dimensions are ${(geometry.area / primaryArea * 100).toFixed(0)}% of primary action.`;
				}
				if (fontSize && fontSize < 11) {
					isSmall = true;
					smallReason = `Cancellation alternative rendered with tiny ${fontSize}px font size.`;
				}
				if (isSmall) {
					// Strong requires semantic competing action + meaningful size disparity (e.g. <= 8px or area <= 25% with small font)
					strength = (fontSize && fontSize <= 8) || (hasMeaningfulAreaDiff && fontSize && fontSize < 11) ? "strong" : "moderate";
				}
			} else {
				// Without semantic competing action, font size alone must NEVER produce strong signal
				if (fontSize && fontSize < 11) {
					isSmall = true;
					strength = "moderate";
					smallReason = `Cancellation action rendered with small ${fontSize}px font size.`;
				}
			}

			if (isSmall) {
				const primaryRef = primaryComp ? (primaryComp.element_ref || makeElementRef(primaryComp.tag || "BUTTON", primaryComp.role || "button", primaryComp.text, containerType)) : null;
				const areaRatio = (primaryComp && primaryComp.area && geometry.area > 0) ? Number((primaryComp.area / geometry.area).toFixed(2)) : null;

				signals.push({
					type: "small_secondary_action",
					detected: true,
					strength,
					reason: smallReason,
					element_ref: elementRef,
					event_indices: [idx],
					route,
					dom_properties: {
						font_size_px: fontSize,
						width: geometry.width,
						height: geometry.height,
						area: geometry.area,
						area_ratio: areaRatio,
						primary_element_ref: primaryRef,
						secondary_element_ref: elementRef,
						container_type: containerType
					}
				});
			}
		}

		// Also check competing elements if clicked element is primary and competing cancel is tiny
		competing.forEach((comp, cIdx) => {
			const compText = normalizeText(comp.text || "");
			const isCompCancel = containsAny(compText, ["cancel", "decline", "no thanks", "opt out", "continue to cancel"]);
			const compNonCompeting = containsAny(compText, ["back", "previous", "close", "learn more", "help", "save"]);
			const compFontSize = Number(comp.font_size_px) || null;
			const compArea = comp.area || (comp.width && comp.height ? comp.width * comp.height : 0);

			if (isCompCancel && !compNonCompeting && isAlternativeDecisionPair(labelText, compText) && (cancellationSeen || decisionContext === "cancellation" || decisionContext === "dialog")) {
				let tinyComp = false;
				let tinyReason = "";
				let tinyStrength = "moderate";

				const hasCompAreaDiff = geometry.area > 0 && compArea > 0 && (compArea / geometry.area) <= 0.25;
				if (compFontSize && compFontSize < 11) {
					tinyComp = true;
					tinyReason = `Cancellation alternative "${compText}" rendered with tiny ${compFontSize}px font size.`;
				}
				if (hasCompAreaDiff) {
					tinyComp = true;
					tinyReason = `Cancellation alternative "${compText}" dimensions are ${(compArea / geometry.area * 100).toFixed(0)}% of primary action.`;
				}
				if (tinyComp) {
					tinyStrength = (compFontSize && compFontSize <= 8) || (hasCompAreaDiff && compFontSize && compFontSize < 11) ? "strong" : "moderate";
				}

				if (tinyComp) {
					const compRef = comp.element_ref || makeElementRef(comp.tag || "A", comp.role || "link", compText, containerType, cIdx + 1);
					const areaRatio = (geometry.area > 0 && compArea > 0) ? Number((geometry.area / compArea).toFixed(2)) : null;

					signals.push({
						type: "small_secondary_action",
						detected: true,
						strength: tinyStrength,
						reason: tinyReason,
						element_ref: compRef,
						event_indices: [idx],
						route,
						dom_properties: {
							font_size_px: compFontSize,
							width: comp.width,
							height: comp.height,
							area: compArea,
							area_ratio: areaRatio,
							primary_element_ref: elementRef,
							secondary_element_ref: compRef,
							container_type: containerType
						}
					});
				}
			}
		});

		// =========================================================
		// SIGNAL 7: VISIBILITY_MISMATCH
		// =========================================================
		// Requirements:
		// VISIBLE PRIMARY ACTION + SEMANTICALLY RELATED ALTERNATIVE + ALTERNATIVE IS HIDDEN/COLLAPSED + RELEVANT DECISION CONTEXT
		// Non-competing content like FAQ, Privacy Policy, or Help must NOT trigger visibility_mismatch.
		if ((dom.has_collapsed_alternative === true || dom.alternative_in_accordion === true) && (cancellationSeen || decisionContext === "cancellation" || decisionContext === "subscription")) {
			signals.push({
				type: "visibility_mismatch",
				detected: true,
				strength: "moderate",
				reason: "Primary choice is fully visible while cancellation/decline option is placed in a collapsed section.",
				element_ref: elementRef,
				event_indices: [idx],
				route,
				dom_properties: {
					primary_text: labelText,
					container_type: containerType,
					decision_context: decisionContext
				}
			});
		}

		// =========================================================
		// SIGNAL 8: ACTION_STATE_MISMATCH
		// =========================================================
		// Primary retention action is enabled while cancel action is disabled in the same container
		if (competing.length > 0 && (cancellationSeen || isCancellationContext(ev, route))) {
			const enabledRetention = (dom.is_disabled !== true && containsAny(labelText, ["keep", "stay", "upgrade", "renew", "discount"]))
				? { text: labelText, ref: elementRef }
				: competing.find(c => c.disabled !== true && c.is_disabled !== true && containsAny(normalizeText(c.text), ["keep", "stay", "upgrade", "renew", "discount"]));

			const disabledCancel = (dom.is_disabled === true && containsAny(labelText, ["cancel", "decline", "stop", "delete"]))
				? { text: labelText, ref: elementRef }
				: competing.find(c => (c.disabled === true || c.is_disabled === true) && containsAny(normalizeText(c.text), ["cancel", "decline", "stop", "delete"]));

			if (enabledRetention && disabledCancel) {
				signals.push({
					type: "action_state_mismatch",
					detected: true,
					strength: "strong",
					reason: `Retention option "${normalizeText(enabledRetention.text)}" is enabled while cancellation option "${normalizeText(disabledCancel.text)}" is disabled.`,
					element_ref: disabledCancel.ref || elementRef,
					event_indices: [idx],
					route,
					dom_properties: {
						enabled_action: normalizeText(enabledRetention.text),
						disabled_action: normalizeText(disabledCancel.text),
						container_type: containerType
					}
				});
			}
		}

		// =========================================================
		// SIGNAL 9: MODAL_INTERFERENCE
		// =========================================================
		// Active modal/dialog appears during cancellation flow
		const isModalContainer = containerType === "dialog" || containerType === "modal" || dom.is_modal === true;
		if (isModalContainer && cancellationSeen) {
			const hasNoClose = dom.has_close_button === false || dom.close_button_disabled === true;
			const strength = hasNoClose ? "strong" : "moderate";

			signals.push({
				type: "modal_interference",
				detected: true,
				strength,
				reason: hasNoClose
					? "Modal dialog interrupted the cancellation flow without an accessible close button."
					: "Modal dialog interrupted the cancellation flow with retention offers.",
				element_ref: elementRef,
				event_indices: [idx],
				route,
				dom_properties: {
					container_type: containerType,
					has_close_button: !hasNoClose
				}
			});
		}

		// =========================================================
		// SIGNAL 10: CONFIRMATION_UI
		// =========================================================
		// Confirmation dialogs are normal UI. confirmation_ui primarily means "confirmation structure observed" (weak).
		// Stronger evidence (moderate) only if the dialog contains observable asymmetry.
		if (isModalContainer || containsAny(labelText, ["confirm", "are you sure", "really want to cancel", "confirm cancellation"])) {
			const isConfirmContext = containsAny(labelText, ["confirm", "are you sure", "really want to cancel"])
				|| containsAny(route, ["confirm", "review"]);

			if (isConfirmContext && cancellationSeen) {
				const isAsymmetric = Boolean(
					dom.has_confirm_shaming === true
					|| (competing.length > 0 && geometry.area > 0 && competing.some(c => (c.area || (c.width * c.height) || 0) > geometry.area * 2))
				);
				const strength = isAsymmetric ? "moderate" : "weak";

				signals.push({
					type: "confirmation_ui",
					detected: true,
					strength,
					reason: isAsymmetric
						? "Asymmetric confirmation dialog observed with unbalanced choice presentation."
						: "Confirmation structure observed.",
					element_ref: elementRef,
					event_indices: [idx],
					route,
					dom_properties: {
						container_type: containerType,
						is_asymmetric: isAsymmetric
					}
				});
			}
		}
	});

	// Deduplicate signals by type + element_ref + route, merging event_indices
	const uniqueSignals = [];
	const signalMap = new Map();

	signals.forEach(sig => {
		const key = `${sig.type}::${sig.element_ref}::${sig.route}`;
		if (signalMap.has(key)) {
			const existing = signalMap.get(key);
			sig.event_indices.forEach(idx => {
				if (!existing.event_indices.includes(idx)) {
					existing.event_indices.push(idx);
				}
			});
			existing.event_indices.sort((a, b) => a - b);
		} else {
			signalMap.set(key, sig);
			uniqueSignals.push(sig);
		}
	});

	// Format traceable evidence records
	const evidence = uniqueSignals.map(sig => ({
		signal_type: sig.type,
		strength: sig.strength,
		description: sig.reason,
		element_ref: sig.element_ref,
		event_indices: sig.event_indices,
		route: sig.route
	}));

	return {
		dom_signals: uniqueSignals,
		evidence
	};
}

if (typeof module !== "undefined" && module.exports) {
	module.exports = {
		analyzeDomContext,
		makeElementRef,
		calculateContrastRatio,
		computeProminenceMetrics,
		getEffectiveOpacity,
		isAlternativeDecisionPair,
		getDecisionContext,
		diffSnapshots: getDiffSnapshotsFn(),
		createSnapshot: domDiffModule ? domDiffModule.createSnapshot : null,
		analyzeSemanticPairs: getSemanticPairsFn(),
		findSemanticPairs: semanticPairingModule ? semanticPairingModule.findSemanticPairs : null,
		normalizeAction: semanticPairingModule ? semanticPairingModule.normalizeAction : null,
		isCompetingAction: semanticPairingModule ? semanticPairingModule.isCompetingAction : null
	};
}

if (typeof globalThis !== "undefined") {
	globalThis.analyzeDomContext = analyzeDomContext;
	globalThis.makeElementRef = makeElementRef;
	globalThis.calculateContrastRatio = calculateContrastRatio;
	globalThis.computeProminenceMetrics = computeProminenceMetrics;
	globalThis.getEffectiveOpacity = getEffectiveOpacity;
	globalThis.diffSnapshots = getDiffSnapshotsFn();
	globalThis.analyzeSemanticPairs = getSemanticPairsFn();
}

