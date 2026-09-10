/**
 * DarkShield Phase B2 - Behavioral Feature Extraction Test Suite
 *
 * Validates all 30 B2 behavioral features across 20 primary test scenarios
 * including positive detections and hard negative controls.
 */

const assert = require("assert");
const { extractBehaviorFeatures } = require("./extension/analyzer/behaviorFeatures.js");

let passedCount = 0;
let failedCount = 0;

function runTest(name, fn) {
	try {
		fn();
		console.log(`✓ PASS: ${name}`);
		passedCount++;
	} catch (err) {
		console.error(`✗ FAIL: ${name}\n  Error: ${err.message}`);
		failedCount++;
	}
}

console.log("\n==================================================");
console.log("RUNNING DARKSHIELD PHASE B2 FEATURE EXTRACTION TESTS");
console.log("==================================================\n");

// Helper to create timestamped events
function createEvent(action, text, route, extra = {}) {
	const now = Date.now();
	return {
		action,
		text,
		route,
		url: `https://example.com${route.startsWith("/") ? route : `/${route}`}`,
		timestamp: new Date(now + (extra.offsetMs || 0)).toISOString(),
		element: {
			tag: action === "INPUT_CHANGE" ? "INPUT" : "BUTTON",
			text,
			visible: true,
			disabled: Boolean(extra.disabled),
			...extra.element
		},
		...extra
	};
}

// 1. Normal Navigation
runTest("1. Normal Navigation (Positive & Hard Negative)", () => {
	// Normal browsing sequence
	const normalEvents = [
		createEvent("PAGE_INIT", "", "/home", { offsetMs: 0 }),
		createEvent("CLICK", "View Pricing", "/home", { offsetMs: 1000 }),
		createEvent("NAVIGATION", "", "/pricing", { offsetMs: 1500 }),
		createEvent("CLICK", "View Features", "/pricing", { offsetMs: 2500 }),
		createEvent("NAVIGATION", "", "/features", { offsetMs: 3000 }),
		createEvent("CLICK", "Documentation", "/features", { offsetMs: 4000 })
	];

	const res = extractBehaviorFeatures(normalEvents);
	const f = res.behavior_features;

	assert.strictEqual(f.total_events, 6);
	assert.strictEqual(f.total_clicks, 3);
	assert.strictEqual(f.total_navigation_events, 2);
	assert.strictEqual(f.cancellation_detected, false);
	assert.strictEqual(f.cancellation_steps, 0);
	assert.strictEqual(f.retention_offer_count, 0);
	assert.strictEqual(f.backtracking_count, 0);
	assert.strictEqual(f.dead_end_count, 0);
	assert.strictEqual(f.forced_action_count, 0);
	assert.strictEqual(f.survey_detected, false);
	assert.strictEqual(f.abandonment_detected, false);
	assert.strictEqual(f.flow_duration_seconds, 4);

	// Hard Negative: Informational link mentioning "Cancellation Policy" must NOT trigger cancellation
	const policyEvents = [
		createEvent("CLICK", "Read Cancellation Policy", "/help", { offsetMs: 0 }),
		createEvent("NAVIGATION", "", "/help/cancellation-policy", { offsetMs: 1000 })
	];
	const policyRes = extractBehaviorFeatures(policyEvents);
	assert.strictEqual(policyRes.behavior_features.cancellation_detected, false, "Informational policy link must not trigger cancellation intent");
});

