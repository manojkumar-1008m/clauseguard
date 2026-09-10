/**
 * DarkShield Phase B4.3 — Dynamic DOM Diff & Post-Action Change Detection Test Suite
 *
 * Comprehensive tests covering:
 * - 20 Hard Negatives (loading spinners, animations, timestamps, ads, analytics, normal rerenders, etc.)
 * - 20 Positive Scenarios (fee injections, preselection, hidden/disabled alternatives, price shifts, etc.)
 * - 10 Edge Cases (re-rendering identity, currency variations, multiple changes, noise mixtures, etc.)
 *
 * Verifies that the DOM diff engine acts purely as an evidence producer, without declaring dark patterns or risk scores.
 */

const { diffSnapshots, createSnapshot, parsePrice } = require("./extension/analyzer/domDiff.js");
const { analyzeDomContext } = require("./extension/analyzer/domAnalyzer.js");

let totalTests = 0;
let passedTests = 0;
let failedTests = 0;

function assert(condition, message) {
	totalTests++;
	if (condition) {
		passedTests++;
		console.log(`✓ PASS: ${message}`);
	} else {
		failedTests++;
		console.error(`✗ FAIL: ${message}`);
	}
}

console.log("==================================================");
console.log("RUNNING DARKSHIELD PHASE B4.3 DYNAMIC DOM DIFF TESTS");
console.log("==================================================\n");

// =========================================================
// 1. HARD NEGATIVES (20 Tests)
// =========================================================
console.log("--- 1. HARD NEGATIVES ---");

// 1. Loading spinner
{
	const before = createSnapshot([
		{ element_ref: "BTN_1", tag: "BUTTON", visible_text: "Submit", is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "BTN_1", tag: "BUTTON", visible_text: "Submit", is_visible: true },
		{ element_ref: "SPINNER_1", tag: "DIV", class_name: "spinner loading-icon", visible_text: "Loading...", role: "progressbar" }
	]);
	const res = diffSnapshots(before, after, { route: "/form" });
	assert(res.diff_signals.length === 0, "1. Hard Negative: Loading spinner filtered out");
}

// 2. Animation
{
	const before = createSnapshot([
		{ element_ref: "BOX_1", tag: "DIV", visible_text: "Card Content", is_visible: true, is_animating: false }
	]);
	const after = createSnapshot([
		{ element_ref: "BOX_1", tag: "DIV", visible_text: "Card Content", is_visible: true, is_animating: true }
	]);
	const res = diffSnapshots(before, after, { route: "/home" });
	assert(res.diff_signals.length === 0, "2. Hard Negative: Animation transition filtered out");
}

