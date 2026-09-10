/**
 * DarkShield Phase B4.1 — Audit Fix Verification Suite
 *
 * Validates B4.1 audit fixes:
 * - 25 False-Positive / Hard-Negative tests (verifies conservative boundaries)
 * - 10 Positive scenario tests (verifies observable DOM signals & evidence schema)
 * - Verification of Fixes 1-14:
 *   • action_size_asymmetry requires alternative decision pair in relevant context
 *   • small_secondary_action requires decision context and semantic competitor
 *   • visibility_mismatch requires related decision alternative (not FAQs / Privacy)
 *   • confirmation_ui defaults to weak structure without confirm-shaming unless asymmetric
 *   • preselected_option records commercial_context and commercial_reason
 *   • deduplication merges event_indices
 *   • zero final risk scores or legal claims
 */

const assert = require("assert");
const { analyzeDomContext, makeElementRef } = require("./extension/analyzer/domAnalyzer.js");

console.log("==================================================");
console.log("RUNNING DARKSHIELD PHASE B4.1 AUDIT FIX VERIFICATION");
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
// PART 1: 25 FALSE-POSITIVE / HARD-NEGATIVE TESTS (FIX 10)
// =====================================================================

// 1. Continue 6x larger than Back
runTest("1. False-Positive Control: Continue 6x larger than Back (Navigation)", () => {
	const events = [{
		action: "CLICK",
		route: "/onboarding/step-2",
		text: "Continue",
		dom_context: {
			tag: "BUTTON",
			visible_text: "Continue",
			geometry: { width: 300, height: 60, area: 18000 },
			container_type: "form",
			competing_actions: [
				{ tag: "BUTTON", text: "Back", width: 100, height: 30, area: 3000, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const asymmetry = res.dom_signals.find(s => s.type === "action_size_asymmetry");
	assert.strictEqual(asymmetry, undefined, "Continue vs Back is navigation, must NOT trigger action_size_asymmetry");
});

// 2. Next 5x larger than Previous
runTest("2. False-Positive Control: Next 5x larger than Previous (Pagination/Stepper)", () => {
	const events = [{
		action: "CLICK",
		route: "/survey/page2",
		text: "Next",
		dom_context: {
			tag: "BUTTON",
			visible_text: "Next",
			geometry: { width: 250, height: 50, area: 12500 },
			container_type: "form",
			competing_actions: [
				{ tag: "BUTTON", text: "Previous", width: 100, height: 25, area: 2500, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const asymmetry = res.dom_signals.find(s => s.type === "action_size_asymmetry");
	assert.strictEqual(asymmetry, undefined, "Next vs Previous must NOT trigger action_size_asymmetry");
});

// 3. Save 4x larger than Cancel (in ordinary settings)
runTest("3. False-Positive Control: Save 4x larger than Cancel in ordinary settings", () => {
	const events = [{
		action: "CLICK",
		route: "/settings/preferences",
		text: "Save Changes",
		dom_context: {
			tag: "BUTTON",
			visible_text: "Save Changes",
			geometry: { width: 200, height: 40, area: 8000 },
			container_type: "form",
			competing_actions: [
				{ tag: "BUTTON", text: "Cancel", width: 80, height: 25, area: 2000, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const asymmetry = res.dom_signals.find(s => s.type === "action_size_asymmetry");
	assert.strictEqual(asymmetry, undefined, "Save vs Cancel in ordinary settings must NOT trigger action_size_asymmetry");
});

// 4. Small Close button
runTest("4. False-Positive Control: Small Close button (10px icon/button)", () => {
	const events = [{
		action: "CLICK",
		route: "/dashboard",
		text: "Close",
		dom_context: {
			tag: "BUTTON",
			visible_text: "Close",
			font_size_px: 10,
			geometry: { width: 20, height: 20, area: 400 },
			container_type: "modal"
		}
	}];
	const res = analyzeDomContext(events);
	const smallSig = res.dom_signals.find(s => s.type === "small_secondary_action");
	assert.strictEqual(smallSig, undefined, "Ordinary modal close button must NOT trigger small_secondary_action");
});

// 5. Small Help link
runTest("5. False-Positive Control: Small Help link (footer/header)", () => {
	const events = [{
		action: "CLICK",
		route: "/store",
		text: "Help & FAQ",
		dom_context: {
			tag: "A",
			visible_text: "Help & FAQ",
			font_size_px: 10,
			geometry: { width: 60, height: 15, area: 900 },
			container_type: "page"
		}
	}];
	const res = analyzeDomContext(events);
	const smallSig = res.dom_signals.find(s => s.type === "small_secondary_action");
	assert.strictEqual(smallSig, undefined, "Small Help link must NOT trigger small_secondary_action");
});

// 6. Small Back link
runTest("6. False-Positive Control: Small Back link (breadcrumb/header)", () => {
	const events = [{
		action: "CLICK",
		route: "/products/item-123",
		text: "Back to search results",
		dom_context: {
			tag: "A",
			visible_text: "Back to search results",
			font_size_px: 10,
			geometry: { width: 140, height: 16, area: 2240 },
			container_type: "page"
		}
	}];
	const res = analyzeDomContext(events);
	const smallSig = res.dom_signals.find(s => s.type === "small_secondary_action");
	assert.strictEqual(smallSig, undefined, "Breadcrumb back link must NOT trigger small_secondary_action");
});

// 7. Large Buy button + normal footer
runTest("7. False-Positive Control: Large Buy button + normal footer links", () => {
	const events = [{
		action: "CLICK",
		route: "/product",
		text: "Buy Now",
		dom_context: {
			tag: "BUTTON",
			visible_text: "Buy Now",
			geometry: { width: 300, height: 60, area: 18000 },
			container_type: "page",
			competing_actions: [
				{ tag: "A", text: "Privacy Policy", width: 90, height: 18, area: 1620, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const asymmetry = res.dom_signals.find(s => s.type === "action_size_asymmetry");
	assert.strictEqual(asymmetry, undefined, "Buy Now vs Privacy Policy are non-competing; must NOT trigger asymmetry");
});

// 8. Hidden FAQ
runTest("8. False-Positive Control: Hidden FAQ content", () => {
	const events = [{
		action: "CLICK",
		route: "/faq",
		text: "FAQ Question",
		dom_context: {
			tag: "BUTTON",
			visible_text: "FAQ Question",
			has_collapsed_alternative: false,
			competing_actions: [
				{ tag: "DIV", text: "Answer content (hidden)", visible: false, display: "none" }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const mismatch = res.dom_signals.find(s => s.type === "visibility_mismatch");
	const hiddenAlt = res.dom_signals.find(s => s.type === "hidden_alternative");
	assert.strictEqual(mismatch, undefined);
	assert.strictEqual(hiddenAlt, undefined);
});

// 9. Hidden Privacy Policy
runTest("9. False-Positive Control: Hidden Privacy Policy link in collapsed footer", () => {
	const events = [{
		action: "NAVIGATION",
		route: "/home",
		text: "Home",
		dom_context: {
			container_type: "page",
			competing_actions: [
				{ tag: "A", text: "Privacy Policy", visible: false, display: "none" }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const hiddenAlt = res.dom_signals.find(s => s.type === "hidden_alternative");
	assert.strictEqual(hiddenAlt, undefined, "Hidden Privacy Policy link must NOT trigger hidden_alternative");
});

// 10. Hidden Help section
runTest("10. False-Positive Control: Hidden Help section", () => {
	const events = [{
		action: "CLICK",
		route: "/checkout",
		text: "Proceed to Checkout",
		dom_context: {
			tag: "BUTTON",
			visible_text: "Proceed to Checkout",
			competing_actions: [
				{ tag: "DIV", text: "Help and FAQs", visible: false, display: "none" }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const hiddenAlt = res.dom_signals.find(s => s.type === "hidden_alternative");
	assert.strictEqual(hiddenAlt, undefined);
});

// 11. Normal confirmation dialog
runTest("11. False-Positive Control: Normal confirmation dialog (standard structure)", () => {
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
				has_confirm_shaming: false
			}
		}
	];
	const res = analyzeDomContext(events);
	const conf = res.dom_signals.find(s => s.type === "confirmation_ui");
	assert.ok(conf, "Should observe confirmation structure");
	assert.strictEqual(conf.strength, "weak", "Normal confirmation dialog must be weak evidence only");
	assert.strictEqual(conf.dom_properties.is_asymmetric, false);
});

// 12. Delete confirmation
runTest("12. False-Positive Control: Delete item confirmation", () => {
	const events = [{
		action: "CLICK",
		route: "/files",
		text: "Delete Document?",
		dom_context: {
			tag: "DIV",
			container_type: "modal",
			visible_text: "Delete Document?",
			competing_actions: [
				{ tag: "BUTTON", text: "Delete", visible: true, width: 80, height: 30, area: 2400 },
				{ tag: "BUTTON", text: "Cancel", visible: true, width: 80, height: 30, area: 2400 }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const strongSig = res.dom_signals.find(s => s.strength === "strong");
	assert.strictEqual(strongSig, undefined, "Delete item dialog must NOT produce strong suspicious signals");
});

// 13. Purchase confirmation
runTest("13. False-Positive Control: Purchase confirmation dialog", () => {
	const events = [{
		action: "CLICK",
		route: "/checkout/review",
		text: "Confirm purchase of item",
		dom_context: {
			tag: "DIV",
			container_type: "modal",
			visible_text: "Confirm purchase of item",
			competing_actions: [
				{ tag: "BUTTON", text: "Place Order", visible: true, width: 140, height: 40, area: 5600 },
				{ tag: "BUTTON", text: "Edit Cart", visible: true, width: 120, height: 40, area: 4800 }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const strongSig = res.dom_signals.find(s => s.strength === "strong");
	assert.strictEqual(strongSig, undefined, "Standard purchase confirmation must NOT produce strong signals");
});

// 14. Logout confirmation
runTest("14. False-Positive Control: Logout confirmation dialog", () => {
	const events = [{
		action: "CLICK",
		route: "/account",
		text: "Are you sure you want to log out?",
		dom_context: {
			tag: "DIV",
			container_type: "dialog",
			visible_text: "Are you sure you want to log out?",
			competing_actions: [
				{ tag: "BUTTON", text: "Log Out", visible: true, width: 90, height: 32, area: 2880 },
				{ tag: "BUTTON", text: "Cancel", visible: true, width: 90, height: 32, area: 2880 }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const strongSig = res.dom_signals.find(s => s.strength === "strong");
	assert.strictEqual(strongSig, undefined, "Logout confirmation dialog must NOT produce strong signals");
});

// 15. Preselected country
runTest("15. False-Positive Control: Preselected country default", () => {
	const events = [{
		action: "PAGE_INIT",
		route: "/checkout",
		text: "Country selector",
		dom_context: {
			container_type: "form",
			preselected_options: [
				{ text: "Country: India", checked: true, type: "select" }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const preselected = res.dom_signals.find(s => s.type === "preselected_option");
	assert.strictEqual(preselected, undefined, "Country default must NOT trigger preselected_option");
});

// 16. Preselected language
runTest("16. False-Positive Control: Preselected language default", () => {
	const events = [{
		action: "PAGE_INIT",
		route: "/preferences",
		text: "Language",
		dom_context: {
			container_type: "form",
			preselected_options: [
				{ text: "Language: English (US)", checked: true, type: "radio" }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const preselected = res.dom_signals.find(s => s.type === "preselected_option");
	assert.strictEqual(preselected, undefined, "Language default must NOT trigger preselected_option");
});

// 17. Remember-me checkbox
runTest("17. False-Positive Control: Remember-me checkbox on sign-in", () => {
	const events = [{
		action: "PAGE_INIT",
		route: "/signin",
		text: "Sign In",
		dom_context: {
			container_type: "form",
			preselected_options: [
				{ text: "Remember me", checked: true, type: "checkbox" }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const preselected = res.dom_signals.find(s => s.type === "preselected_option");
	assert.strictEqual(preselected, undefined, "Remember me must NOT trigger preselected_option");
});

// 18. Standard shipping default
runTest("18. False-Positive Control: Standard shipping default", () => {
	const events = [{
		action: "PAGE_INIT",
		route: "/checkout",
		text: "Delivery Options",
		dom_context: {
			container_type: "form",
			preselected_options: [
				{ text: "Standard shipping (3-5 days)", checked: true, type: "radio" }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const preselected = res.dom_signals.find(s => s.type === "preselected_option");
	assert.strictEqual(preselected, undefined, "Standard shipping must NOT trigger preselected_option");
});

// 19. Free shipping default
runTest("19. False-Positive Control: Free shipping default", () => {
	const events = [{
		action: "PAGE_INIT",
		route: "/checkout",
		text: "Shipping Method",
		dom_context: {
			container_type: "form",
			preselected_options: [
				{ text: "Free ground shipping", checked: true, type: "radio" }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const preselected = res.dom_signals.find(s => s.type === "preselected_option");
	assert.strictEqual(preselected, undefined, "Free shipping default must NOT trigger preselected_option");
});

// 20. Disabled Submit because required fields missing
runTest("20. False-Positive Control: Disabled Submit button due to missing required fields", () => {
	const events = [{
		action: "CLICK",
		route: "/register",
		text: "Create Account",
		dom_context: {
			tag: "BUTTON",
			visible_text: "Create Account",
			is_disabled: true,
			container_type: "form",
			competing_actions: []
		}
	}];
	const res = analyzeDomContext(events);
	const disabledSig = res.dom_signals.find(s => s.type === "disabled_action");
	assert.strictEqual(disabledSig, undefined, "Disabled submit on incomplete form must NOT trigger disabled_action");
});

// 21. Disabled current subscription plan
runTest("21. False-Positive Control: Disabled current subscription plan button", () => {
	const events = [{
		action: "CLICK",
		route: "/pricing",
		text: "Current Plan",
		dom_context: {
			tag: "BUTTON",
			visible_text: "Current Plan",
			is_disabled: true,
			container_type: "page",
			competing_actions: [
				{ tag: "BUTTON", text: "Select Enterprise", disabled: false, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const disabledSig = res.dom_signals.find(s => s.type === "disabled_action");
	assert.strictEqual(disabledSig, undefined, "Disabled current plan badge must NOT trigger disabled_action");
});

// 22. Responsive mobile layout (vertical buttons)
runTest("22. False-Positive Control: Responsive mobile layout with stacked equal buttons", () => {
	const events = [{
		action: "CLICK",
		route: "/cart",
		text: "Checkout",
		dom_context: {
			tag: "BUTTON",
			visible_text: "Checkout",
			geometry: { width: 320, height: 48, area: 15360 },
			container_type: "page",
			competing_actions: [
				{ tag: "BUTTON", text: "Continue Shopping", width: 320, height: 48, area: 15360, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const asymmetry = res.dom_signals.find(s => s.type === "action_size_asymmetry");
	assert.strictEqual(asymmetry, undefined);
});

// 23. Accessibility-hidden alternative
runTest("23. False-Positive Control: Accessibility-hidden element (aria-hidden)", () => {
	const events = [
		{ action: "CLICK", route: "/account/cancel", text: "Cancel Subscription" },
		{
			action: "CLICK",
			route: "/account/cancel",
			text: "Stay",
			dom_context: {
				tag: "BUTTON",
				visible_text: "Stay Subscribed",
				competing_actions: [
					{ tag: "SPAN", text: "Screen reader skip", visible: false, aria_hidden: true }
				]
			}
		}
	];
	const res = analyzeDomContext(events);
	const hiddenAlt = res.dom_signals.find(s => s.type === "hidden_alternative");
	assert.strictEqual(hiddenAlt, undefined, "aria-hidden element must NOT be treated as hidden alternative");
});

// 24. Modal with ordinary close button
runTest("24. False-Positive Control: Modal with ordinary accessible close button", () => {
	const events = [{
		action: "CLICK",
		route: "/shop",
		text: "Seasonal Promotion",
		dom_context: {
			tag: "DIV",
			container_type: "modal",
			visible_text: "Seasonal Promotion",
			has_close_button: true
		}
	}];
	const res = analyzeDomContext(events);
	const interference = res.dom_signals.find(s => s.type === "modal_interference");
	assert.strictEqual(interference, undefined, "Ordinary modal with close button in shopping context must NOT trigger interference");
});

// 25. Duplicate DOM elements caused by SPA rerender
runTest("25. False-Positive Control: Duplicate DOM elements caused by SPA rerender (Merged)", () => {
	const domCtx = {
		tag: "INPUT",
		element_ref: "INPUT::role(checkbox)::text(warranty)::ord(1)",
		checked_state: true,
		visible_text: "Add Paid Warranty (₹149)",
		container_type: "form"
	};
	const events = [
		{ action: "CLICK", route: "/checkout", text: "Warranty", dom_context: domCtx },
		{ action: "CLICK", route: "/checkout", text: "Warranty", dom_context: domCtx }
	];
	const res = analyzeDomContext(events);
	const preselectedList = res.dom_signals.filter(s => s.type === "preselected_option");
	assert.strictEqual(preselectedList.length, 1, "Duplicate events on same element must merge into 1 signal");
	assert.deepStrictEqual(preselectedList[0].event_indices, [0, 1], "event_indices must merge both sightings");
});

// =====================================================================
// PART 2: 10 POSITIVE SCENARIOS (FIX 11)
// =====================================================================

// 1. 5x Keep Subscription vs Cancel
runTest("26. Positive: 5x Keep Subscription vs Cancel (action_size_asymmetry)", () => {
	const events = [
		{ action: "CLICK", route: "/account/cancel", text: "Cancel Subscription" },
		{
			action: "CLICK",
			route: "/account/cancel/offer",
			text: "Keep Subscription",
			dom_context: {
				tag: "BUTTON",
				visible_text: "Keep Subscription",
				geometry: { width: 250, height: 50, area: 12500 },
				container_type: "dialog",
				competing_actions: [
					{ tag: "A", text: "Cancel Subscription", width: 100, height: 25, area: 2500, visible: true }
				]
			}
		}
	];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "action_size_asymmetry");
	assert.ok(sig, "Should detect action size asymmetry");
	assert.strictEqual(sig.strength, "strong");
	assert.strictEqual(sig.dom_properties.ratio, 5);
	assert.strictEqual(sig.dom_properties.context, "cancellation");
	assert.ok(sig.dom_properties.primary_element_ref);
	assert.ok(sig.dom_properties.secondary_element_ref);
});

// 2. 6x Continue Plan vs Cancel Plan
runTest("27. Positive: 6x Continue Plan vs Cancel Plan (action_size_asymmetry)", () => {
	const events = [
		{ action: "CLICK", route: "/billing/cancel", text: "Cancel Subscription" },
		{
			action: "CLICK",
			route: "/billing/cancel/confirm",
			text: "Continue with Plan",
			dom_context: {
				tag: "BUTTON",
				visible_text: "Continue with Plan",
				geometry: { width: 300, height: 60, area: 18000 },
				container_type: "modal",
				competing_actions: [
					{ tag: "A", text: "Cancel Plan", width: 100, height: 30, area: 3000, visible: true }
				]
			}
		}
	];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "action_size_asymmetry");
	assert.ok(sig);
	assert.strictEqual(sig.strength, "strong");
	assert.strictEqual(sig.dom_properties.ratio, 6);
});

// 3. 8px Cancel Subscription
runTest("28. Positive: 8px Cancel Subscription (small_secondary_action)", () => {
	const events = [
		{ action: "CLICK", route: "/account/cancel", text: "Cancel Subscription" },
		{
			action: "CLICK",
			route: "/account/cancel/step2",
			text: "Proceed with cancellation",
			dom_context: {
				tag: "A",
				visible_text: "Proceed with cancellation",
				font_size_px: 8,
				geometry: { width: 90, height: 12, area: 1080 },
				container_type: "modal",
				competing_actions: [
					{ tag: "BUTTON", text: "Keep Subscription", width: 200, height: 40, area: 8000, visible: true }
				]
			}
		}
	];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "small_secondary_action");
	assert.ok(sig, "Should detect small secondary action");
	assert.strictEqual(sig.strength, "strong");
	assert.strictEqual(sig.dom_properties.font_size_px, 8);
	assert.ok(sig.dom_properties.primary_element_ref);
	assert.ok(sig.dom_properties.secondary_element_ref);
});

// 4. hidden Cancel Subscription
runTest("29. Positive: Hidden Cancel Subscription (hidden_alternative)", () => {
	const events = [
		{ action: "CLICK", route: "/account/cancel", text: "Cancel Subscription" },
		{
			action: "CLICK",
			route: "/account/cancel/options",
			text: "Stay with discount",
			dom_context: {
				tag: "BUTTON",
				visible_text: "Stay with discount",
				container_type: "dialog",
				competing_actions: [
					{ tag: "A", text: "Cancel Subscription", visible: false, display: "none" }
				]
			}
		}
	];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "hidden_alternative");
	assert.ok(sig, "Should detect hidden cancellation alternative");
	assert.strictEqual(sig.strength, "strong");
});

// 5. disabled Cancel + enabled Keep Plan
runTest("30. Positive: Disabled Cancel + enabled Keep Plan (disabled_action)", () => {
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
					{ tag: "BUTTON", text: "Keep Plan", disabled: false, visible: true }
				]
			}
		}
	];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "disabled_action");
	assert.ok(sig, "Should detect disabled cancellation action");
	assert.strictEqual(sig.strength, "strong");
});

// 6. preselected paid warranty
runTest("31. Positive: Preselected paid warranty (preselected_option)", () => {
	const events = [{
		action: "NAVIGATION",
		route: "/checkout",
		text: "Checkout",
		dom_context: {
			container_type: "form",
			preselected_options: [
				{ text: "Add 3-Year Extended Warranty (₹599)", checked: true, type: "checkbox" }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "preselected_option");
	assert.ok(sig);
	assert.strictEqual(sig.dom_properties.commercial_context, true);
	assert.strictEqual(sig.dom_properties.commercial_reason, "paid_warranty");
});

// 7. preselected insurance
runTest("32. Positive: Preselected insurance (preselected_option)", () => {
	const events = [{
		action: "NAVIGATION",
		route: "/checkout",
		text: "Checkout",
		dom_context: {
			container_type: "form",
			preselected_options: [
				{ text: "Add Trip Insurance Coverage (₹199)", checked: true, type: "checkbox" }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "preselected_option");
	assert.ok(sig);
	assert.strictEqual(sig.dom_properties.commercial_context, true);
	assert.strictEqual(sig.dom_properties.commercial_reason, "insurance");
});

// 8. preselected recurring billing
runTest("33. Positive: Preselected recurring billing (preselected_option)", () => {
	const events = [{
		action: "NAVIGATION",
		route: "/subscribe",
		text: "Subscription Tier",
		dom_context: {
			container_type: "form",
			preselected_options: [
				{ text: "Annual auto-renew subscription", checked: true, type: "checkbox" }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "preselected_option");
	assert.ok(sig);
	assert.strictEqual(sig.dom_properties.commercial_context, true);
	assert.strictEqual(sig.dom_properties.commercial_reason, "annual_auto_renew");
});

// 9. preselected paid add-on
runTest("34. Positive: Preselected paid add-on (preselected_option)", () => {
	const events = [{
		action: "NAVIGATION",
		route: "/cart",
		text: "Cart Review",
		dom_context: {
			container_type: "form",
			preselected_options: [
				{ text: "Add-on Premium Gift Wrap (₹99)", checked: true, type: "checkbox" }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "preselected_option");
	assert.ok(sig);
	assert.strictEqual(sig.dom_properties.commercial_context, true);
	assert.strictEqual(sig.dom_properties.commercial_reason, "paid_add_on");
});

// 10. hidden decline inside cancellation dialog
runTest("35. Positive: Hidden decline inside cancellation dialog (hidden_alternative)", () => {
	const events = [
		{ action: "CLICK", route: "/account/cancel", text: "Cancel Subscription" },
		{
			action: "CLICK",
			route: "/account/cancel/dialog",
			text: "Keep Subscription",
			dom_context: {
				tag: "BUTTON",
				visible_text: "Keep Subscription",
				container_type: "dialog",
				competing_actions: [
					{ tag: "A", text: "Decline and cancel subscription", visible: false, display: "none" }
				]
			}
		}
	];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "hidden_alternative");
	assert.ok(sig, "Should detect hidden decline option in dialog");
	assert.strictEqual(sig.strength, "strong");
});

// =====================================================================
// PART 3: EVIDENCE CONTRACT & NO RISK SCORE VERIFICATION (FIX 12 & 13)
// =====================================================================

runTest("36. Evidence Contract: Every signal has required fields and observable facts only", () => {
	const events = [
		{ action: "CLICK", route: "/account/cancel", text: "Cancel Subscription" },
		{
			action: "CLICK",
			route: "/account/cancel/offer",
			text: "Keep Subscription",
			dom_context: {
				tag: "BUTTON",
				visible_text: "Keep Subscription",
				geometry: { width: 300, height: 60, area: 18000 },
				container_type: "modal",
				competing_actions: [
					{ tag: "A", text: "Cancel Subscription", width: 60, height: 20, area: 1200, visible: true }
				]
			}
		}
	];
	const res = analyzeDomContext(events);
	assert.ok(res.dom_signals.length > 0);
	res.dom_signals.forEach(sig => {
		assert.ok(sig.type, "Missing type");
		assert.strictEqual(sig.detected, true);
		assert.ok(["weak", "moderate", "strong"].includes(sig.strength), `Invalid strength: ${sig.strength}`);
		assert.ok(typeof sig.reason === "string" && sig.reason.length > 0, "Missing reason");
		assert.ok(sig.element_ref, "Missing element_ref");
		assert.ok(Array.isArray(sig.event_indices), "event_indices must be array");
		assert.ok(typeof sig.route === "string", "Missing route");
		assert.ok(sig.dom_properties && typeof sig.dom_properties === "object", "dom_properties must be object");

		// Fix 12: Avoid subjective claims
		assert.ok(!sig.reason.toLowerCase().includes("manipulated"), "Reason must not claim manipulation");
		assert.ok(!sig.reason.toLowerCase().includes("dark pattern confirmed"), "Reason must not claim dark pattern confirmed");
	});

	// Fix 13: Ensure output contains NO riskScore, legal_violation, etc.
	assert.strictEqual(res.riskScore, undefined);
	assert.strictEqual(res.risk_probability, undefined);
	assert.strictEqual(res.final_risk, undefined);
	assert.strictEqual(res.legal_violation, undefined);
	assert.strictEqual(res.confirmed_dark_pattern, undefined);
});

console.log("\n==================================================");
console.log(`TEST RESULTS: ${passed} PASSED, ${failed} FAILED (TOTAL: ${passed + failed})`);
console.log("==================================================");

if (failed > 0) {
	process.exit(1);
}