// 2. Normal Cancellation
runTest("2. Normal Cancellation (Positive & Hard Negative)", () => {
	// Positive: 2-step direct cancellation
	const cancelEvents = [
		createEvent("CLICK", "Cancel Subscription", "/account#subscription", { offsetMs: 0 }),
		createEvent("NAVIGATION", "", "/account/cancel", { offsetMs: 1000 }),
		createEvent("CLICK", "Confirm Cancellation", "/account/cancel#confirm", { offsetMs: 2500 })
	];
	const res = extractBehaviorFeatures(cancelEvents);
	const f = res.behavior_features;

	assert.strictEqual(f.cancellation_detected, true);
	assert.strictEqual(f.cancellation_steps, 3);
	assert.strictEqual(f.retention_offer_count, 0);
	assert.strictEqual(f.survey_detected, false);
	assert.strictEqual(f.abandonment_detected, false);
	assert.strictEqual(f.cancel_attempt_count, 1);

	// Hard Negative: Viewing cancelled orders does not count as cancelling
	const ordersEvents = [
		createEvent("CLICK", "View Cancelled Orders", "/orders", { offsetMs: 0 }),
		createEvent("NAVIGATION", "", "/orders/history", { offsetMs: 1000 })
	];
	const ordersRes = extractBehaviorFeatures(ordersEvents);
	assert.strictEqual(ordersRes.behavior_features.cancellation_detected, false);
});

// 3. 5-Step Cancellation
runTest("3. 5-Step Cancellation", () => {
	const events = [
		createEvent("CLICK", "Cancel Subscription", "/billing", { offsetMs: 0 }),
		createEvent("NAVIGATION", "", "/cancel/step1", { offsetMs: 1000 }),
		createEvent("CLICK", "Continue", "/cancel/step1", { offsetMs: 2000 }),
		createEvent("NAVIGATION", "", "/cancel/step2", { offsetMs: 3000 }),
		createEvent("CLICK", "Confirm Cancellation", "/cancel/step2", { offsetMs: 4000 })
	];
	const res = extractBehaviorFeatures(events);
	assert.strictEqual(res.behavior_features.cancellation_steps, 5);
	assert.strictEqual(res.behavior_features.cancellation_detected, true);
	assert.strictEqual(res.behavior_features.abandonment_detected, false);
});

// 4. Excessive Cancellation Steps
runTest("4. Excessive Cancellation Steps (Positive & Hard Negative)", () => {
	// Positive: 8-step cancellation labyrinth
	const excessiveEvents = [
		createEvent("CLICK", "Cancel Subscription", "/sub", { offsetMs: 0 }),
		createEvent("NAVIGATION", "", "/cancel-1", { offsetMs: 1000 }),
		createEvent("CLICK", "Continue", "/cancel-1", { offsetMs: 2000 }),
		createEvent("NAVIGATION", "", "/cancel-2", { offsetMs: 3000 }),
		createEvent("CLICK", "Next", "/cancel-2", { offsetMs: 4000 }),
		createEvent("NAVIGATION", "", "/cancel-3", { offsetMs: 5000 }),
		createEvent("CLICK", "Proceed", "/cancel-3", { offsetMs: 6000 }),
		createEvent("CLICK", "Confirm Cancellation", "/cancel-final", { offsetMs: 7000 })
	];
	const res = extractBehaviorFeatures(excessiveEvents);
	assert(res.behavior_features.cancellation_steps >= 7, "Must measure excessive cancellation steps >= 7");

	// Hard Negative: Standard 3-step checkout flow (not cancellation)
	const checkoutEvents = [
		createEvent("CLICK", "Add to Cart", "/product", { offsetMs: 0 }),
		createEvent("NAVIGATION", "", "/cart", { offsetMs: 1000 }),
		createEvent("CLICK", "Checkout", "/cart", { offsetMs: 2000 }),
		createEvent("NAVIGATION", "", "/payment", { offsetMs: 3000 }),
		createEvent("CLICK", "Place Order", "/payment", { offsetMs: 4000 })
	];
	const checkoutRes = extractBehaviorFeatures(checkoutEvents);
	assert.strictEqual(checkoutRes.behavior_features.cancellation_detected, false);
	assert.strictEqual(checkoutRes.behavior_features.cancellation_steps, 0);
});

