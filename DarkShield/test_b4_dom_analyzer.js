/**
 * DarkShield Phase B4 — DOM / Interaction Context Test Suite
 *
 * Validates deterministic DOM reasoning:
 * - 15 Hard Negative tests (standard web design patterns must NOT trigger suspicious DOM signals)
 * - 15 Positive scenario tests (identifies verifiable, observable DOM/UI signals)
 * - 12 Edge Case & Resilience tests (ensures graceful handling of missing/malformed DOM data)
 */

const assert = require("assert");
const { analyzeDomContext, makeElementRef } = require("./extension/analyzer/domAnalyzer.js");

console.log("==================================================");
console.log("RUNNING DARKSHIELD PHASE B4 DOM ANALYZER TESTS");
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

// =====================================================================
// PART 1: HARD NEGATIVES (15 Scenarios)
// =====================================================================

// 1. Preselected country dropdown
runTest("1. Hard Negative: Preselected country dropdown", () => {
	const events = [{
		action: "CLICK",
		route: "/settings/profile",
		text: "United States",
		dom_context: {
			tag: "SELECT",
			visible_text: "United States",
			checked_state: true,
			preselected_options: [{ text: "Country: United States", checked: true }]
		}
	}];
	const res = analyzeDomContext(events);
	const preselected = res.dom_signals.find(s => s.type === "preselected_option");
	assert.strictEqual(preselected, undefined, "Normal country dropdown must NOT trigger preselected_option");
});

// 2. Remember-me checkbox
runTest("2. Hard Negative: Remember-me checkbox on login", () => {
	const events = [{
		action: "CLICK",
		route: "/login",
		text: "Remember me on this device",
		dom_context: {
			tag: "INPUT",
			type: "checkbox",
			visible_text: "Remember me on this device",
			checked_state: true
		}
	}];
	const res = analyzeDomContext(events);
	const preselected = res.dom_signals.find(s => s.type === "preselected_option");
	assert.strictEqual(preselected, undefined, "Remember me checkbox must NOT trigger preselected_option");
});

// 3. Disabled submit due to incomplete form
runTest("3. Hard Negative: Disabled submit button due to incomplete form", () => {
	const events = [{
		action: "CLICK",
		route: "/contact",
		text: "Submit Form",
		dom_context: {
			tag: "BUTTON",
			visible_text: "Submit Form",
			is_disabled: true,
			container_type: "form",
			competing_actions: []
		}
	}];
	const res = analyzeDomContext(events);
	const disabledSig = res.dom_signals.find(s => s.type === "disabled_action");
	assert.strictEqual(disabledSig, undefined, "Disabled submit on incomplete form must NOT trigger disabled_action");
});

