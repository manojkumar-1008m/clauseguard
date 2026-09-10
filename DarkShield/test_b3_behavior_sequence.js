/**
 * DarkShield Phase B3 — Sequence-Based Behavior Analysis Test Suite
 *
 * Validates deterministic behavior sequence reasoning:
 * - 10 Hard Negative tests (legitimate interaction flows must NOT trigger strong suspicious signals)
 * - 10 Positive scenarios (detects specific sequence patterns and verifies traceable evidence)
 */

const assert = require("assert");
const { analyzeBehaviorSequence } = require("./extension/analyzer/behaviorSequence.js");
const { extractBehaviorFeatures } = require("./extension/analyzer/behaviorFeatures.js");

console.log("==================================================");
console.log("RUNNING DARKSHIELD PHASE B3 BEHAVIOR SEQUENCE TESTS");
console.log("==================================================");

let passed = 0;
let failed = 0;

function runTest(name, fn) {
	try {
		fn();
		console.log(`✓ PASS: ${name}`);
		passed++;
	} catch (err) {
		console.error(`✗ FAIL: ${name}`);
		console.error(err);
		failed++;
	}
}

// ---------------------------------------------------------------------
// HARD NEGATIVES (10 Scenarios)
// ---------------------------------------------------------------------

// 1. Normal 2-step cancellation
runTest("1. Hard Negative: Normal 2-step cancellation", () => {
	const events = [
		{ action: "NAVIGATION", route: "/settings/subscription", text: "Subscription Settings" },
		{ action: "CLICK", route: "/settings/subscription", text: "Cancel Subscription" },
		{ action: "NAVIGATION", route: "/settings/cancel-confirm", text: "Confirm Cancellation" },
		{ action: "CLICK", route: "/settings/cancel-confirm", text: "Confirm Cancellation" },
		{ action: "NAVIGATION", route: "/settings/success", text: "Cancellation Complete" }
	];
	const res = analyzeBehaviorSequence(events);
	assert.ok(Array.isArray(res.behavior_signals));
	assert.ok(Array.isArray(res.evidence));

	// No suspicious signals should be detected
	const retentionSig = res.behavior_signals.find(s => s.type === "repeated_retention_interference");
	const obstructionSig = res.behavior_signals.find(s => s.type === "cancellation_obstruction");
	const repeatedConfirmSig = res.behavior_signals.find(s => s.type === "repeated_confirmation_pressure");
	const deadEndSig = res.behavior_signals.find(s => s.type === "dead_end_behavior");
	const abandonSig = res.behavior_signals.find(s => s.type === "cancellation_abandonment");

	assert.strictEqual(retentionSig, undefined);
	assert.strictEqual(obstructionSig, undefined);
	assert.strictEqual(repeatedConfirmSig, undefined);
	assert.strictEqual(deadEndSig, undefined);
	assert.strictEqual(abandonSig, undefined);
});

// 2. Legitimate 5-step cancellation
runTest("2. Hard Negative: Legitimate 5-step cancellation", () => {
	const events = [
		{ action: "CLICK", route: "/billing", text: "Cancel Subscription" },
		{ action: "NAVIGATION", route: "/cancel/effective-date", text: "Choose End Date" },
		{ action: "CLICK", route: "/cancel/effective-date", text: "End at period end" },
		{ action: "NAVIGATION", route: "/cancel/data-retention", text: "Data retention info" },
		{ action: "CLICK", route: "/cancel/data-retention", text: "I understand" },
		{ action: "NAVIGATION", route: "/cancel/summary", text: "Cancellation Summary" },
		{ action: "CLICK", route: "/cancel/summary", text: "Finish Cancellation" },
		{ action: "NAVIGATION", route: "/cancel/success", text: "Subscription Ended" }
	];
	const res = analyzeBehaviorSequence(events);

	const obstructionSig = res.behavior_signals.find(s => s.type === "cancellation_obstruction");
	const retentionSig = res.behavior_signals.find(s => s.type === "repeated_retention_interference");
	const surveySig = res.behavior_signals.find(s => s.type === "required_survey");

	assert.strictEqual(obstructionSig, undefined, "Multi-step legitimate cancellation should NOT be obstruction");
	assert.strictEqual(retentionSig, undefined);
	assert.strictEqual(surveySig, undefined);
});