// 5. Repeated Retention Offers
runTest("5. Repeated Retention Offers (Positive & Hard Negative)", () => {
	// Positive: Multiple discounts/offers presented during cancellation
	const events = [
		createEvent("CLICK", "Cancel Subscription", "/cancel", { offsetMs: 0 }),
		createEvent("CLICK", "Save 20% Discount", "/cancel/offer1", { offsetMs: 1000 }),
		createEvent("CLICK", "No Thanks", "/cancel/offer1", { offsetMs: 2000 }),
		createEvent("CLICK", "Pause Plan for 3 Months", "/cancel/offer2", { offsetMs: 3000 }),
		createEvent("CLICK", "No Thanks", "/cancel/offer2", { offsetMs: 4000 }),
		createEvent("CLICK", "Get 1 Free Month", "/cancel/offer3", { offsetMs: 5000 }),
		createEvent("CLICK", "Confirm Cancellation", "/cancel/done", { offsetMs: 6000 })
	];
	const res = extractBehaviorFeatures(events);
	const f = res.behavior_features;

	assert.strictEqual(f.retention_offer_count, 3);
	assert(f.retention_offer_types.includes("DISCOUNT"), "DISCOUNT retention offer should be classified");
	assert(f.retention_offer_types.includes("PAUSE_PLAN"), "PAUSE_PLAN retention offer should be classified");
	assert(f.retention_offer_types.includes("FREE_EXTENSION"), "FREE_EXTENSION retention offer should be classified");

	// Hard Negative: Normal subscription tier selection without cancellation
	const tierEvents = [
		createEvent("CLICK", "Select Pro Plan", "/pricing", { offsetMs: 0 }),
		createEvent("CLICK", "Annual Billing", "/checkout", { offsetMs: 1000 })
	];
	const tierRes = extractBehaviorFeatures(tierEvents);
	assert.strictEqual(tierRes.behavior_features.retention_offer_count, 0);
});

// 6. Repeated Prompts
runTest("6. Repeated Prompts (Positive & Hard Negative)", () => {
	// Positive: Same "Are you sure?" prompt repeated
	const promptEvents = [
		createEvent("CLICK", "Cancel", "/cancel", { offsetMs: 0 }),
		createEvent("CLICK", "Are you sure?", "/cancel/step1", { offsetMs: 1000 }),
		createEvent("CLICK", "Continue", "/cancel/step1", { offsetMs: 2000 }),
		createEvent("CLICK", "Are you sure?", "/cancel/step2", { offsetMs: 3000 }),
		createEvent("CLICK", "Confirm", "/cancel/final", { offsetMs: 4000 })
	];
	const res = extractBehaviorFeatures(promptEvents);
	assert(res.behavior_features.repeated_prompt_count >= 1);
	assert(res.behavior_features.repeated_prompt_texts.some(t => t.includes("are you sure")));

	// Hard Negative: Distinct buttons with common words like "Next Step" vs "Next Item"
	const distinctEvents = [
		createEvent("CLICK", "Next Step", "/form1", { offsetMs: 0 }),
		createEvent("CLICK", "Next Item", "/form2", { offsetMs: 1000 })
	];
	const distinctRes = extractBehaviorFeatures(distinctEvents);
	assert.strictEqual(distinctRes.behavior_features.repeated_prompt_count, 0);
});

// 7. Meaningful Backtracking
runTest("7. Meaningful Backtracking (Positive & Hard Negative)", () => {
	// Positive: A → B → C → B (meaningful backtrack to B)
	const backtrackEvents = [
		createEvent("NAVIGATION", "", "/step-a", { offsetMs: 0 }),
		createEvent("NAVIGATION", "", "/step-b", { offsetMs: 1000 }),
		createEvent("NAVIGATION", "", "/step-c", { offsetMs: 2000 }),
		createEvent("NAVIGATION", "", "/step-b", { offsetMs: 3000 })
	];
	const res = extractBehaviorFeatures(backtrackEvents);
	assert.strictEqual(res.behavior_features.backtracking_count, 1);
	assert(res.behavior_features.backtracked_routes.includes("/step-b"));

	// Hard Negative: Straight progressive navigation A → B → C → D
	const forwardEvents = [
		createEvent("NAVIGATION", "", "/step-a", { offsetMs: 0 }),
		createEvent("NAVIGATION", "", "/step-b", { offsetMs: 1000 }),
		createEvent("NAVIGATION", "", "/step-c", { offsetMs: 2000 }),
		createEvent("NAVIGATION", "", "/step-d", { offsetMs: 3000 })
	];
	const forwardRes = extractBehaviorFeatures(forwardEvents);
	assert.strictEqual(forwardRes.behavior_features.backtracking_count, 0);
	assert.strictEqual(forwardRes.behavior_features.backtracked_routes.length, 0);
});

