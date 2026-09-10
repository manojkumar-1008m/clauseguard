if (typeof importScripts === "function") {
	importScripts("analyzer/rules.js", "analyzer/analyzer.js", "analyzer/datasetMatcher.js", "analyzer/behaviorFeatures.js", "analyzer/behaviorSequence.js", "analyzer/domAnalyzer.js", "analyzer/journeyManager.js");
}

let JourneyManagerClass;
if (typeof JourneyManager !== "undefined") {
	JourneyManagerClass = JourneyManager.JourneyManager || JourneyManager;
} else if (typeof require === "function") {
	try {
		const jm = require("./analyzer/journeyManager");
		JourneyManagerClass = jm.JourneyManager || jm;
	} catch (e) {
		JourneyManagerClass = null;
	}
}
const journeyManager = JourneyManagerClass ? new JourneyManagerClass() : null;

const EVENTS_KEY = "behaviorEvents";
const ANALYSIS_KEY = "behaviorAnalysis";
const SESSIONS_KEY = "behaviorSessions";
const TAB_SESSIONS_KEY = "behaviorTabSessions";
const JOURNEYS_KEY = "behaviorJourneys";
const MAX_EVENTS = 500;
const MAX_SESSIONS = 20;
const SESSION_TIMEOUT_MS = 30 * 60 * 1000;
let eventWriteQueue = Promise.resolve();

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
	evidence: [],
	dataset_matches: [],
	features: {
		totalSteps: 0,
		actionTypes: [],
		cancellationSteps: 0,
		repeatedPromptCount: 0,
		retentionInterference: { detected: false, count: 0 },
		forcedActionDetected: false,
		forcedActionType: null,
		meaningfulBacktracking: 0,
		cancellationDetected: false
	}
};

function getStorage(keys) {
	return new Promise(resolve => chrome.storage.local.get(keys, resolve));
}

function setStorage(value) {
	return new Promise((resolve, reject) => {
		chrome.storage.local.set(value, () => {
			if (chrome.runtime.lastError) reject(chrome.runtime.lastError);
			else resolve();
		});
	});
}