// 3. One normal discount
runTest("3. Hard Negative: One normal discount", () => {
	const events = [
		{ action: "NAVIGATION", route: "/store", text: "Store" },
		{ action: "CLICK", route: "/store/checkout", text: "Apply 20% discount coupon" },
		{ action: "CLICK", route: "/store/checkout", text: "Place order" }
	];
	const res = analyzeBehaviorSequence(events);
	const retentionSig = res.behavior_signals.find(s => s.type === "repeated_retention_interference");
	assert.strictEqual(retentionSig, undefined, "Single coupon discount must NOT trigger repeated retention interference");
});

// 4. One normal confirmation
runTest("4. Hard Negative: One normal confirmation", () => {
	const events = [
		{ action: "CLICK", route: "/account", text: "Cancel account" },
		{ action: "CLICK", route: "/account/confirm", text: "Are you sure you want to cancel?" },
		{ action: "CLICK", route: "/account/confirm", text: "Confirm cancellation" },
		{ action: "NAVIGATION", route: "/account/cancelled", text: "Cancelled successfully" }
	];
	const res = analyzeBehaviorSequence(events);
	const repeatedConfirmSig = res.behavior_signals.find(s => s.type === "repeated_confirmation_pressure");
	assert.strictEqual(repeatedConfirmSig, undefined, "Single confirmation screen must NOT trigger repeated confirmation pressure");
});

// 5. Optional survey
runTest("5. Hard Negative: Optional survey", () => {
	const events = [
		{ action: "CLICK", route: "/account", text: "Cancel Plan" },
		{ action: "NAVIGATION", route: "/account/feedback", text: "Tell us why you are leaving (Optional)" },
		{ action: "CLICK", route: "/account/feedback", text: "Skip survey" },
		{ action: "CLICK", route: "/account/confirm", text: "Confirm cancellation" },
		{ action: "NAVIGATION", route: "/account/success", text: "Cancellation complete" }
	];
	const res = analyzeBehaviorSequence(events);
	const surveySig = res.behavior_signals.find(s => s.type === "required_survey");
	const forcedSig = res.behavior_signals.find(s => s.type === "forced_action_sequence");
	assert.strictEqual(surveySig, undefined, "Optional survey with skip option must NOT trigger required_survey");
	assert.strictEqual(forcedSig, undefined, "Optional survey must NOT trigger forced_action_sequence");
});

// 6. Normal backtracking
runTest("6. Hard Negative: Normal backtracking (Voluntary non-loop)", () => {
	const events = [
		{ action: "NAVIGATION", route: "/catalog", text: "Catalog" },
		{ action: "NAVIGATION", route: "/catalog/item1", text: "Item 1" },
		{ action: "NAVIGATION", route: "/catalog/item1/details", text: "Details" },
		{ action: "NAVIGATION", route: "/catalog/item1", text: "Back to Item 1" }
	];
	const res = analyzeBehaviorSequence(events);
	const strongBacktrack = res.behavior_signals.find(s => s.type === "backtracking_loop" && s.strength === "strong");
	assert.strictEqual(strongBacktrack, undefined, "Voluntary return to previous item must NOT be strong loop");
});

// 7. Repeated clicks on same page
runTest("7. Hard Negative: Repeated clicks on same page", () => {
	const events = [
		{ action: "NAVIGATION", route: "/checkout", text: "Checkout" },
		{ action: "CLICK", route: "/checkout", text: "First Name" },
		{ action: "INPUT_CHANGE", route: "/checkout", text: "John" },
		{ action: "CLICK", route: "/checkout", text: "Last Name" },
		{ action: "INPUT_CHANGE", route: "/checkout", text: "Doe" },
		{ action: "CLICK", route: "/checkout", text: "Submit Order" }
	];
	const res = analyzeBehaviorSequence(events);
	const backtrackSig = res.behavior_signals.find(s => s.type === "backtracking_loop");
	assert.strictEqual(backtrackSig, undefined, "Clicks on same route must NOT trigger backtracking loop");
});