// 3. Timestamp change
{
	const before = createSnapshot([
		{ element_ref: "TIME_1", tag: "SPAN", visible_text: "Updated 5 seconds ago", is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "TIME_1", tag: "SPAN", visible_text: "Updated 6 seconds ago", is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/feed" });
	assert(res.diff_signals.length === 0, "3. Hard Negative: Timestamp change ignored as noise");
}

// 4. Rotating advertisement
{
	const before = createSnapshot([
		{ element_ref: "AD_1", tag: "DIV", class_name: "ad-slot advertisement", visible_text: "Sponsored deal A", role: "region" }
	]);
	const after = createSnapshot([
		{ element_ref: "AD_1", tag: "DIV", class_name: "ad-slot advertisement", visible_text: "Sponsored deal B", role: "region" }
	]);
	const res = diffSnapshots(before, after, { route: "/news" });
	assert(res.diff_signals.length === 0, "4. Hard Negative: Rotating advertisement filtered out");
}

// 5. Analytics DOM change
{
	const before = createSnapshot([
		{ element_ref: "MAIN_1", tag: "MAIN", visible_text: "Welcome", is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "MAIN_1", tag: "MAIN", visible_text: "Welcome", is_visible: true },
		{ element_ref: "ANALYTICS_1", tag: "DIV", class_name: "analytics-beacon tracker", visible_text: "pixel tracker" }
	]);
	const res = diffSnapshots(before, after, { route: "/home" });
	assert(res.diff_signals.length === 0, "5. Hard Negative: Analytics beacon insertion filtered out");
}

// 6. Normal SPA rerender (new element_refs, identical semantic content)
{
	const before = createSnapshot([
		{ element_ref: "BTN_OLD_1", tag: "BUTTON", role: "button", visible_text: "Checkout Now", is_visible: true, is_disabled: false },
		{ element_ref: "SPAN_OLD_2", tag: "SPAN", visible_text: "$49.99", is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "BTN_NEW_9", tag: "BUTTON", role: "button", visible_text: "Checkout Now", is_visible: true, is_disabled: false },
		{ element_ref: "SPAN_NEW_8", tag: "SPAN", visible_text: "$49.99", is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/cart" });
	assert(res.diff_signals.length === 0, "6. Hard Negative: Normal SPA rerender produces 0 diff signals");
}

// 7. FAQ expansion (accordion answer appears)
{
	const before = createSnapshot([
		{ element_ref: "FAQ_HDR", tag: "BUTTON", visible_text: "What is your return policy?", is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "FAQ_HDR", tag: "BUTTON", visible_text: "What is your return policy?", is_visible: true },
		{ element_ref: "FAQ_BODY", tag: "DIV", visible_text: "You can return items within 30 days for a full refund.", is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/faq" });
	assert(res.diff_signals.length === 0, "7. Hard Negative: Normal FAQ expansion does not trigger diff signals");
}

// 8. Normal modal (standard informational modal)
{
	const before = createSnapshot([
		{ element_ref: "BTN_HELP", tag: "BUTTON", visible_text: "Help Guide", is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "BTN_HELP", tag: "BUTTON", visible_text: "Help Guide", is_visible: true },
		{ element_ref: "MODAL_HELP", tag: "DIALOG", is_modal: true, visible_text: "User Guide: How to search products", is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/help" });
	const hasDeceptiveSignal = res.diff_signals.some(s => s.type === "post_action_fee_added" || s.type === "post_action_preselection" || s.type === "post_action_alternative_removed");
	assert(!hasDeceptiveSignal && res.diff_signals.length <= 1, "8. Hard Negative: Normal info modal produces no commercial or deceptive signals");
}

// 9. Normal confirmation dialog (standard logout confirmation, not cancellation trick)
{
	const before = createSnapshot([
		{ element_ref: "BTN_LOGOUT", tag: "BUTTON", visible_text: "Sign Out", is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "BTN_LOGOUT", tag: "BUTTON", visible_text: "Sign Out", is_visible: true },
		{ element_ref: "CONFIRM_LOGOUT", tag: "DIALOG", is_modal: true, visible_text: "Are you sure you want to sign out of your account?", is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/settings" });
	const hasAlternativeRemoved = res.diff_signals.some(s => s.type === "post_action_alternative_removed");
	assert(!hasAlternativeRemoved, "9. Hard Negative: Normal signout confirmation does not flag alternative removed");
}

// 10. Normal checkbox interaction (user clicks benign preference checkbox)
{
	const before = createSnapshot([
		{ element_ref: "CHK_NEWS", tag: "INPUT", type: "checkbox", visible_text: "Subscribe to quarterly newsletter", checked_state: false, is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "CHK_NEWS", tag: "INPUT", type: "checkbox", visible_text: "Subscribe to quarterly newsletter", checked_state: true, is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/profile" });
	assert(res.diff_signals.length === 0, "10. Hard Negative: Normal benign preference checkbox interaction produces no signal");
}

// 11. Remember-me checkbox
{
	const before = createSnapshot([
		{ element_ref: "CHK_REM", tag: "INPUT", type: "checkbox", visible_text: "Remember me on this computer", checked_state: false, is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "CHK_REM", tag: "INPUT", type: "checkbox", visible_text: "Remember me on this computer", checked_state: true, is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/login" });
	assert(res.diff_signals.length === 0, "11. Hard Negative: Remember-me checkbox toggling produces 0 signals");
}

// 12. Country selector
{
	const before = createSnapshot([
		{ element_ref: "SEL_CTRY", tag: "SELECT", visible_text: "Country: United States", is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "SEL_CTRY", tag: "SELECT", visible_text: "Country: Canada", is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/shipping" });
	assert(res.diff_signals.length === 0, "12. Hard Negative: Country selector change produces 0 signals");
}

// 13. Language selector
{
	const before = createSnapshot([
		{ element_ref: "SEL_LANG", tag: "SELECT", visible_text: "Language: English", is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "SEL_LANG", tag: "SELECT", visible_text: "Language: Spanish", is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/settings" });
	assert(res.diff_signals.length === 0, "13. Hard Negative: Language selector change produces 0 signals");
}

// 14. Normal disabled submit after validation (e.g. searching/submitting in-flight)
{
	const before = createSnapshot([
		{ element_ref: "BTN_SUBMIT", tag: "BUTTON", role: "button", visible_text: "Search Flights", is_disabled: false, is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "BTN_SUBMIT", tag: "BUTTON", role: "button", visible_text: "Search Flights", is_disabled: true, is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/search" });
	assert(res.diff_signals.length === 0, "14. Hard Negative: Normal submit button disabling during search produces 0 signals");
}

// 15. Responsive layout (resizing width and height)
{
	const before = createSnapshot([
		{ element_ref: "BTN_SHOP", tag: "BUTTON", visible_text: "Continue Shopping", geometry: { width: 200, height: 40 }, is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "BTN_SHOP", tag: "BUTTON", visible_text: "Continue Shopping", geometry: { width: 300, height: 48 }, is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/shop" });
	assert(res.diff_signals.length === 0, "15. Hard Negative: Responsive button resize produces 0 signals");
}

// 16. Skeleton loader
{
	const before = createSnapshot([
		{ element_ref: "SKEL_1", tag: "DIV", class_name: "skeleton-card shimmer", visible_text: "", is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "PROD_1", tag: "DIV", visible_text: "Blue Cotton T-Shirt", is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/products" });
	assert(res.diff_signals.length === 0, "16. Hard Negative: Skeleton loader disappearance produces 0 signals");
}

// 17. Normal price formatting change ($499 -> $499.00)
{
	const before = createSnapshot([
		{ element_ref: "PRICE_1", tag: "SPAN", visible_text: "$499", is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "PRICE_1", tag: "SPAN", visible_text: "$499.00", is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/cart" });
	assert(res.diff_signals.length === 0, "17. Hard Negative: Formatting change with identical numerical amount emits no price signal");
}

// 18. Unrelated text update (footer copyright year)
{
	const before = createSnapshot([
		{ element_ref: "FOOTER_1", tag: "P", visible_text: "© 2025 Global Services Inc. All rights reserved.", is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "FOOTER_1", tag: "P", visible_text: "© 2026 Global Services Inc. All rights reserved.", is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/home" });
	assert(res.diff_signals.length === 0, "18. Hard Negative: Unrelated footer text update produces 0 signals");
}

// 19. Normal step navigation (Step 1 of 3 -> Step 2 of 3)
{
	const before = createSnapshot([
		{ element_ref: "STEP_1", tag: "DIV", visible_text: "Step 1 of 3: Shipping Details", is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "STEP_1", tag: "DIV", visible_text: "Step 2 of 3: Payment Method", is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/checkout" });
	assert(res.diff_signals.length === 0, "19. Hard Negative: Normal step navigation produces 0 signals");
}

// 20. Decorative DOM insertion (SVG icon or divider)
{
	const before = createSnapshot([
		{ element_ref: "CONT_1", tag: "DIV", visible_text: "Checkout Items", is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "CONT_1", tag: "DIV", visible_text: "Checkout Items", is_visible: true },
		{ element_ref: "DIV_DECOR", tag: "DIV", class_name: "divider separator", visible_text: "" }
	]);
	const res = diffSnapshots(before, after, { route: "/checkout" });
	assert(res.diff_signals.length === 0, "20. Hard Negative: Decorative divider insertion produces 0 signals");
}

// =========================================================
// 2. POSITIVE SCENARIOS (20 Tests)
// =========================================================
console.log("\n--- 2. POSITIVE SCENARIOS ---");

// 1. Fee appears after Continue
{
	const before = createSnapshot([
		{ element_ref: "BTN_CONT", tag: "BUTTON", visible_text: "Continue to Payment", is_visible: true },
		{ element_ref: "PRICE_1", tag: "SPAN", visible_text: "₹499", is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "BTN_CONT", tag: "BUTTON", visible_text: "Continue to Payment", is_visible: true },
		{ element_ref: "PRICE_1", tag: "SPAN", visible_text: "₹499", is_visible: true },
		{ element_ref: "FEE_1", tag: "SPAN", visible_text: "₹79 processing fee", is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/checkout" });
	const sig = res.diff_signals.find(s => s.type === "post_action_fee_added");
	assert(Boolean(sig) && sig.dom_properties.after.amount === 79, "1. Positive: Fee appears after Continue");
}

// 2. Processing fee appears
{
	const before = createSnapshot([
		{ element_ref: "TOTAL", tag: "SPAN", visible_text: "Total: $100.00", is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "TOTAL", tag: "SPAN", visible_text: "Total: $100.00", is_visible: true },
		{ element_ref: "PROC_FEE", tag: "DIV", visible_text: "+ $4.99 Processing Fee", is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/cart" });
	const sig = res.diff_signals.find(s => s.type === "post_action_fee_added");
	assert(Boolean(sig) && sig.dom_properties.after.amount === 4.99, "2. Positive: Processing fee appears");
}

// 3. Service fee appears
{
	const before = createSnapshot([
		{ element_ref: "ITEM", tag: "SPAN", visible_text: "Concert Ticket $120", is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "ITEM", tag: "SPAN", visible_text: "Concert Ticket $120", is_visible: true },
		{ element_ref: "SERV_FEE", tag: "SPAN", visible_text: "$15 Service Fee", is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/tickets" });
	const sig = res.diff_signals.find(s => s.type === "post_action_fee_added");
	assert(Boolean(sig) && sig.dom_properties.after.amount === 15, "3. Positive: Service fee appears");
}

// 4. Protection checkbox auto-selected
{
	const before = createSnapshot([
		{ element_ref: "CHK_PROT", tag: "INPUT", type: "checkbox", visible_text: "Travel Protection Plan", checked_state: false, is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "CHK_PROT", tag: "INPUT", type: "checkbox", visible_text: "Travel Protection Plan", checked_state: true, is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/booking" });
	const sig = res.diff_signals.find(s => s.type === "post_action_preselection");
	assert(Boolean(sig) && sig.dom_properties.after.commercial_reason === "paid_protection", "4. Positive: Protection checkbox auto-selected");
}

// 5. Warranty auto-selected
{
	const before = createSnapshot([
		{ element_ref: "CHK_WARR", tag: "INPUT", type: "checkbox", visible_text: "2-Year Extended Warranty", checked_state: false, is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "CHK_WARR", tag: "INPUT", type: "checkbox", visible_text: "2-Year Extended Warranty", checked_state: true, is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/cart" });
	const sig = res.diff_signals.find(s => s.type === "post_action_preselection");
	assert(Boolean(sig) && sig.dom_properties.after.commercial_reason === "paid_warranty", "5. Positive: Warranty auto-selected");
}

// 6. Insurance auto-selected
{
	const before = createSnapshot([
		{ element_ref: "CHK_INS", tag: "INPUT", type: "checkbox", visible_text: "Device Insurance Plan", checked_state: false, is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "CHK_INS", tag: "INPUT", type: "checkbox", visible_text: "Device Insurance Plan", checked_state: true, is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/electronics" });
	const sig = res.diff_signals.find(s => s.type === "post_action_preselection");
	assert(Boolean(sig) && sig.dom_properties.after.commercial_reason === "insurance", "6. Positive: Insurance auto-selected");
}

// 7. Cancellation button becomes disabled
{
	const before = createSnapshot([
		{ element_ref: "BTN_CANCEL", tag: "BUTTON", role: "button", visible_text: "Cancel Subscription", is_disabled: false, is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "BTN_CANCEL", tag: "BUTTON", role: "button", visible_text: "Cancel Subscription", is_disabled: true, is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/account/cancel" });
	const sig = res.diff_signals.find(s => s.type === "post_action_action_disabled");
	assert(Boolean(sig) && sig.dom_properties.after.disabled === true, "7. Positive: Cancellation button becomes disabled");
}

// 8. Rejection option disappears
{
	const before = createSnapshot([
		{ element_ref: "BTN_REJECT", tag: "BUTTON", visible_text: "No thanks, I don't want this offer", is_visible: true }
	]);
	const after = createSnapshot([]);
	const res = diffSnapshots(before, after, { route: "/upgrade" });
	const sig = res.diff_signals.find(s => s.type === "post_action_alternative_removed");
	assert(Boolean(sig), "8. Positive: Rejection option disappears from DOM");
}

// 9. Cancel becomes hidden
{
	const before = createSnapshot([
		{ element_ref: "BTN_CANCEL", tag: "BUTTON", visible_text: "Cancel Account", is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "BTN_CANCEL", tag: "BUTTON", visible_text: "Cancel Account", is_visible: false }
	]);
	const res = diffSnapshots(before, after, { route: "/membership" });
	const sig = res.diff_signals.find(s => s.type === "post_action_alternative_removed");
	assert(Boolean(sig) && sig.dom_properties.after.is_visible === false, "9. Positive: Cancel becomes hidden");
}

// 10. Retention modal appears
{
	const before = createSnapshot([]);
	const after = createSnapshot([
		{ element_ref: "MODAL_RET", tag: "DIALOG", is_modal: true, visible_text: "Wait! Stay and save 50% on your membership", is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/cancel" });
	const sig = res.diff_signals.find(s => s.type === "post_action_modal_appeared");
	assert(Boolean(sig) && sig.strength === "strong", "10. Positive: Retention modal appears with strong strength");
}

// 11. New retention offer appears
{
	const before = createSnapshot([]);
	const after = createSnapshot([
		{ element_ref: "OFFER_BOX", tag: "DIV", visible_text: "Claim your 50% discount today before you go", is_modal: true, is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/cancel" });
	const sig = res.diff_signals.find(s => s.type === "post_action_modal_appeared");
	assert(Boolean(sig), "11. Positive: New retention offer box appearance detected");
}

// 12. Price increases after interaction
{
	const before = createSnapshot([
		{ element_ref: "PRICE_VAL", tag: "SPAN", role: "price", visible_text: "$49.00", is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "PRICE_VAL", tag: "SPAN", role: "price", visible_text: "$69.00", is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/checkout" });
	const sig = res.diff_signals.find(s => s.type === "post_action_price_changed");
	assert(Boolean(sig) && sig.dom_properties.after.amount === 69 && sig.dom_properties.after.price_increased === true, "12. Positive: Price increases after interaction");
}

// 13. Total changes after interaction
{
	const before = createSnapshot([
		{ element_ref: "TOTAL_VAL", tag: "SPAN", visible_text: "Total: ₹1,200", is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "TOTAL_VAL", tag: "SPAN", visible_text: "Total: ₹1,450", is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/checkout" });
	const sig = res.diff_signals.find(s => s.type === "post_action_price_changed");
	assert(Boolean(sig) && sig.dom_properties.after.amount === 1450, "13. Positive: Total changes after interaction");
}

// 14. Mandatory acknowledgement appears
{
	const before = createSnapshot([]);
	const after = createSnapshot([
		{ element_ref: "CHK_ACK", tag: "INPUT", type: "checkbox", visible_text: "Acknowledge that early termination forfeits all perks", is_required: true, is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/cancel" });
	const sig = res.diff_signals.find(s => s.type === "post_action_required_step");
	assert(Boolean(sig) && sig.dom_properties.after.is_required === true, "14. Positive: Mandatory acknowledgement appears");
}

// 15. New required survey appears
{
	const before = createSnapshot([]);
	const after = createSnapshot([
		{ element_ref: "SEL_SURVEY", tag: "SELECT", visible_text: "Why are you leaving? Required survey before cancel", is_required: true, is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/cancel" });
	const sig = res.diff_signals.find(s => s.type === "post_action_required_step");
	assert(Boolean(sig), "15. Positive: New required survey appears in cancellation flow");
}

// 16. Skip option disappears
{
	const before = createSnapshot([
		{ element_ref: "BTN_SKIP", tag: "BUTTON", visible_text: "Skip this step", is_visible: true }
	]);
	const after = createSnapshot([]);
	const res = diffSnapshots(before, after, { route: "/upsell" });
	const sig = res.diff_signals.find(s => s.type === "post_action_alternative_removed");
	assert(Boolean(sig), "16. Positive: Skip option disappears");
}

// 17. Decline option disappears
{
	const before = createSnapshot([
		{ element_ref: "BTN_DECLINE", tag: "BUTTON", visible_text: "Decline Coverage", is_visible: true }
	]);
	const after = createSnapshot([]);
	const res = diffSnapshots(before, after, { route: "/checkout" });
	const sig = res.diff_signals.find(s => s.type === "post_action_alternative_removed");
	assert(Boolean(sig), "17. Positive: Decline option disappears");
}

// 18. Modal blocks cancellation
{
	const before = createSnapshot([]);
	const after = createSnapshot([
		{ element_ref: "DIALOG_BLOCK", tag: "DIALOG", is_modal: true, visible_text: "Are you sure you want to cancel your benefits?", is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/cancel" });
	const sig = res.diff_signals.find(s => s.type === "post_action_confirmation_ui");
	assert(Boolean(sig), "18. Positive: Confirmation modal appears blocking cancellation");
}

// 19. Scroll lock after retention modal
{
	const before = createSnapshot([], { scroll_locked: false });
	const after = createSnapshot([
		{ element_ref: "MODAL_RET", tag: "DIALOG", is_modal: true, visible_text: "Special Retention Offer", is_visible: true }
	], { scroll_locked: true });
	const res = diffSnapshots(before, after, { route: "/cancel" });
	const sig = res.diff_signals.find(s => s.type === "post_action_scroll_lock");
	assert(Boolean(sig) && sig.dom_properties.after.scroll_locked === true, "19. Positive: Scroll lock after retention modal");
}

// 20. Commercial add-on becomes selected
{
	const before = createSnapshot([]);
	const after = createSnapshot([
		{ element_ref: "RADIO_PRIO", tag: "INPUT", type: "radio", visible_text: "Priority expedited shipping add-on", checked_state: true, is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/checkout" });
	const sig = res.diff_signals.find(s => s.type === "post_action_preselection");
	assert(Boolean(sig) && sig.dom_properties.after.checked === true, "20. Positive: Newly rendered commercial add-on is preselected");
}

// =========================================================
// 3. EDGE CASES (10 Tests)
// =========================================================
console.log("\n--- 3. EDGE CASES ---");

// 1. Same text but new DOM node (SPA re-render with new element_ref)
{
	const before = createSnapshot([
		{ element_ref: "NODE_ALPHA", tag: "BUTTON", role: "button", visible_text: "Cancel Subscription", is_disabled: false, is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "NODE_OMEGA", tag: "BUTTON", role: "button", visible_text: "Cancel Subscription", is_disabled: false, is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/cancel" });
	assert(res.diff_signals.length === 0, "1. Edge Case: Same text but new DOM node safely matched without false removal");
}

// 2. Different text but same semantic action (Minor label refinement)
{
	const before = createSnapshot([
		{ element_ref: "BTN_C1", tag: "BUTTON", role: "button", visible_text: "Cancel", is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "BTN_C1", tag: "BUTTON", role: "button", visible_text: "Cancel Subscription", is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/cancel" });
	const hasRemoved = res.diff_signals.some(s => s.type === "post_action_alternative_removed");
	assert(!hasRemoved, "2. Edge Case: Semantic label update does not emit false alternative removed");
}

// 3. Nested modal safely handled without crash
{
	const before = createSnapshot([]);
	const after = createSnapshot([
		{ element_ref: "MODAL_OUTER", tag: "DIALOG", is_modal: true, visible_text: "Outer Dialog", is_visible: true },
		{ element_ref: "MODAL_INNER", tag: "DIV", is_modal: true, visible_text: "Are you sure? Confirm cancellation", is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/cancel" });
	assert(res.diff_signals.length >= 1 && res.diff_signals.every(s => s.type.startsWith("post_action_")), "3. Edge Case: Nested modal processed cleanly without error");
}

// 4. Delayed rendering (snapshot with empty before and asynchronous after)
{
	const before = createSnapshot([
		{ element_ref: "CONTAINER", tag: "DIV", visible_text: "Please wait...", is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "CONTAINER", tag: "DIV", visible_text: "Total: $120.00", is_visible: true },
		{ element_ref: "FEE_E", tag: "SPAN", visible_text: "₹99 booking fee", is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/book" });
	const feeSig = res.diff_signals.find(s => s.type === "post_action_fee_added");
	assert(Boolean(feeSig), "4. Edge Case: Delayed rendering captures post-settle fee addition");
}

// 5. Fast SPA rerender (reordered candidates in snapshot)
{
	const before = createSnapshot([
		{ element_ref: "ITEM_A", tag: "SPAN", visible_text: "Item A: $10", is_visible: true },
		{ element_ref: "ITEM_B", tag: "SPAN", visible_text: "Item B: $20", is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "ITEM_B", tag: "SPAN", visible_text: "Item B: $20", is_visible: true },
		{ element_ref: "ITEM_A", tag: "SPAN", visible_text: "Item A: $10", is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/cart" });
	assert(res.diff_signals.length === 0, "5. Edge Case: Reordered list items during fast SPA rerender produce 0 signals");
}

// 6. Multiple changes in one interaction (price increased AND fee added)
{
	const before = createSnapshot([
		{ element_ref: "PRICE_ROW", tag: "SPAN", visible_text: "$100.00", is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "PRICE_ROW", tag: "SPAN", visible_text: "$120.00", is_visible: true },
		{ element_ref: "FEE_ROW", tag: "SPAN", visible_text: "$10.00 handling fee", is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/checkout" });
	const hasPrice = res.diff_signals.some(s => s.type === "post_action_price_changed");
	const hasFee = res.diff_signals.some(s => s.type === "post_action_fee_added");
	assert(hasPrice && hasFee && res.diff_signals.length === 2, "6. Edge Case: Multiple concurrent changes emit both distinct signals");
}

// 7. Multiple fees added simultaneously
{
	const before = createSnapshot([]);
	const after = createSnapshot([
		{ element_ref: "FEE_1", tag: "SPAN", visible_text: "₹50 processing fee", is_visible: true },
		{ element_ref: "FEE_2", tag: "SPAN", visible_text: "₹30 convenience fee", is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/pay" });
	const feeSignals = res.diff_signals.filter(s => s.type === "post_action_fee_added");
	assert(feeSignals.length === 2, "7. Edge Case: Multiple fee additions captured distinctly");
}

// 8. Price changes without currency symbol
{
	const before = createSnapshot([
		{ element_ref: "PRICE_BOX", tag: "SPAN", role: "price", visible_text: "49.99", is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "PRICE_BOX", tag: "SPAN", role: "price", visible_text: "79.99", is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/pricing" });
	const sig = res.diff_signals.find(s => s.type === "post_action_price_changed");
	assert(Boolean(sig) && sig.dom_properties.after.amount === 79.99 && sig.dom_properties.before.amount === 49.99, "8. Edge Case: Price change detected when amount has no currency symbol");
}

// 9. Same price but formatting changes (₹ 1,000 -> ₹1000.00)
{
	const before = createSnapshot([
		{ element_ref: "AMT", tag: "SPAN", visible_text: "₹ 1,000", is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "AMT", tag: "SPAN", visible_text: "₹1000.00", is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/cart" });
	const hasPriceChange = res.diff_signals.some(s => s.type === "post_action_price_changed");
	assert(!hasPriceChange, "9. Edge Case: Formatting changes with identical mathematical amount do not trigger price changed signal");
}

// 10. Unrelated changes mixed with meaningful change (noisy timestamp/ad update + genuine warranty preselection)
{
	const before = createSnapshot([
		{ element_ref: "TIME", tag: "SPAN", visible_text: "Last checked 10 seconds ago", is_visible: true },
		{ element_ref: "AD", tag: "DIV", class_name: "ad-slot", visible_text: "Buy shoes today", is_visible: true },
		{ element_ref: "CHK_WARR", tag: "INPUT", type: "checkbox", visible_text: "2-Year Protection Plan", checked_state: false, is_visible: true }
	]);
	const after = createSnapshot([
		{ element_ref: "TIME", tag: "SPAN", visible_text: "Last checked 11 seconds ago", is_visible: true },
		{ element_ref: "AD", tag: "DIV", class_name: "ad-slot", visible_text: "Buy jackets today", is_visible: true },
		{ element_ref: "CHK_WARR", tag: "INPUT", type: "checkbox", visible_text: "2-Year Protection Plan", checked_state: true, is_visible: true }
	]);
	const res = diffSnapshots(before, after, { route: "/checkout" });
	const preselect = res.diff_signals.find(s => s.type === "post_action_preselection");
	assert(res.diff_signals.length === 1 && Boolean(preselect), "10. Edge Case: Noisy changes filtered out, leaving only genuine preselection evidence");
}

// =========================================================
// INTEGRATION VERIFICATION: analyzeDomContext with snapshots
// =========================================================
console.log("\n--- INTEGRATION: analyzeDomContext Integration ---");
{
	const beforeSnap = createSnapshot([
		{ element_ref: "BTN_1", tag: "BUTTON", visible_text: "Continue", is_visible: true }
	]);
	const afterSnap = createSnapshot([
		{ element_ref: "BTN_1", tag: "BUTTON", visible_text: "Continue", is_visible: true },
		{ element_ref: "FEE_NEW", tag: "SPAN", visible_text: "₹50 processing fee", is_visible: true }
	]);
	const events = [
		{
			action: "CLICK",
			event_id: "ev_click_1",
			route: "/checkout",
			element: { text: "Continue", tag: "BUTTON" },
			snapshot_before: beforeSnap,
			snapshot_after: afterSnap
		}
	];
	const analysis = analyzeDomContext(events);
	const feeSig = analysis.dom_signals.find(s => s.type === "post_action_fee_added");
	assert(Boolean(feeSig) && analysis.evidence.some(e => e.signal_type === "post_action_fee_added"), "Integration: analyzeDomContext evaluates pre/post snapshots and emits observable evidence");
}

console.log("\n==================================================");
console.log(`TEST RESULTS: ${passedTests} PASSED, ${failedTests} FAILED (TOTAL: ${totalTests})`);
console.log("==================================================");

if (failedTests > 0) {
	process.exit(1);
} else {
	process.exit(0);
}
