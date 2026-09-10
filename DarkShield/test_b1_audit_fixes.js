/**
 * DarkShield Phase B1 - Post-Audit Verification Tests
 * Verifies all 10 requirements specified in the B1 Fix Phase:
 * 1. INPUT_CHANGE is not NAVIGATION
 * 2. PAGE_INIT is not NAVIGATION
 * 3. NAVIGATION remains NAVIGATION
 * 4. generic CLICK does not become NAVIGATION
 * 5. unknown action does not become NAVIGATION
 * 6. extension install initializes storage
 * 7. extension update preserves existing storage
 * 8. compound sensitive URL parameters are sanitized
 * 9. session pruning removes old sessions
 * 10. active session is preserved during pruning
 */

const assert = require("assert");
const path = require("path");
const fs = require("fs");
const vm = require("vm");

const { classifyAction, analyzeBehavior } = require("./extension/analyzer/analyzer.js");
const { isSensitiveParam, sanitizeRoute, pruneSessions, MAX_SESSIONS } = require("./extension/background.js");

const backgroundSource = fs.readFileSync(path.join(__dirname, "extension", "background.js"), "utf8");
const rulesSource = fs.readFileSync(path.join(__dirname, "extension", "analyzer", "rules.js"), "utf8");
const analyzerSource = fs.readFileSync(path.join(__dirname, "extension", "analyzer", "analyzer.js"), "utf8");

let passedCount = 0;
let failedCount = 0;

async function runTest(name, fn) {
	try {
		await fn();
		console.log(`✓ PASS: ${name}`);
		passedCount++;
	} catch (err) {
		console.error(`✗ FAIL: ${name}\n  Error: ${err.message}`);
		failedCount++;
	}
}

function createMockBackground(initialStorage = {}) {
	const storage = { ...initialStorage };
	let onInstalledListener = null;

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
				onMessage: { addListener: () => {} },
				onInstalled: {
					addListener: fn => { onInstalledListener = fn; }
				}
			},
			tabs: {
				onRemoved: { addListener: () => {} }
			}
		}
	};

	vm.createContext(context);
	vm.runInContext(rulesSource, context);
	vm.runInContext(analyzerSource, context);
	vm.runInContext(backgroundSource, context);

	return {
		storage,
		async triggerInstall(details) {
			if (onInstalledListener) {
				await onInstalledListener(details);
			}
		}
	};
}