// 8. Repeated Same-Route Clicks
runTest("8. Repeated Same-Route Clicks (Positive & Hard Negative)", () => {
	// Positive: Multiple clicks on the same screen (e.g. form fields, checkboxes)
	const sameRouteEvents = [
		createEvent("CLICK", "Option A", "/settings", { offsetMs: 0 }),
		createEvent("CLICK", "Option B", "/settings", { offsetMs: 500 }),
		createEvent("CLICK", "Option C", "/settings", { offsetMs: 1000 })
	];
	const res = extractBehaviorFeatures(sameRouteEvents);
	assert.strictEqual(res.behavior_features.repeated_route_count, 2);
	assert.strictEqual(res.behavior_features.backtracking_count, 0, "Same-route clicks must NOT count as backtracking");

	// Hard Negative: Normal multi-screen clicks
	const multiRouteEvents = [
		createEvent("CLICK", "Tab 1", "/tab1", { offsetMs: 0 }),
		createEvent("CLICK", "Tab 2", "/tab2", { offsetMs: 1000 })
	];
	const multiRes = extractBehaviorFeatures(multiRouteEvents);
	assert.strictEqual(multiRes.behavior_features.repeated_route_count, 0);
});

// 9. Required Survey
runTest("9. Required Survey (Positive & Hard Negative)", () => {
	// Positive: Survey placed between cancellation start and completion
	const surveyEvents = [
		createEvent("CLICK", "Cancel Subscription", "/account", { offsetMs: 0 }),
		createEvent("NAVIGATION", "", "/cancel/survey", { offsetMs: 1000 }),
		createEvent("CLICK", "Why are you leaving? (Survey)", "/cancel/survey", { offsetMs: 2000 }),
		createEvent("CLICK", "Confirm Cancellation", "/cancel/confirm", { offsetMs: 3000 })
	];
	const res = extractBehaviorFeatures(surveyEvents);
	assert.strictEqual(res.behavior_features.survey_detected, true);
	assert.strictEqual(res.behavior_features.survey_required, true);

	// Hard Negative: Voluntary feedback survey on website footer
	const voluntaryEvents = [
		createEvent("CLICK", "Give Feedback", "/feedback", { offsetMs: 0 }),
		createEvent("CLICK", "Submit Feedback", "/feedback", { offsetMs: 1000 })
	];
	const voluntaryRes = extractBehaviorFeatures(voluntaryEvents);
	assert.strictEqual(voluntaryRes.behavior_features.survey_detected, true);
	assert.strictEqual(voluntaryRes.behavior_features.survey_required, false, "Voluntary survey outside cancellation is not required");
});

// 10. Forced Action
runTest("10. Forced Action (Positive & Hard Negative)", () => {
	// Positive: Required to call customer service or complete survey to cancel
	const forcedEvents = [
		createEvent("CLICK", "Cancel Subscription", "/cancel", { offsetMs: 0 }),
		createEvent("CLICK", "Call customer support to cancel", "/cancel/support", { offsetMs: 1000 }),
		createEvent("CLICK", "Confirm", "/cancel/done", { offsetMs: 2000 })
	];
	const res = extractBehaviorFeatures(forcedEvents);
	assert(res.behavior_features.forced_action_count >= 1);
	assert(res.behavior_features.forced_action_types.includes("REQUIRED_SUPPORT_CONTACT"));

	// Hard Negative: Optional "Contact Us" link on a support page
	const supportEvents = [
		createEvent("CLICK", "Contact Us", "/support", { offsetMs: 0 }),
		createEvent("CLICK", "Send Email", "/support/email", { offsetMs: 1000 })
	];
	const supportRes = extractBehaviorFeatures(supportEvents);
	assert.strictEqual(supportRes.behavior_features.forced_action_count, 0);
});

