/**
 * DarkShield Phase B1 - Comprehensive 19-Point Test Suite
 * Validates:
 *  1. Event schema validation
 *  2. Unique event_id
 *  3. Unique session_id
 *  4. page_load_id generation
 *  5. Tab/session isolation
 *  6. Multiple tabs simultaneously
 *  7. 500-event session limit
 *  8. Session timeout (30 min inactivity)
 *  9. Tab cleanup on close
 * 10. PAGE_INIT event
 * 11. CLICK event
 * 12. INPUT_CHANGE event
 * 13. pushState navigation
 * 14. replaceState navigation
 * 15. popstate navigation
 * 16. hashchange navigation & deduplication
 * 17. Sensitive input protection
 * 18. URL & route sanitization
 * 19. Existing Behavior Analyzer compatibility
 */

const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const analyzerPath = path.join(__dirname, "extension", "analyzer", "analyzer.js");
const rulesPath = path.join(__dirname, "extension", "analyzer", "rules.js");
const contentPath = path.join(__dirname, "extension", "content.js");
const backgroundPath = path.join(__dirname, "extension", "background.js");

const analyzerSource = fs.readFileSync(analyzerPath, "utf8");
const rulesSource = fs.readFileSync(rulesPath, "utf8");
const contentSource = fs.readFileSync(contentPath, "utf8");
const backgroundSource = fs.readFileSync(backgroundPath, "utf8");

const { classifyAction, analyzeBehavior } = require(analyzerPath);
const { isSensitiveParam, sanitizeRoute, pruneSessions, MAX_SESSIONS } = require(backgroundPath);

let passedCount = 0;
let failedCount = 0;
const testResults = [];

async function runTest(name, fn) {
	try {
		await fn();
		console.log(`✓ PASS: ${name}`);
		passedCount++;
		testResults.push({ name, status: "PASS" });
	} catch (err) {
		console.error(`✗ FAIL: ${name}\n  Error: ${err.message}`);
		failedCount++;
		testResults.push({ name, status: "FAIL", error: err.message });
	}
}

// -------------------------------------------------------------
// Helper: Create background service worker sandbox
// -------------------------------------------------------------
function createBackgroundContext() {
	const storage = {
		behaviorEvents: [],
		behaviorAnalysis: null,
		behaviorSessions: {},
		behaviorTabSessions: {}
	};

	const messageListeners = [];
	const tabRemovedListeners = [];

	const context = {
		console,
		URL,
		URLSearchParams,
		Date,
		Math,
		Promise,
		Set,
		Array,
		Object,
		String,
		Boolean,
		Number,
		importScripts: () => {},
		chrome: {
			storage: {
				local: {
					get(keys, cb) {
						let result = {};
						if (Array.isArray(keys)) {
							keys.forEach(k => { result[k] = storage[k]; });
						} else if (typeof keys === "object" && keys !== null) {
							Object.keys(keys).forEach(k => {
								result[k] = storage[k] !== undefined ? storage[k] : keys[k];
							});
						} else if (typeof keys === "string") {
							result[keys] = storage[keys];
						} else {
							result = { ...storage };
						}
						Promise.resolve().then(() => cb(result));
					},
					set(items, cb) {
						Object.assign(storage, items);
						if (cb) Promise.resolve().then(() => cb());
					}
				}
			},
			runtime: {
				onMessage: {
					addListener(fn) { messageListeners.push(fn); }
				},
				onInstalled: {
					addListener(fn) { Promise.resolve().then(() => fn()); }
				}
			},
			tabs: {
				onRemoved: {
					addListener(fn) { tabRemovedListeners.push(fn); }
				}
			}
		}
	};

	vm.createContext(context);
	vm.runInContext(rulesSource, context);
	vm.runInContext(analyzerSource, context);
	vm.runInContext(backgroundSource, context);

	return {
		context,
		storage,
		async sendMessage(message, sender) {
			for (const listener of messageListeners) {
				await new Promise(resolve => {
					listener(message, sender, resolve);
				});
			}
		},
		async removeTab(tabId) {
			for (const listener of tabRemovedListeners) {
				listener(tabId);
			}
			await new Promise(r => setTimeout(r, 50));
		}
	};
}

