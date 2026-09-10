/**
 * DarkShield Phase B4.3 — Dynamic DOM Diff & Post-Action Change Detection
 *
 * Implements a deterministic, bounded Dynamic DOM Diff Engine that detects
 * meaningful UI/state changes caused by a user interaction.
 *
 * Core Concept:
 * PRE-ACTION STATE -> USER INTERACTION -> POST-ACTION STATE -> DOM/STATE DIFF -> OBSERVABLE CHANGE EVIDENCE
 *
 * Privacy Guarantees:
 * - Never captures input.value, textarea.value, passwords, payment info, tokens, CVVs.
 * - No full HTML/outerHTML/innerHTML serialization.
 * - Bounded to maximum 25 candidate elements per snapshot.
 * - No permanent or global MutationObserver.
 * - Observable facts only; never declares legal violation or final consumer risk.
 */

// =========================================================
// LEXICONS & KEYWORDS
// =========================================================

const FEE_KEYWORDS = [
	"processing fee",
	"service fee",
	"platform fee",
	"booking fee",
	"handling fee",
	"convenience fee",
	"delivery fee",
	"shipping fee",
	"protection fee",
	"additional charge",
	"service charge",
	"extra fee",
	"handling charge"
];

const FEE_EXCLUSIONS = [
	"free",
	"no fee",
	"fee included",
	"no additional fee",
	"cancel fee",
	"zero fee",
	"without fee",
	"free shipping"
];

const REJECTION_KEYWORDS = [
	"cancel",
	"decline",
	"reject",
	"opt out",
	"skip",
	"delete",
	"no thanks",
	"don't allow",
	"stop subscription",
	"end subscription"
];

const COMMERCIAL_ADDON_KEYWORDS = [
	"warranty",
	"insurance",
	"protection",
	"add-on",
	"addon",
	"priority",
	"expedited",
	"donation",
	"recurring",
	"annual",
	"auto-renew",
	"premium support",
	"coverage"
];

const BENIGN_PRESELECT_KEYWORDS = [
	"remember me",
	"keep me logged in",
	"language",
	"country",
	"standard shipping",
	"free shipping",
	"terms",
	"privacy policy"
];

const NOISE_INDICATOR_KEYWORDS = [
	"loading",
	"spinner",
	"skeleton",
	"shimmer",
	"advertisement",
	"sponsored",
	"ad-slot",
	"ad-banner",
	"tracker",
	"analytics",
	"pixel"
];

// =========================================================
// HELPER FUNCTIONS
// =========================================================

function normalizeText(value) {
	return String(value || "").toLowerCase().replace(/\s+/g, " ").trim();
}

function containsAny(text, keywords) {
	if (!text || !keywords) return false;
	const norm = normalizeText(text);
	return keywords.some(k => norm.includes(k));
}

function parsePrice(text, hint = "") {
	if (!text || typeof text !== "string") return null;
	const norm = text.replace(/\s+/g, " ").trim();
	// Matches ₹499, $19.99, 499 INR, €25.50, £10, etc.
	const match = norm.match(/(?:([₹$€£]|INR|USD|EUR|GBP)\s*([\d,]+(?:\.\d{1,2})?))|(?:([\d,]+(?:\.\d{1,2})?)\s*([₹$€£]|INR|USD|EUR|GBP))/i);
	if (match) {
		const currency = (match[1] || match[4] || "").toUpperCase();
		const rawAmount = (match[2] || match[3] || "").replace(/,/g, "");
		const amount = parseFloat(rawAmount);

		if (!isNaN(amount)) {
			return {
				currency,
				amount,
				formatted: `${currency} ${amount}`
			};
		}
	}

	// Decimal or numeric amount fallback when in a price/total context or matches standard decimal format (e.g. "49.99")
	const contextHint = String(hint || "").toLowerCase();
	const isPriceContext = contextHint.includes("price") || contextHint.includes("total") || contextHint.includes("cost") || /^(?:price|total)?\s*[:=]?\s*[\d,]+(?:\.\d{1,2})?$/i.test(norm);
	if (isPriceContext) {
		const numMatch = norm.match(/([\d,]+(?:\.\d{1,2})?)/);
		if (numMatch) {
			const rawAmount = numMatch[1].replace(/,/g, "");
			const amount = parseFloat(rawAmount);
			if (!isNaN(amount)) {
				return {
					currency: null,
					amount,
					formatted: `${amount}`
				};
			}
		}
	}
	return null;
}