// 4. Equal accept/decline buttons
runTest("4. Hard Negative: Equal accept/decline buttons", () => {
	const events = [{
		action: "CLICK",
		route: "/privacy-consent",
		text: "Accept Cookies",
		dom_context: {
			tag: "BUTTON",
			visible_text: "Accept Cookies",
			geometry: { width: 120, height: 40, area: 4800 },
			container_type: "dialog",
			competing_actions: [
				{ tag: "BUTTON", text: "Decline Cookies", width: 120, height: 40, area: 4800, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const asymmetry = res.dom_signals.find(s => s.type === "action_size_asymmetry");
	assert.strictEqual(asymmetry, undefined, "Equal buttons must NOT trigger action_size_asymmetry");
});

// 5. Normal confirmation dialog
runTest("5. Hard Negative: Normal confirmation dialog (balanced Save vs Cancel)", () => {
	const events = [{
		action: "CLICK",
		route: "/settings/account",
		text: "Confirm changes?",
		dom_context: {
			tag: "DIV",
			container_type: "modal",
			visible_text: "Confirm changes?",
			geometry: { width: 100, height: 36, area: 3600 },
			competing_actions: [
				{ tag: "BUTTON", text: "Save", width: 100, height: 36, area: 3600, visible: true },
				{ tag: "BUTTON", text: "Cancel", width: 100, height: 36, area: 3600, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const asymmetry = res.dom_signals.find(s => s.type === "action_size_asymmetry");
	const interference = res.dom_signals.find(s => s.type === "modal_interference");
	assert.strictEqual(asymmetry, undefined);
	assert.strictEqual(interference, undefined);
});

// 6. Normal secondary button (ratio < 2.5)
runTest("6. Hard Negative: Normal secondary button with modest ratio < 2.5", () => {
	const events = [{
		action: "CLICK",
		route: "/profile/edit",
		text: "Save Profile",
		dom_context: {
			tag: "BUTTON",
			visible_text: "Save Profile",
			geometry: { width: 120, height: 40, area: 4800 },
			container_type: "form",
			competing_actions: [
				{ tag: "BUTTON", text: "Cancel", width: 100, height: 30, area: 3000, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const asymmetry = res.dom_signals.find(s => s.type === "action_size_asymmetry");
	assert.strictEqual(asymmetry, undefined, "Standard secondary button ratio 1.6 must NOT trigger action_size_asymmetry");
});

// 7. Responsive mobile layout (stacked buttons with equal width)
runTest("7. Hard Negative: Responsive mobile layout with stacked buttons", () => {
	const events = [{
		action: "CLICK",
		route: "/order",
		text: "Continue to Payment",
		dom_context: {
			tag: "BUTTON",
			visible_text: "Continue to Payment",
			geometry: { width: 280, height: 44, area: 12320 },
			container_type: "page",
			competing_actions: [
				{ tag: "BUTTON", text: "Cancel Order", width: 280, height: 44, area: 12320, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const asymmetry = res.dom_signals.find(s => s.type === "action_size_asymmetry");
	assert.strictEqual(asymmetry, undefined);
});

// 8. Hidden hamburger menu
runTest("8. Hard Negative: Hidden hamburger menu in navigation", () => {
	const events = [{
		action: "NAVIGATION",
		route: "/products",
		text: "Products",
		dom_context: {
			tag: "NAV",
			container_type: "page",
			competing_actions: [
				{ tag: "DIV", text: "Mobile Menu Drawer", visible: false, display: "none" }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const hiddenAlt = res.dom_signals.find(s => s.type === "hidden_alternative");
	assert.strictEqual(hiddenAlt, undefined, "Hidden nav drawer must NOT trigger hidden_alternative");
});

// 9. Collapsed FAQ accordion
runTest("9. Hard Negative: Collapsed FAQ accordion", () => {
	const events = [{
		action: "CLICK",
		route: "/faq",
		text: "How do I update billing?",
		dom_context: {
			tag: "BUTTON",
			visible_text: "How do I update billing?",
			has_collapsed_alternative: false,
			container_type: "page"
		}
	}];
	const res = analyzeDomContext(events);
	const mismatch = res.dom_signals.find(s => s.type === "visibility_mismatch");
	assert.strictEqual(mismatch, undefined);
});

// 10. Disabled current plan in tier selector
runTest("10. Hard Negative: Disabled current plan in plan selector", () => {
	const events = [{
		action: "CLICK",
		route: "/plans",
		text: "Current Plan",
		dom_context: {
			tag: "BUTTON",
			visible_text: "Current Plan",
			is_disabled: true,
			container_type: "page",
			competing_actions: [
				{ tag: "BUTTON", text: "Upgrade to Pro", disabled: false, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const disabledSig = res.dom_signals.find(s => s.type === "disabled_action");
	assert.strictEqual(disabledSig, undefined, "Disabled current plan badge must NOT trigger disabled_action");
});

// 11. Normal required terms checkbox
runTest("11. Hard Negative: Standard required terms checkbox before checkout", () => {
	const events = [{
		action: "CLICK",
		route: "/checkout",
		text: "I agree to the Terms of Service",
		dom_context: {
			tag: "INPUT",
			type: "checkbox",
			visible_text: "I agree to the Terms of Service",
			is_required: true,
			container_type: "form"
		}
	}];
	const res = analyzeDomContext(events);
	const requiredSig = res.dom_signals.find(s => s.type === "required_option");
	assert.strictEqual(requiredSig, undefined, "Standard terms checkbox on checkout must NOT trigger required_option");
});

// 12. Cookie preference default
runTest("12. Hard Negative: Cookie preference default (optional marketing off)", () => {
	const events = [{
		action: "NAVIGATION",
		route: "/cookies",
		text: "Cookie Settings",
		dom_context: {
			container_type: "modal",
			preselected_options: [
				{ text: "Strictly Necessary Cookies", checked: true, required: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const preselected = res.dom_signals.find(s => s.type === "preselected_option");
	assert.strictEqual(preselected, undefined, "Essential cookies preselected must NOT trigger preselected_option");
});

// 13. Normal radio default (standard shipping selected)
runTest("13. Hard Negative: Normal radio default (Standard Shipping Free)", () => {
	const events = [{
		action: "NAVIGATION",
		route: "/checkout/shipping",
		text: "Select Shipping",
		dom_context: {
			container_type: "form",
			preselected_options: [
				{ text: "Standard Shipping (Free)", checked: true, required: false }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const preselected = res.dom_signals.find(s => s.type === "preselected_option");
	assert.strictEqual(preselected, undefined, "Free standard shipping default must NOT trigger preselected_option");
});

// 14. Standard multi-step form stepper
runTest("14. Hard Negative: Standard multi-step form stepper", () => {
	const events = [{
		action: "CLICK",
		route: "/onboarding/step2",
		text: "Next Step",
		dom_context: {
			tag: "BUTTON",
			visible_text: "Next Step",
			geometry: { width: 140, height: 40, area: 5600 },
			container_type: "form",
			competing_actions: [
				{ tag: "BUTTON", text: "Previous Step", width: 140, height: 40, area: 5600, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const asymmetry = res.dom_signals.find(s => s.type === "action_size_asymmetry");
	assert.strictEqual(asymmetry, undefined);
});

// 15. Normal small back link in header
runTest("15. Hard Negative: Normal small back link in header", () => {
	const events = [{
		action: "CLICK",
		route: "/account/billing",
		text: "Back to Dashboard",
		dom_context: {
			tag: "A",
			role: "link",
			visible_text: "Back to Dashboard",
			font_size_px: 12,
			geometry: { width: 120, height: 20, area: 2400 },
			container_type: "page"
		}
	}];
	const res = analyzeDomContext(events);
	const smallSig = res.dom_signals.find(s => s.type === "small_secondary_action");
	assert.strictEqual(smallSig, undefined, "12px back link in header must NOT trigger small_secondary_action");
});

// =====================================================================
// PART 2: POSITIVE SCENARIOS (15 Scenarios)
// =====================================================================

// 1. Preselected paid add-on
runTest("16. Positive: Preselected paid warranty/protection add-on", () => {
	const events = [{
		action: "NAVIGATION",
		route: "/checkout",
		text: "Checkout Review",
		dom_context: {
			container_type: "form",
			preselected_options: [
				{ text: "Add 2-Year Protection Plan (₹499)", checked: true, type: "checkbox" }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "preselected_option");
	assert.ok(sig, "Should detect preselected commercial add-on");
	assert.strictEqual(sig.detected, true);
	assert.ok(sig.strength === "moderate" || sig.strength === "strong");
});

// 2. Disabled cancellation with enabled keep-plan action
runTest("17. Positive: Disabled cancellation button with enabled keep-plan action", () => {
	const events = [
		{ action: "CLICK", route: "/account/cancel", text: "Cancel Subscription" },
		{
			action: "CLICK",
			route: "/account/cancel",
			text: "Cancel Subscription",
			dom_context: {
				tag: "BUTTON",
				visible_text: "Cancel Subscription",
				is_disabled: true,
				container_type: "modal",
				competing_actions: [
					{ tag: "BUTTON", text: "Keep My Subscription", disabled: false, visible: true }
				]
			}
		}
	];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "disabled_action");
	assert.ok(sig, "Should detect disabled cancellation action");
	assert.strictEqual(sig.detected, true);
	assert.strictEqual(sig.strength, "strong");
});

// 3. Hidden cancel/decline option
runTest("18. Positive: Hidden cancel/decline option (display: none)", () => {
	const events = [
		{ action: "CLICK", route: "/account/cancel", text: "Cancel Subscription" },
		{
			action: "CLICK",
			route: "/account/cancel/offer",
			text: "Stay and Save 50%",
			dom_context: {
				tag: "BUTTON",
				visible_text: "Stay and Save 50%",
				container_type: "modal",
				competing_actions: [
					{ tag: "A", text: "No thanks, proceed with cancellation", visible: false, display: "none" }
				]
			}
		}
	];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "hidden_alternative");
	assert.ok(sig, "Should detect hidden cancellation alternative");
	assert.strictEqual(sig.detected, true);
	assert.strictEqual(sig.strength, "strong");
});

// 4. Required cancellation survey
runTest("19. Positive: Required cancellation survey", () => {
	const events = [
		{ action: "CLICK", route: "/account/cancel", text: "Cancel Subscription" },
		{
			action: "CLICK",
			route: "/account/cancel/survey",
			text: "Select a reason for leaving",
			dom_context: {
				tag: "SELECT",
				visible_text: "Select a reason for leaving",
				is_required: true,
				container_type: "form"
			}
		}
	];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "required_option");
	assert.ok(sig, "Should detect required cancellation survey");
	assert.strictEqual(sig.detected, true);
});

// 5. Large keep-plan vs small cancel (Action size asymmetry)
runTest("20. Positive: Action size asymmetry (Keep Plan 6x larger than Cancel)", () => {
	const events = [
		{ action: "CLICK", route: "/account/cancel", text: "Cancel Subscription" },
		{
			action: "CLICK",
			route: "/account/cancel/offers",
			text: "Keep Subscription",
			dom_context: {
				tag: "BUTTON",
				visible_text: "Keep Subscription",
				geometry: { width: 300, height: 60, area: 18000 },
				container_type: "dialog",
				competing_actions: [
					{ tag: "A", text: "Cancel Subscription", width: 100, height: 30, area: 3000, visible: true }
				]
			}
		}
	];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "action_size_asymmetry");
	assert.ok(sig, "Should detect action size asymmetry");
	assert.strictEqual(sig.detected, true);
	assert.strictEqual(sig.strength, "strong");
	assert.strictEqual(sig.dom_properties.area_ratio, 6);
});

// 6. Tiny cancellation action (8px font)
runTest("21. Positive: Tiny cancellation action (8px font size)", () => {
	const events = [
		{ action: "CLICK", route: "/account/cancel", text: "Cancel Subscription" },
		{
			action: "CLICK",
			route: "/account/cancel/step2",
			text: "Continue to cancel",
			dom_context: {
				tag: "A",
				visible_text: "Continue to cancel",
				font_size_px: 8,
				geometry: { width: 80, height: 12, area: 960 },
				container_type: "modal"
			}
		}
	];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "small_secondary_action");
	assert.ok(sig, "Should detect small secondary action by font size");
	assert.strictEqual(sig.detected, true);
});

// 7. Preselected annual billing toggle
runTest("22. Positive: Preselected annual auto-renew billing toggle", () => {
	const events = [{
		action: "NAVIGATION",
		route: "/subscribe",
		text: "Choose Plan",
		dom_context: {
			container_type: "form",
			preselected_options: [
				{ text: "Annual auto-renew subscription (Save ₹1000)", checked: true, type: "checkbox" }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "preselected_option");
	assert.ok(sig, "Should detect preselected annual recurring billing");
	assert.strictEqual(sig.detected, true);
	assert.strictEqual(sig.strength, "strong");
});

// 8. Recurring donation default
runTest("23. Positive: Preselected recurring donation toggle", () => {
	const events = [{
		action: "NAVIGATION",
		route: "/donate",
		text: "Donate",
		dom_context: {
			container_type: "form",
			preselected_options: [
				{ text: "Make this a recurring monthly donation", checked: true, type: "checkbox" }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "preselected_option");
	assert.ok(sig, "Should detect preselected recurring donation");
	assert.strictEqual(sig.detected, true);
	assert.strictEqual(sig.strength, "strong");
});

// 9. Hidden opt-out in collapsed footer
runTest("24. Positive: Hidden opt-out in collapsed section during cancel", () => {
	const events = [
		{ action: "CLICK", route: "/account/cancel", text: "Cancel Subscription" },
		{
			action: "CLICK",
			route: "/account/cancel/review",
			text: "Stay with us",
			dom_context: {
				tag: "BUTTON",
				visible_text: "Stay with us",
				has_collapsed_alternative: true,
				container_type: "dialog"
			}
		}
	];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "visibility_mismatch");
	assert.ok(sig, "Should detect visibility mismatch with collapsed alternative");
	assert.strictEqual(sig.detected, true);
});

// 10. Enabled retention action + disabled cancellation (Action State Mismatch)
runTest("25. Positive: Action state mismatch (Retention enabled, Cancel disabled)", () => {
	const events = [
		{ action: "CLICK", route: "/account/cancel", text: "Cancel Subscription" },
		{
			action: "CLICK",
			route: "/account/cancel/offers",
			text: "Keep Plan with Discount",
			dom_context: {
				tag: "BUTTON",
				visible_text: "Keep Plan with Discount",
				is_disabled: false,
				container_type: "modal",
				competing_actions: [
					{ tag: "BUTTON", text: "Proceed to Cancel", disabled: true, visible: true }
				]
			}
		}
	];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "action_state_mismatch");
	assert.ok(sig, "Should detect action state mismatch");
	assert.strictEqual(sig.detected, true);
	assert.strictEqual(sig.strength, "strong");
});

// 11. Cancellation modal interference
runTest("26. Positive: Cancellation modal interference without close button", () => {
	const events = [
		{ action: "CLICK", route: "/account/cancel", text: "Cancel Subscription" },
		{
			action: "CLICK",
			route: "/account/cancel",
			text: "Wait! Don't go!",
			dom_context: {
				tag: "DIV",
				container_type: "modal",
				visible_text: "Wait! Don't go!",
				has_close_button: false
			}
		}
	];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "modal_interference");
	assert.ok(sig, "Should detect modal interference");
	assert.strictEqual(sig.detected, true);
	assert.strictEqual(sig.strength, "strong");
});

// 12. Mandatory feedback before cancellation
runTest("27. Positive: Mandatory feedback form before cancellation", () => {
	const events = [
		{ action: "CLICK", route: "/account/cancel", text: "Cancel Subscription" },
		{
			action: "CLICK",
			route: "/account/cancel/feedback",
			text: "Tell us why you are cancelling (Required feedback)",
			dom_context: {
				tag: "TEXTAREA",
				visible_text: "Tell us why you are cancelling (Required feedback)",
				is_required: true,
				container_type: "form"
			}
		}
	];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "required_option");
	assert.ok(sig, "Should detect mandatory feedback gating cancellation");
	assert.strictEqual(sig.detected, true);
});

// 13. Preselected expedited shipping with extra fee
runTest("28. Positive: Preselected expedited priority shipping with fee", () => {
	const events = [{
		action: "NAVIGATION",
		route: "/checkout/delivery",
		text: "Delivery Options",
		dom_context: {
			container_type: "form",
			preselected_options: [
				{ text: "Expedited Priority Shipping (₹199 extra)", checked: true, type: "radio" }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "preselected_option");
	assert.ok(sig, "Should detect preselected expedited shipping fee");
	assert.strictEqual(sig.detected, true);
});

// 14. Asymmetric confirmation dialog
runTest("29. Positive: Asymmetric confirmation dialog with confirm-shaming", () => {
	const events = [
		{ action: "CLICK", route: "/account/cancel", text: "Cancel Subscription" },
		{
			action: "CLICK",
			route: "/account/cancel/confirm",
			text: "Are you sure you want to cancel?",
			dom_context: {
				tag: "DIV",
				container_type: "dialog",
				visible_text: "Are you sure you want to cancel?",
				has_confirm_shaming: true
			}
		}
	];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "confirmation_ui");
	assert.ok(sig, "Should detect confirmation UI with asymmetric styling");
	assert.strictEqual(sig.detected, true);
	assert.strictEqual(sig.dom_properties.is_asymmetric, true);
});

// 15. Multiple required cancellation acknowledgements
runTest("30. Positive: Multiple required cancellation acknowledgements", () => {
	const events = [
		{ action: "CLICK", route: "/account/cancel", text: "Cancel Subscription" },
		{
			action: "CLICK",
			route: "/account/cancel/acknowledgements",
			text: "Check all boxes to enable cancellation",
			dom_context: {
				tag: "FORM",
				container_type: "form",
				visible_text: "Check all boxes to enable cancellation",
				required_acknowledgements: [
					{ label: "I forfeit my points", checked: false, required: true },
					{ label: "I understand data will be deleted", checked: false, required: true },
					{ label: "I agree cancellation is irreversible", checked: false, required: true }
				]
			}
		}
	];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "required_option");
	assert.ok(sig, "Should detect multiple required acknowledgements gating cancel");
	assert.strictEqual(sig.detected, true);
	assert.strictEqual(sig.strength, "strong");
});

// =====================================================================
// PART 3: EDGE CASES & RESILIENCE (12 Scenarios)
// =====================================================================

// 31. null events
runTest("31. Edge Case: null events parameter", () => {
	const res = analyzeDomContext(null);
	assert.deepStrictEqual(res.dom_signals, []);
	assert.deepStrictEqual(res.evidence, []);
});

// 32. empty events array
runTest("32. Edge Case: empty events array", () => {
	const res = analyzeDomContext([]);
	assert.deepStrictEqual(res.dom_signals, []);
	assert.deepStrictEqual(res.evidence, []);
});

// 33. missing dom_context on event
runTest("33. Edge Case: missing dom_context on event", () => {
	const res = analyzeDomContext([{ action: "CLICK", route: "/home", text: "Home" }]);
	assert.deepStrictEqual(res.dom_signals, []);
	assert.deepStrictEqual(res.evidence, []);
});

// 34. empty competing_actions
runTest("34. Edge Case: empty competing_actions array", () => {
	const events = [{
		action: "CLICK",
		route: "/settings",
		text: "Save",
		dom_context: {
			tag: "BUTTON",
			competing_actions: []
		}
	}];
	const res = analyzeDomContext(events);
	assert.ok(Array.isArray(res.dom_signals));
});

// 35. missing geometry object
runTest("35. Edge Case: missing geometry object defaults safely", () => {
	const events = [{
		action: "CLICK",
		route: "/page",
		text: "Click me",
		dom_context: {
			tag: "BUTTON",
			geometry: null
		}
	}];
	const res = analyzeDomContext(events);
	assert.ok(Array.isArray(res.dom_signals));
});

// 36. zero-size element
runTest("36. Edge Case: zero-size element (width: 0, height: 0, area: 0)", () => {
	const events = [{
		action: "CLICK",
		route: "/cancel",
		text: "Cancel",
		dom_context: {
			tag: "BUTTON",
			geometry: { width: 0, height: 0, area: 0 },
			competing_actions: [
				{ tag: "BUTTON", text: "Stay", width: 100, height: 40, area: 4000 }
			]
		}
	}];
	const res = analyzeDomContext(events);
	// Should not throw divide-by-zero exception
	assert.ok(Array.isArray(res.dom_signals));
});

// 37. duplicate element labels in competing actions
runTest("37. Edge Case: duplicate element labels in competing actions", () => {
	const events = [{
		action: "CLICK",
		route: "/cancel",
		text: "Cancel",
		dom_context: {
			tag: "BUTTON",
			competing_actions: [
				{ tag: "BUTTON", text: "Cancel", width: 100, height: 30, area: 3000 },
				{ tag: "BUTTON", text: "Cancel", width: 100, height: 30, area: 3000 }
			]
		}
	}];
	const res = analyzeDomContext(events);
	assert.ok(Array.isArray(res.dom_signals));
});

// 38. SPA rerender (same element_ref across multiple events deduplicates)
runTest("38. Edge Case: SPA rerender duplicate signal deduplication", () => {
	const domContext = {
		tag: "INPUT",
		element_ref: "INPUT::role(checkbox)::text(warranty)::ord(1)",
		checked_state: true,
		visible_text: "Add Warranty Protection (₹199)",
		container_type: "form"
	};
	const events = [
		{ action: "CLICK", route: "/checkout", text: "Add Warranty", dom_context: domContext },
		{ action: "CLICK", route: "/checkout", text: "Add Warranty", dom_context: domContext }
	];
	const res = analyzeDomContext(events);
	const preselectedList = res.dom_signals.filter(s => s.type === "preselected_option");
	// Should deduplicate identical signals
	assert.strictEqual(preselectedList.length, 1);
});

// 39. dynamic modal without close button vs with close button
runTest("39. Edge Case: dynamic modal with close button does not trigger interference without cancel flow", () => {
	const events = [{
		action: "CLICK",
		route: "/browse",
		text: "Welcome Offer",
		dom_context: {
			container_type: "modal",
			has_close_button: true
		}
	}];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "modal_interference");
	assert.strictEqual(sig, undefined, "Modal with close button on normal browse must NOT trigger modal_interference");
});

// 40. cross-origin iframe boundary (null / empty dom_context)
runTest("40. Edge Case: cross-origin iframe boundary handles gracefully", () => {
	const events = [
		{ action: "CLICK", route: "/payment", text: "Stripe Frame", dom_context: null }
	];
	const res = analyzeDomContext(events);
	assert.deepStrictEqual(res.dom_signals, []);
});

// 41. accessibility hidden elements (aria-hidden or sr-only)
runTest("41. Edge Case: accessibility hidden elements (aria-hidden or sr-only) not flagged as hidden alternative", () => {
	const events = [
		{ action: "CLICK", route: "/cancel", text: "Cancel" },
		{
			action: "CLICK",
			route: "/cancel",
			text: "Cancel",
			dom_context: {
				tag: "BUTTON",
				competing_actions: [
					{ tag: "SPAN", text: "Screen reader skip link", visible: false, aria_hidden: true }
				]
			}
		}
	];
	const res = analyzeDomContext(events);
	const hiddenAlt = res.dom_signals.find(s => s.type === "hidden_alternative");
	assert.strictEqual(hiddenAlt, undefined, "aria-hidden element must NOT be flagged as hidden_alternative");
});

// 42. malformed DOM payload (strings instead of numbers, unexpected types)
runTest("42. Edge Case: malformed DOM payload handled gracefully", () => {
	const events = [{
		action: "CLICK",
		route: "/cancel",
		text: "Cancel",
		dom_context: {
			tag: 12345,
			geometry: { width: "invalid", height: null, area: undefined },
			font_size_px: "not-a-number",
			competing_actions: "not-an-array"
		}
	}];
	const res = analyzeDomContext(events);
	assert.ok(Array.isArray(res.dom_signals));
});

console.log("\n==================================================");
console.log(`TEST RESULTS: ${passed} PASSED, ${failed} FAILED (TOTAL: ${passed + failed})`);
console.log("==================================================");

if (failed > 0) {
	process.exit(1);
}