// 8. Normal checkout loop
runTest("8. Hard Negative: Normal checkout review flow", () => {
	const events = [
		{ action: "NAVIGATION", route: "/cart", text: "Cart" },
		{ action: "NAVIGATION", route: "/checkout/shipping", text: "Shipping" },
		{ action: "CLICK", route: "/checkout/shipping", text: "Next to Payment" },
		{ action: "NAVIGATION", route: "/checkout/payment", text: "Payment" },
		{ action: "CLICK", route: "/checkout/payment", text: "Place Order" },
		{ action: "NAVIGATION", route: "/checkout/success", text: "Thank you for your order" }
	];
	const res = analyzeBehaviorSequence(events);
	const obstructionSig = res.behavior_signals.find(s => s.type === "cancellation_obstruction");
	const deadEndSig = res.behavior_signals.find(s => s.type === "dead_end_behavior");
	assert.strictEqual(obstructionSig, undefined);
	assert.strictEqual(deadEndSig, undefined);
});

// 9. Legitimate multi-page account deletion
runTest("9. Hard Negative: Legitimate multi-page account deletion", () => {
	const events = [
		{ action: "CLICK", route: "/settings/security", text: "Delete Account" },
		{ action: "NAVIGATION", route: "/settings/delete/warning", text: "Warning: Data Loss" },
		{ action: "CLICK", route: "/settings/delete/warning", text: "I understand the risks" },
		{ action: "NAVIGATION", route: "/settings/delete/auth", text: "Re-enter password" },
		{ action: "CLICK", route: "/settings/delete/auth", text: "Confirm Deletion" },
		{ action: "NAVIGATION", route: "/settings/delete/done", text: "Account deleted successfully" }
	];
	const res = analyzeBehaviorSequence(events);
	const obstructionSig = res.behavior_signals.find(s => s.type === "cancellation_obstruction");
	const retentionSig = res.behavior_signals.find(s => s.type === "repeated_retention_interference");
	assert.strictEqual(obstructionSig, undefined);
	assert.strictEqual(retentionSig, undefined);
});

// 10. User voluntarily returning to a previous page
runTest("10. Hard Negative: User voluntarily returning to previous page while browsing", () => {
	const events = [
		{ action: "NAVIGATION", route: "/products", text: "Products" },
		{ action: "CLICK", route: "/products/phone", text: "Phone A" },
		{ action: "NAVIGATION", route: "/products", text: "Back to Products" },
		{ action: "CLICK", route: "/products/laptop", text: "Laptop B" }
	];
	const res = analyzeBehaviorSequence(events);
	const strongSig = res.behavior_signals.filter(s => s.strength === "strong");
	assert.strictEqual(strongSig.length, 0, "Voluntary navigation between product pages must NOT trigger strong signals");
});

// ---------------------------------------------------------------------
// POSITIVE SCENARIOS (10 Scenarios)
// ---------------------------------------------------------------------