// -------------------------------------------------------------
// Helper: Create content script sandbox
// -------------------------------------------------------------
function createContentContext(initialUrl = "https://example.com/account?token=secret123&page=1#section") {
	const sentMessages = [];
	const listeners = {};

	const parsedUrl = new URL(initialUrl);

	const location = {
		origin: parsedUrl.origin,
		pathname: parsedUrl.pathname,
		search: parsedUrl.search,
		hash: parsedUrl.hash,
		href: initialUrl
	};

	const history = {
		pushState(state, title, url) {
			if (url) {
				const next = new URL(url, location.href);
				location.origin = next.origin;
				location.pathname = next.pathname;
				location.search = next.search;
				location.hash = next.hash;
				location.href = next.href;
			}
		},
		replaceState(state, title, url) {
			if (url) {
				const next = new URL(url, location.href);
				location.origin = next.origin;
				location.pathname = next.pathname;
				location.search = next.search;
				location.hash = next.hash;
				location.href = next.href;
			}
		}
	};

	class MockElement {
		constructor(tagName, attributes = {}, text = "") {
			this.tagName = tagName.toUpperCase();
			this.attributes = { ...attributes };
			this.innerText = text;
			this.textContent = text;
			this.checked = Boolean(attributes.checked);
			this.disabled = Boolean(attributes.disabled);
		}
		getAttribute(name) { return this.attributes[name] ?? null; }
		closest(selector) { return this; }
		getBoundingClientRect() { return { width: 100, height: 30 }; }
		matches(sel) {
			if (sel.includes("checkbox") && this.attributes.type === "checkbox") return true;
			if (sel.includes("radio") && this.attributes.type === "radio") return true;
			return false;
		}
	}

	const context = {
		console,
		URL,
		URLSearchParams,
		Date,
		Math,
		Promise,
		queueMicrotask: fn => Promise.resolve().then(fn),
		window: {
			location,
			addEventListener(evt, fn) {
				listeners[evt] = listeners[evt] || [];
				listeners[evt].push(fn);
			},
			getComputedStyle() {
				return { display: "block", visibility: "visible", opacity: "1" };
			}
		},
		document: {
			addEventListener(evt, fn) {
				listeners[evt] = listeners[evt] || [];
				listeners[evt].push(fn);
			}
		},
		history,
		Element: MockElement,
		chrome: {
			runtime: {
				sendMessage(msg) { sentMessages.push(msg); }
			}
		}
	};

	vm.createContext(context);
	vm.runInContext(contentSource, context);

	return {
		context,
		sentMessages,
		listeners,
		location,
		history,
		MockElement,
		trigger(evt, eventObj) {
			const arr = (listeners[evt] || []);
			arr.forEach(fn => fn(eventObj));
		}
	};
}