function isTimestampOrDate(text) {
	if (!text) return false;
	const t = text.trim();
	// Matches HH:MM:SS, ISO dates YYYY-MM-DD, relative timestamps like "2 seconds ago"
	if (/^\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?$/i.test(t)) return true;
	if (/^\d{4}-\d{2}-\d{2}(?:T[\d:.]+Z?)?$/.test(t)) return true;
	if (/^(?:\d+\s*(?:second|minute|hour|day|sec|min|hr)s?\s*ago|just now)$/i.test(t)) return true;
	return false;
}

function isNoiseElement(el) {
	if (!el) return false;
	const text = normalizeText(el.visible_text || el.text || "");
	const tag = String(el.tag || "").toUpperCase();
	const role = normalizeText(el.role || "");
	const ref = normalizeText(el.element_ref || "");
	const className = normalizeText(el.class_name || el.class || "");

	if (el.is_animating === true) return true;
	if (role === "progressbar" || role === "presentation" || role === "none") return true;
	if (tag === "SVG" || tag === "PATH") return true;
	if (containsAny(className, ["divider", "separator", "skeleton", "spinner", "loader", "ad-slot", "advertisement", "analytics"])) return true;
	if (isTimestampOrDate(text)) return true;
	if (containsAny(text, NOISE_INDICATOR_KEYWORDS)) return true;
	if (containsAny(role, NOISE_INDICATOR_KEYWORDS)) return true;
	if (containsAny(ref, NOISE_INDICATOR_KEYWORDS)) return true;

	// Purely decorative empty element
	if (!text && !el.aria_label && tag === "DIV" && !el.role && !el.checked_state) {
		return true;
	}

	return false;
}

function classifyCommercialReason(text) {
	const t = normalizeText(text);
	if (t.includes("warranty")) return "paid_warranty";
	if (t.includes("insurance")) return "insurance";
	if (t.includes("protection") || t.includes("coverage")) return "paid_protection";
	if (t.includes("donation") && (t.includes("recurring") || t.includes("monthly"))) return "recurring_donation";
	if (t.includes("annual") || t.includes("auto-renew") || t.includes("autorenew")) return "annual_auto_renew";
	if (t.includes("expedited") || t.includes("priority shipping")) return "expedited_shipping_fee";
	if (t.includes("premium support")) return "premium_support";
	if (t.includes("add-on") || t.includes("addon")) return "paid_add_on";
	return "commercial_add_on";
}

// =========================================================
// SNAPSHOT ENGINE
// =========================================================

/**
 * Creates a bounded, privacy-safe snapshot of candidate elements.
 *
 * @param {Array<Object>|Document|Element} input - Array of element descriptors or DOM root.
 * @param {Object} [options] - Configuration options.
 * @returns {Object} Snapshot containing bounded candidate elements array and metadata.
 */