// 1. Two retention offers after cancellation
runTest("11. Positive: Two retention offers after cancellation", () => {
	const events = [
		{ action: "CLICK", route: "/account", text: "Cancel Subscription" }, // 0
		{ action: "NAVIGATION", route: "/cancel/offer-1", text: "Special Offer: 50% discount to stay!" }, // 1
		{ action: "CLICK", route: "/cancel/offer-1", text: "No thanks, continue cancelling" }, // 2
		{ action: "NAVIGATION", route: "/cancel/offer-2", text: "Wait! Pause your plan for 3 months free" }, // 3
		{ action: "CLICK", route: "/cancel/offer-2", text: "No, proceed to cancel" }, // 4
		{ action: "CLICK", route: "/cancel/confirm", text: "Confirm cancellation" }, // 5
		{ action: "NAVIGATION", route: "/cancel/success", text: "Cancellation complete" } // 6
	];
	const res = analyzeBehaviorSequence(events);
	const retentionSig = res.behavior_signals.find(s => s.type === "repeated_retention_interference");
	assert.ok(retentionSig, "Should detect repeated retention interference");
	assert.strictEqual(retentionSig.detected, true);
	assert.ok(retentionSig.strength === "moderate" || retentionSig.strength === "strong");
	assert.ok(retentionSig.event_indices.includes(0));
	assert.ok(retentionSig.event_indices.includes(1));
	assert.ok(retentionSig.event_indices.includes(3));
});

// 2. Repeated confirmation screens
runTest("12. Positive: Repeated confirmation screens", () => {
	const events = [
		{ action: "CLICK", route: "/account", text: "Cancel Subscription" }, // 0
		{ action: "CLICK", route: "/cancel/confirm1", text: "Are you sure you want to cancel?" }, // 1
		{ action: "CLICK", route: "/cancel/confirm1", text: "Continue cancellation" }, // 2
		{ action: "CLICK", route: "/cancel/confirm2", text: "Do you really want to lose all benefits?" }, // 3
		{ action: "CLICK", route: "/cancel/confirm2", text: "Yes, continue to cancel" }, // 4
		{ action: "CLICK", route: "/cancel/confirm3", text: "Final warning: confirm cancellation" }, // 5
		{ action: "NAVIGATION", route: "/cancel/success", text: "Cancellation complete" } // 6
	];
	const res = analyzeBehaviorSequence(events);
	const confirmSig = res.behavior_signals.find(s => s.type === "repeated_confirmation_pressure");
	assert.ok(confirmSig, "Should detect repeated confirmation pressure");
	assert.strictEqual(confirmSig.detected, true);
	assert.strictEqual(confirmSig.strength, "strong");
	assert.ok(confirmSig.event_indices.length >= 3);
});

// 3. Required survey during cancellation
runTest("13. Positive: Required survey during cancellation", () => {
	const events = [
		{ action: "CLICK", route: "/account", text: "Cancel Subscription" }, // 0
		{ action: "NAVIGATION", route: "/cancel/survey", text: "Required cancellation survey" }, // 1
		{ action: "INPUT_CHANGE", route: "/cancel/survey", element: { tag: "select", required: true }, text: "Price too high" }, // 2
		{ action: "CLICK", route: "/cancel/survey", text: "Submit response and continue cancellation" }, // 3
		{ action: "CLICK", route: "/cancel/confirm", text: "Confirm cancellation" }, // 4
		{ action: "NAVIGATION", route: "/cancel/success", text: "Cancellation complete" } // 5
	];
	const res = analyzeBehaviorSequence(events);
	const surveySig = res.behavior_signals.find(s => s.type === "required_survey");
	assert.ok(surveySig, "Should detect required survey during cancellation");
	assert.strictEqual(surveySig.detected, true);
	assert.ok(surveySig.event_indices.includes(0));
	assert.ok(surveySig.event_indices.includes(1));
});

// 4. Cancellation loop
runTest("14. Positive: Cancellation loop (Route oscillation during cancel)", () => {
	const events = [
		{ action: "CLICK", route: "/account", text: "Cancel Subscription" },
		{ action: "NAVIGATION", route: "/cancel", text: "Cancel" },
		{ action: "NAVIGATION", route: "/offers", text: "Offers" },
		{ action: "NAVIGATION", route: "/cancel", text: "Cancel" },
		{ action: "NAVIGATION", route: "/offers", text: "Offers" },
		{ action: "NAVIGATION", route: "/cancel", text: "Cancel" }
	];
	const res = analyzeBehaviorSequence(events);
	const loopSig = res.behavior_signals.find(s => s.type === "backtracking_loop");
	assert.ok(loopSig, "Should detect backtracking loop");
	assert.strictEqual(loopSig.detected, true);
	assert.strictEqual(loopSig.strength, "strong");
});

