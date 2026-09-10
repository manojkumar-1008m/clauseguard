/**
 * DarkShield Phase B4.2 — Visual Prominence & Contrast Engine Tests
 *
 * Comprehensive test suite validating:
 * 1. 25 Hard-Negative Controls (normal UI, loading, disabled, navigation, dark mode, CSS vars, etc.)
 * 2. 25 Positive Tests (opacity, contrast, typography, area asymmetries, covered actions, etc.)
 * 3. 10 Edge Cases (nested opacity, transparent bg, rgba, animated opacity, gradients, etc.)
 * Total: 60 tests
 */

const assert = require("assert");
const {
	analyzeDomContext,
	makeElementRef,
	calculateContrastRatio,
	computeProminenceMetrics,
	getEffectiveOpacity,
	isAlternativeDecisionPair,
	getDecisionContext
} = require("./extension/analyzer/domAnalyzer.js");

let totalTests = 0;
let passedTests = 0;
let failedTests = 0;

function runTest(name, fn) {
	totalTests++;
	try {
		fn();
		passedTests++;
		console.log(`✓ PASS: ${name}`);
	} catch (err) {
		failedTests++;
		console.error(`✗ FAIL: ${name}`);
		console.error(err);
	}
}

console.log("==================================================");
console.log("RUNNING DARKSHIELD PHASE B4.2 VISUAL PROMINENCE TESTS");
console.log("==================================================");

// =========================================================
// PART 1: 25 HARD-NEGATIVE CONTROLS
// =========================================================