// 11. Dead-End Behavior
runTest("11. Dead-End Behavior (Positive & Hard Negative)", () => {
	// Positive: Navigation loop trap X → Y → X → Y
	const trapEvents = [
		createEvent("NAVIGATION", "", "/loop-x", { offsetMs: 0 }),
		createEvent("NAVIGATION", "", "/loop-y", { offsetMs: 1000 }),
		createEvent("NAVIGATION", "", "/loop-x", { offsetMs: 2000 }),
		createEvent("NAVIGATION", "", "/loop-y", { offsetMs: 3000 })
	];
	const res = extractBehaviorFeatures(trapEvents);
	assert(res.behavior_features.dead_end_count >= 1);
	assert(res.behavior_features.dead_end_routes.includes("/loop-x"));

	// Positive Variant: Click on disabled button preventing cancellation
	const disabledEvents = [
		createEvent("CLICK", "Cancel Subscription", "/settings", { offsetMs: 0, disabled: true })
	];
	const disabledRes = extractBehaviorFeatures(disabledEvents);
	assert(disabledRes.behavior_features.dead_end_count >= 1);

	// Hard Negative: Normal linear navigation with forward progress
	const linearEvents = [
		createEvent("NAVIGATION", "", "/page-1", { offsetMs: 0 }),
		createEvent("NAVIGATION", "", "/page-2", { offsetMs: 1000 }),
		createEvent("NAVIGATION", "", "/page-3", { offsetMs: 2000 })
	];
	const linearRes = extractBehaviorFeatures(linearEvents);
	assert.strictEqual(linearRes.behavior_features.dead_end_count, 0);
});

// 12. Abandonment
runTest("12. Abandonment (Positive & Hard Negative)", () => {
	// Positive: User starts cancellation, but navigates back to /home without completing
	const abandonEvents = [
		createEvent("CLICK", "Cancel Subscription", "/account", { offsetMs: 0 }),
		createEvent("CLICK", "Save 10%", "/cancel/offer", { offsetMs: 1000 }),
		createEvent("NAVIGATION", "", "/home", { offsetMs: 2000 })
	];
	const res = extractBehaviorFeatures(abandonEvents);
	assert.strictEqual(res.behavior_features.cancellation_detected, true);
	assert.strictEqual(res.behavior_features.abandonment_detected, true);

	// Hard Negative: User completes cancellation successfully
	const completeEvents = [
		createEvent("CLICK", "Cancel Subscription", "/account", { offsetMs: 0 }),
		createEvent("CLICK", "Confirm Cancellation", "/cancel/confirm", { offsetMs: 1000 }),
		createEvent("NAVIGATION", "", "/cancel/success", { offsetMs: 1500 })
	];
	const completeRes = extractBehaviorFeatures(completeEvents);
	assert.strictEqual(completeRes.behavior_features.abandonment_detected, false);
});

// 13. Normal Discount (Outside Cancellation)
runTest("13. Normal Discount Outside Cancellation (Positive & Hard Negative)", () => {
	// Shopping discount coupon: not retention
	const shopEvents = [
		createEvent("CLICK", "Apply 10% Discount Code", "/store/cart", { offsetMs: 0 }),
		createEvent("CLICK", "Checkout", "/store/checkout", { offsetMs: 1000 })
	];
	const res = extractBehaviorFeatures(shopEvents);
	assert.strictEqual(res.behavior_features.cancellation_detected, false);
	assert.strictEqual(res.behavior_features.retention_offer_count, 0);

	// Hard Negative / Counterpart: Discount during cancellation flow IS a retention offer
	const cancelDiscountEvents = [
		createEvent("CLICK", "Cancel Subscription", "/account", { offsetMs: 0 }),
		createEvent("CLICK", "Take 50% discount instead", "/cancel/save", { offsetMs: 1000 })
	];
	const cancelDiscountRes = extractBehaviorFeatures(cancelDiscountEvents);
	assert.strictEqual(cancelDiscountRes.behavior_features.retention_offer_count, 1);
});