// 5. Dead-end cancellation
runTest("15. Positive: Dead-end cancellation (Disabled button without exit)", () => {
	const events = [
		{ action: "CLICK", route: "/account", text: "Cancel Subscription" },
		{ action: "NAVIGATION", route: "/cancel", text: "Cancel" },
		{ action: "CLICK", route: "/cancel", element: { tag: "button", disabled: true }, text: "Confirm Cancel" },
		{ action: "CLICK", route: "/cancel", element: { tag: "button", disabled: true }, text: "Confirm Cancel" },
		{ action: "CLICK", route: "/cancel", element: { tag: "button", disabled: true }, text: "Confirm Cancel" }
	];
	const res = analyzeBehaviorSequence(events);
	const deadEndSig = res.behavior_signals.find(s => s.type === "dead_end_behavior");
	assert.ok(deadEndSig, "Should detect dead end behavior with disabled button");
	assert.strictEqual(deadEndSig.detected, true);
	assert.strictEqual(deadEndSig.strength, "strong");
});

// 6. Mandatory feedback before cancellation
runTest("16. Positive: Mandatory feedback before cancellation", () => {
	const events = [
		{ action: "CLICK", route: "/account", text: "Cancel Subscription" },
		{ action: "NAVIGATION", route: "/cancel/feedback", text: "Mandatory feedback required to proceed" },
		{ action: "INPUT_CHANGE", route: "/cancel/feedback", element: { tag: "textarea", required: true }, text: "Too expensive" },
		{ action: "CLICK", route: "/cancel/feedback", text: "Submit required feedback" },
		{ action: "CLICK", route: "/cancel/confirm", text: "Confirm cancellation" },
		{ action: "NAVIGATION", route: "/cancel/success", text: "Cancellation complete" }
	];
	const res = analyzeBehaviorSequence(events);
	const forcedSig = res.behavior_signals.find(s => s.type === "forced_action_sequence");
	assert.ok(forcedSig, "Should detect forced action sequence");
	assert.strictEqual(forcedSig.detected, true);
});

// 7. Multiple retention alternatives
runTest("17. Positive: Multiple retention alternatives", () => {
	const events = [
		{ action: "CLICK", route: "/account", text: "Cancel Subscription" },
		{ action: "CLICK", route: "/cancel/options", text: "Switch to basic plan instead" },
		{ action: "CLICK", route: "/cancel/options", text: "No thanks, continue cancelling" },
		{ action: "CLICK", route: "/cancel/options", text: "Pause instead of cancel" },
		{ action: "CLICK", route: "/cancel/options", text: "No, proceed to cancel" },
		{ action: "CLICK", route: "/cancel/confirm", text: "Confirm cancellation" }
	];
	const res = analyzeBehaviorSequence(events);
	const retentionSig = res.behavior_signals.find(s => s.type === "repeated_retention_interference");
	assert.ok(retentionSig, "Should detect repeated retention interference with alternatives");
	assert.strictEqual(retentionSig.detected, true);
});

// 8. Cancellation abandonment after repeated friction
runTest("18. Positive: Cancellation abandonment after repeated friction", () => {
	const events = [
		{ action: "CLICK", route: "/account", text: "Cancel Subscription" }, // 0
		{ action: "NAVIGATION", route: "/cancel/offer", text: "Special Offer: 50% off" }, // 1
		{ action: "CLICK", route: "/cancel/offer", text: "No thanks" }, // 2
		{ action: "NAVIGATION", route: "/cancel/survey", text: "Required cancellation survey" }, // 3
		{ action: "NAVIGATION", route: "/dashboard", text: "Dashboard Home" } // 4: Exited to dashboard without confirm
	];
	const res = analyzeBehaviorSequence(events);
	const abandonSig = res.behavior_signals.find(s => s.type === "cancellation_abandonment");
	assert.ok(abandonSig, "Should detect cancellation abandonment");
	assert.strictEqual(abandonSig.detected, true);
	assert.ok(abandonSig.event_indices.includes(0));
	assert.ok(abandonSig.event_indices.includes(4));
});