async function runAll() {
	console.log("\n==================================================");
	console.log("RUNNING DARKSHIELD PHASE B1 AUDIT FIX VERIFICATION");
	console.log("==================================================\n");

	// 1. INPUT_CHANGE is not NAVIGATION
	await runTest("1. INPUT_CHANGE is not NAVIGATION", () => {
		const actionType = classifyAction({ action: "INPUT_CHANGE", element: { tag: "INPUT", type: "checkbox" } });
		assert.notStrictEqual(actionType, "NAVIGATION", "INPUT_CHANGE must not be classified as NAVIGATION");
		assert.strictEqual(actionType, "INPUT_CHANGE", "INPUT_CHANGE should be classified as INPUT_CHANGE");
	});

	// 2. PAGE_INIT is not NAVIGATION
	await runTest("2. PAGE_INIT is not NAVIGATION", () => {
		const actionType = classifyAction({ action: "PAGE_INIT" });
		assert.notStrictEqual(actionType, "NAVIGATION", "PAGE_INIT must not be classified as NAVIGATION");
		assert.strictEqual(actionType, "PAGE_INIT", "PAGE_INIT should be preserved as PAGE_INIT");
	});

	// 3. NAVIGATION remains NAVIGATION
	await runTest("3. NAVIGATION remains NAVIGATION", () => {
		const actionType = classifyAction({ action: "NAVIGATION" });
		assert.strictEqual(actionType, "NAVIGATION", "NAVIGATION must remain NAVIGATION");
	});

	// 4. generic CLICK does not become NAVIGATION
	await runTest("4. generic CLICK does not become NAVIGATION", () => {
		const actionWithText = classifyAction({ action: "CLICK", text: "Read Documentation", element: { tag: "BUTTON", text: "Read Documentation" } });
		assert.notStrictEqual(actionWithText, "NAVIGATION", "generic CLICK with text must not become NAVIGATION");
		assert.strictEqual(actionWithText, "CLICK", "generic CLICK should remain CLICK");

		const actionWithoutText = classifyAction({ action: "CLICK", text: "", element: null });
		assert.notStrictEqual(actionWithoutText, "NAVIGATION", "generic CLICK without text must not become NAVIGATION");
		assert.strictEqual(actionWithoutText, "CLICK", "generic CLICK without text should remain CLICK");
	});

	// 5. unknown action does not become NAVIGATION
	await runTest("5. unknown action does not become NAVIGATION", () => {
		const customAction = classifyAction({ action: "CUSTOM_GESTURE" });
		assert.notStrictEqual(customAction, "NAVIGATION", "unknown action must not become NAVIGATION");
		assert.strictEqual(customAction, "CUSTOM_GESTURE", "unknown action should retain its identifier");

		const emptyAction = classifyAction({ action: "" });
		assert.notStrictEqual(emptyAction, "NAVIGATION", "empty action must not become NAVIGATION");
	});

	// 6. extension install initializes storage
	await runTest("6. extension install initializes storage", async () => {
		const bg = createMockBackground({});
		await bg.triggerInstall({ reason: "install" });
		await new Promise(r => setTimeout(r, 50));

		assert(Array.isArray(bg.storage.behaviorEvents), "behaviorEvents must be initialized to an array");
		assert.strictEqual(bg.storage.behaviorEvents.length, 0);
		assert(bg.storage.behaviorAnalysis != null, "behaviorAnalysis must be initialized");
		assert.strictEqual(typeof bg.storage.behaviorSessions, "object", "behaviorSessions must be an object");
		assert.strictEqual(Object.keys(bg.storage.behaviorSessions).length, 0, "behaviorSessions must be empty");
		assert.strictEqual(typeof bg.storage.behaviorTabSessions, "object", "behaviorTabSessions must be an object");
		assert.strictEqual(Object.keys(bg.storage.behaviorTabSessions).length, 0, "behaviorTabSessions must be empty");
	});

	// 7. extension update preserves existing storage
	await runTest("7. extension update preserves existing storage", async () => {
		const preExistingSessions = {
			"session-existing-1": {
				session_id: "session-existing-1",
				event_count: 5,
				last_activity: Date.now()
			}
		};
		const preExistingEvents = [
			{ event_id: "evt-123", action: "CLICK", text: "Cancel Subscription" }
		];
		const preExistingAnalysis = {
			riskScore: 50,
			overallSeverity: "MEDIUM"
		};
		const preExistingTabSessions = { "101": "session-existing-1" };

		const bg = createMockBackground({
			behaviorEvents: preExistingEvents,
			behaviorAnalysis: preExistingAnalysis,
			behaviorSessions: preExistingSessions,
			behaviorTabSessions: preExistingTabSessions
		});

		await bg.triggerInstall({ reason: "update" });
		await new Promise(r => setTimeout(r, 50));

		assert.strictEqual(bg.storage.behaviorEvents.length, 1, "Existing events must be preserved on update");
		assert.strictEqual(bg.storage.behaviorEvents[0].event_id, "evt-123");
		assert.strictEqual(bg.storage.behaviorAnalysis.riskScore, 50, "Existing analysis must be preserved on update");
		assert(bg.storage.behaviorSessions["session-existing-1"] != null, "Existing session must be preserved on update");
		assert.strictEqual(bg.storage.behaviorTabSessions["101"], "session-existing-1", "Existing tabSession mapping preserved");
	});

	// 8. compound sensitive URL parameters are sanitized
	await runTest("8. compound sensitive URL parameters are sanitized", () => {
		const compoundParams = [
			"session_id", "sessionId", "user_email", "phone_number",
			"authToken", "reset_token", "verification_code",
			"api_key", "access_token", "refresh_token", "password", "otp"
		];

		compoundParams.forEach(param => {
			assert(isSensitiveParam(param), `Parameter '${param}' must be recognized as sensitive`);
		});

		// Harmless params must be preserved
		const harmlessParams = ["page", "sort", "category", "country_code", "currency_code", "author", "product_id"];
		harmlessParams.forEach(param => {
			assert(!isSensitiveParam(param), `Harmless parameter '${param}' must not be flagged sensitive`);
		});

		const urlWithSensitive = "https://example.com/account/settings?session_id=secret123&user_email=consumer@test.com&authToken=tok999&page=2&sort=desc";
		const sanitized = sanitizeRoute(urlWithSensitive);

		assert(!sanitized.includes("session_id"), "session_id should be removed");
		assert(!sanitized.includes("secret123"), "secret123 value should be removed");
		assert(!sanitized.includes("user_email"), "user_email should be removed");
		assert(!sanitized.includes("consumer@test.com"), "email value should be removed");
		assert(!sanitized.includes("authToken"), "authToken should be removed");
		assert(!sanitized.includes("tok999"), "tok999 value should be removed");
		assert(sanitized.includes("page=2"), "Safe parameter page=2 should be retained");
		assert(sanitized.includes("sort=desc"), "Safe parameter sort=desc should be retained");
	});

	// 9. session pruning removes old sessions
	await runTest("9. session pruning removes old sessions", () => {
		const sessions = {};
		const now = Date.now();
		// Create 25 closed sessions
		for (let i = 0; i < 25; i++) {
			sessions[`session_${i}`] = {
				session_id: `session_${i}`,
				last_activity: now + (i * 1000), // session_0 is oldest, session_24 is newest
				closed_at: new Date().toISOString()
			};
		}
		const tabSessions = { "10": "session_24" }; // session_24 is active
		const pruned = pruneSessions(sessions, tabSessions);

		const keys = Object.keys(pruned);
		assert.strictEqual(keys.length, MAX_SESSIONS, `Pruned sessions must equal MAX_SESSIONS (${MAX_SESSIONS})`);
		// Oldest sessions (0 to 4) should be pruned
		assert(!pruned["session_0"], "Oldest session session_0 should be pruned");
		assert(!pruned["session_1"], "Oldest session session_1 should be pruned");
		assert(!pruned["session_2"], "Oldest session session_2 should be pruned");
		assert(!pruned["session_3"], "Oldest session session_3 should be pruned");
		assert(!pruned["session_4"], "Oldest session session_4 should be pruned");
		// Newest sessions should be retained
		assert(pruned["session_24"], "Newest session session_24 should be retained");
		assert(pruned["session_23"], "Newest session session_23 should be retained");
	});

	// 10. active session is preserved during pruning
	await runTest("10. active session is preserved during pruning", () => {
		const sessions = {};
		const now = Date.now();
		// Create 25 sessions where session_0 is the OLDEST
		for (let i = 0; i < 25; i++) {
			sessions[`session_${i}`] = {
				session_id: `session_${i}`,
				last_activity: now + (i * 1000)
			};
		}
		// Crucial: session_0 is the oldest, but it is currently mapped to an active tab!
		const tabSessions = { "99": "session_0" };
		const pruned = pruneSessions(sessions, tabSessions);

		assert(pruned["session_0"] != null, "Active session session_0 MUST be preserved even if it is the oldest");
		assert(Object.keys(pruned).length <= MAX_SESSIONS, "Total sessions should not exceed MAX_SESSIONS");
	});

	console.log("\n==================================================");
	console.log(`TEST RESULTS: ${passedCount} PASSED, ${failedCount} FAILED (TOTAL: ${passedCount + failedCount})`);
	console.log("==================================================\n");

	if (failedCount > 0) {
		process.exit(1);
	}
}

runAll();