async function runAll() {
	console.log("\n==================================================");
	console.log("RUNNING DARKSHIELD PHASE B1 COMPREHENSIVE TESTS");
	console.log("==================================================\n");

	// -------------------------------------------------------------
	// Test 1: Event Schema Validation
	// -------------------------------------------------------------
	await runTest("1. Event schema validation (all required fields and types)", async () => {
		const bg = createBackgroundContext();
		await bg.sendMessage({
			type: "BEHAVIOR_EVENT",
			event: {
				page_load_id: "page-xyz-123",
				action: "CLICK",
				url: "https://example.com/account",
				route: "/account",
				element: {
					tag: "BUTTON",
					role: "button",
					text: "Cancel Subscription",
					aria_label: "Cancel Subscription",
					visible: true,
					disabled: false,
					type: null
				}
			}
		}, { tab: { id: 101, windowId: 202 } });

		const events = bg.storage.behaviorEvents;
		assert.strictEqual(events.length, 1);
		const evt = events[0];

		// Verify required top-level fields
		assert.ok(typeof evt.event_id === "string" && evt.event_id.length > 0, "event_id missing or invalid");
		assert.ok(typeof evt.session_id === "string" && evt.session_id.length > 0, "session_id missing or invalid");
		assert.strictEqual(evt.page_load_id, "page-xyz-123", "page_load_id mismatch");
		assert.strictEqual(evt.tab_id, 101, "tab_id mismatch");
		assert.strictEqual(evt.window_id, 202, "window_id mismatch");
		assert.ok(!isNaN(Date.parse(evt.timestamp)), "timestamp is not ISO-8601");
		assert.strictEqual(evt.action, "CLICK");
		assert.strictEqual(evt.url, "https://example.com/account");
		assert.strictEqual(evt.route, "/account");

		// Verify element schema
		assert.ok(evt.element && typeof evt.element === "object", "element is not an object");
		assert.strictEqual(evt.element.tag, "BUTTON");
		assert.strictEqual(evt.element.role, "button");
		assert.strictEqual(evt.element.text, "Cancel Subscription");
		assert.strictEqual(evt.element.aria_label, "Cancel Subscription");
		assert.strictEqual(evt.element.visible, true);
		assert.strictEqual(evt.element.disabled, false);
		assert.strictEqual(evt.element.type, null);
	});

	// -------------------------------------------------------------
	// Test 2: Unique event_id
	// -------------------------------------------------------------
	await runTest("2. Unique event_id generation", async () => {
		const bg = createBackgroundContext();
		const eventIds = new Set();
		for (let i = 0; i < 50; i++) {
			await bg.sendMessage({
				type: "BEHAVIOR_EVENT",
				event: { action: "CLICK", element: { tag: "BUTTON", text: `Btn ${i}` } }
			}, { tab: { id: 10, windowId: 1 } });
		}
		const events = bg.storage.behaviorEvents;
		assert.strictEqual(events.length, 50);
		events.forEach(e => eventIds.add(e.event_id));
		assert.strictEqual(eventIds.size, 50, "Generated duplicate event_id values");
	});

	// -------------------------------------------------------------
	// Test 3: Unique session_id
	// -------------------------------------------------------------
	await runTest("3. Unique session_id generation", async () => {
		const bg = createBackgroundContext();
		for (let tabId = 1; tabId <= 10; tabId++) {
			await bg.sendMessage({
				type: "BEHAVIOR_EVENT",
				event: { action: "PAGE_INIT" }
			}, { tab: { id: tabId, windowId: 1 } });
		}
		const sessions = Object.values(bg.storage.behaviorSessions);
		assert.strictEqual(sessions.length, 10);
		const sessionIds = new Set(sessions.map(s => s.session_id));
		assert.strictEqual(sessionIds.size, 10, "Multiple tabs received duplicate session_id");
	});

	// -------------------------------------------------------------
	// Test 4: page_load_id generation
	// -------------------------------------------------------------
	await runTest("4. page_load_id generation", async () => {
		const c1 = createContentContext();
		const c2 = createContentContext();
		const id1 = c1.sentMessages[0].event.page_load_id;
		const id2 = c2.sentMessages[0].event.page_load_id;
		assert.ok(typeof id1 === "string" && id1.length > 0, "c1 page_load_id missing");
		assert.ok(typeof id2 === "string" && id2.length > 0, "c2 page_load_id missing");
		assert.notStrictEqual(id1, id2, "Independent page loads generated identical page_load_id");
	});

	// -------------------------------------------------------------
	// Test 5: Tab/session isolation
	// -------------------------------------------------------------
	await runTest("5. Tab/session isolation (Session A never sees Session B events)", async () => {
		const bg = createBackgroundContext();
		// Tab 10 events
		await bg.sendMessage({ type: "BEHAVIOR_EVENT", event: { action: "CLICK", text: "Tab10-A1" } }, { tab: { id: 10 } });
		await bg.sendMessage({ type: "BEHAVIOR_EVENT", event: { action: "CLICK", text: "Tab10-A2" } }, { tab: { id: 10 } });

		// Tab 20 events
		await bg.sendMessage({ type: "BEHAVIOR_EVENT", event: { action: "CLICK", text: "Tab20-B1" } }, { tab: { id: 20 } });
		await bg.sendMessage({ type: "BEHAVIOR_EVENT", event: { action: "CLICK", text: "Tab20-B2" } }, { tab: { id: 20 } });

		const tab10SessionId = bg.storage.behaviorTabSessions["10"];
		const tab20SessionId = bg.storage.behaviorTabSessions["20"];

		const session10 = bg.storage.behaviorSessions[tab10SessionId];
		const session20 = bg.storage.behaviorSessions[tab20SessionId];

		assert.strictEqual(session10.events.length, 2);
		assert.strictEqual(session20.events.length, 2);

		const texts10 = session10.events.map(e => e.text);
		const texts20 = session20.events.map(e => e.text);

		assert.ok(!texts10.includes("Tab20-B1") && !texts10.includes("Tab20-B2"), "Tab 10 received Tab 20 events");
		assert.ok(!texts20.includes("Tab10-A1") && !texts20.includes("Tab10-A2"), "Tab 20 received Tab 10 events");
	});

	// -------------------------------------------------------------
	// Test 6: Multiple tabs simultaneously
	// -------------------------------------------------------------
	await runTest("6. Multiple tabs active simultaneously with interleaved events", async () => {
		const bg = createBackgroundContext();
		const tabs = [100, 200, 300];

		// Interleaved events across tabs
		for (let i = 0; i < 30; i++) {
			const tabId = tabs[i % tabs.length];
			await bg.sendMessage({
				type: "BEHAVIOR_EVENT",
				event: { action: "CLICK", text: `Click-tab-${tabId}-${i}` }
			}, { tab: { id: tabId } });
		}

		tabs.forEach(tabId => {
			const sid = bg.storage.behaviorTabSessions[String(tabId)];
			const session = bg.storage.behaviorSessions[sid];
			assert.strictEqual(session.events.length, 10, `Tab ${tabId} should have exactly 10 events`);
			session.events.forEach(e => {
				assert.strictEqual(e.tab_id, tabId, `Event in session ${sid} has incorrect tab_id`);
				assert.ok(e.text.includes(`Click-tab-${tabId}`), `Cross-tab leakage found in tab ${tabId}`);
			});
		});
	});

	// -------------------------------------------------------------
	// Test 7: 500-event session limit
	// -------------------------------------------------------------
	await runTest("7. 500-event session limit enforced", async () => {
		const bg = createBackgroundContext();
		for (let i = 1; i <= 550; i++) {
			await bg.sendMessage({
				type: "BEHAVIOR_EVENT",
				event: { action: "CLICK", text: `Step-${i}` }
			}, { tab: { id: 77 } });
		}
		const sid = bg.storage.behaviorTabSessions["77"];
		const session = bg.storage.behaviorSessions[sid];
		assert.strictEqual(session.events.length, 500, "Session exceeded 500 events");
		assert.strictEqual(session.events[0].text, "Step-51", "Oldest events not properly pruned");
		assert.strictEqual(session.events[499].text, "Step-550", "Latest event not present");
	});

	// -------------------------------------------------------------
	// Test 8: Session timeout after 30 minutes
	// -------------------------------------------------------------
	await runTest("8. Session timeout expires after 30 minutes of inactivity", async () => {
		const bg = createBackgroundContext();
		await bg.sendMessage({ type: "BEHAVIOR_EVENT", event: { action: "PAGE_INIT" } }, { tab: { id: 88 } });
		const initialSessionId = bg.storage.behaviorTabSessions["88"];

		// Advance last_activity back 31 minutes
		const thirtyOneMinutesAgo = Date.now() - (31 * 60 * 1000);
		bg.storage.behaviorSessions[initialSessionId].last_activity = thirtyOneMinutesAgo;

		// Send next event
		await bg.sendMessage({ type: "BEHAVIOR_EVENT", event: { action: "CLICK", text: "Resume" } }, { tab: { id: 88 } });
		const newSessionId = bg.storage.behaviorTabSessions["88"];

		assert.notStrictEqual(initialSessionId, newSessionId, "Expired session was not replaced");
		assert.strictEqual(bg.storage.behaviorSessions[newSessionId].events.length, 1);
	});

	// -------------------------------------------------------------
	// Test 9: Tab cleanup
	// -------------------------------------------------------------
	await runTest("9. Tab cleanup removes tab-session mapping when tab closes", async () => {
		const bg = createBackgroundContext();
		await bg.sendMessage({ type: "BEHAVIOR_EVENT", event: { action: "PAGE_INIT" } }, { tab: { id: 99 } });
		assert.ok(bg.storage.behaviorTabSessions["99"], "Tab session mapping missing");

		await bg.removeTab(99);
		assert.strictEqual(bg.storage.behaviorTabSessions["99"], undefined, "Tab mapping not cleaned up");
	});

	// -------------------------------------------------------------
	// Test 10: PAGE_INIT event
	// -------------------------------------------------------------
	await runTest("10. PAGE_INIT event generated on load", async () => {
		const c = createContentContext();
		assert.ok(c.sentMessages.length >= 1, "No message sent on load");
		const initMsg = c.sentMessages[0];
		assert.strictEqual(initMsg.type, "BEHAVIOR_EVENT");
		assert.strictEqual(initMsg.event.action, "PAGE_INIT");
		assert.strictEqual(initMsg.event.element, null);
	});

	// -------------------------------------------------------------
	// Test 11: CLICK event
	// -------------------------------------------------------------
	await runTest("11. Structured CLICK event collection", async () => {
		const c = createContentContext();
		const btn = new c.MockElement("button", { "role": "button", "aria-label": "Cancel Service" }, "Cancel Service");
		c.trigger("click", { target: btn });

		const clickEvent = c.sentMessages.find(m => m.event.action === "CLICK");
		assert.ok(clickEvent, "CLICK event not emitted");
		assert.strictEqual(clickEvent.event.element.tag, "BUTTON");
		assert.strictEqual(clickEvent.event.element.role, "button");
		assert.strictEqual(clickEvent.event.element.text, "Cancel Service");
		assert.strictEqual(clickEvent.event.element.visible, true);
		assert.strictEqual(clickEvent.event.element.disabled, false);
	});

	// -------------------------------------------------------------
	// Test 12: INPUT_CHANGE event
	// -------------------------------------------------------------
	await runTest("12. Safe INPUT_CHANGE event tracks metadata only", async () => {
		const c = createContentContext();
		const checkbox = new c.MockElement("input", { type: "checkbox", checked: true, "aria-label": "Keep subscription" });
		c.trigger("change", { target: checkbox });

		const changeEvent = c.sentMessages.find(m => m.event.action === "INPUT_CHANGE");
		assert.ok(changeEvent, "INPUT_CHANGE event not emitted");
		assert.strictEqual(changeEvent.event.element.tag, "INPUT");
		assert.strictEqual(changeEvent.event.element.type, "checkbox");
		assert.strictEqual(changeEvent.event.metadata.checked, true);
		assert.strictEqual(changeEvent.event.element.text, "", "Input element should not have text value");
	});

	// -------------------------------------------------------------
	// Test 13: pushState navigation
	// -------------------------------------------------------------
	await runTest("13. pushState navigation event emitted on route change", async () => {
		const c = createContentContext("https://example.com/step1");
		const initialMsgCount = c.sentMessages.length;

		c.history.pushState({}, "", "/step2");
		await new Promise(r => setImmediate(r));

		const navEvents = c.sentMessages.slice(initialMsgCount).filter(m => m.event.action === "NAVIGATION");
		assert.strictEqual(navEvents.length, 1, "Expected exactly 1 NAVIGATION event");
		assert.strictEqual(navEvents[0].event.route, "/step2");
	});

	// -------------------------------------------------------------
	// Test 14: replaceState navigation
	// -------------------------------------------------------------
	await runTest("14. replaceState navigation event emitted on route change", async () => {
		const c = createContentContext("https://example.com/step2");
		const initialMsgCount = c.sentMessages.length;

		c.history.replaceState({}, "", "/step3");
		await new Promise(r => setImmediate(r));

		const navEvents = c.sentMessages.slice(initialMsgCount).filter(m => m.event.action === "NAVIGATION");
		assert.strictEqual(navEvents.length, 1, "Expected exactly 1 NAVIGATION event");
		assert.strictEqual(navEvents[0].event.route, "/step3");
	});

	// -------------------------------------------------------------
	// Test 15: popstate navigation
	// -------------------------------------------------------------
	await runTest("15. popstate navigation event", async () => {
		const c = createContentContext("https://example.com/step3");
		const initialMsgCount = c.sentMessages.length;

		c.location.pathname = "/step4";
		c.trigger("popstate", {});

		const navEvents = c.sentMessages.slice(initialMsgCount).filter(m => m.event.action === "NAVIGATION");
		assert.strictEqual(navEvents.length, 1, "Expected NAVIGATION on popstate");
		assert.strictEqual(navEvents[0].event.route, "/step4");
	});

	// -------------------------------------------------------------
	// Test 16: hashchange navigation & deduplication
	// -------------------------------------------------------------
	await runTest("16. hashchange navigation and duplicate suppression", async () => {
		const c = createContentContext("https://example.com/page");
		const initialMsgCount = c.sentMessages.length;

		c.location.hash = "#section1";
		c.trigger("hashchange", {});

		let navEvents = c.sentMessages.slice(initialMsgCount).filter(m => m.event.action === "NAVIGATION");
		assert.strictEqual(navEvents.length, 1, "Expected NAVIGATION on first hashchange");

		// Trigger again without route change -> should be suppressed
		c.trigger("hashchange", {});
		navEvents = c.sentMessages.slice(initialMsgCount).filter(m => m.event.action === "NAVIGATION");
		assert.strictEqual(navEvents.length, 1, "Duplicate navigation event was not suppressed");
	});

	// -------------------------------------------------------------
	// Test 17: Sensitive input protection
	// -------------------------------------------------------------
	await runTest("17. Sensitive input values are never captured", async () => {
		const c = createContentContext();
		const pwdInput = new c.MockElement("input", {
			type: "password",
			value: "SuperSecretPassword123!",
			name: "pwd",
			id: "password"
		}, "SuperSecretPassword123!");

		c.trigger("click", { target: pwdInput });

		// Check messages
		c.sentMessages.forEach(msg => {
			const str = JSON.stringify(msg);
			assert.ok(!str.includes("SuperSecretPassword123!"), "Sensitive password string captured!");
		});

		// Check background normalization does not leak sensitive text on inputs
		const bg = createBackgroundContext();
		await bg.sendMessage({
			type: "BEHAVIOR_EVENT",
			event: {
				action: "CLICK",
				element: {
					tag: "INPUT",
					type: "password",
					text: "SecretPassword"
				}
			}
		}, { tab: { id: 1 } });

		const evt = bg.storage.behaviorEvents[0];
		assert.strictEqual(evt.element.text, "", "Input element text not cleared in background");
		assert.strictEqual(evt.text, "", "Top-level text not cleared for sensitive input");
	});

	// -------------------------------------------------------------
	// Test 18: URL sanitization
	// -------------------------------------------------------------
	await runTest("18. URL sanitization removes sensitive query params", async () => {
		const c = createContentContext("https://shop.example.com/checkout?token=xyz987&email=user@test.com&ref=banner&auth=session123#final");
		const initMsg = c.sentMessages[0].event;

		assert.strictEqual(initMsg.url, "https://shop.example.com/checkout");
		assert.ok(!initMsg.route.includes("token=xyz987"), "token query param was not stripped from route");
		assert.ok(!initMsg.route.includes("email="), "email query param was not stripped from route");
		assert.ok(!initMsg.route.includes("auth="), "auth query param was not stripped from route");
		assert.ok(initMsg.route.includes("ref=banner"), "Safe query param was erroneously removed");

		// Also verify background sanitizes incoming URLs and routes
		const bg = createBackgroundContext();
		await bg.sendMessage({
			type: "BEHAVIOR_EVENT",
			event: {
				action: "CLICK",
				url: "https://example.com/account?password=mypassword&session=active",
				route: "/account?password=mypassword&code=123456&tab=billing#history"
			}
		}, { tab: { id: 1 } });

		const stored = bg.storage.behaviorEvents[0];
		assert.strictEqual(stored.url, "https://example.com/account");
		assert.ok(!stored.route.includes("password="), "password param present in stored route");
		assert.ok(!stored.route.includes("code="), "code param present in stored route");
		assert.ok(stored.route.includes("tab=billing"), "safe route param missing");
	});

	// -------------------------------------------------------------
	// Test 19: Existing Behavior Analyzer compatibility
	// -------------------------------------------------------------
	await runTest("19. Existing Behavior Analyzer backward and structured schema compatibility", async () => {
		const vmContext = {
			console,
			URL,
			require: undefined,
			ANALYZER_RULES: undefined
		};
		vm.createContext(vmContext);
		vm.runInContext(rulesSource, vmContext);
		vm.runInContext(analyzerSource, vmContext);

		// Test with new structured events
		const structuredEvents = [
			{
				event_id: "evt-1",
				session_id: "s-1",
				action: "CLICK",
				route: "/account",
				url: "https://example.com/account",
				element: { tag: "BUTTON", role: "button", text: "Cancel Subscription", visible: true, disabled: false }
			},
			{
				event_id: "evt-2",
				session_id: "s-1",
				action: "NAVIGATION",
				route: "/cancel",
				url: "https://example.com/cancel",
				element: null
			},
			{
				event_id: "evt-3",
				session_id: "s-1",
				action: "CLICK",
				route: "/cancel",
				url: "https://example.com/cancel",
				element: { tag: "BUTTON", role: "button", text: "Confirm Cancellation", visible: true, disabled: false }
			}
		];

		const structuredResult = vmContext.analyzeBehavior(structuredEvents);
		assert.ok(structuredResult, "Structured result is null");
		assert.strictEqual(structuredResult.intent.type, "CANCEL");
		assert.strictEqual(structuredResult.features.cancellationSteps, 2);

		// Test with legacy flat events
		const legacyEvents = [
			{ timestamp: "1", action: "CLICK", element: "BUTTON", text: "Cancel Subscription", url: "#cancel" },
			{ timestamp: "2", action: "NAVIGATION", element: "document", text: "", url: "#cancel" },
			{ timestamp: "3", action: "CLICK", element: "BUTTON", text: "Confirm Cancellation", url: "#confirm" }
		];

		const legacyResult = vmContext.analyzeBehavior(legacyEvents);
		assert.ok(legacyResult, "Legacy result is null");
		assert.strictEqual(legacyResult.intent.type, "CANCEL");
		assert.strictEqual(legacyResult.features.cancellationSteps, 2);
	});

	// 20. Action Semantics: INPUT_CHANGE does not become NAVIGATION
	await runTest("20. Action Semantics: INPUT_CHANGE does not become NAVIGATION", async () => {
		const actionType = classifyAction({ action: "INPUT_CHANGE", element: { tag: "INPUT", type: "checkbox" } });
		assert.notStrictEqual(actionType, "NAVIGATION", "INPUT_CHANGE must not be classified as NAVIGATION");
		assert.strictEqual(actionType, "INPUT_CHANGE", "INPUT_CHANGE should be classified as INPUT_CHANGE");
	});

	// 21. Action Semantics: PAGE_INIT does not become NAVIGATION
	await runTest("21. Action Semantics: PAGE_INIT does not become NAVIGATION", async () => {
		const actionType = classifyAction({ action: "PAGE_INIT" });
		assert.notStrictEqual(actionType, "NAVIGATION", "PAGE_INIT must not be classified as NAVIGATION");
		assert.strictEqual(actionType, "PAGE_INIT", "PAGE_INIT should be preserved as PAGE_INIT");
	});

	// 22. Action Semantics: NAVIGATION remains NAVIGATION
	await runTest("22. Action Semantics: NAVIGATION remains NAVIGATION", async () => {
		const actionType = classifyAction({ action: "NAVIGATION" });
		assert.strictEqual(actionType, "NAVIGATION", "NAVIGATION must remain NAVIGATION");
	});

	// 23. Action Semantics: generic CLICK does not become NAVIGATION
	await runTest("23. Action Semantics: generic CLICK does not become NAVIGATION", async () => {
		const actionWithText = classifyAction({ action: "CLICK", text: "Read Documentation", element: { tag: "BUTTON", text: "Read Documentation" } });
		assert.notStrictEqual(actionWithText, "NAVIGATION", "generic CLICK with text must not become NAVIGATION");
		assert.strictEqual(actionWithText, "CLICK", "generic CLICK should remain CLICK");

		const actionWithoutText = classifyAction({ action: "CLICK", text: "", element: null });
		assert.notStrictEqual(actionWithoutText, "NAVIGATION", "generic CLICK without text must not become NAVIGATION");
		assert.strictEqual(actionWithoutText, "CLICK", "generic CLICK without text should remain CLICK");
	});

	// 24. Action Semantics: unknown action does not become NAVIGATION
	await runTest("24. Action Semantics: unknown action does not become NAVIGATION", async () => {
		const customAction = classifyAction({ action: "CUSTOM_GESTURE" });
		assert.notStrictEqual(customAction, "NAVIGATION", "unknown action must not become NAVIGATION");
		assert.strictEqual(customAction, "CUSTOM_GESTURE", "unknown action should retain its identifier");

		const emptyAction = classifyAction({ action: "" });
		assert.notStrictEqual(emptyAction, "NAVIGATION", "empty action must not become NAVIGATION");
	});

	// 25. Storage Safety: extension install initializes missing storage keys
	await runTest("25. Storage Safety: extension install initializes missing storage keys", async () => {
		let onInstalledListener = null;
		const storage = {};
		const context = {
			console, URL, URLSearchParams, Date, Math, Promise, Set, Array, Object, String, Boolean, Number,
			importScripts: () => {},
			chrome: {
				runtime: {
					onMessage: { addListener: () => {} },
					onInstalled: { addListener: fn => { onInstalledListener = fn; } }
				},
				tabs: { onRemoved: { addListener: () => {} } },
				storage: {
					local: {
						get(keys, cb) {
							const res = {};
							for (const k of Object.keys(keys)) {
								res[k] = storage[k] !== undefined ? storage[k] : keys[k];
							}
							cb(res);
						},
						set(items, cb) {
							Object.assign(storage, items);
							if (cb) cb();
						}
					}
				}
			}
		};
		vm.createContext(context);
		vm.runInContext(rulesSource, context);
		vm.runInContext(analyzerSource, context);
		vm.runInContext(backgroundSource, context);

		await onInstalledListener({ reason: "install" });
		assert(Array.isArray(storage.behaviorEvents), "behaviorEvents must be an array");
		assert.strictEqual(storage.behaviorEvents.length, 0);
		assert(storage.behaviorAnalysis != null, "behaviorAnalysis must be initialized");
		assert.strictEqual(typeof storage.behaviorSessions, "object", "behaviorSessions must be an object");
		assert.strictEqual(Object.keys(storage.behaviorSessions).length, 0, "behaviorSessions must be empty");
		assert.strictEqual(typeof storage.behaviorTabSessions, "object", "behaviorTabSessions must be an object");
		assert.strictEqual(Object.keys(storage.behaviorTabSessions).length, 0, "behaviorTabSessions must be empty");
	});

	// 26. Storage Safety: extension update preserves existing sessions and analysis
	await runTest("26. Storage Safety: extension update preserves existing sessions and analysis", async () => {
		let onInstalledListener = null;
		const storage = {
			behaviorEvents: [{ event_id: "evt-preserve-1" }],
			behaviorAnalysis: { riskScore: 75 },
			behaviorSessions: { "sess-1": { session_id: "sess-1" } },
			behaviorTabSessions: { "5": "sess-1" }
		};
		const context = {
			console, URL, URLSearchParams, Date, Math, Promise, Set, Array, Object, String, Boolean, Number,
			importScripts: () => {},
			chrome: {
				runtime: {
					onMessage: { addListener: () => {} },
					onInstalled: { addListener: fn => { onInstalledListener = fn; } }
				},
				tabs: { onRemoved: { addListener: () => {} } },
				storage: {
					local: {
						get(keys, cb) {
							const res = {};
							for (const k of Object.keys(keys)) {
								res[k] = storage[k] !== undefined ? storage[k] : keys[k];
							}
							cb(res);
						},
						set(items, cb) {
							Object.assign(storage, items);
							if (cb) cb();
						}
					}
				}
			}
		};
		vm.createContext(context);
		vm.runInContext(rulesSource, context);
		vm.runInContext(analyzerSource, context);
		vm.runInContext(backgroundSource, context);

		await onInstalledListener({ reason: "update" });
		assert.strictEqual(storage.behaviorEvents.length, 1);
		assert.strictEqual(storage.behaviorEvents[0].event_id, "evt-preserve-1");
		assert.strictEqual(storage.behaviorAnalysis.riskScore, 75);
		assert(storage.behaviorSessions["sess-1"] != null);
		assert.strictEqual(storage.behaviorTabSessions["5"], "sess-1");
	});

	// 27. Privacy: compound sensitive URL parameters are sanitized
	await runTest("27. Privacy: compound sensitive URL parameters are sanitized", async () => {
		const compoundParams = [
			"session_id", "sessionId", "user_email", "phone_number",
			"authToken", "reset_token", "verification_code",
			"api_key", "access_token", "refresh_token", "password", "otp"
		];
		compoundParams.forEach(p => {
			assert(isSensitiveParam(p), `Param '${p}' must be sensitive`);
		});

		const harmless = ["page", "sort", "category", "country_code", "currency_code", "author", "product_id"];
		harmless.forEach(h => {
			assert(!isSensitiveParam(h), `Param '${h}' must not be sensitive`);
		});

		const url = "https://example.com/checkout?session_id=s123&user_email=user@test.com&authToken=tok9&page=2&sort=asc";
		const sanitized = sanitizeRoute(url);
		assert(!sanitized.includes("session_id"), "session_id must be removed");
		assert(!sanitized.includes("s123"), "s123 must be removed");
		assert(!sanitized.includes("user_email"), "user_email must be removed");
		assert(!sanitized.includes("user@test.com"), "user@test.com must be removed");
		assert(!sanitized.includes("authToken"), "authToken must be removed");
		assert(!sanitized.includes("tok9"), "tok9 must be removed");
		assert(sanitized.includes("page=2"), "page=2 must be preserved");
		assert(sanitized.includes("sort=asc"), "sort=asc must be preserved");
	});

	// 28. Session Management: session pruning removes old closed sessions
	await runTest("28. Session Management: session pruning removes old closed sessions", async () => {
		const sessions = {};
		const now = Date.now();
		for (let i = 0; i < 25; i++) {
			sessions[`session_${i}`] = {
				session_id: `session_${i}`,
				last_activity: now + (i * 1000),
				closed_at: new Date().toISOString()
			};
		}
		const tabSessions = { "10": "session_24" };
		const pruned = pruneSessions(sessions, tabSessions);

		const keys = Object.keys(pruned);
		assert.strictEqual(keys.length, MAX_SESSIONS, `Pruned sessions must equal MAX_SESSIONS (${MAX_SESSIONS})`);
		assert(!pruned["session_0"], "Oldest session session_0 should be pruned");
		assert(!pruned["session_1"], "Oldest session session_1 should be pruned");
		assert(!pruned["session_2"], "Oldest session session_2 should be pruned");
		assert(!pruned["session_3"], "Oldest session session_3 should be pruned");
		assert(!pruned["session_4"], "Oldest session session_4 should be pruned");
		assert(pruned["session_24"], "Newest session session_24 should be retained");
		assert(pruned["session_23"], "Newest session session_23 should be retained");
	});

	// 29. Session Management: active sessions are preserved during pruning
	await runTest("29. Session Management: active sessions are preserved during pruning", async () => {
		const sessions = {};
		const now = Date.now();
		for (let i = 0; i < 25; i++) {
			sessions[`session_${i}`] = {
				session_id: `session_${i}`,
				last_activity: now + (i * 1000)
			};
		}
		// session_0 is the oldest, but it is active in tab 99
		const tabSessions = { "99": "session_0" };
		const pruned = pruneSessions(sessions, tabSessions);

		assert(pruned["session_0"] != null, "Active session session_0 must be preserved even if oldest");
		assert(Object.keys(pruned).length <= MAX_SESSIONS, "Total sessions must not exceed MAX_SESSIONS");
	});

	console.log("\n==================================================");
	console.log(`TEST RESULTS: ${passedCount} PASSED, ${failedCount} FAILED (TOTAL: ${passedCount + failedCount})`);
	console.log("==================================================\n");

	if (failedCount > 0) {
		process.exit(1);
	}
}

runAll().catch(err => {
	console.error("Test runner failed:", err);
	process.exit(1);
});