// 9. Combined retention + survey + confirmation sequence (Cancellation Obstruction)
runTest("19. Positive: Combined retention + survey + confirmation (Cancellation Obstruction)", () => {
	const events = [
		{ action: "CLICK", route: "/account", text: "Cancel Subscription" },
		{ action: "NAVIGATION", route: "/cancel/offer", text: "Retention Offer: 30% discount" },
		{ action: "CLICK", route: "/cancel/offer", text: "No thanks, continue" },
		{ action: "NAVIGATION", route: "/cancel/offer2", text: "Retention Offer: Pause plan" },
		{ action: "CLICK", route: "/cancel/offer2", text: "No thanks" },
		{ action: "NAVIGATION", route: "/cancel/survey", element: { tag: "select", required: true }, text: "Mandatory survey" },
		{ action: "CLICK", route: "/cancel/survey", text: "Submit response" },
		{ action: "CLICK", route: "/cancel/confirm1", text: "Are you sure you want to cancel?" },
		{ action: "CLICK", route: "/cancel/confirm1", text: "Yes, continue" },
		{ action: "CLICK", route: "/cancel/confirm2", text: "Final confirmation: confirm cancellation" },
		{ action: "NAVIGATION", route: "/cancel/success", text: "Cancellation complete" }
	];
	const res = analyzeBehaviorSequence(events);
	const obstructionSig = res.behavior_signals.find(s => s.type === "cancellation_obstruction");
	assert.ok(obstructionSig, "Should detect cancellation obstruction on multi-friction combination");
	assert.strictEqual(obstructionSig.detected, true);
	assert.strictEqual(obstructionSig.strength, "strong");
});

// 10. Repeated route oscillation
runTest("20. Positive: Repeated route oscillation (A -> B -> A -> B -> A)", () => {
	const events = [
		{ action: "NAVIGATION", route: "/page-a", text: "Page A" },
		{ action: "NAVIGATION", route: "/page-b", text: "Page B" },
		{ action: "NAVIGATION", route: "/page-a", text: "Page A" },
		{ action: "NAVIGATION", route: "/page-b", text: "Page B" },
		{ action: "NAVIGATION", route: "/page-a", text: "Page A" }
	];
	const res = analyzeBehaviorSequence(events);
	const loopSig = res.behavior_signals.find(s => s.type === "backtracking_loop");
	assert.ok(loopSig, "Should detect route oscillation loop");
	assert.strictEqual(loopSig.detected, true);
	assert.strictEqual(loopSig.strength, "strong");
});

// ---------------------------------------------------------------------
// EDGE CASES & EVIDENCE TRACE VALIDATION (5 Scenarios)
// ---------------------------------------------------------------------

// 21. Empty session
runTest("21. Edge Case: Empty session handles gracefully", () => {
	const res = analyzeBehaviorSequence([]);
	assert.deepStrictEqual(res.behavior_signals, []);
	assert.deepStrictEqual(res.evidence, []);
});

// 22. Single event session
runTest("22. Edge Case: Single event session", () => {
	const res = analyzeBehaviorSequence([{ action: "CLICK", route: "/", text: "Home" }]);
	assert.deepStrictEqual(res.behavior_signals, []);
	assert.deepStrictEqual(res.evidence, []);
});