// 14. Normal Confirmation
runTest("14. Normal Confirmation (Positive & Hard Negative)", () => {
	// Single clean confirmation step
	const confirmEvents = [
		createEvent("CLICK", "Place Order", "/checkout", { offsetMs: 0 }),
		createEvent("CLICK", "Confirm", "/checkout#confirm", { offsetMs: 1000 })
	];
	const res = extractBehaviorFeatures(confirmEvents);
	assert.strictEqual(res.behavior_features.confirmation_screen_count, 1);
	assert.strictEqual(res.behavior_features.repeated_confirmation_count, 0);

	// Hard Negative: Repeated confirmations
	const repeatedConfirmEvents = [
		createEvent("CLICK", "Are you sure?", "/step1", { offsetMs: 0 }),
		createEvent("CLICK", "Confirm", "/step2#confirm", { offsetMs: 1000 }),
		createEvent("CLICK", "Are you really sure? Confirm again", "/step3#confirm", { offsetMs: 2000 })
	];
	const repeatedRes = extractBehaviorFeatures(repeatedConfirmEvents);
	assert(repeatedRes.behavior_features.repeated_confirmation_count >= 1);
});

// 15. Legitimate Long Cancellation Flow
runTest("15. Legitimate Long Cancellation Flow", () => {
	// Pre-navigation in account settings before initiating cancellation
	const events = [
		createEvent("CLICK", "Profile", "/dashboard", { offsetMs: 0 }),
		createEvent("CLICK", "Settings", "/profile", { offsetMs: 1000 }),
		createEvent("CLICK", "Billing", "/settings", { offsetMs: 2000 }),
		createEvent("CLICK", "Manage Subscription", "/billing", { offsetMs: 3000 }),
		// Cancellation initiated here:
		createEvent("CLICK", "Cancel Subscription", "/manage-sub", { offsetMs: 4000 }),
		createEvent("NAVIGATION", "", "/cancel/feedback", { offsetMs: 5000 }),
		createEvent("CLICK", "Confirm Cancellation", "/cancel/feedback", { offsetMs: 6000 })
	];
	const res = extractBehaviorFeatures(events);
	const f = res.behavior_features;

	assert.strictEqual(f.total_events, 7);
	assert.strictEqual(f.cancellation_detected, true);
	// Only steps from "Cancel Subscription" onwards are cancellation steps (3 steps)
	assert.strictEqual(f.cancellation_steps, 3);
	assert.strictEqual(f.abandonment_detected, false);
});

// 16. Empty Session
runTest("16. Empty Session", () => {
	const res = extractBehaviorFeatures([]);
	const f = res.behavior_features;

	assert.strictEqual(f.total_events, 0);
	assert.strictEqual(f.total_clicks, 0);
	assert.strictEqual(f.total_navigation_events, 0);
	assert.strictEqual(f.total_input_changes, 0);
	assert.strictEqual(f.unique_routes, 0);
	assert.strictEqual(f.cancellation_detected, false);
	assert.strictEqual(f.cancellation_steps, 0);
	assert.strictEqual(f.flow_duration_seconds, 0);
	assert(Array.isArray(res.evidence));
});

// 17. Single-Event Session
runTest("17. Single-Event Session", () => {
	const events = [createEvent("CLICK", "Home", "/home")];
	const res = extractBehaviorFeatures(events);
	const f = res.behavior_features;

	assert.strictEqual(f.total_events, 1);
	assert.strictEqual(f.total_clicks, 1);
	assert.strictEqual(f.unique_routes, 1);
	assert.strictEqual(f.flow_duration_seconds, 0);
});