function createSnapshot(input, options = {}) {
	const maxElements = options.maxElements || 25;
	const route = options.route || "/";
	const timestamp = options.timestamp || new Date().toISOString();
	const scrollLocked = Boolean(options.scroll_locked);

	// Case 1: Input is already an array of element descriptors (e.g. in tests or background)
	if (Array.isArray(input)) {
		const safeElements = input.slice(0, maxElements).map((el, idx) => sanitizeSnapshotElement(el, idx));
		return {
			timestamp,
			route,
			scroll_locked: scrollLocked,
			elements: safeElements
		};
	}

	// Case 2: Input is an object with an `elements` array
	if (input && Array.isArray(input.elements)) {
		const safeElements = input.elements.slice(0, maxElements).map((el, idx) => sanitizeSnapshotElement(el, idx));
		return {
			timestamp: input.timestamp || timestamp,
			route: input.route || route,
			scroll_locked: typeof input.scroll_locked === "boolean" ? input.scroll_locked : scrollLocked,
			elements: safeElements
		};
	}

	// Case 3: Browser DOM root (document or container element)
	const doc = (input && typeof input.querySelectorAll === "function") ? input : (typeof document !== "undefined" ? document : null);
	if (!doc) {
		return {
			timestamp,
			route,
			scroll_locked: scrollLocked,
			elements: []
		};
	}

	const candidates = [];
	try {
		const selector = "button, a[href], [role='button'], input[type='checkbox'], input[type='radio'], input[type='submit'], select, dialog, [role='dialog'], .modal, [class*='fee'], [class*='price'], [id*='price'], [id*='fee']";
		const nodes = doc.querySelectorAll(selector);

		for (let i = 0; i < nodes.length && candidates.length < maxElements; i++) {
			const node = nodes[i];
			if (!(node instanceof Element)) continue;

			// Extract safe presentation properties only (NO input values, NO passwords, NO card data)
			const tag = String(node.tagName || "DIV").toUpperCase();
			const isInput = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
			const type = node.getAttribute("type") ? String(node.getAttribute("type")).toLowerCase() : (isInput ? "text" : null);

			// Exclude sensitive input types entirely
			if (type === "password" || type === "email" || type === "tel") continue;

			let text = "";
			if (!isInput) {
				text = String(node.innerText || node.textContent || "").replace(/\s+/g, " ").trim().slice(0, 80);
			} else if (type === "checkbox" || type === "radio") {
				const parentLabel = node.closest("label");
				text = String(parentLabel?.innerText || node.getAttribute("aria-label") || node.getAttribute("name") || "").replace(/\s+/g, " ").trim().slice(0, 80);
			}

			const ariaLabel = String(node.getAttribute("aria-label") || "").replace(/\s+/g, " ").trim().slice(0, 80);
			const role = String(node.getAttribute("role") || (tag === "A" ? "link" : (tag === "BUTTON" ? "button" : ""))).toLowerCase();
			const checkedState = (type === "checkbox" || type === "radio") ? Boolean(node.checked) : null;
			const isRequired = Boolean(node.required || node.getAttribute("aria-required") === "true");

			let isVisible = true;
			let isDisabled = Boolean(node.disabled || node.getAttribute("aria-disabled") === "true");

			let width = 0, height = 0;
			try {
				const rect = node.getBoundingClientRect();
				width = Math.round(rect.width || 0);
				height = Math.round(rect.height || 0);
				if (width === 0 && height === 0 && node.offsetParent === null) {
					isVisible = false;
				}
			} catch {}

			const isModal = tag === "DIALOG" || role === "dialog" || node.classList?.contains("modal") || node.getAttribute("role") === "alertdialog";

			candidates.push({
				element_ref: `${tag}::role(${role || "none"})::text(${normalizeText(text || ariaLabel).slice(0, 30)})`,
				tag,
				role: role || null,
				type,
				visible_text: text,
				aria_label: ariaLabel || null,
				is_visible: isVisible,
				is_disabled: isDisabled,
				is_required: isRequired,
				is_modal: isModal,
				checked_state: checkedState,
				geometry: { width, height }
			});
		}
	} catch {}

	let isBodyScrollLocked = false;
	try {
		if (typeof window !== "undefined" && window.getComputedStyle) {
			const bodyCs = window.getComputedStyle(document.body);
			isBodyScrollLocked = bodyCs.overflow === "hidden" || bodyCs.position === "fixed";
		}
	} catch {}

	return {
		timestamp,
		route,
		scroll_locked: isBodyScrollLocked,
		elements: candidates
	};
}