// 23. Precomputed B2 features passed as second parameter
runTest("23. Edge Case: Precomputed B2 features passed into analyzeBehaviorSequence", () => {
	const events = [
		{ action: "CLICK", route: "/account", text: "Cancel Subscription" },
		{ action: "NAVIGATION", route: "/cancel/offer-1", text: "Offer: 50% discount" },
		{ action: "CLICK", route: "/cancel/offer-1", text: "No thanks" },
		{ action: "NAVIGATION", route: "/cancel/offer-2", text: "Offer: 3 months free" },
		{ action: "CLICK", route: "/cancel/offer-2", text: "No, proceed to cancel" },
		{ action: "CLICK", route: "/cancel/confirm", text: "Confirm cancellation" }
	];
	const b2Result = extractBehaviorFeatures(events);
	const res = analyzeBehaviorSequence(events, b2Result);
	const retentionSig = res.behavior_signals.find(s => s.type === "repeated_retention_interference");
	assert.ok(retentionSig, "Should work with precomputed B2 features");
	assert.strictEqual(retentionSig.detected, true);
});

// 24. Legacy event schema compatibility
runTest("24. Edge Case: Legacy event schema compatibility", () => {
	const legacyEvents = [
		{ action: "CLICK", url: "https://example.com/account", text: "Cancel Subscription" },
		{ action: "NAVIGATION", url: "https://example.com/cancel/survey", text: "Why are you leaving? (Mandatory)" },
		{ action: "INPUT_CHANGE", url: "https://example.com/cancel/survey", element: { tag: "select", required: true }, text: "Price" },
		{ action: "CLICK", url: "https://example.com/cancel/survey", text: "Submit and continue" },
		{ action: "CLICK", url: "https://example.com/cancel/confirm", text: "Confirm cancellation" }
	];
	const res = analyzeBehaviorSequence(legacyEvents);
	const surveySig = res.behavior_signals.find(s => s.type === "required_survey");
	assert.ok(surveySig, "Should work with legacy url format");
	assert.strictEqual(surveySig.detected, true);
});

// 25. Traceable evidence integrity
runTest("25. Evidence Integrity: Every detected signal maps to valid event indices", () => {
	const events = [
		{ action: "CLICK", route: "/account", text: "Cancel Subscription" }, // 0
		{ action: "NAVIGATION", route: "/cancel/offer", text: "Discount 40%" }, // 1
		{ action: "CLICK", route: "/cancel/offer", text: "No thanks" }, // 2
		{ action: "NAVIGATION", route: "/cancel/offer2", text: "Pause subscription" }, // 3
		{ action: "CLICK", route: "/cancel/offer2", text: "No thanks" }, // 4
		{ action: "NAVIGATION", route: "/cancel/survey", text: "Mandatory exit survey", element: { required: true } }, // 5
		{ action: "CLICK", route: "/cancel/confirm1", text: "Are you sure you want to cancel?" }, // 6
		{ action: "CLICK", route: "/cancel/confirm1", text: "Yes" }, // 7
		{ action: "CLICK", route: "/cancel/confirm2", text: "Final warning: confirm" } // 8
	];
	const res = analyzeBehaviorSequence(events);
	assert.ok(res.behavior_signals.length > 0);
	assert.strictEqual(res.behavior_signals.length, res.evidence.length);

	res.behavior_signals.forEach(sig => {
		assert.ok(["weak", "moderate", "strong"].includes(sig.strength), `Invalid strength: ${sig.strength}`);
		assert.ok(Array.isArray(sig.event_indices), "event_indices must be array");
		assert.ok(sig.event_indices.length > 0, "event_indices must not be empty");
		sig.event_indices.forEach(idx => {
			assert.ok(idx >= 0 && idx < events.length, `Index ${idx} out of range [0, ${events.length})`);
		});
		assert.ok(Array.isArray(sig.route_sequence), "route_sequence must be array");
	});

	res.evidence.forEach(ev => {
		assert.ok(ev.signal_type, "Evidence must have signal_type");
		assert.ok(ev.strength, "Evidence must have strength");
		assert.ok(ev.description, "Evidence must have description");
		assert.ok(Array.isArray(ev.event_indices), "Evidence event_indices must be array");
	});
});

console.log("\n==================================================");
console.log(`TEST RESULTS: ${passed} PASSED, ${failed} FAILED (TOTAL: ${passed + failed})`);
console.log("==================================================");

if (failed > 0) {
	process.exit(1);
}