function makeId(prefix) {
	if (globalThis.crypto && typeof globalThis.crypto.randomUUID === "function") {
		return `${prefix}-${globalThis.crypto.randomUUID()}`;
	}
	return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

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

function sanitizeUrl(urlString) {
	if (!urlString) return "";
	try {
		const parsed = new URL(urlString);
		return `${parsed.origin}${parsed.pathname}`.slice(0, 500);
	} catch {
		return String(urlString).split("?")[0].split("#")[0].slice(0, 500);
	}
}

function sanitizeRoute(routeOrUrl) {
	if (!routeOrUrl) return "/";
	try {
		const path = String(routeOrUrl);
		if (path.startsWith("http://") || path.startsWith("https://")) {
			const parsed = new URL(path);
			const safeParams = new URLSearchParams();
			parsed.searchParams.forEach((val, key) => {
				if (!isSensitiveParam(key)) {
					safeParams.append(key, val);
				}
			});
			const query = safeParams.toString();
			return `${parsed.pathname}${query ? `?${query}` : ""}${parsed.hash || ""}` || "/";
		}
		const dummy = new URL(path.startsWith("/") ? `http://local${path}` : `http://local/${path}`);
		const safeParams = new URLSearchParams();
		dummy.searchParams.forEach((val, key) => {
			if (!isSensitiveParam(key)) {
				safeParams.append(key, val);
			}
		});
		const query = safeParams.toString();
		return `${dummy.pathname}${query ? `?${query}` : ""}${dummy.hash || ""}` || "/";
	} catch {
		return String(routeOrUrl).slice(0, 500);
	}
}

function sanitizeElement(element) {
	if (!element || typeof element !== "object") return null;
	const tag = String(element.tag || "").trim().toUpperCase() || null;
	const isInput = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
	// Strictly record metadata only for input/form elements - no typed values or form contents
	const text = isInput ? "" : String(element.text || "").replace(/\s+/g, " ").trim().slice(0, 200);
	return {
		tag,
		role: String(element.role || "").slice(0, 80) || null,
		text,
		aria_label: String(element.aria_label || "").replace(/\s+/g, " ").trim().slice(0, 160) || null,
		visible: Boolean(element.visible),
		disabled: Boolean(element.disabled),
		type: element.type ? String(element.type).slice(0, 40).toLowerCase() : null
	};
}

function sanitizeDomContext(dom) {
	if (!dom || typeof dom !== "object") return null;

	const clean = {
		element_ref: dom.element_ref ? String(dom.element_ref).slice(0, 160) : null,
		tag: dom.tag ? String(dom.tag).slice(0, 30).toUpperCase() : null,
		role: dom.role ? String(dom.role).slice(0, 50).toLowerCase() : null,
		type: dom.type ? String(dom.type).slice(0, 30).toLowerCase() : null,
		visible_text: dom.visible_text ? String(dom.visible_text).replace(/\s+/g, " ").trim().slice(0, 80) : "",
		aria_label: dom.aria_label ? String(dom.aria_label).replace(/\s+/g, " ").trim().slice(0, 100) : null,
		is_visible: Boolean(dom.is_visible),
		is_disabled: Boolean(dom.is_disabled || dom.disabled),
		is_required: Boolean(dom.is_required || dom.required),
		checked_state: typeof dom.checked_state === "boolean" ? dom.checked_state : null,
		geometry: dom.geometry && typeof dom.geometry === "object" ? {
			width: Number(dom.geometry.width) || 0,
			height: Number(dom.geometry.height) || 0,
			area: Number(dom.geometry.area) || 0
		} : null,
		font_size_px: typeof dom.font_size_px === "number" ? dom.font_size_px : null,
		opacity: typeof dom.opacity === "number" ? Number(dom.opacity.toFixed(2)) : null,
		effective_opacity: typeof dom.effective_opacity === "number" ? Number(dom.effective_opacity.toFixed(2)) : (typeof dom.opacity === "number" ? Number(dom.opacity.toFixed(2)) : null),
		font_weight: typeof dom.font_weight === "number" ? dom.font_weight : null,
		line_height: typeof dom.line_height === "number" ? Number(dom.line_height.toFixed(2)) : null,
		color: dom.color ? String(dom.color).slice(0, 40) : null,
		background_color: dom.background_color ? String(dom.background_color).slice(0, 40) : null,
		contrast_ratio: typeof dom.contrast_ratio === "number" ? Number(dom.contrast_ratio.toFixed(2)) : null,
		pointer_events: dom.pointer_events ? String(dom.pointer_events).slice(0, 20).toLowerCase() : null,
		cursor: dom.cursor ? String(dom.cursor).slice(0, 20).toLowerCase() : null,
		position: dom.position ? String(dom.position).slice(0, 20).toLowerCase() : null,
		z_index: typeof dom.z_index === "number" ? dom.z_index : null,
		is_animating: Boolean(dom.is_animating),
		container_type: dom.container_type ? String(dom.container_type).slice(0, 30).toLowerCase() : "page",
		competing_actions: Array.isArray(dom.competing_actions) ? dom.competing_actions.slice(0, 4).map(c => ({
			tag: c.tag ? String(c.tag).slice(0, 30).toUpperCase() : "BUTTON",
			role: c.role ? String(c.role).slice(0, 50).toLowerCase() : "button",
			text: c.text ? String(c.text).replace(/\s+/g, " ").trim().slice(0, 80) : "",
			visible: c.visible !== false,
			disabled: Boolean(c.disabled || c.is_disabled),
			width: Number(c.width) || 0,
			height: Number(c.height) || 0,
			area: Number(c.area) || 0,
			font_size_px: typeof c.font_size_px === "number" ? c.font_size_px : null,
			opacity: typeof c.opacity === "number" ? Number(c.opacity.toFixed(2)) : null,
			effective_opacity: typeof c.effective_opacity === "number" ? Number(c.effective_opacity.toFixed(2)) : (typeof c.opacity === "number" ? Number(c.opacity.toFixed(2)) : null),
			font_weight: typeof c.font_weight === "number" ? c.font_weight : null,
			line_height: typeof c.line_height === "number" ? Number(c.line_height.toFixed(2)) : null,
			color: c.color ? String(c.color).slice(0, 40) : null,
			background_color: c.background_color ? String(c.background_color).slice(0, 40) : null,
			contrast_ratio: typeof c.contrast_ratio === "number" ? Number(c.contrast_ratio.toFixed(2)) : null,
			pointer_events: c.pointer_events ? String(c.pointer_events).slice(0, 20).toLowerCase() : null,
			cursor: c.cursor ? String(c.cursor).slice(0, 20).toLowerCase() : null,
			position: c.position ? String(c.position).slice(0, 20).toLowerCase() : null,
			z_index: typeof c.z_index === "number" ? c.z_index : null,
			is_animating: Boolean(c.is_animating)
		})) : [],
		preselected_options: Array.isArray(dom.preselected_options) ? dom.preselected_options.slice(0, 6).map(o => ({
			tag: o.tag ? String(o.tag).slice(0, 30).toUpperCase() : "INPUT",
			type: o.type ? String(o.type).slice(0, 30).toLowerCase() : "checkbox",
			text: o.text ? String(o.text).replace(/\s+/g, " ").trim().slice(0, 80) : "",
			checked: Boolean(o.checked),
			required: Boolean(o.required)
		})) : []
	};

	if (dom.has_collapsed_alternative) clean.has_collapsed_alternative = true;
	if (dom.alternative_in_accordion) clean.alternative_in_accordion = true;
	if (dom.is_modal) clean.is_modal = true;
	if (typeof dom.has_close_button === "boolean") clean.has_close_button = dom.has_close_button;
	if (dom.has_confirm_shaming) clean.has_confirm_shaming = true;
	if (Array.isArray(dom.required_acknowledgements)) clean.required_acknowledgements = dom.required_acknowledgements;
	if (Array.isArray(dom.candidate_actions)) {
		clean.candidate_actions = dom.candidate_actions.slice(0, 15).map(c => ({
			tag: c.tag ? String(c.tag).slice(0, 30).toUpperCase() : "BUTTON",
			role: c.role ? String(c.role).slice(0, 50).toLowerCase() : "button",
			text: c.text || c.visible_text ? String(c.text || c.visible_text).replace(/\s+/g, " ").trim().slice(0, 80) : "",
			aria_label: c.aria_label ? String(c.aria_label).replace(/\s+/g, " ").trim().slice(0, 80) : null,
			element_ref: c.element_ref ? String(c.element_ref).slice(0, 120) : null,
			container_type: c.container_type || c.container ? String(c.container_type || c.container).slice(0, 30) : "page",
			visible: c.visible !== false && c.is_visible !== false,
			disabled: Boolean(c.disabled || c.is_disabled),
			area: Number(c.area) || 0,
			font_size_px: typeof c.font_size_px === "number" ? c.font_size_px : null,
			opacity: typeof c.opacity === "number" ? Number(c.opacity.toFixed(2)) : null,
			contrast_ratio: typeof c.contrast_ratio === "number" ? Number(c.contrast_ratio.toFixed(2)) : null
		}));
	}

	return clean;
}

function normalizeEvent(rawEvent, sender, sessionId) {
	const event = rawEvent && typeof rawEvent === "object" ? rawEvent : {};
	const action = String(event.action || "OTHER").toUpperCase();
	const element = sanitizeElement(event.element);
	const tag = element?.tag || "";
	const isInput = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
	const text = isInput ? "" : (element?.text || String(event.text || "").replace(/\s+/g, " ").trim().slice(0, 200));

	const normalized = {
		event_id: makeId("evt"),
		session_id: sessionId,
		page_load_id: String(event.page_load_id || "").slice(0, 100) || null,
		tab_id: sender?.tab?.id ?? null,
		window_id: sender?.tab?.windowId ?? null,
		timestamp: event.timestamp || new Date().toISOString(),
		action,
		url: sanitizeUrl(event.url),
		route: sanitizeRoute(event.route || event.url),
		element,
		text,
		metadata: event.metadata && typeof event.metadata === "object"
			? { checked: Boolean(event.metadata.checked) }
			: {}
	};

	if (event.dom_context) {
		normalized.dom_context = sanitizeDomContext(event.dom_context);
	}
	if (event.snapshot_before) normalized.snapshot_before = event.snapshot_before;
	if (event.snapshot_after) normalized.snapshot_after = event.snapshot_after;
	if (event.dom_diff) normalized.dom_diff = event.dom_diff;
	if (event.diff_signals) normalized.diff_signals = event.diff_signals;
	if (event.candidate_actions) normalized.candidate_actions = event.candidate_actions;
	if (event.cross_container_actions) normalized.cross_container_actions = event.cross_container_actions;
	if (event.journey_id) normalized.journey_id = String(event.journey_id);
	if (event.journey_stage) normalized.journey_stage = String(event.journey_stage);
	if (typeof event.is_auxiliary === "boolean") normalized.is_auxiliary = event.is_auxiliary;
	if (event.auxiliary_id) normalized.auxiliary_id = String(event.auxiliary_id);

	return normalized;
}

async function getSessionState() {
	const stored = await getStorage({
		[SESSIONS_KEY]: {},
		[TAB_SESSIONS_KEY]: {}
	});
	return {
		sessions: stored[SESSIONS_KEY] || {},
		tabSessions: stored[TAB_SESSIONS_KEY] || {}
	};
}

function pruneSessions(sessions, tabSessions) {
	if (!sessions || typeof sessions !== "object") return {};
	const sessionIds = Object.keys(sessions);
	if (sessionIds.length <= MAX_SESSIONS) return sessions;

	const activeSessionIds = new Set(Object.values(tabSessions || {}));
	const sorted = [...sessionIds].sort((a, b) => {
		const aTime = Number(sessions[a]?.last_activity || 0);
		const bTime = Number(sessions[b]?.last_activity || 0);
		return bTime - aTime;
	});

	const retained = {};
	let retainedCount = 0;

	// Always retain currently active sessions
	for (const id of sorted) {
		if (activeSessionIds.has(id)) {
			retained[id] = sessions[id];
			retainedCount++;
		}
	}

	// Retain most recent sessions up to MAX_SESSIONS
	for (const id of sorted) {
		if (retained[id]) continue;
		if (retainedCount < MAX_SESSIONS) {
			retained[id] = sessions[id];
			retainedCount++;
		}
	}

	return retained;
}

async function resolveSession(sender, event) {
	const { sessions, tabSessions } = await getSessionState();
	const tabId = sender?.tab?.id;
	const now = Date.now();
	const current = tabId != null ? tabSessions[String(tabId)] : null;

	if (!current || !sessions[current]
		|| now - Number(sessions[current].last_activity || 0) > SESSION_TIMEOUT_MS) {
		const sessionId = makeId("session");
		tabSessions[String(tabId)] = sessionId;
		sessions[sessionId] = {
			session_id: sessionId,
			tab_id: tabId ?? null,
			window_id: sender?.tab?.windowId ?? null,
			created_at: new Date().toISOString(),
			last_activity: now,
			event_count: 0,
			events: []
		};
		const pruned = pruneSessions(sessions, tabSessions);
		await setStorage({ [SESSIONS_KEY]: pruned, [TAB_SESSIONS_KEY]: tabSessions });
		return sessionId;
	}

	sessions[current].last_activity = now;
	sessions[current].event_count = Number(sessions[current].event_count || 0) + 1;
	await setStorage({ [SESSIONS_KEY]: sessions });
	return current;
}

async function getSessionEvents(sessionId) {
	const stored = await getStorage({ [SESSIONS_KEY]: {} });
	return Array.isArray(stored[SESSIONS_KEY]?.[sessionId]?.events)
		? stored[SESSIONS_KEY][sessionId].events
		: [];
}

async function storeEventAndAnalysis(event) {
	const existingEvents = await getSessionEvents(event.session_id);
	const events = [...existingEvents, event].slice(-MAX_EVENTS);
	const behaviorAnalysis = analyzeBehavior(events);
	const stored = await getStorage({ [SESSIONS_KEY]: {}, [TAB_SESSIONS_KEY]: {} });
	const sessions = stored[SESSIONS_KEY] || {};
	const tabSessions = stored[TAB_SESSIONS_KEY] || {};
	if (!sessions[event.session_id]) return;

	sessions[event.session_id].events = events;
	sessions[event.session_id].analysis = behaviorAnalysis;
	sessions[event.session_id].last_activity = Date.now();
	sessions[event.session_id].event_count = events.length;

	const pruned = pruneSessions(sessions, tabSessions);

	// Keep legacy keys so the existing popup and demo continue to work.
	await setStorage({
		[SESSIONS_KEY]: pruned,
		[EVENTS_KEY]: events,
		[ANALYSIS_KEY]: behaviorAnalysis
	});
}

if (typeof chrome !== "undefined" && chrome.runtime) {
	if (chrome.runtime.onMessage) {
		chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
			if (message?.type === "DOM_DIFF_EVENT" && message.diff) {
				eventWriteQueue = eventWriteQueue
					.then(async () => {
						const sessionId = await resolveSession(sender, { route: message.route });
						const stored = await getStorage({ [SESSIONS_KEY]: {} });
						const sessions = stored[SESSIONS_KEY] || {};
						if (sessions[sessionId]) {
							sessions[sessionId].diff_signals = [
								...(sessions[sessionId].diff_signals || []),
								...(message.diff.diff_signals || [])
							];
							await setStorage({ [SESSIONS_KEY]: sessions });
						}
						sendResponse({ stored: true });
					})
					.catch(error => {
						sendResponse({ stored: false, error: String(error?.message || error) });
					});
				return true;
			}

			if (message?.type !== "BEHAVIOR_EVENT" || !message.event) return;

			eventWriteQueue = eventWriteQueue
				.then(async () => {
					const sessionId = await resolveSession(sender, message.event);
					let rawEvent = { ...message.event };
					if (journeyManager) {
						const storedJourneys = await getStorage({ [JOURNEYS_KEY]: {} });
						const tabJourneys = storedJourneys[JOURNEYS_KEY] || {};
						const jResolution = journeyManager.resolveJourney(rawEvent, sender, sessionId, tabJourneys);
						await setStorage({ [JOURNEYS_KEY]: tabJourneys });
						rawEvent.journey_id = jResolution.journey_id;
						rawEvent.journey_stage = jResolution.journey_stage;
						rawEvent.is_auxiliary = Boolean(jResolution.is_auxiliary);
						if (jResolution.auxiliary_id) rawEvent.auxiliary_id = jResolution.auxiliary_id;
					}
					const event = normalizeEvent(rawEvent, sender, sessionId);
					await storeEventAndAnalysis(event);
					sendResponse({
						stored: true,
						session_id: sessionId,
						event_id: event.event_id,
						journey_id: event.journey_id || null,
						journey_stage: event.journey_stage || null
					});
				})
				.catch(error => {
					console.error("Behavior event storage failed:", error);
					sendResponse({ stored: false, error: String(error?.message || error) });
				});
			return true;
		});
	}

	if (chrome.tabs?.onRemoved) {
		chrome.tabs.onRemoved.addListener(tabId => {
			eventWriteQueue = eventWriteQueue.then(async () => {
				const stored = await getStorage({
					[SESSIONS_KEY]: {},
					[TAB_SESSIONS_KEY]: {}
				});
				const sessions = stored[SESSIONS_KEY] || {};
				const tabSessions = stored[TAB_SESSIONS_KEY] || {};
				const sessionId = tabSessions[String(tabId)];
				delete tabSessions[String(tabId)];
				if (sessionId && sessions[sessionId]) {
					sessions[sessionId].closed_at = new Date().toISOString();
				}
				const pruned = pruneSessions(sessions, tabSessions);
				await setStorage({ [SESSIONS_KEY]: pruned, [TAB_SESSIONS_KEY]: tabSessions });
			}).catch(error => console.error("Session cleanup failed:", error));
		});
	}

	if (chrome.runtime.onInstalled) {
		chrome.runtime.onInstalled.addListener(async details => {
			const stored = await getStorage({
				[EVENTS_KEY]: null,
				[ANALYSIS_KEY]: null,
				[SESSIONS_KEY]: null,
				[TAB_SESSIONS_KEY]: null
			});
			const updates = {};
			if (stored[EVENTS_KEY] == null) updates[EVENTS_KEY] = [];
			if (stored[ANALYSIS_KEY] == null) updates[ANALYSIS_KEY] = EMPTY_ANALYSIS;
			if (stored[SESSIONS_KEY] == null) updates[SESSIONS_KEY] = {};
			if (stored[TAB_SESSIONS_KEY] == null) updates[TAB_SESSIONS_KEY] = {};
			if (Object.keys(updates).length > 0) {
				await setStorage(updates);
			}
		});
	}
}

if (typeof module !== "undefined" && module.exports) {
	module.exports = {
		makeId,
		isSensitiveParam,
		sanitizeUrl,
		sanitizeRoute,
		sanitizeElement,
		sanitizeDomContext,
		normalizeEvent,
		pruneSessions,
		resolveSession,
		storeEventAndAnalysis,
		journeyManager,
		JOURNEYS_KEY,
		MAX_SESSIONS,
		SESSION_TIMEOUT_MS,
		MAX_EVENTS
	};
}