function sanitizeSnapshotElement(el, idx = 0) {
	if (!el || typeof el !== "object") {
		return {
			element_ref: `ELEMENT::ord(${idx})`,
			tag: "DIV",
			visible_text: "",
			is_visible: false,
			is_disabled: false,
			checked_state: null
		};
	}

	const tag = String(el.tag || "DIV").toUpperCase();
	const role = el.role ? String(el.role).toLowerCase() : null;
	const type = el.type ? String(el.type).toLowerCase() : null;
	const visibleText = String(el.visible_text || el.text || "").replace(/\s+/g, " ").trim().slice(0, 80);
	const ariaLabel = el.aria_label ? String(el.aria_label).replace(/\s+/g, " ").trim().slice(0, 80) : null;
	const isVisible = el.is_visible !== false && el.visible !== false;
	const isDisabled = Boolean(el.is_disabled || el.disabled);
	const isRequired = Boolean(el.is_required || el.required);
	const isModal = Boolean(el.is_modal || el.container_type === "modal" || el.container_type === "dialog");

	let checkedState = null;
	if (typeof el.checked_state === "boolean") checkedState = el.checked_state;
	else if (typeof el.checked === "boolean") checkedState = el.checked;

	const ref = el.element_ref ? String(el.element_ref) : `${tag}::role(${role || "none"})::text(${normalizeText(visibleText || ariaLabel).slice(0, 30)})::ord(${idx + 1})`;

	return {
		element_ref: ref,
		tag,
		role,
		type,
		visible_text: visibleText,
		aria_label: ariaLabel,
		is_visible: isVisible,
		is_disabled: isDisabled,
		is_required: isRequired,
		is_modal: isModal,
		checked_state: checkedState,
		geometry: el.geometry || { width: Number(el.width) || 0, height: Number(el.height) || 0 }
	};
}

// =========================================================
// ELEMENT MATCHING (EPHEMERAL FINGERPRINT)
// =========================================================

function makeElementFingerprint(el) {
	if (!el) return "";
	const tag = String(el.tag || "").toUpperCase();
	const role = String(el.role || "").toLowerCase();
	const type = String(el.type || "").toLowerCase();
	const text = normalizeText(el.visible_text || el.text || "");
	const aria = normalizeText(el.aria_label || "");
	const isInput = tag === "INPUT";

	// Composite ephemeral fingerprint
	return `${tag}|${role}|${type}|${isInput ? aria || text : text || aria}`;
}

function matchElements(beforeElements = [], afterElements = []) {
	const matched = [];
	const unmatchedBefore = [...beforeElements];
	const unmatchedAfter = [...afterElements];

	// Pass 1: Exact composite fingerprint match (tag, role, type, and exact text/aria)
	for (let i = unmatchedBefore.length - 1; i >= 0; i--) {
		const b = unmatchedBefore[i];
		const fpB = makeElementFingerprint(b);

		const aIdx = unmatchedAfter.findIndex(a => makeElementFingerprint(a) === fpB);
		if (aIdx !== -1) {
			const a = unmatchedAfter[aIdx];
			matched.push({ before: b, after: a });
			unmatchedBefore.splice(i, 1);
			unmatchedAfter.splice(aIdx, 1);
		}
	}

	// Pass 2: Explicit element_ref match (same candidate node whose state or text updated)
	for (let i = unmatchedBefore.length - 1; i >= 0; i--) {
		const b = unmatchedBefore[i];
		if (!b.element_ref) continue;

		const aIdx = unmatchedAfter.findIndex(a => a.element_ref === b.element_ref && a.tag === b.tag);
		if (aIdx !== -1) {
			const a = unmatchedAfter[aIdx];
			matched.push({ before: b, after: a });
			unmatchedBefore.splice(i, 1);
			unmatchedAfter.splice(aIdx, 1);
		}
	}

	// Pass 3: Semantic fuzzy match (tag + normalized text or aria-label substring)
	for (let i = unmatchedBefore.length - 1; i >= 0; i--) {
		const b = unmatchedBefore[i];
		const textB = normalizeText(b.visible_text || b.aria_label);
		if (!textB) continue;

		const aIdx = unmatchedAfter.findIndex(a => {
			const textA = normalizeText(a.visible_text || a.aria_label);
			return a.tag === b.tag && textA && (textA === textB || textA.includes(textB) || textB.includes(textA));
		});

		if (aIdx !== -1) {
			const a = unmatchedAfter[aIdx];
			matched.push({ before: b, after: a });
			unmatchedBefore.splice(i, 1);
			unmatchedAfter.splice(aIdx, 1);
		}
	}

	// Pass 4: Price container match (when both elements contain prices and share tag/role or total/price semantics)
	for (let i = unmatchedBefore.length - 1; i >= 0; i--) {
		const b = unmatchedBefore[i];
		const textB = b.visible_text || b.aria_label || "";
		const priceB = parsePrice(textB, b.element_ref || b.role || b.tag || "");
		if (!priceB) continue;

		const aIdx = unmatchedAfter.findIndex(a => {
			const textA = a.visible_text || a.aria_label || "";
			const priceA = parsePrice(textA, a.element_ref || a.role || a.tag || "");
			return Boolean(priceA) && (a.tag === b.tag || a.role === b.role || textA.toLowerCase().includes("price") || textA.toLowerCase().includes("total"));
		});

		if (aIdx !== -1) {
			const a = unmatchedAfter[aIdx];
			matched.push({ before: b, after: a });
			unmatchedBefore.splice(i, 1);
			unmatchedAfter.splice(aIdx, 1);
		}
	}

	return {
		matched,
		removed: unmatchedBefore,
		added: unmatchedAfter
	};
}