// 18. Legacy Event Compatibility
runTest("18. Legacy Event Compatibility", () => {
	const legacyEvents = [
		{ action: "CLICK", element: "BUTTON", text: "Cancel Subscription", url: "http://test.local/#cancel", timestamp: "2026-09-09T12:00:00.000Z" },
		{ action: "NAVIGATION", element: "document", text: "", url: "http://test.local/#cancel", timestamp: "2026-09-09T12:00:05.000Z" },
		{ action: "CLICK", element: "BUTTON", text: "Confirm Cancellation", url: "http://test.local/#confirm", timestamp: "2026-09-09T12:00:10.000Z" }
	];
	const res = extractBehaviorFeatures(legacyEvents);
	const f = res.behavior_features;

	assert.strictEqual(f.total_events, 3);
	assert.strictEqual(f.cancellation_detected, true);
	assert.strictEqual(f.flow_duration_seconds, 10);
	assert(f.cancellation_routes.length >= 1);
});

// 19. Structured B1 Event Compatibility
runTest("19. Structured B1 Event Compatibility", () => {
	const b1Events = [
		{
			event_id: "evt-uuid-1",
			session_id: "session-uuid-1",
			page_load_id: "page-load-1",
			timestamp: "2026-09-09T12:00:00.000Z",
			action: "PAGE_INIT",
			url: "https://example.com/billing",
			route: "/billing",
			element: null
		},
		{
			event_id: "evt-uuid-2",
			session_id: "session-uuid-1",
			page_load_id: "page-load-1",
			timestamp: "2026-09-09T12:00:02.000Z",
			action: "CLICK",
			url: "https://example.com/billing",
			route: "/billing",
			element: {
				tag: "BUTTON",
				role: "button",
				text: "Cancel Subscription",
				visible: true,
				disabled: false,
				type: null
			}
		},
		{
			event_id: "evt-uuid-3",
			session_id: "session-uuid-1",
			page_load_id: "page-load-1",
			timestamp: "2026-09-09T12:00:05.000Z",
			action: "CLICK",
			url: "https://example.com/billing/confirm",
			route: "/billing/confirm",
			element: {
				tag: "BUTTON",
				role: "button",
				text: "Confirm Cancellation",
				visible: true,
				disabled: false,
				type: null
			}
		}
	];
	const res = extractBehaviorFeatures(b1Events);
	const f = res.behavior_features;

	assert.strictEqual(f.total_events, 3);
	assert.strictEqual(f.total_clicks, 2);
	assert.strictEqual(f.cancellation_detected, true);
	assert.strictEqual(f.flow_duration_seconds, 5);

	// Verify evidence traceability
	const clickEvidence = res.evidence.find(e => e.feature === "total_clicks");
	assert.deepStrictEqual(clickEvidence.event_indices, [1, 2]);
});

// 20. Mixed Event Types
runTest("20. Mixed Event Types (CLICK, NAVIGATION, INPUT_CHANGE, PAGE_INIT)", () => {
	const mixedEvents = [
		createEvent("PAGE_INIT", "", "/checkout"),
		createEvent("INPUT_CHANGE", "", "/checkout", {
			element: { tag: "INPUT", type: "checkbox" },
			metadata: { checked: true }
		}),
		createEvent("CLICK", "Continue", "/checkout"),
		createEvent("NAVIGATION", "", "/checkout/confirm")
	];
	const res = extractBehaviorFeatures(mixedEvents);
	const f = res.behavior_features;

	assert.strictEqual(f.total_events, 4);
	assert.strictEqual(f.total_clicks, 1);
	assert.strictEqual(f.total_navigation_events, 1);
	assert.strictEqual(f.total_input_changes, 1);
});

console.log("\n==================================================");
console.log(`TEST RESULTS: ${passedCount} PASSED, ${failedCount} FAILED (TOTAL: ${passedCount + failedCount})`);
console.log("==================================================\n");

if (failedCount > 0) {
	process.exit(1);
}