// 1. Loading opacity
runTest("1. Hard Negative: Loading opacity (in-flight state)", () => {
	const events = [{
		action: "CLICK",
		route: "/account/cancel",
		text: "Keep Plan",
		dom_context: {
			visible_text: "Keep Plan",
			geometry: { width: 150, height: 40, area: 6000 },
			opacity: 1.0,
			competing_actions: [
				{ text: "Cancel Plan", width: 140, height: 40, area: 5600, opacity: 0.5, is_animating: true, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const deemphasis = res.dom_signals.find(s => s.type === "action_visual_deemphasis");
	assert.strictEqual(deemphasis, undefined, "Active animation/loading state should not trigger visual deemphasis");
});

// 2. Disabled opacity
runTest("2. Hard Negative: Disabled opacity (standard disabled styling)", () => {
	const events = [{
		action: "CLICK",
		route: "/checkout",
		text: "Pay ₹999",
		dom_context: {
			visible_text: "Pay ₹999",
			geometry: { width: 180, height: 45, area: 8100 },
			opacity: 1.0,
			competing_actions: [
				{ text: "Cancel Order", width: 160, height: 40, area: 6400, opacity: 0.4, disabled: true, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const deemphasis = res.dom_signals.find(s => s.type === "action_visual_deemphasis");
	assert.strictEqual(deemphasis, undefined, "Disabled element opacity should not trigger visual deemphasis");
});

// 3. Continue vs Back
runTest("3. Hard Negative: Continue vs Back (Navigation)", () => {
	const events = [{
		action: "CLICK",
		route: "/signup/step2",
		text: "Continue",
		dom_context: {
			visible_text: "Continue",
			geometry: { width: 250, height: 50, area: 12500 },
			opacity: 1.0,
			font_size_px: 16,
			font_weight: 700,
			competing_actions: [
				{ text: "Back", width: 60, height: 30, area: 1800, opacity: 0.3, font_size_px: 12, font_weight: 400, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const deemphasis = res.dom_signals.find(s => s.type === "action_visual_deemphasis" || s.type === "action_size_asymmetry" || s.type === "typography_asymmetry");
	assert.strictEqual(deemphasis, undefined, "Navigation pairs must never trigger visual asymmetry");
});

// 4. Next vs Previous
runTest("4. Hard Negative: Next vs Previous (Pagination)", () => {
	const events = [{
		action: "CLICK",
		route: "/onboarding/step3",
		text: "Next",
		dom_context: {
			visible_text: "Next",
			geometry: { width: 200, height: 45, area: 9000 },
			opacity: 1.0,
			competing_actions: [
				{ text: "Previous", width: 80, height: 35, area: 2800, opacity: 0.35, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const deemphasis = res.dom_signals.find(s => s.type === "action_visual_deemphasis" || s.type === "action_size_asymmetry");
	assert.strictEqual(deemphasis, undefined, "Next vs Previous is standard pagination");
});

// 5. Save vs Cancel settings
runTest("5. Hard Negative: Save vs Cancel settings", () => {
	const events = [{
		action: "CLICK",
		route: "/settings/profile",
		text: "Save Changes",
		dom_context: {
			visible_text: "Save Changes",
			geometry: { width: 200, height: 45, area: 9000 },
			opacity: 1.0,
			font_weight: 700,
			competing_actions: [
				{ text: "Cancel", width: 70, height: 30, area: 2100, opacity: 0.4, font_weight: 400, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const deemphasis = res.dom_signals.find(s => s.type === "action_visual_deemphasis" || s.type === "action_size_asymmetry");
	assert.strictEqual(deemphasis, undefined, "Save vs Cancel in ordinary settings is standard form design");
});

// 6. Normal ghost button
runTest("6. Hard Negative: Normal ghost button (balanced choices)", () => {
	const events = [{
		action: "CLICK",
		route: "/account/billing",
		text: "Keep Plan",
		dom_context: {
			visible_text: "Keep Plan",
			geometry: { width: 160, height: 40, area: 6400 },
			opacity: 1.0,
			color: "rgb(255, 255, 255)",
			background_color: "rgb(0, 102, 204)",
			competing_actions: [
				{ text: "Cancel Plan", width: 150, height: 40, area: 6000, opacity: 0.95, color: "rgb(0, 102, 204)", background_color: "rgb(255, 255, 255)", visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const deemphasis = res.dom_signals.find(s => s.type === "action_visual_deemphasis" || s.type === "contrast_asymmetry");
	assert.strictEqual(deemphasis, undefined, "Normal ghost button with high contrast is legitimate design");
});

// 7. Normal modal
runTest("7. Hard Negative: Normal modal (dialog with balanced close)", () => {
	const events = [{
		action: "CLICK",
		route: "/account/security",
		text: "Confirm Password",
		dom_context: {
			visible_text: "Confirm Password",
			is_modal: true,
			container_type: "modal",
			has_close_button: true,
			geometry: { width: 180, height: 40, area: 7200 }
		}
	}];
	const res = analyzeDomContext(events);
	const interference = res.dom_signals.find(s => s.type === "modal_interference");
	assert.strictEqual(interference, undefined, "Modal outside cancellation without trapping is benign");
});

// 8. Normal close button
runTest("8. Hard Negative: Normal close button (accessible icon button)", () => {
	const events = [{
		action: "CLICK",
		route: "/account",
		text: "",
		dom_context: {
			aria_label: "Close modal",
			role: "button",
			geometry: { width: 24, height: 24, area: 576 },
			opacity: 0.8
		}
	}];
	const res = analyzeDomContext(events);
	const deemphasis = res.dom_signals.find(s => s.type === "small_secondary_action" || s.type === "action_visual_deemphasis");
	assert.strictEqual(deemphasis, undefined, "Normal accessible close button should not be flagged");
});

// 9. FAQ hidden content
runTest("9. Hard Negative: FAQ hidden content", () => {
	const events = [{
		action: "CLICK",
		route: "/help/faq",
		text: "What is your refund policy?",
		dom_context: {
			visible_text: "What is your refund policy?",
			has_collapsed_alternative: true,
			alternative_in_accordion: true
		}
	}];
	const res = analyzeDomContext(events);
	const mismatch = res.dom_signals.find(s => s.type === "visibility_mismatch");
	assert.strictEqual(mismatch, undefined, "Collapsed FAQ is normal layout");
});

// 10. Accessibility hidden content
runTest("10. Hard Negative: Accessibility hidden content (sr-only)", () => {
	const events = [{
		action: "CLICK",
		route: "/account/cancel",
		text: "Cancel Subscription",
		dom_context: {
			visible_text: "Cancel Subscription",
			competing_actions: [
				{ text: "Screen reader instructions", is_sr_only: true, aria_hidden: true, visible: false }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const hidden = res.dom_signals.find(s => s.type === "hidden_alternative");
	assert.strictEqual(hidden, undefined, "Accessibility hidden elements must be excluded");
});

// 11. Normal country selector
runTest("11. Hard Negative: Normal country selector", () => {
	const events = [{
		action: "PAGE_INIT",
		route: "/checkout",
		dom_context: {
			preselected_options: [{ text: "Country: India", checked: true }]
		}
	}];
	const res = analyzeDomContext(events);
	const pre = res.dom_signals.find(s => s.type === "preselected_option");
	assert.strictEqual(pre, undefined, "Country default is benign");
});

// 12. Normal language selector
runTest("12. Hard Negative: Normal language selector", () => {
	const events = [{
		action: "PAGE_INIT",
		route: "/settings",
		dom_context: {
			preselected_options: [{ text: "Language: English", checked: true }]
		}
	}];
	const res = analyzeDomContext(events);
	const pre = res.dom_signals.find(s => s.type === "preselected_option");
	assert.strictEqual(pre, undefined, "Language default is benign");
});

// 13. Remember-me checkbox
runTest("13. Hard Negative: Remember-me checkbox", () => {
	const events = [{
		action: "CLICK",
		route: "/login",
		dom_context: {
			preselected_options: [{ text: "Remember me on this computer", checked: true }]
		}
	}];
	const res = analyzeDomContext(events);
	const pre = res.dom_signals.find(s => s.type === "preselected_option");
	assert.strictEqual(pre, undefined, "Remember me is benign");
});

// 14. Normal free shipping default
runTest("14. Hard Negative: Normal free shipping default", () => {
	const events = [{
		action: "CLICK",
		route: "/checkout/shipping",
		dom_context: {
			preselected_options: [{ text: "Standard Free Shipping (5-7 days)", checked: true }]
		}
	}];
	const res = analyzeDomContext(events);
	const pre = res.dom_signals.find(s => s.type === "preselected_option");
	assert.strictEqual(pre, undefined, "Free shipping default is benign");
});

// 15. Normal stepper
runTest("15. Hard Negative: Normal stepper (Step 1 of 4)", () => {
	const events = [{
		action: "CLICK",
		route: "/onboarding",
		text: "Next Step",
		dom_context: {
			visible_text: "Next Step",
			geometry: { width: 140, height: 40, area: 5600 },
			competing_actions: [
				{ text: "Previous Step", width: 120, height: 40, area: 4800, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	assert.strictEqual(res.dom_signals.length, 0, "Normal stepper should produce no suspicious signals");
});

// 16. Normal responsive button
runTest("16. Hard Negative: Normal responsive button (stacked mobile buttons)", () => {
	const events = [{
		action: "CLICK",
		route: "/account/cancel",
		text: "Keep Plan",
		dom_context: {
			visible_text: "Keep Plan",
			geometry: { width: 280, height: 48, area: 13440 },
			competing_actions: [
				{ text: "Cancel Plan", width: 280, height: 48, area: 13440, opacity: 1.0, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const asymmetry = res.dom_signals.find(s => s.type === "action_size_asymmetry" || s.type === "action_visual_deemphasis");
	assert.strictEqual(asymmetry, undefined, "Equal stacked responsive buttons are completely balanced");
});

// 17. Dark mode
runTest("17. Hard Negative: Dark mode (light text on dark background)", () => {
	const contrast = calculateContrastRatio("rgb(240, 240, 240)", "rgb(18, 18, 18)");
	assert.ok(contrast > 12.0, "Dark mode should compute high contrast ratio");
});

// 18. Transparent background
runTest("18. Hard Negative: Transparent background (graceful null)", () => {
	const contrast = calculateContrastRatio("rgb(0, 0, 0)", "transparent");
	assert.strictEqual(contrast, null, "Transparent background returns null safely");
});

// 19. CSS variable color
runTest("19. Hard Negative: CSS variable color (graceful null)", () => {
	const contrast = calculateContrastRatio("var(--primary-color)", "var(--bg-color)");
	assert.strictEqual(contrast, null, "CSS variables return null without throwing");
});

// 20. Normal typography hierarchy
runTest("20. Hard Negative: Normal typography hierarchy (modest 16px vs 14px)", () => {
	const events = [{
		action: "CLICK",
		route: "/account/subscription",
		text: "Keep Plan",
		dom_context: {
			visible_text: "Keep Plan",
			font_size_px: 16,
			font_weight: 700,
			geometry: { width: 150, height: 40, area: 6000 },
			competing_actions: [
				{ text: "Cancel Plan", font_size_px: 14, font_weight: 400, width: 140, height: 40, area: 5600, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const typo = res.dom_signals.find(s => s.type === "typography_asymmetry");
	assert.strictEqual(typo, undefined, "Modest typography disparity (16px vs 14px) should not trigger typography asymmetry");
});

// 21. Normal fixed header
runTest("21. Hard Negative: Normal fixed header", () => {
	const events = [{
		action: "CLICK",
		route: "/home",
		text: "Profile",
		dom_context: {
			visible_text: "Profile",
			position: "fixed",
			z_index: 100
		}
	}];
	const res = analyzeDomContext(events);
	assert.strictEqual(res.dom_signals.length, 0, "Fixed header is normal UI");
});

// 22. Normal z-index
runTest("22. Hard Negative: Normal z-index on dropdown", () => {
	const events = [{
		action: "CLICK",
		route: "/dashboard",
		text: "Menu",
		dom_context: {
			visible_text: "Menu",
			z_index: 1000
		}
	}];
	const res = analyzeDomContext(events);
	assert.strictEqual(res.dom_signals.length, 0, "High z-index alone is benign");
});

// 23. Normal cursor:not-allowed
runTest("23. Hard Negative: Normal cursor:not-allowed on disabled submit", () => {
	const events = [{
		action: "CLICK",
		route: "/form",
		text: "Submit",
		dom_context: {
			visible_text: "Submit",
			disabled: true,
			cursor: "not-allowed",
			pointer_events: "none",
			opacity: 0.5
		}
	}];
	const res = analyzeDomContext(events);
	const deemphasis = res.dom_signals.find(s => s.type === "action_visual_deemphasis");
	assert.strictEqual(deemphasis, undefined, "Disabled submit with not-allowed cursor is benign");
});

// 24. Normal pointer-events:none
runTest("24. Hard Negative: Normal pointer-events:none on decorative overlay", () => {
	const events = [{
		action: "CLICK",
		route: "/gallery",
		text: "View Image",
		dom_context: {
			visible_text: "View Image",
			pointer_events: "none"
		}
	}];
	const res = analyzeDomContext(events);
	assert.strictEqual(res.dom_signals.length, 0, "Pointer-events:none outside competing decisions is benign");
});

// 25. Normal animation
runTest("25. Hard Negative: Normal animation (element in transition)", () => {
	const events = [{
		action: "CLICK",
		route: "/account/cancel",
		text: "Keep Subscription",
		dom_context: {
			visible_text: "Keep Subscription",
			opacity: 1.0,
			competing_actions: [
				{ text: "Cancel Subscription", opacity: 0.3, is_animating: true, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const deemphasis = res.dom_signals.find(s => s.type === "action_visual_deemphasis");
	assert.strictEqual(deemphasis, undefined, "Transient active animation must suppress deemphasis evidence");
});

// =========================================================
// PART 2: 25 POSITIVE TESTS
// =========================================================

// 1. Opacity 0.20 cancel vs opacity 1.0 keep
runTest("26. Positive: Opacity 0.20 cancel vs opacity 1.0 keep", () => {
	const events = [{
		action: "CLICK",
		route: "/account/cancel",
		text: "Keep Subscription",
		dom_context: {
			visible_text: "Keep Subscription",
			opacity: 1.0,
			geometry: { width: 200, height: 40, area: 8000 },
			competing_actions: [
				{ text: "Cancel Subscription", opacity: 0.20, width: 200, height: 40, area: 8000, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "action_visual_deemphasis");
	assert.ok(sig, "Should detect action_visual_deemphasis");
	assert.strictEqual(sig.strength, "strong");
	assert.strictEqual(sig.dom_properties.deemphasis_type, "opacity");
	assert.strictEqual(sig.dom_properties.secondary_opacity, 0.2);
});

// 2. Opacity 0.30 cancel
runTest("27. Positive: Opacity 0.30 cancel", () => {
	const events = [{
		action: "CLICK",
		route: "/account/cancel",
		text: "Keep Plan",
		dom_context: {
			visible_text: "Keep Plan",
			opacity: 1.0,
			geometry: { width: 180, height: 40, area: 7200 },
			competing_actions: [
				{ text: "Cancel Plan", opacity: 0.30, width: 180, height: 40, area: 7200, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "action_visual_deemphasis");
	assert.ok(sig, "Should detect action_visual_deemphasis");
	assert.strictEqual(sig.strength, "moderate");
	assert.strictEqual(sig.dom_properties.secondary_opacity, 0.3);
});

// 3. Area ratio 5x cancellation
runTest("28. Positive: Area ratio 5x cancellation", () => {
	const events = [{
		action: "CLICK",
		route: "/account/cancel",
		text: "Keep Plan",
		dom_context: {
			visible_text: "Keep Plan",
			geometry: { width: 250, height: 50, area: 12500 },
			competing_actions: [
				{ text: "Cancel Plan", width: 100, height: 25, area: 2500, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "action_size_asymmetry");
	assert.ok(sig, "Should detect action_size_asymmetry");
	assert.strictEqual(sig.strength, "strong");
	assert.strictEqual(sig.dom_properties.ratio, 5);
});

// 4. Area ratio 3x cancellation
runTest("29. Positive: Area ratio 3x cancellation", () => {
	const events = [{
		action: "CLICK",
		route: "/account/cancel",
		text: "Stay Subscribed",
		dom_context: {
			visible_text: "Stay Subscribed",
			geometry: { width: 180, height: 40, area: 7200 },
			competing_actions: [
				{ text: "Cancel Subscription", width: 120, height: 20, area: 2400, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "action_size_asymmetry");
	assert.ok(sig, "Should detect action_size_asymmetry");
	assert.strictEqual(sig.strength, "moderate");
	assert.strictEqual(sig.dom_properties.ratio, 3);
});

// 5. Tiny rejection action (8px font)
runTest("30. Positive: Tiny rejection action (8px font)", () => {
	const events = [{
		action: "CLICK",
		route: "/account/cancel",
		text: "Keep Subscription",
		dom_context: {
			visible_text: "Keep Subscription",
			font_size_px: 16,
			geometry: { width: 200, height: 40, area: 8000 },
			competing_actions: [
				{ text: "Cancel Subscription", font_size_px: 8, width: 80, height: 15, area: 1200, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "action_visual_deemphasis" || s.type === "small_secondary_action");
	assert.ok(sig, "Should detect tiny secondary action");
	assert.strictEqual(sig.strength, "strong");
});

// 6. Low contrast rejection
runTest("31. Positive: Low contrast rejection", () => {
	const events = [{
		action: "CLICK",
		route: "/account/cancel",
		text: "Keep Plan",
		dom_context: {
			visible_text: "Keep Plan",
			color: "rgb(255, 255, 255)",
			background_color: "rgb(0, 51, 153)", // high contrast ~ 11:1
			geometry: { width: 180, height: 40, area: 7200 },
			competing_actions: [
				{ text: "Cancel Plan", color: "rgb(180, 180, 180)", background_color: "rgb(255, 255, 255)", width: 180, height: 40, area: 7200, visible: true } // low contrast ~ 2.1:1
			]
		}
	}];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "contrast_asymmetry");
	assert.ok(sig, "Should detect contrast_asymmetry");
	assert.strictEqual(sig.strength, "strong");
	assert.ok(sig.dom_properties.secondary_contrast < 2.5);
});

// 7. Typography disparity
runTest("32. Positive: Typography disparity (font size 2x + bold vs light)", () => {
	const events = [{
		action: "CLICK",
		route: "/account/cancel",
		text: "Keep Subscription",
		dom_context: {
			visible_text: "Keep Subscription",
			font_size_px: 20,
			font_weight: 700,
			geometry: { width: 180, height: 40, area: 7200 },
			competing_actions: [
				{ text: "Cancel Subscription", font_size_px: 10, font_weight: 300, width: 180, height: 40, area: 7200, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "typography_asymmetry");
	assert.ok(sig, "Should detect typography_asymmetry");
	assert.strictEqual(sig.strength, "strong");
	assert.strictEqual(sig.dom_properties.font_size_ratio, 2);
});

// 8. Font-size disparity
runTest("33. Positive: Font-size disparity (2.2x ratio)", () => {
	const events = [{
		action: "CLICK",
		route: "/account/subscription",
		text: "Keep Plan",
		dom_context: {
			visible_text: "Keep Plan",
			font_size_px: 22,
			font_weight: 400,
			geometry: { width: 180, height: 40, area: 7200 },
			competing_actions: [
				{ text: "Cancel Plan", font_size_px: 10, font_weight: 400, width: 180, height: 40, area: 7200, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "typography_asymmetry");
	assert.ok(sig, "Should detect typography asymmetry with high font ratio");
	assert.strictEqual(sig.strength, "moderate");
});

// 9. Font-weight disparity (700 vs 400 with 1.6x size)
runTest("34. Positive: Font-weight disparity (700 vs 400 with 1.6x size)", () => {
	const events = [{
		action: "CLICK",
		route: "/account/cancel",
		text: "Keep Subscription",
		dom_context: {
			visible_text: "Keep Subscription",
			font_size_px: 16,
			font_weight: 700,
			geometry: { width: 180, height: 40, area: 7200 },
			competing_actions: [
				{ text: "Cancel Subscription", font_size_px: 10, font_weight: 400, width: 180, height: 40, area: 7200, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "typography_asymmetry");
	assert.ok(sig, "Should detect typography asymmetry with weight difference");
	assert.strictEqual(sig.dom_properties.font_weight_difference, 300);
});

// 10. Combined opacity + contrast
runTest("35. Positive: Combined opacity + contrast", () => {
	const events = [{
		action: "CLICK",
		route: "/account/cancel",
		text: "Keep Plan",
		dom_context: {
			visible_text: "Keep Plan",
			opacity: 1.0,
			contrast_ratio: 8.5,
			geometry: { width: 180, height: 40, area: 7200 },
			competing_actions: [
				{ text: "Cancel Plan", opacity: 0.25, contrast_ratio: 2.1, width: 180, height: 40, area: 7200, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const deemphasis = res.dom_signals.find(s => s.type === "action_visual_deemphasis");
	const contrast = res.dom_signals.find(s => s.type === "contrast_asymmetry");
	assert.ok(deemphasis, "Should detect visual deemphasis");
	assert.ok(contrast, "Should detect contrast asymmetry");
});

// 11. Combined area + typography
runTest("36. Positive: Combined area + typography", () => {
	const events = [{
		action: "CLICK",
		route: "/account/cancel",
		text: "Stay with Discount",
		dom_context: {
			visible_text: "Stay with Discount",
			font_size_px: 18,
			font_weight: 700,
			geometry: { width: 250, height: 50, area: 12500 },
			competing_actions: [
				{ text: "Cancel Plan", font_size_px: 9, font_weight: 400, width: 80, height: 25, area: 2000, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const sizeSig = res.dom_signals.find(s => s.type === "action_size_asymmetry");
	const typoSig = res.dom_signals.find(s => s.type === "typography_asymmetry");
	assert.ok(sizeSig, "Should detect area asymmetry");
	assert.ok(typoSig, "Should detect typography asymmetry");
});

// 12. Combined area + opacity
runTest("37. Positive: Combined area + opacity", () => {
	const events = [{
		action: "CLICK",
		route: "/account/cancel",
		text: "Keep Subscription",
		dom_context: {
			visible_text: "Keep Subscription",
			opacity: 1.0,
			geometry: { width: 240, height: 48, area: 11520 },
			competing_actions: [
				{ text: "Cancel Subscription", opacity: 0.20, width: 80, height: 24, area: 1920, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const sizeSig = res.dom_signals.find(s => s.type === "action_size_asymmetry");
	const deemphasis = res.dom_signals.find(s => s.type === "action_visual_deemphasis");
	assert.ok(sizeSig, "Should detect size asymmetry");
	assert.ok(deemphasis, "Should detect opacity deemphasis");
});

// 13. Disabled cancel + active retention
runTest("38. Positive: Disabled cancel + active retention", () => {
	const events = [{
		action: "CLICK",
		route: "/account/cancel",
		text: "Keep My Subscription",
		dom_context: {
			visible_text: "Keep My Subscription",
			disabled: false,
			competing_actions: [
				{ text: "Cancel Subscription", disabled: true, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "disabled_action" || s.type === "action_state_mismatch");
	assert.ok(sig, "Should detect disabled cancel alongside enabled retention");
	assert.strictEqual(sig.strength, "strong");
});

// 14. Hidden alternative
runTest("39. Positive: Hidden alternative in cancellation", () => {
	const events = [{
		action: "CLICK",
		route: "/account/cancel",
		text: "Keep Plan",
		dom_context: {
			visible_text: "Keep Plan",
			competing_actions: [
				{ text: "Cancel Plan", visible: false, display: "none" }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "hidden_alternative");
	assert.ok(sig, "Should detect hidden alternative");
	assert.strictEqual(sig.strength, "strong");
});

// 15. Commercial preselection
runTest("40. Positive: Commercial preselection (paid warranty)", () => {
	const events = [{
		action: "CLICK",
		route: "/checkout",
		dom_context: {
			preselected_options: [{ text: "Add 2-year warranty ₹499", checked: true }]
		}
	}];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "preselected_option");
	assert.ok(sig, "Should detect preselected commercial add-on");
	assert.strictEqual(sig.dom_properties.commercial_reason, "paid_warranty");
});

// 16. Visual de-emphasis in subscription
runTest("41. Positive: Visual de-emphasis in subscription", () => {
	const events = [{
		action: "CLICK",
		route: "/subscribe",
		text: "Start Trial",
		dom_context: {
			visible_text: "Start Trial",
			opacity: 1.0,
			geometry: { width: 200, height: 45, area: 9000 },
			competing_actions: [
				{ text: "Continue without trial", opacity: 0.20, width: 200, height: 45, area: 9000, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "action_visual_deemphasis");
	assert.ok(sig, "Should detect visual de-emphasis in subscription flow");
	assert.strictEqual(sig.strength, "strong");
});

// 17. Visual de-emphasis in billing
runTest("42. Positive: Visual de-emphasis in billing", () => {
	const events = [{
		action: "CLICK",
		route: "/billing/plan",
		text: "Renew Plan",
		dom_context: {
			visible_text: "Renew Plan",
			opacity: 1.0,
			geometry: { width: 180, height: 40, area: 7200 },
			competing_actions: [
				{ text: "Stop Subscription", opacity: 0.25, width: 180, height: 40, area: 7200, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "action_visual_deemphasis");
	assert.ok(sig, "Should detect visual de-emphasis in billing context");
});

// 18. Visual de-emphasis in consent
runTest("43. Positive: Visual de-emphasis in consent (Accept All vs Reject)", () => {
	const events = [{
		action: "CLICK",
		route: "/privacy/consent",
		text: "Accept All",
		dom_context: {
			visible_text: "Accept All",
			container_type: "dialog",
			opacity: 1.0,
			geometry: { width: 180, height: 40, area: 7200 },
			competing_actions: [
				{ text: "Reject", opacity: 0.20, width: 180, height: 40, area: 7200, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "action_visual_deemphasis");
	assert.ok(sig, "Should detect visual de-emphasis in consent banner");
	assert.strictEqual(sig.strength, "strong");
});

// 19. Visually asymmetric checkout choices
runTest("44. Positive: Visually asymmetric checkout choices (Add Protection vs Skip)", () => {
	const events = [{
		action: "CLICK",
		route: "/checkout/review",
		text: "Add Protection",
		dom_context: {
			visible_text: "Add Protection",
			geometry: { width: 220, height: 45, area: 9900 },
			opacity: 1.0,
			competing_actions: [
				{ text: "Skip", width: 60, height: 25, area: 1500, opacity: 0.30, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const size = res.dom_signals.find(s => s.type === "action_size_asymmetry");
	const deemphasis = res.dom_signals.find(s => s.type === "action_visual_deemphasis");
	assert.ok(size, "Should detect area asymmetry on protection");
	assert.ok(deemphasis, "Should detect visual deemphasis on skip");
});

// 20. Covered action
runTest("45. Positive: Covered action in cancellation", () => {
	const events = [{
		action: "CLICK",
		route: "/account/cancel",
		text: "Keep Plan",
		dom_context: {
			visible_text: "Keep Plan",
			geometry: { width: 180, height: 40, area: 7200 },
			competing_actions: [
				{ text: "Cancel Plan", is_covered: true, width: 180, height: 40, area: 7200, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "covered_action");
	assert.ok(sig, "Should detect covered action");
	assert.strictEqual(sig.strength, "strong");
});

// 21. Fixed retention action bar
runTest("46. Positive: Fixed retention action bar", () => {
	const events = [{
		action: "CLICK",
		route: "/account/cancel",
		text: "Keep Subscription",
		dom_context: {
			visible_text: "Keep Subscription",
			position: "fixed",
			z_index: 9999,
			geometry: { width: 300, height: 50, area: 15000 },
			competing_actions: [
				{ text: "Cancel Subscription", width: 90, height: 25, area: 2250, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "action_size_asymmetry");
	assert.ok(sig, "Should detect asymmetry in fixed action bar");
	assert.strictEqual(sig.dom_properties.ratio, 6.67);
});

// 22. Semantically related cross-position actions
runTest("47. Positive: Semantically related cross-position actions (Allow vs Don't Allow)", () => {
	const events = [{
		action: "CLICK",
		route: "/consent",
		text: "Allow",
		dom_context: {
			visible_text: "Allow",
			opacity: 1.0,
			geometry: { width: 160, height: 40, area: 6400 },
			competing_actions: [
				{ text: "Don't Allow", opacity: 0.20, width: 160, height: 40, area: 6400, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "action_visual_deemphasis");
	assert.ok(sig, "Should detect deemphasis for Allow vs Don't Allow");
});

// 23. Low-opacity cancellation link
runTest("48. Positive: Low-opacity cancellation link", () => {
	const events = [{
		action: "CLICK",
		route: "/account/cancel",
		text: "Keep Plan",
		dom_context: {
			visible_text: "Keep Plan",
			opacity: 1.0,
			geometry: { width: 200, height: 45, area: 9000 },
			competing_actions: [
				{ text: "Proceed with cancel", opacity: 0.15, width: 150, height: 30, area: 4500, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "action_visual_deemphasis");
	assert.ok(sig, "Should detect low-opacity cancel link");
	assert.strictEqual(sig.strength, "strong");
});

// 24. Weak rejection button (low opacity + low contrast)
runTest("49. Positive: Weak rejection button (low opacity + low contrast)", () => {
	const events = [{
		action: "CLICK",
		route: "/account/cancel",
		text: "Stay Subscribed",
		dom_context: {
			visible_text: "Stay Subscribed",
			opacity: 1.0,
			contrast_ratio: 7.0,
			geometry: { width: 180, height: 40, area: 7200 },
			competing_actions: [
				{ text: "Cancel Subscription", opacity: 0.25, contrast_ratio: 1.8, width: 180, height: 40, area: 7200, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const deemphasis = res.dom_signals.find(s => s.type === "action_visual_deemphasis");
	const contrast = res.dom_signals.find(s => s.type === "contrast_asymmetry");
	assert.ok(deemphasis, "Should detect deemphasis");
	assert.ok(contrast, "Should detect contrast asymmetry");
});

// 25. Strong visual asymmetry with complete evidence
runTest("50. Positive: Strong visual asymmetry with complete evidence", () => {
	const events = [{
		action: "CLICK",
		route: "/account/cancel",
		text: "Keep Subscription",
		dom_context: {
			visible_text: "Keep Subscription",
			opacity: 1.0,
			font_size_px: 18,
			font_weight: 700,
			contrast_ratio: 9.0,
			geometry: { width: 250, height: 50, area: 12500 },
			competing_actions: [
				{ text: "Cancel Subscription", opacity: 0.20, font_size_px: 9, font_weight: 300, contrast_ratio: 2.0, width: 50, height: 20, area: 1000, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	assert.ok(res.dom_signals.length >= 3, "Should detect multiple compound asymmetries");
	const sizeSig = res.dom_signals.find(s => s.type === "action_size_asymmetry");
	const deemphasis = res.dom_signals.find(s => s.type === "action_visual_deemphasis");
	const contrastSig = res.dom_signals.find(s => s.type === "contrast_asymmetry");
	const typoSig = res.dom_signals.find(s => s.type === "typography_asymmetry");
	assert.ok(sizeSig && deemphasis && contrastSig && typoSig, "All 4 visual asymmetry signals should be emitted");
	assert.ok(sizeSig.dom_properties.metrics, "Metrics should be included in dom_properties");
	assert.strictEqual(sizeSig.dom_properties.metrics.area_ratio, 12.5);
});

// =========================================================
// PART 3: 10 EDGE CASES
// =========================================================

// 1. Opacity inherited through parent
runTest("51. Edge Case: Opacity bounded ancestor walk (effective opacity)", () => {
	const eff = getEffectiveOpacity({ opacity: 0.5, parent_opacities: [0.5, 0.8] });
	assert.strictEqual(eff, 0.2);
});

// 2. Nested opacity bounded to 3 levels
runTest("52. Edge Case: Nested opacity bounded to max 3 levels", () => {
	const eff = getEffectiveOpacity({ opacity: 1.0, parent_opacities: [0.5, 0.5, 0.5, 0.1, 0.1] });
	assert.strictEqual(eff, 0.13, "Should bound to first 3 parent levels (1.0 * 0.5 * 0.5 * 0.5 = 0.125 -> 0.13)");
});

// 3. Animated opacity
runTest("53. Edge Case: Animated opacity suppressed from strong deemphasis", () => {
	const events = [{
		action: "CLICK",
		route: "/account/cancel",
		text: "Keep Plan",
		dom_context: {
			visible_text: "Keep Plan",
			opacity: 1.0,
			competing_actions: [
				{ text: "Cancel Plan", opacity: 0.1, is_animating: true, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "action_visual_deemphasis");
	assert.strictEqual(sig, undefined, "Active animation should suppress deemphasis");
});

// 4. Transparent colors
runTest("54. Edge Case: Transparent colors return null safely", () => {
	const contrast = calculateContrastRatio("rgba(255, 255, 255, 0)", "rgb(0, 0, 0)");
	assert.strictEqual(contrast, null, "Transparent foreground returns null");
});

// 5. RGBA alpha blending
runTest("55. Edge Case: RGBA with high alpha computes valid contrast", () => {
	const contrast = calculateContrastRatio("rgba(0, 0, 0, 0.9)", "rgb(255, 255, 255)");
	assert.ok(contrast > 15.0, "Near-opaque black on white should yield high contrast");
});

// 6. CSS variable color string handling
runTest("56. Edge Case: CSS variable color does not crash", () => {
	const contrast = calculateContrastRatio("var(--text-color)", "#ffffff");
	assert.strictEqual(contrast, null, "CSS variable string returns null gracefully");
});

// 7. Gradient background handling
runTest("57. Edge Case: Gradient background returns null safely", () => {
	const contrast = calculateContrastRatio("#000000", "linear-gradient(to right, red, yellow)");
	assert.strictEqual(contrast, null, "Gradient background returns null gracefully");
});

// 8. Missing background color
runTest("58. Edge Case: Missing background color returns null safely", () => {
	const contrast = calculateContrastRatio("#ffffff", null);
	assert.strictEqual(contrast, null, "Missing background returns null safely");
});

// 9. SVG/icon action without text
runTest("59. Edge Case: Icon button with aria-label correctly recognized", () => {
	const events = [{
		action: "CLICK",
		route: "/account/cancel",
		text: "Keep Subscription",
		dom_context: {
			visible_text: "Keep Subscription",
			opacity: 1.0,
			geometry: { width: 200, height: 40, area: 8000 },
			competing_actions: [
				{ tag: "BUTTON", aria_label: "cancel subscription", text: "cancel subscription", opacity: 0.20, width: 200, height: 40, area: 8000, visible: true }
			]
		}
	}];
	const res = analyzeDomContext(events);
	const sig = res.dom_signals.find(s => s.type === "action_visual_deemphasis");
	assert.ok(sig, "Icon button with aria-label should be analyzed as competing alternative");
});

// 10. Rerendered action deduplication preserves evidence
runTest("60. Edge Case: Rerendered action deduplication aggregates event indices", () => {
	const events = [
		{
			action: "CLICK",
			route: "/account/cancel",
			text: "Keep Plan",
			dom_context: {
				visible_text: "Keep Plan",
				opacity: 1.0,
				geometry: { width: 200, height: 40, area: 8000 },
				competing_actions: [
					{ text: "Cancel Plan", opacity: 0.20, width: 200, height: 40, area: 8000, visible: true }
				]
			}
		},
		{
			action: "CLICK",
			route: "/account/cancel",
			text: "Keep Plan",
			dom_context: {
				visible_text: "Keep Plan",
				opacity: 1.0,
				geometry: { width: 200, height: 40, area: 8000 },
				competing_actions: [
					{ text: "Cancel Plan", opacity: 0.20, width: 200, height: 40, area: 8000, visible: true }
				]
			}
		}
	];
	const res = analyzeDomContext(events);
	const sigs = res.dom_signals.filter(s => s.type === "action_visual_deemphasis");
	assert.strictEqual(sigs.length, 1, "Should deduplicate repeated signal");
	assert.deepStrictEqual(sigs[0].event_indices, [0, 1], "Should merge event_indices from both events");
});

console.log("\n==================================================");
console.log(`TEST RESULTS: ${passedTests} PASSED, ${failedTests} FAILED (TOTAL: ${totalTests})`);
console.log("==================================================");

if (failedTests > 0) {
	process.exit(1);
}