// =========================================================
// DETERMINISTIC DIFF ENGINE
// =========================================================

/**
 * Compares pre-action and post-action snapshots to produce deterministic change signals.
 *
 * @param {Object} snapshotBefore - Pre-action snapshot.
 * @param {Object} snapshotAfter - Post-action snapshot.
 * @param {Object} [context] - Interaction context (route, event_indices, etc.).
 * @returns {{ diff_signals: Array<Object>, evidence: Array<Object> }}
 */
function diffSnapshots(snapshotBefore = {}, snapshotAfter = {}, context = {}) {
	const signals = [];
	const beforeElements = (snapshotBefore && Array.isArray(snapshotBefore.elements)) ? snapshotBefore.elements : [];
	const afterElements = (snapshotAfter && Array.isArray(snapshotAfter.elements)) ? snapshotAfter.elements : [];

	const route = context.route || snapshotAfter.route || snapshotBefore.route || "/";
	const eventIndices = Array.isArray(context.event_indices) ? context.event_indices : [0];
	const provenance = {
		timestamp: snapshotAfter.timestamp || new Date().toISOString(),
		page_load_id: context.page_load_id || null,
		session_id: context.session_id || null,
		tab_id: context.tab_id || null
	};

	const { matched, removed, added } = matchElements(beforeElements, afterElements);

	// ---------------------------------------------------------
	// 1. DETECT ELEMENT ADDITIONS (Fee injection, Modal, Confirmation)
	// ---------------------------------------------------------
	added.forEach(el => {
		if (isNoiseElement(el)) return;
		const text = el.visible_text || el.aria_label || "";
		const normText = normalizeText(text);

		// Fee Added
		const hasFeeKeyword = containsAny(normText, FEE_KEYWORDS);
		const hasFeeExclusion = containsAny(normText, FEE_EXCLUSIONS);

		if (hasFeeKeyword && !hasFeeExclusion) {
			const parsed = parsePrice(text);
			signals.push({
				type: "post_action_fee_added",
				detected: true,
				strength: "strong",
				reason: `Additional fee element "${text}" appeared after interaction without prior disclosure.`,
				element_ref: el.element_ref,
				event_indices: eventIndices,
				route,
				dom_properties: {
					before: null,
					after: {
						text,
						amount: parsed ? parsed.amount : null,
						currency: parsed ? parsed.currency : null,
						tag: el.tag
					}
				},
				provenance
			});
			return; // Avoid double-counting fee as modal text
		}

		// Modal Appearance
		if (el.is_modal || containsAny(normText, ["cancel subscription", "keep plan", "are you sure", "special offer", "don't leave"])) {
			const isRetentionModal = containsAny(normText, ["save", "discount", "offer", "keep", "stay", "pause", "before you go"]);
			const isConfirmModal = containsAny(normText, ["are you sure", "confirm", "really want to"]);

			if (isConfirmModal) {
				signals.push({
					type: "post_action_confirmation_ui",
					detected: true,
					strength: "moderate",
					reason: `Confirmation prompt "${text}" appeared post-action.`,
					element_ref: el.element_ref,
					event_indices: eventIndices,
					route,
					dom_properties: {
						before: null,
						after: {
							text,
							tag: el.tag,
							is_modal: true
						}
					},
					provenance
				});
			} else if (isRetentionModal || el.is_modal) {
				signals.push({
					type: "post_action_modal_appeared",
					detected: true,
					strength: isRetentionModal ? "strong" : "moderate",
					reason: `Modal dialog with text "${text.slice(0, 60)}" appeared post-interaction.`,
					element_ref: el.element_ref,
					event_indices: eventIndices,
					route,
					dom_properties: {
						before: null,
						after: {
							text,
							tag: el.tag,
							is_modal: true
						}
					},
					provenance
				});
			}
		}

		// Preselected Commercial Add-on in added elements
		if (el.checked_state === true) {
			const isCommercial = containsAny(normText, COMMERCIAL_ADDON_KEYWORDS);
			const isBenign = containsAny(normText, BENIGN_PRESELECT_KEYWORDS);
			if (isCommercial && !isBenign) {
				const reasonKey = classifyCommercialReason(normText);
				signals.push({
					type: "post_action_preselection",
					detected: true,
					strength: "strong",
					reason: `Commercial add-on "${text}" appeared in a pre-checked state post-interaction.`,
					element_ref: el.element_ref,
					event_indices: eventIndices,
					route,
					dom_properties: {
						before: null,
						after: { checked: true, label: text, commercial_reason: reasonKey }
					},
					provenance
				});
				return;
			}
		}

		// Mandatory Acknowledgements or Required Survey
		if (el.is_required && containsAny(normText, ["reason", "survey", "feedback", "why are you leaving", "acknowledge"])) {
			signals.push({
				type: "post_action_required_step",
				detected: true,
				strength: "moderate",
				reason: `Required form field or survey "${text}" appeared post-action.`,
				element_ref: el.element_ref,
				event_indices: eventIndices,
				route,
				dom_properties: {
					before: null,
					after: {
						text,
						tag: el.tag,
						is_required: true
					}
				},
				provenance
			});
		}
	});

	// ---------------------------------------------------------
	// 2. DETECT ELEMENT REMOVALS (Meaningful decision alternatives disappeared)
	// ---------------------------------------------------------
	removed.forEach(el => {
		if (isNoiseElement(el)) return;
		const text = el.visible_text || el.aria_label || "";
		const isRejection = containsAny(text, REJECTION_KEYWORDS);

		if (isRejection && el.is_visible) {
			signals.push({
				type: "post_action_alternative_removed",
				detected: true,
				strength: "strong",
				reason: `Cancellation/decline choice "${text}" was removed or disappeared from the DOM after interaction.`,
				element_ref: el.element_ref,
				event_indices: eventIndices,
				route,
				dom_properties: {
					before: {
						text,
						tag: el.tag,
						role: el.role
					},
					after: null
				},
				provenance
			});
		}
	});

	// ---------------------------------------------------------
	// 3. DETECT STATE MUTATIONS ON MATCHED ELEMENTS
	// ---------------------------------------------------------
	matched.forEach(({ before, after }) => {
		const textBefore = before.visible_text || before.aria_label || "";
		const textAfter = after.visible_text || after.aria_label || "";
		const ref = after.element_ref || before.element_ref;

		// A. PRESELECTION STATE MUTATION (unchecked -> checked)
		if (before.checked_state === false && after.checked_state === true) {
			const label = textAfter || textBefore;
			const isCommercial = containsAny(label, COMMERCIAL_ADDON_KEYWORDS);
			const isBenign = containsAny(label, BENIGN_PRESELECT_KEYWORDS);

			if (isCommercial && !isBenign) {
				const reasonKey = classifyCommercialReason(label);
				signals.push({
					type: "post_action_preselection",
					detected: true,
					strength: "strong",
					reason: `Commercial add-on "${label}" automatically toggled from unchecked to checked post-interaction.`,
					element_ref: ref,
					event_indices: eventIndices,
					route,
					dom_properties: {
						before: { checked: false, label },
						after: { checked: true, label, commercial_reason: reasonKey }
					},
					provenance
				});
				return; // Suppress redundant attribute mutation signals
			}
		}

		// B. ACTION DISABLEMENT (enabled -> disabled on rejection actions)
		if (before.is_disabled === false && after.is_disabled === true) {
			const label = textAfter || textBefore;
			const isRejection = containsAny(label, REJECTION_KEYWORDS);

			if (isRejection) {
				signals.push({
					type: "post_action_action_disabled",
					detected: true,
					strength: "strong",
					reason: `Cancellation/decline alternative "${label}" became disabled after interaction.`,
					element_ref: ref,
					event_indices: eventIndices,
					route,
					dom_properties: {
						before: { disabled: false, label },
						after: { disabled: true, label }
					},
					provenance
				});
				return;
			}
		}

		// C. ALTERNATIVE HIDDEN (visible: true -> visible: false)
		if (before.is_visible === true && after.is_visible === false) {
			const label = textBefore || textAfter;
			const isRejection = containsAny(label, REJECTION_KEYWORDS);

			if (isRejection) {
				signals.push({
					type: "post_action_alternative_removed",
					detected: true,
					strength: "strong",
					reason: `Cancellation/decline choice "${label}" became visually hidden post-action.`,
					element_ref: ref,
					event_indices: eventIndices,
					route,
					dom_properties: {
						before: { is_visible: true, label },
						after: { is_visible: false, label }
					},
					provenance
				});
				return;
			}
		}

		// D. PRICE CHANGE ON MATCHED PRICE CONTAINER
		const priceB = parsePrice(textBefore, before.element_ref || before.role || before.tag || "");
		const priceA = parsePrice(textAfter, after.element_ref || after.role || after.tag || "");

		if (priceB && priceA && priceB.amount !== priceA.amount) {
			const isIncrease = priceA.amount > priceB.amount;
			signals.push({
				type: "post_action_price_changed",
				detected: true,
				strength: isIncrease ? "strong" : "moderate",
				reason: `Visible price changed from ${priceB.formatted} to ${priceA.formatted} post-interaction.`,
				element_ref: ref,
				event_indices: eventIndices,
				route,
				dom_properties: {
					before: {
						text: textBefore,
						amount: priceB.amount,
						currency: priceB.currency
					},
					after: {
						text: textAfter,
						amount: priceA.amount,
						currency: priceA.currency,
						price_increased: isIncrease
					}
				},
				provenance
			});
		}
	});

	// ---------------------------------------------------------
	// 4. SCROLL LOCK DETECTION
	// ---------------------------------------------------------
	if (snapshotBefore.scroll_locked === false && snapshotAfter.scroll_locked === true) {
		signals.push({
			type: "post_action_scroll_lock",
			detected: true,
			strength: "moderate",
			reason: "Page scrolling was locked (overflow: hidden) following interaction.",
			element_ref: "BODY::ctx(page)",
			event_indices: eventIndices,
			route,
			dom_properties: {
				before: { scroll_locked: false },
				after: { scroll_locked: true }
			},
			provenance
		});
	}

	// ---------------------------------------------------------
	// 5. SIGNAL DEDUPLICATION & EVIDENCE STRUCTURING
	// ---------------------------------------------------------
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
		diff_signals: uniqueSignals,
		evidence
	};
}

// =========================================================
// EXPORTS
// =========================================================

if (typeof module !== "undefined" && module.exports) {
	module.exports = {
		createSnapshot,
		matchElements,
		diffSnapshots,
		parsePrice,
		makeElementFingerprint
	};
}

if (typeof globalThis !== "undefined") {
	globalThis.createSnapshot = createSnapshot;
	globalThis.matchElements = matchElements;
	globalThis.diffSnapshots = diffSnapshots;
}
