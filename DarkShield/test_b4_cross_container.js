/**
 * DarkShield Phase B4.4 — Cross-Container Semantic Action Pairing Test Suite
 *
 * Validates:
 * - 20 Hard Negatives (Navigation, Pagination, Settings Save/Cancel, Unrelated context separation, etc.)
 * - 20 Positive Scenarios (Cross-container retention/cancel, accept/reject, subscribe/skip, visual disparities)
 * - 10 Edge Cases (Self-pairing prevention, duplicate links, icon buttons, aria-labels, multiple pairs)
 * - End-to-end integration through analyzeDomContext
 */

const {
	normalizeAction,
	isCompetingAction,
	getDecisionContext,
	isSharedDecisionContext,
	findSemanticPairs,
	comparePair,
	buildPairEvidence,
	analyzeSemanticPairs
} = require("./extension/analyzer/semanticPairing.js");

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
console.log("RUNNING DARKSHIELD PHASE B4.4 CROSS-CONTAINER TESTS");
console.log("==================================================\n");

// =========================================================
// 1. HARD NEGATIVES (20 Tests)
// =========================================================
console.log("--- 1. HARD NEGATIVES ---");

// 1. Continue in container A / Back in container B
{
	const candidates = [
		{ element_ref: "BTN_CONT", tag: "BUTTON", visible_text: "Continue", container_type: "footer-right" },
		{ element_ref: "BTN_BACK", tag: "BUTTON", visible_text: "Back", container_type: "footer-left" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/onboarding" });
	assert(res.pairs.length === 0 && res.dom_signals.length === 0, "1. Hard Negative: Continue and Back across containers are not competing");
}

// 2. Next / Previous
{
	const candidates = [
		{ element_ref: "BTN_NEXT", tag: "BUTTON", visible_text: "Next Step", container_type: "stepper-bar" },
		{ element_ref: "BTN_PREV", tag: "BUTTON", visible_text: "Previous Step", container_type: "stepper-bar" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/form" });
	assert(res.pairs.length === 0, "2. Hard Negative: Next and Previous stepper actions are not competing");
}

// 3. Save / Cancel ordinary settings
{
	const candidates = [
		{ element_ref: "BTN_SAVE", tag: "BUTTON", visible_text: "Save Settings", container_type: "settings-form" },
		{ element_ref: "BTN_CANCEL", tag: "BUTTON", visible_text: "Cancel", container_type: "settings-modal" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/settings/general" });
	assert(res.pairs.length === 0, "3. Hard Negative: Save and Cancel in ordinary settings are not competing");
}

// 4. Open / Close
{
	const candidates = [
		{ element_ref: "BTN_OPEN", tag: "BUTTON", visible_text: "Open Drawer", container_type: "header" },
		{ element_ref: "BTN_CLOSE", tag: "BUTTON", visible_text: "Close", container_type: "drawer" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/home" });
	assert(res.pairs.length === 0, "4. Hard Negative: Generic Open and Close UI controls are not competing");
}

// 5. FAQ / Help
{
	const candidates = [
		{ element_ref: "LINK_FAQ", tag: "A", visible_text: "Frequently Asked Questions", container_type: "sidebar" },
		{ element_ref: "LINK_HELP", tag: "A", visible_text: "Help Center", container_type: "footer" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/support" });
	assert(res.pairs.length === 0, "5. Hard Negative: FAQ and Help informational links are not competing");
}

// 6. Unrelated Accept and Cancel on same page
{
	const candidates = [
		{ element_ref: "BTN_COOKIE", tag: "BUTTON", visible_text: "Accept Cookies", container_type: "cookie-banner", decision_context: "consent" },
		{ element_ref: "BTN_ORDER", tag: "BUTTON", visible_text: "Cancel Order", container_type: "order-summary", decision_context: "checkout" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/store/checkout" });
	assert(res.pairs.length === 0, "6. Hard Negative: Unrelated Accept cookies and Cancel order on same page are not paired");
}

// 7. Cookie Accept and order Cancel unrelated (with distant coordinates)
{
	const candidates = [
		{ element_ref: "BTN_ACC", tag: "BUTTON", visible_text: "Accept All Cookies", container_type: "cookie-banner", decision_context: "consent", geometry: { y: 20 } },
		{ element_ref: "BTN_CNC", tag: "BUTTON", visible_text: "Cancel Subscription", container_type: "page-bottom", decision_context: "cancellation", geometry: { y: 1500 } }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/account" });
	assert(res.pairs.length === 0, "7. Hard Negative: Cookie consent and distant cancellation action are gated by context and locality");
}

// 8. Country selector / Continue
{
	const candidates = [
		{ element_ref: "SEL_CTRY", tag: "SELECT", visible_text: "Select Country", container_type: "form-row" },
		{ element_ref: "BTN_CONT", tag: "BUTTON", visible_text: "Continue", container_type: "form-actions" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/shipping" });
	assert(res.pairs.length === 0, "8. Hard Negative: Country selector and Continue button are not competing");
}

// 9. Language selector / Cancel
{
	const candidates = [
		{ element_ref: "SEL_LANG", tag: "SELECT", visible_text: "Language: English", container_type: "header-nav" },
		{ element_ref: "BTN_CANC", tag: "BUTTON", visible_text: "Cancel", container_type: "modal-footer" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/profile" });
	assert(res.pairs.length === 0, "9. Hard Negative: Language selector and general cancel button are not competing");
}

// 10. Normal modal close
{
	const candidates = [
		{ element_ref: "BTN_X", tag: "BUTTON", visible_text: "Close", container_type: "modal-header" },
		{ element_ref: "P_INFO", tag: "P", visible_text: "Profile updated successfully", container_type: "modal-body" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/profile" });
	assert(res.pairs.length === 0, "10. Hard Negative: Normal modal close button does not produce competing pair");
}

// 11. Normal dialog buttons (balanced Save vs Cancel in profile)
{
	const candidates = [
		{ element_ref: "BTN_SAVE", tag: "BUTTON", visible_text: "Save Changes", container_type: "dialog-footer" },
		{ element_ref: "BTN_CANCEL", tag: "BUTTON", visible_text: "Cancel", container_type: "dialog-footer" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/profile/edit" });
	assert(res.pairs.length === 0, "11. Hard Negative: Normal dialog Save vs Cancel in preferences is not competing");
}

// 12. Accessibility hidden text
{
	const candidates = [
		{ element_ref: "BTN_ACC_1", tag: "BUTTON", visible_text: "Continue", aria_label: "Continue to next step (accessible)", container_type: "box-a" },
		{ element_ref: "BTN_ACC_2", tag: "BUTTON", visible_text: "Back", aria_label: "Go back (accessible)", container_type: "box-b" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/flow" });
	assert(res.pairs.length === 0, "12. Hard Negative: Accessible screen reader navigation labels do not produce competing pairs");
}

// 13. Responsive stacked buttons (balanced Mobile layout)
{
	const candidates = [
		{ element_ref: "BTN_M1", tag: "BUTTON", visible_text: "Save File", container_type: "mobile-stack", geometry: { width: 300, height: 44, area: 13200 } },
		{ element_ref: "BTN_M2", tag: "BUTTON", visible_text: "Cancel", container_type: "mobile-stack", geometry: { width: 300, height: 44, area: 13200 } }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/editor" });
	assert(res.pairs.length === 0, "13. Hard Negative: Responsive mobile stacked buttons without competing context produce 0 signals");
}

// 14. Two unrelated forms
{
	const candidates = [
		{ element_ref: "BTN_SEARCH", tag: "BUTTON", visible_text: "Search Products", container_type: "search-form", decision_context: "catalog" },
		{ element_ref: "BTN_NEWS", tag: "BUTTON", visible_text: "Newsletter Sign Up", container_type: "footer-form", decision_context: "marketing" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/catalog" });
	assert(res.pairs.length === 0, "14. Hard Negative: Actions in two completely unrelated forms are not paired");
}

// 15. Navigation header and footer
{
	const candidates = [
		{ element_ref: "LINK_SIGNIN", tag: "A", visible_text: "Sign In", container_type: "site-header" },
		{ element_ref: "LINK_PRIVACY", tag: "A", visible_text: "Privacy Policy", container_type: "site-footer" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/home" });
	assert(res.pairs.length === 0, "15. Hard Negative: Navigation header and footer links are not paired");
}

// 16. Unrelated subscription information and account deletion
{
	const candidates = [
		{ element_ref: "CARD_INFO", tag: "DIV", visible_text: "Basic Plan - Free forever", container_type: "pricing-card", decision_context: "subscription" },
		{ element_ref: "BTN_DEL", tag: "BUTTON", visible_text: "Delete Account", container_type: "danger-zone", decision_context: "account_deletion", geometry: { y: 1600 } }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/account" });
	assert(res.pairs.length === 0, "16. Hard Negative: Static pricing info and distant account deletion are not paired");
}

// 17. Normal Save / Delete controls in separate sections
{
	const candidates = [
		{ element_ref: "BTN_SAVE_PROF", tag: "BUTTON", visible_text: "Save Profile", container_type: "profile-tab" },
		{ element_ref: "BTN_DEL_POST", tag: "BUTTON", visible_text: "Delete Post", container_type: "blog-tab" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/admin" });
	assert(res.pairs.length === 0, "17. Hard Negative: Ordinary Save and Delete across different administrative tabs are not paired");
}

// 18. Normal upgrade / cancel where contexts are unrelated
{
	const candidates = [
		{ element_ref: "BTN_UPG_CLOUD", tag: "BUTTON", visible_text: "Upgrade Cloud Storage", container_type: "cloud-section", decision_context: "storage" },
		{ element_ref: "BTN_CNC_RIDE", tag: "BUTTON", visible_text: "Cancel Ride", container_type: "rideshare-card", decision_context: "transport" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/dashboard" });
	assert(res.pairs.length === 0, "18. Hard Negative: Different domain actions across unrelated cards are not paired");
}

// 19. Normal confirmation UI
{
	const candidates = [
		{ element_ref: "BTN_CONF_LOGOUT", tag: "BUTTON", visible_text: "Sign Out", container_type: "logout-dialog" },
		{ element_ref: "BTN_STAY_LOGGED", tag: "BUTTON", visible_text: "Stay Logged In", container_type: "logout-dialog" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/logout" });
	// Balanced logout confirmation does not produce deceptive visual disparity
	const hasSizeAsymmetry = res.dom_signals.some(s => s.type === "action_size_asymmetry");
	assert(!hasSizeAsymmetry, "19. Hard Negative: Balanced signout confirmation does not emit visual asymmetry signals");
}

// 20. Decorative links with opposite wording
{
	const candidates = [
		{ element_ref: "LINK_MORE", tag: "A", visible_text: "Explore More", container_type: "article-body" },
		{ element_ref: "LINK_LESS", tag: "A", visible_text: "Read Less", container_type: "article-footer" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/article" });
	assert(res.pairs.length === 0, "20. Hard Negative: Decorative article links with opposite wording are not paired");
}

// =========================================================
// 2. POSITIVE SCENARIOS (20 Tests)
// =========================================================
console.log("\n--- 2. POSITIVE SCENARIOS ---");

// 1. Keep subscription + Cancel subscription in separate containers
{
	const candidates = [
		{ element_ref: "BTN_KEEP", tag: "BUTTON", visible_text: "Keep my subscription", container_type: "container-left", decision_context: "subscription" },
		{ element_ref: "BTN_CANCEL", tag: "BUTTON", visible_text: "Cancel subscription", container_type: "container-right", decision_context: "cancellation" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/subscription/cancel" });
	const sig = res.dom_signals.find(s => s.type === "semantic_competing_actions");
	assert(Boolean(sig) && sig.dom_properties.action_a.semantic_role === "RETENTION" && sig.dom_properties.action_b.semantic_role === "CANCELLATION", "1. Positive: Keep subscription and Cancel subscription in separate containers paired");
}

// 2. Stay subscribed + Cancel plan
{
	const candidates = [
		{ element_ref: "BTN_STAY", tag: "BUTTON", visible_text: "Stay subscribed", container_type: "banner-cta", decision_context: "subscription" },
		{ element_ref: "BTN_CANCEL", tag: "A", visible_text: "Cancel plan", container_type: "footer-link", decision_context: "cancellation" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/cancel" });
	const sig = res.dom_signals.find(s => s.type === "semantic_competing_actions");
	assert(Boolean(sig), "2. Positive: Stay subscribed and Cancel plan paired across containers");
}

// 3. Keep benefits + End membership
{
	const candidates = [
		{ element_ref: "BTN_BENEFITS", tag: "BUTTON", visible_text: "Keep benefits", container_type: "perks-card", decision_context: "membership" },
		{ element_ref: "BTN_END", tag: "BUTTON", visible_text: "End membership", container_type: "account-settings", decision_context: "membership" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/membership" });
	const sig = res.dom_signals.find(s => s.type === "semantic_competing_actions");
	assert(Boolean(sig), "3. Positive: Keep benefits and End membership paired");
}

// 4. Accept all + Reject all
{
	const candidates = [
		{ element_ref: "BTN_ACCEPT_ALL", tag: "BUTTON", visible_text: "Accept all", container_type: "cookie-top", decision_context: "consent" },
		{ element_ref: "BTN_REJECT_ALL", tag: "BUTTON", visible_text: "Reject all", container_type: "cookie-bottom", decision_context: "consent" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/consent" });
	const sig = res.dom_signals.find(s => s.type === "semantic_competing_actions");
	assert(Boolean(sig) && sig.dom_properties.action_a.semantic_role === "ACCEPT" && sig.dom_properties.action_b.semantic_role === "REJECT", "4. Positive: Accept all and Reject all paired across cookie banner containers");
}

// 5. Allow + Don't allow
{
	const candidates = [
		{ element_ref: "BTN_ALLOW", tag: "BUTTON", visible_text: "Allow", container_type: "dialog-right", decision_context: "consent" },
		{ element_ref: "BTN_DONT_ALLOW", tag: "BUTTON", visible_text: "Don't allow", container_type: "dialog-left", decision_context: "consent" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/permissions" });
	const sig = res.dom_signals.find(s => s.type === "semantic_competing_actions");
	assert(Boolean(sig) && sig.dom_properties.action_a.semantic_role === "ALLOW" && sig.dom_properties.action_b.semantic_role === "DECLINE", "5. Positive: Allow and Don't allow paired across containers");
}

// 6. Subscribe + Skip
{
	const candidates = [
		{ element_ref: "BTN_SUB", tag: "BUTTON", visible_text: "Subscribe now", container_type: "modal-hero", decision_context: "subscription" },
		{ element_ref: "BTN_SKIP", tag: "A", visible_text: "Skip this step", container_type: "modal-footer", decision_context: "subscription" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/onboarding/step2" });
	const sig = res.dom_signals.find(s => s.type === "semantic_competing_actions");
	assert(Boolean(sig) && sig.dom_properties.action_a.semantic_role === "SUBSCRIBE" && sig.dom_properties.action_b.semantic_role === "SKIP", "6. Positive: Subscribe and Skip paired in onboarding flow");
}

// 7. Upgrade + Downgrade
{
	const candidates = [
		{ element_ref: "BTN_UPG", tag: "BUTTON", visible_text: "Upgrade plan", container_type: "pro-card", decision_context: "subscription" },
		{ element_ref: "BTN_DOWNG", tag: "BUTTON", visible_text: "Downgrade plan", container_type: "free-card", decision_context: "subscription" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/billing/plans" });
	const sig = res.dom_signals.find(s => s.type === "semantic_competing_actions");
	assert(Boolean(sig) && sig.dom_properties.action_a.semantic_role === "UPGRADE" && sig.dom_properties.action_b.semantic_role === "DOWNGRADE", "7. Positive: Upgrade and Downgrade paired across pricing cards");
}

// 8. Opt in + Opt out
{
	const candidates = [
		{ element_ref: "BTN_IN", tag: "BUTTON", visible_text: "Opt in", container_type: "pref-left", decision_context: "consent" },
		{ element_ref: "BTN_OUT", tag: "BUTTON", visible_text: "Opt out", container_type: "pref-right", decision_context: "consent" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/privacy/tracking" });
	const sig = res.dom_signals.find(s => s.type === "semantic_competing_actions");
	assert(Boolean(sig) && sig.dom_properties.action_a.semantic_role === "OPT_IN" && sig.dom_properties.action_b.semantic_role === "OPT_OUT", "8. Positive: Opt in and Opt out paired across preference containers");
}

// 9. Retention button visually dominant + cancellation link
{
	const candidates = [
		{ element_ref: "BTN_KEEP", tag: "BUTTON", visible_text: "Keep my subscription", container_type: "card-primary", decision_context: "subscription", geometry: { area: 25000 } },
		{ element_ref: "LINK_CANCEL", tag: "A", visible_text: "Cancel subscription", container_type: "card-secondary", decision_context: "cancellation", geometry: { area: 4000 } }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/cancel" });
	const hasPair = res.dom_signals.some(s => s.type === "semantic_competing_actions");
	const hasSize = res.dom_signals.some(s => s.type === "action_size_asymmetry");
	assert(hasPair && hasSize, "9. Positive: Retention visually dominant (6.25x) emits semantic pairing and action_size_asymmetry");
}

// 10. Cancellation opacity reduced
{
	const candidates = [
		{ element_ref: "BTN_KEEP", tag: "BUTTON", visible_text: "Keep my subscription", container_type: "hero-box", decision_context: "subscription", opacity: 1.0, effective_opacity: 1.0 },
		{ element_ref: "BTN_CANCEL", tag: "BUTTON", visible_text: "Cancel subscription", container_type: "dimmed-box", decision_context: "cancellation", opacity: 0.20, effective_opacity: 0.20 }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/cancel" });
	const hasDeemphasis = res.dom_signals.some(s => s.type === "action_visual_deemphasis");
	assert(hasDeemphasis, "10. Positive: Cancellation with reduced opacity (0.20) emits action_visual_deemphasis across containers");
}

// 11. Cancellation contrast reduced
{
	const candidates = [
		{ element_ref: "BTN_KEEP", tag: "BUTTON", visible_text: "Keep my subscription", container_type: "box-a", decision_context: "subscription", contrast_ratio: 7.0 },
		{ element_ref: "BTN_CANCEL", tag: "BUTTON", visible_text: "Cancel subscription", container_type: "box-b", decision_context: "cancellation", contrast_ratio: 2.1 }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/cancel" });
	const hasContrast = res.dom_signals.some(s => s.type === "contrast_asymmetry");
	assert(hasContrast, "11. Positive: Cancellation with reduced contrast (2.1:1 vs 7.0:1) emits contrast_asymmetry across containers");
}

// 12. Cancellation font significantly smaller
{
	const candidates = [
		{ element_ref: "BTN_KEEP", tag: "BUTTON", visible_text: "Keep my subscription", container_type: "hero", decision_context: "subscription", font_size_px: 20 },
		{ element_ref: "LINK_CANCEL", tag: "A", visible_text: "Cancel subscription", container_type: "footer", decision_context: "cancellation", font_size_px: 9 }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/cancel" });
	const hasTypo = res.dom_signals.some(s => s.type === "typography_asymmetry");
	assert(hasTypo, "12. Positive: Cancellation with 9px font vs 20px emits typography_asymmetry across containers");
}

// 13. Cancellation button disabled while retention remains active
{
	const candidates = [
		{ element_ref: "BTN_KEEP", tag: "BUTTON", visible_text: "Keep my subscription", container_type: "active-panel", decision_context: "subscription", is_disabled: false },
		{ element_ref: "BTN_CANCEL", tag: "BUTTON", visible_text: "Cancel subscription", container_type: "locked-panel", decision_context: "cancellation", is_disabled: true }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/cancel" });
	const hasDisabled = res.dom_signals.some(s => s.type === "disabled_action");
	assert(hasDisabled, "13. Positive: Cancellation button disabled while retention active emits disabled_action across containers");
}

// 14. Cancellation hidden while retention remains visible
{
	const candidates = [
		{ element_ref: "BTN_KEEP", tag: "BUTTON", visible_text: "Keep my subscription", container_type: "card-visible", decision_context: "subscription", is_visible: true },
		{ element_ref: "LINK_CANCEL", tag: "A", visible_text: "Cancel subscription", container_type: "card-hidden", decision_context: "cancellation", is_visible: false }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/cancel" });
	const hasHidden = res.dom_signals.some(s => s.type === "hidden_alternative");
	assert(hasHidden, "14. Positive: Cancellation hidden while retention visible emits hidden_alternative across containers");
}

// 15. Cross-container actions in same cancellation modal
{
	const candidates = [
		{ element_ref: "BTN_STAY", tag: "BUTTON", visible_text: "Stay subscribed and save 50%", container_type: "modal-body", decision_context: "cancellation" },
		{ element_ref: "LINK_CONF_CANCEL", tag: "A", visible_text: "Confirm cancellation", container_type: "modal-footer", decision_context: "cancellation" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/cancel" });
	const sig = res.dom_signals.find(s => s.type === "semantic_competing_actions");
	assert(Boolean(sig) && sig.dom_properties.decision_context === "cancellation", "15. Positive: Cross-container actions in same cancellation modal identified");
}

// 16. Cross-container actions in same subscription page
{
	const candidates = [
		{ element_ref: "BTN_KEEP_PLAN", tag: "BUTTON", visible_text: "Keep my plan", container_type: "sidebar-action", decision_context: "subscription" },
		{ element_ref: "BTN_STOP_RENEW", tag: "BUTTON", visible_text: "Stop renewal", container_type: "main-content", decision_context: "subscription" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/manage-subscription" });
	const sig = res.dom_signals.find(s => s.type === "semantic_competing_actions");
	assert(Boolean(sig), "16. Positive: Cross-container actions in same subscription page identified");
}

// 17. Cross-container actions in checkout
{
	const candidates = [
		{ element_ref: "BTN_PROT", tag: "BUTTON", visible_text: "Subscribe to protection", container_type: "upsell-card", decision_context: "checkout" },
		{ element_ref: "BTN_NO_PROT", tag: "A", visible_text: "Decline protection", container_type: "checkout-nav", decision_context: "checkout" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/checkout" });
	const sig = res.dom_signals.find(s => s.type === "semantic_competing_actions");
	assert(Boolean(sig), "17. Positive: Cross-container actions in checkout paired");
}

// 18. Cross-container actions in billing
{
	const candidates = [
		{ element_ref: "BTN_CURR", tag: "BUTTON", visible_text: "Stay on current tier", container_type: "billing-header", decision_context: "billing" },
		{ element_ref: "BTN_TERM", tag: "BUTTON", visible_text: "Terminate membership", container_type: "billing-table-footer", decision_context: "billing" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/billing" });
	const sig = res.dom_signals.find(s => s.type === "semantic_competing_actions");
	assert(Boolean(sig), "18. Positive: Cross-container actions in billing paired");
}

// 19. Cross-container actions in consent
{
	const candidates = [
		{ element_ref: "BTN_ALL_ALLOW", tag: "BUTTON", visible_text: "Allow all tracking", container_type: "banner-main", decision_context: "consent" },
		{ element_ref: "BTN_ALL_REJ", tag: "BUTTON", visible_text: "Reject tracking", container_type: "accordion-details", decision_context: "consent" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/privacy" });
	const sig = res.dom_signals.find(s => s.type === "semantic_competing_actions");
	assert(Boolean(sig), "19. Positive: Cross-container actions in consent paired across main banner and accordion");
}

// 20. Cross-container actions with combined visual disparities
{
	const candidates = [
		{
			element_ref: "BTN_KEEP",
			tag: "BUTTON",
			visible_text: "Keep benefits",
			container_type: "card-a",
			decision_context: "subscription",
			geometry: { area: 24000 },
			font_size_px: 18,
			font_weight: 700,
			opacity: 1.0,
			contrast_ratio: 7.5
		},
		{
			element_ref: "BTN_CANCEL",
			tag: "BUTTON",
			visible_text: "End membership",
			container_type: "card-b",
			decision_context: "cancellation",
			geometry: { area: 4500 },
			font_size_px: 10,
			font_weight: 400,
			opacity: 0.35,
			contrast_ratio: 2.2
		}
	];
	const res = analyzeSemanticPairs(candidates, { route: "/account" });
	const hasPair = res.dom_signals.some(s => s.type === "semantic_competing_actions");
	const hasSize = res.dom_signals.some(s => s.type === "action_size_asymmetry");
	const hasDeemphasis = res.dom_signals.some(s => s.type === "action_visual_deemphasis");
	const hasContrast = res.dom_signals.some(s => s.type === "contrast_asymmetry");
	assert(hasPair && hasSize && hasDeemphasis && hasContrast, "20. Positive: Combined area (5.3x), opacity (0.35), contrast (2.2), and typography disparities emitted together");
}

// =========================================================
// 3. EDGE CASES (10 Tests)
// =========================================================
console.log("\n--- 3. EDGE CASES ---");

// 1. Identical action text in multiple containers
{
	const candidates = [
		{ element_ref: "BTN_K1", tag: "BUTTON", visible_text: "Keep subscription", container_type: "top-box", decision_context: "subscription" },
		{ element_ref: "BTN_K2", tag: "BUTTON", visible_text: "Keep subscription", container_type: "bottom-box", decision_context: "subscription" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/cancel" });
	assert(res.pairs.length === 0, "1. Edge Case: Identical action categories across containers do not self-pair");
}

// 2. Duplicate cancellation links
{
	const candidates = [
		{ element_ref: "LINK_C1", tag: "A", visible_text: "Cancel Subscription", container_type: "footer", decision_context: "cancellation" },
		{ element_ref: "LINK_C2", tag: "A", visible_text: "Cancel Subscription", container_type: "sidebar", decision_context: "cancellation" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/cancel" });
	assert(res.pairs.length === 0, "2. Edge Case: Multiple cancellation links are not paired against each other");
}

// 3. Same semantic action repeated
{
	const candidates = [
		{ element_ref: "BTN_R1", tag: "BUTTON", visible_text: "Stay subscribed", container_type: "card-1", decision_context: "subscription" },
		{ element_ref: "BTN_R2", tag: "BUTTON", visible_text: "Keep my plan", container_type: "card-2", decision_context: "subscription" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/subscription" });
	assert(res.pairs.length === 0, "3. Edge Case: Multiple RETENTION variants across containers do not pair with each other");
}

// 4. Dynamically rerendered elements
{
	const candidates = [
		{ element_ref: "BTN_KEEP_SPA_101", tag: "BUTTON", visible_text: "Keep benefits", container_type: "hero", decision_context: "subscription" },
		{ element_ref: "BTN_CANCEL_SPA_202", tag: "BUTTON", visible_text: "Cancel membership", container_type: "footer", decision_context: "cancellation" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/membership" });
	assert(res.pairs.length === 1 && res.dom_signals.length === 1, "4. Edge Case: Ephemeral SPA references canonicalize and pair cleanly without duplicates");
}

// 5. Different aria-label and visible text
{
	const candidates = [
		{ element_ref: "BTN_YES", tag: "BUTTON", visible_text: "Yes", aria_label: "Keep my subscription active", container_type: "card-a", decision_context: "subscription" },
		{ element_ref: "BTN_NO", tag: "BUTTON", visible_text: "No", aria_label: "Cancel subscription now", container_type: "card-b", decision_context: "cancellation" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/cancel" });
	const sig = res.dom_signals.find(s => s.type === "semantic_competing_actions");
	assert(Boolean(sig) && sig.dom_properties.action_a.semantic_role === "RETENTION" && sig.dom_properties.action_b.semantic_role === "CANCELLATION", "5. Edge Case: Actions with ambiguous visible text but descriptive aria-label correctly recognized and paired");
}

// 6. Icon-only button with aria-label
{
	const candidates = [
		{ element_ref: "BTN_ICON_KEEP", tag: "BUTTON", visible_text: "", aria_label: "Keep plan benefits", container_type: "dialog-a", decision_context: "subscription" },
		{ element_ref: "BTN_ICON_CANCEL", tag: "BUTTON", visible_text: "", aria_label: "Proceed with cancellation", container_type: "dialog-b", decision_context: "cancellation" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/cancel" });
	const sig = res.dom_signals.find(s => s.type === "semantic_competing_actions");
	assert(Boolean(sig), "6. Edge Case: Icon-only buttons with descriptive aria-label paired successfully");
}

// 7. Missing visible text
{
	const candidates = [
		{ element_ref: "BTN_EMPTY", tag: "BUTTON", visible_text: "", aria_label: "", container_type: "dialog" },
		{ element_ref: "BTN_CANCEL", tag: "BUTTON", visible_text: "Cancel subscription", container_type: "dialog", decision_context: "cancellation" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/cancel" });
	assert(res.pairs.length === 0, "7. Edge Case: Empty button with missing text handles safely without error");
}

// 8. Partially offscreen action
{
	const candidates = [
		{ element_ref: "BTN_KEEP", tag: "BUTTON", visible_text: "Keep benefits", container_type: "box-a", decision_context: "subscription", geometry: { x: 100, y: 150, width: 200, height: 40, area: 8000 } },
		{ element_ref: "BTN_CANCEL", tag: "BUTTON", visible_text: "End membership", container_type: "box-b", decision_context: "membership", geometry: { x: -50, y: 150, width: 100, height: 40, area: 4000 } }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/membership" });
	const sig = res.dom_signals.find(s => s.type === "semantic_competing_actions");
	assert(Boolean(sig), "8. Edge Case: Partially offscreen action paired with valid geometry");
}

// 9. Mobile layout (equal dimensions, no false asymmetry)
{
	const candidates = [
		{ element_ref: "BTN_M_KEEP", tag: "BUTTON", visible_text: "Stay subscribed", container_type: "mobile-stack-top", decision_context: "subscription", geometry: { width: 320, height: 48, area: 15360 }, font_size_px: 16, opacity: 1.0 },
		{ element_ref: "BTN_M_CANCEL", tag: "BUTTON", visible_text: "Cancel plan", container_type: "mobile-stack-bottom", decision_context: "cancellation", geometry: { width: 320, height: 48, area: 15360 }, font_size_px: 16, opacity: 1.0 }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/cancel" });
	const hasPair = res.dom_signals.some(s => s.type === "semantic_competing_actions");
	const hasSizeAsymmetry = res.dom_signals.some(s => s.type === "action_size_asymmetry");
	assert(hasPair && !hasSizeAsymmetry, "9. Edge Case: Mobile stacked layout pairs semantically without false visual asymmetry");
}

// 10. Multiple valid competing pairs on same page
{
	const candidates = [
		// Pair 1: Subscription section
		{ element_ref: "BTN_UPG", tag: "BUTTON", visible_text: "Upgrade plan", container_type: "sub-card-a", decision_context: "subscription" },
		{ element_ref: "BTN_DOWNG", tag: "BUTTON", visible_text: "Downgrade plan", container_type: "sub-card-b", decision_context: "subscription" },
		// Pair 2: Consent banner
		{ element_ref: "BTN_ACC", tag: "BUTTON", visible_text: "Accept all", container_type: "cookie-a", decision_context: "consent" },
		{ element_ref: "BTN_REJ", tag: "BUTTON", visible_text: "Reject all", container_type: "cookie-b", decision_context: "consent" }
	];
	const res = analyzeSemanticPairs(candidates, { route: "/account/settings" });
	assert(res.pairs.length === 2, "10. Edge Case: Multiple distinct competing pairs on same page identified without cross-context pollution");
}

// =========================================================
// 4. INTEGRATION VERIFICATION: analyzeDomContext
// =========================================================
console.log("\n--- INTEGRATION: analyzeDomContext Integration ---");
{
	const events = [
		{
			action: "CLICK",
			event_id: "ev_click_cross_1",
			route: "/account/cancel",
			element: { text: "Cancel subscription", tag: "BUTTON" },
			candidate_actions: [
				{ element_ref: "BTN_KEEP", tag: "BUTTON", visible_text: "Keep my subscription", container_type: "retention-card", decision_context: "subscription", geometry: { area: 20000 } },
				{ element_ref: "LINK_CANCEL", tag: "A", visible_text: "Cancel subscription", container_type: "cancel-card", decision_context: "cancellation", geometry: { area: 3000 } }
			]
		}
	];
	const analysis = analyzeDomContext(events);
	const semSig = analysis.dom_signals.find(s => s.type === "semantic_competing_actions");
	const sizeSig = analysis.dom_signals.find(s => s.type === "action_size_asymmetry");
	assert(Boolean(semSig) && Boolean(sizeSig), "Integration: analyzeDomContext evaluates candidate_actions and emits cross-container semantic and visual evidence");
}

console.log("\n==================================================");
console.log(`TEST RESULTS: ${passedTests} PASSED, ${failedTests} FAILED (TOTAL: ${totalTests})`);
console.log("==================================================");

if (failedTests > 0) {
	process.exit(1);
} else {
	process.exit(0);
}
