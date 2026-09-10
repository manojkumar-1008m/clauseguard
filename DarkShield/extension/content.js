(() => {
	const INTERACTIVE_SELECTOR = 'button, a, [role="button"], input[type="button"], input[type="submit"], input[type="checkbox"], input[type="radio"]';
	const MAX_TEXT_LENGTH = 200;
	const MAX_ARIA_LENGTH = 160;
	const SENSITIVE_PARAM_REGEX = /^(?:token|password|passwd|pwd|email|phone|session|auth|code|otp|key|secret|api_key|access_token|refresh_token)$/i;

	function isSensitiveParam(paramKey) {
		if (!paramKey) return false;
		const key = String(paramKey).trim();
		if (SENSITIVE_PARAM_REGEX.test(key)) return true;
		const lower = key.toLowerCase();
		if (/(?:^|[_-])(?:password|passwd|pwd|email|phone|session|auth|token|otp|secret|api_?key|access_?token|refresh_?token)(?:$|[_-])/i.test(key)) {
			return true;
		}
		if (/^(?:sessionId|userEmail|phoneNumber|authToken|resetToken|verificationCode|apiKey|accessToken|refreshToken|csrfToken|cardNum|cardNumber)$/i.test(key)) {
			return true;
		}
		if (lower.includes("password") || lower.includes("passwd") || lower.includes("token") || lower.includes("secret") || lower.includes("apikey") || lower.includes("api_key")) {
			return true;
		}
		if (/session[_-]?id/i.test(key) || /(?:^|[_-])email[_-]?(?:address|id)?(?:$|[_-])/i.test(key) || /(?:^|[_-])phone[_-]?(?:number|num)?(?:$|[_-])/i.test(key) || /verification[_-]?code/i.test(key) || /(?:^|[_-])auth[_-]?(?:token|code|id|key)?(?:$|[_-])/i.test(key)) {
			return true;
		}
		return false;
	}

	const PAGE_LOAD_ID = (globalThis.crypto && typeof globalThis.crypto.randomUUID === "function")
		? globalThis.crypto.randomUUID()
		: `page-${Date.now()}-${Math.random().toString(16).slice(2)}`;

	function cleanText(value, maxLength = MAX_TEXT_LENGTH) {
		return String(value || "").replace(/\s+/g, " ").trim().slice(0, maxLength);
	}

	function interactiveLabel(element) {
		return cleanText(
			element?.getAttribute("aria-label")
			|| element?.innerText
			|| element?.textContent
			|| ""
		);
	}

	function isVisible(element) {
		if (!element || !(element instanceof Element)) return false;
		const styles = window.getComputedStyle(element);
		const bounds = element.getBoundingClientRect();
		return styles.display !== "none"
			&& styles.visibility !== "hidden"
			&& styles.opacity !== "0"
			&& bounds.width > 0
			&& bounds.height > 0;
	}

	function isDisabled(element) {
		return Boolean(element?.disabled)
			|| element?.getAttribute("aria-disabled") === "true";
	}

	function elementContext(element) {
		if (!element || !(element instanceof Element)) return null;
		const tag = element.tagName.toUpperCase();
		const rawType = element.getAttribute("type");
		const type = rawType ? cleanText(rawType, 40).toLowerCase() : null;
		const isInput = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
		return {
			tag,
			role: cleanText(element.getAttribute("role"), 80) || null,
			text: isInput ? "" : interactiveLabel(element),
			aria_label: cleanText(element.getAttribute("aria-label"), MAX_ARIA_LENGTH) || null,
			visible: isVisible(element),
			disabled: isDisabled(element),
			type: type || null
		};
	}

	function sanitizeSearchString(search) {
		if (!search || search === "?") return "";
		try {
			const params = new URLSearchParams(search);
			const safeParams = new URLSearchParams();
			params.forEach((val, key) => {
				if (!isSensitiveParam(key)) {
					safeParams.append(key, val);
				}
			});
			const safeStr = safeParams.toString();
			return safeStr ? `?${safeStr}` : "";
		} catch {
			return "";
		}
	}

	function sanitizedUrl() {
		return `${window.location.origin}${window.location.pathname}`.slice(0, 500);
	}

	function sanitizedRoute() {
		const safeSearch = sanitizeSearchString(window.location.search);
		const hash = window.location.hash || "";
		return `${window.location.pathname}${safeSearch}${hash}` || "/";
	}

	let lastRecordedRoute = sanitizedRoute();

	function getContainerType(element) {
		if (!element || typeof element.closest !== "function") return "page";
		try {
			if (element.closest("dialog, [role='dialog']")) return "dialog";
			if (element.closest(".modal, [class*='modal'], [id*='modal'], [role='alertdialog']")) return "modal";
			if (element.closest("form")) return "form";
		} catch {
			return "page";
		}
		return "page";
	}

	function getChildOrder(element) {
		if (!element || !element.parentElement) return 1;
		try {
			const siblings = Array.from(element.parentElement.children || []);
			const idx = siblings.indexOf(element);
			return idx >= 0 ? idx + 1 : 1;
		} catch {
			return 1;
		}
	}

	function buildElementRef(tag, role, label, containerType, order = 1) {
		const cleanTag = String(tag || "ELEMENT").toUpperCase();
		const cleanRole = role ? `::role(${cleanText(role, 40).toLowerCase()})` : "";
		const cleanLabel = label ? `::text(${cleanText(label, 30).toLowerCase()})` : "";
		const cleanContainer = containerType ? `::ctx(${cleanText(containerType, 20).toLowerCase()})` : "";
		const cleanOrder = `::ord(${Number(order) || 1})`;
		return `${cleanTag}${cleanRole}${cleanLabel}${cleanContainer}${cleanOrder}`;
	}

	function isAnimating(el) {
		try {
			if (el && typeof el.getAnimations === "function") {
				const anims = el.getAnimations();
				return anims.some(a => a.playState === "running");
			}
		} catch {}
		return false;
	}

	function parseComputedWeight(val) {
		if (!val) return 400;
		if (val === "bold") return 700;
		if (val === "normal") return 400;
		const n = parseInt(val, 10);
		return isNaN(n) ? 400 : n;
	}

	/**
	 * Computes an effective rendering opacity approximation by inspecting
	 * the element and up to 3 bounded ancestors (stopping at container/body boundaries).
	 * Note: CSS opacity creates a stacking context rather than being inherited,
	 * but visually scales composite alpha of descendants.
	 */
	function getEffectiveOpacity(el, elementOpacity) {
		let eff = typeof elementOpacity === "number" ? elementOpacity : 1.0;
		if (!el || !el.parentElement) return eff;
		let curr = el.parentElement;
		let depth = 0;
		while (curr && depth < 3) {
			if (curr === document.body || curr === document.documentElement) break;
			try {
				const cs = window.getComputedStyle(curr);
				const parentOp = parseFloat(cs.opacity);
				if (!isNaN(parentOp)) {
					eff *= parentOp;
				}
				if (cs.position === "fixed" || curr.tagName === "DIALOG" || curr.classList?.contains("modal")) {
					break;
				}
			} catch {}
			curr = curr.parentElement;
			depth++;
		}
		return Number(Math.max(0, Math.min(1, eff)).toFixed(2));
	}

	function extractVisualProperties(el) {
		if (!el || !(el instanceof Element)) return null;
		try {
			const cs = window.getComputedStyle(el);
			const rawOpacity = parseFloat(cs.opacity);
			const opacity = !isNaN(rawOpacity) ? Number(rawOpacity.toFixed(2)) : 1.0;
			const effectiveOpacity = getEffectiveOpacity(el, opacity);
			const fontSize = parseFloat(cs.fontSize) || null;
			const fontWeight = parseComputedWeight(cs.fontWeight);
			const rawLineHeight = parseFloat(cs.lineHeight);
			const lineHeight = !isNaN(rawLineHeight) ? Number(rawLineHeight.toFixed(2)) : null;
			const color = cleanText(cs.color, 40) || null;
			const bgColor = cleanText(cs.backgroundColor, 40) || null;
			const pointerEvents = cleanText(cs.pointerEvents, 20) || null;
			const cursor = cleanText(cs.cursor, 20) || null;
			const position = cleanText(cs.position, 20) || null;
			const rawZ = parseInt(cs.zIndex, 10);
			const zIndex = !isNaN(rawZ) ? rawZ : null;
			const animating = isAnimating(el);

			return {
				opacity,
				effective_opacity: effectiveOpacity,
				font_size_px: fontSize,
				font_weight: fontWeight,
				line_height: lineHeight,
				color,
				background_color: bgColor,
				pointer_events: pointerEvents,
				cursor,
				position,
				z_index: zIndex,
				is_animating: animating
			};
		} catch {
			return null;
		}
	}

	function extractCompetingActions(element) {
		if (!element || typeof element.closest !== "function") return [];
		const container = element.closest("dialog, [role='dialog'], form, .modal, [class*='modal'], [class*='dialog'], [role='group']") || element.parentElement;
		if (!container || typeof container.querySelectorAll !== "function") return [];

		const competing = [];
		try {
			// Bounded scan: limit candidate competing actions to top 3 (max 4 total getComputedStyle calls per interaction)
			const candidates = container.querySelectorAll("button, a[href], [role='button'], input[type='button'], input[type='submit']");
			for (let i = 0; i < candidates.length && competing.length < 3; i++) {
				const cand = candidates[i];
				if (cand === element) continue;
				if (!(cand instanceof Element)) continue;

				const tag = cand.tagName.toUpperCase();
				const role = cleanText(cand.getAttribute("role"), 80) || (tag === "A" ? "link" : "button");
				const text = cleanText(interactiveLabel(cand), 80);
				if (!text) continue;

				const visible = isVisible(cand);
				const disabled = isDisabled(cand);
				let width = 0, height = 0, area = 0;
				try {
					const b = cand.getBoundingClientRect();
					width = Math.round(b.width || 0);
					height = Math.round(b.height || 0);
					area = Math.round(width * height);
				} catch {}

				const visual = extractVisualProperties(cand) || {};

				competing.push({
					tag,
					role,
					text,
					visible,
					disabled,
					width,
					height,
					area,
					font_size_px: visual.font_size_px || null,
					opacity: visual.opacity !== undefined ? visual.opacity : 1.0,
					effective_opacity: visual.effective_opacity !== undefined ? visual.effective_opacity : 1.0,
					font_weight: visual.font_weight || 400,
					line_height: visual.line_height || null,
					color: visual.color || null,
					background_color: visual.background_color || null,
					pointer_events: visual.pointer_events || null,
					cursor: visual.cursor || null,
					position: visual.position || null,
					z_index: visual.z_index || null,
					is_animating: visual.is_animating || false
				});
			}
		} catch {}
		return competing;
	}

	function scanPreselectedCommercialOptions() {
		if (typeof document?.querySelectorAll !== "function") return [];
		const preselected = [];
		try {
			const checkables = document.querySelectorAll("input[type='checkbox']:checked, input[type='radio']:checked, [role='checkbox'][aria-checked='true']");
			for (let i = 0; i < checkables.length && preselected.length < 6; i++) {
				const item = checkables[i];
				const label = cleanText(interactiveLabel(item) || item.getAttribute("name") || "", 80);
				const tag = String(item.tagName || "INPUT").toUpperCase();
				const type = item.getAttribute("type") || (tag === "INPUT" ? "checkbox" : null);
				const required = Boolean(item.required || item.getAttribute("aria-required") === "true");

				preselected.push({
					tag,
					type,
					text: label,
					checked: true,
					required
				});
			}
		} catch {}
		return preselected;
	}

	function buildDomContext(element, action) {
		const isInitOrNav = action === "PAGE_INIT" || action === "NAVIGATION";
		if (!element && isInitOrNav) {
			const preselected = scanPreselectedCommercialOptions();
			return preselected.length > 0 ? {
				container_type: "page",
				preselected_options: preselected
			} : null;
		}

		if (!element || !(element instanceof Element)) return null;

		const tag = element.tagName.toUpperCase();
		const rawType = element.getAttribute("type");
		const type = rawType ? cleanText(rawType, 40).toLowerCase() : null;
		const role = cleanText(element.getAttribute("role"), 80) || null;
		const isInput = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
		const visibleText = isInput ? "" : cleanText(interactiveLabel(element), 80);
		const ariaLabel = cleanText(element.getAttribute("aria-label"), 100) || null;
		const containerType = getContainerType(element);
		const order = getChildOrder(element);
		const elementRef = buildElementRef(tag, role, visibleText || ariaLabel, containerType, order);

		let width = 0, height = 0, area = 0;
		try {
			const b = element.getBoundingClientRect();
			width = Math.round(b.width || 0);
			height = Math.round(b.height || 0);
			area = Math.round(width * height);
		} catch {}

		const visual = extractVisualProperties(element) || {};

		const isCheckable = tag === "INPUT" && (type === "checkbox" || type === "radio");
		const checkedState = isCheckable ? Boolean(element.checked) : null;
		const isRequired = Boolean(element.required || element.getAttribute("aria-required") === "true");
		const competing = extractCompetingActions(element);

		return {
			element_ref: elementRef,
			tag,
			role,
			type,
			visible_text: visibleText,
			aria_label: ariaLabel,
			is_visible: isVisible(element),
			is_disabled: isDisabled(element),
			is_required: isRequired,
			checked_state: checkedState,
			geometry: { width, height, area },
			font_size_px: visual.font_size_px || null,
			opacity: visual.opacity !== undefined ? visual.opacity : 1.0,
			effective_opacity: visual.effective_opacity !== undefined ? visual.effective_opacity : 1.0,
			font_weight: visual.font_weight || 400,
			line_height: visual.line_height || null,
			color: visual.color || null,
			background_color: visual.background_color || null,
			pointer_events: visual.pointer_events || null,
			cursor: visual.cursor || null,
			position: visual.position || null,
			z_index: visual.z_index || null,
			is_animating: visual.is_animating || false,
			container_type: containerType,
			competing_actions: competing
		};
	}

	function collectEvent(action, element, extra = {}) {
		const context = elementContext(element);
		const domContext = buildDomContext(element, action);
		const eventData = {
			page_load_id: PAGE_LOAD_ID,
			timestamp: new Date().toISOString(),
			action,
			url: sanitizedUrl(),
			route: sanitizedRoute(),
			element: context,
			text: context?.text || "",
			...(domContext ? { dom_context: domContext } : {}),
			...extra
		};

		chrome.runtime.sendMessage({ type: "BEHAVIOR_EVENT", event: eventData });
	}

	function recordNavigation() {
		const currentRoute = sanitizedRoute();
		if (currentRoute !== lastRecordedRoute) {
			lastRecordedRoute = currentRoute;
			collectEvent("NAVIGATION", null);
		}
	}

	// Establish the page/session boundary. The background service worker assigns
	// the durable session_id and tab/window metadata.
	collectEvent("PAGE_INIT", null);

	document.addEventListener("click", event => {
		const target = event.target instanceof Element ? event.target : event.target?.parentElement;
		const element = target?.closest(INTERACTIVE_SELECTOR);
		if (!element || !isVisible(element)) return;

		let preSnapshot = null;
		try {
			if (typeof createSnapshot === "function") {
				preSnapshot = createSnapshot(document, { route: sanitizedRoute() });
			}
		} catch {}

		collectEvent("CLICK", element, {
			...(preSnapshot ? { snapshot_before: preSnapshot } : {})
		});

		// Bounded 200ms settle check for post-action changes
		if (preSnapshot) {
			setTimeout(() => {
				try {
					if (typeof createSnapshot === "function" && typeof diffSnapshots === "function") {
						const postSnapshot = createSnapshot(document, { route: sanitizedRoute() });
						const diffResult = diffSnapshots(preSnapshot, postSnapshot, {
							route: sanitizedRoute()
						});
						if (diffResult && diffResult.diff_signals && diffResult.diff_signals.length > 0) {
							chrome.runtime.sendMessage({
								type: "DOM_DIFF_EVENT",
								diff: diffResult,
								route: sanitizedRoute()
							});
						}
					}
				} catch {}
			}, 200);
		}
	}, true);

	document.addEventListener("change", event => {
		const target = event.target instanceof Element ? event.target : null;
		if (!target || !target.matches('input[type="checkbox"], input[type="radio"]')) return;
		if (!isVisible(target)) return;
		collectEvent("INPUT_CHANGE", target, {
			metadata: { checked: Boolean(target.checked) }
		});
	}, true);

	window.addEventListener("hashchange", recordNavigation);
	window.addEventListener("popstate", recordNavigation);

	// SPAs frequently change routes without emitting hashchange/popstate.
	// Wrap history methods without reading or modifying page data.
	const originalPushState = history.pushState;
	const originalReplaceState = history.replaceState;

	history.pushState = function (...args) {
		const result = originalPushState.apply(this, args);
		queueMicrotask(recordNavigation);
		return result;
	};

	history.replaceState = function (...args) {
		const result = originalReplaceState.apply(this, args);
		queueMicrotask(recordNavigation);
		return result;
	};
})();
