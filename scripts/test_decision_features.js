/**
 * scripts/test_decision_features.js
 * Automated test suite for ClauseGuard's 3 new features:
 * 1. Decision Snapshot
 * 2. What Happens If I Continue? (Consequence Engine)
 * 3. Agreement Memory
 */

const assert = require("assert");
const fs = require("fs");
const path = require("path");

const DecisionSnapshot = require("../extension/decision/decisionSnapshot.js");
const ConsequenceEngine = require("../extension/decision/consequenceEngine.js");
const AgreementMemory = require("../extension/decision/agreementMemory.js");

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    console.log(`  ✓ ${name}`);
    passed++;
  } catch (err) {
    console.error(`  ✗ ${name}`);
    console.error(`    ${err.message}`);
    failed++;
  }
}

console.log("\n==========================================");
console.log("TEST SUITE: DECISION SNAPSHOT");
console.log("==========================================");

test("Extracts price, renewal, privacy, and interface from full subscription page", () => {
  const mockAnalysis = {
    risk_score: 6.2,
    risk_level: "LOW",
    potential_pattern: "social_proof",
    financial_impact: {
      known_total: 699,
      currency: "₹",
      billing_period: "month",
      auto_renewal: true
    },
    evidence: [
      { type: "monetary_entity", value: 699, currency: "₹", description: "₹699/month recurring" },
      { type: "auto_renewal", description: "Subscription automatically renews monthly" },
      { type: "privacy_disclosure", description: "Information shared with advertising partners" }
    ]
  };
  const text = "Start your 7-day free trial today. ₹699/month after trial. Automatically renews. 48 people viewing this.";

  const snapshot = DecisionSnapshot.extractDecisionSnapshot(mockAnalysis, text, null);

  assert.strictEqual(snapshot.cost.detected, true);
  assert.strictEqual(snapshot.cost.amount, 699);
  assert.strictEqual(snapshot.cost.text, "₹699/month");

  assert.strictEqual(snapshot.renewal.detected, true);
  assert.strictEqual(snapshot.renewal.autoRenewal, true);
  assert.strictEqual(snapshot.renewal.text, "Automatic renewal detected");

  assert.strictEqual(snapshot.privacy.detected, true);
  assert.strictEqual(snapshot.privacy.hasSharing, true);
  assert.strictEqual(snapshot.privacy.text, "Third-party sharing mentioned");

  assert.strictEqual(snapshot.interface.detected, true);
  assert.strictEqual(snapshot.interface.text, "Social-proof signal detected");

  assert.ok(snapshot.checklist.length > 0);
  assert.ok(snapshot.checklist.includes("Renewal price"));
  assert.ok(snapshot.checklist.includes("Cancellation terms"));
  assert.ok(snapshot.checklist.includes("Data-sharing information"));
});

test("Handles neutral page without detected signals (no false positives)", () => {
  const mockAnalysis = {
    risk_score: 0.0,
    risk_level: "LOW",
    potential_pattern: null,
    financial_impact: null,
    evidence: []
  };
  const text = "Welcome to our information portal. Read documentation, browse articles, and contact us.";

  const snapshot = DecisionSnapshot.extractDecisionSnapshot(mockAnalysis, text, null);

  assert.strictEqual(snapshot.cost.detected, false);
  assert.strictEqual(snapshot.cost.text, "Cost: Not detected");

  assert.strictEqual(snapshot.renewal.detected, false);
  assert.strictEqual(snapshot.renewal.text, "Renewal: Not detected");

  assert.strictEqual(snapshot.privacy.detected, false);
  assert.strictEqual(snapshot.privacy.text, "Privacy: No relevant signal detected");

  assert.strictEqual(snapshot.interface.detected, false);
  assert.strictEqual(snapshot.interface.text, "Standard interface detected");

  assert.strictEqual(snapshot.checklist.length, 2);
  assert.ok(snapshot.checklist.includes("Final checkout amount before confirming"));
});

console.log("\n==========================================");
console.log("TEST SUITE: WHAT HAPPENS IF I CONTINUE?");
console.log("==========================================");

test("Constructs 4-step sequence for trial + subscription + auto-renewal", () => {
  const mockAnalysis = {
    potential_pattern: "social_proof",
    financial_impact: { known_total: 699, currency: "₹", billing_period: "month", auto_renewal: true },
    evidence: []
  };
  const snapshot = {
    cost: { detected: true, text: "₹699/month", amount: 699 },
    renewal: { detected: true, autoRenewal: true }
  };
  const text = "Start your 7-day free trial. Renews automatically at ₹699/month after trial.";

  const flow = ConsequenceEngine.buildConsequenceFlow(mockAnalysis, snapshot, text, null);

  assert.strictEqual(flow.hasFlow, true);
  assert.strictEqual(flow.fallbackMessage, null);
  assert.strictEqual(flow.steps.length, 4);
  assert.strictEqual(flow.steps[0], "Start the free trial");
  assert.strictEqual(flow.steps[1], "Trial ends after 7 days");
  assert.strictEqual(flow.steps[2], "Subscription may begin at ₹699/month");
  assert.strictEqual(flow.steps[3], "Automatic renewal is indicated");
  assert.strictEqual(flow.actionAdvice, "Before continuing, check the renewal price and cancellation terms.");
});

test("Attaches cancellation difficulty and third-party privacy advisories when detected", () => {
  const mockAnalysis = {
    potential_pattern: "obstruction",
    evidence: [
      { description: "Canceling your subscription requires contacting customer support via phone call." },
      { description: "We share your personal data with third-party advertising networks." }
    ]
  };
  const snapshot = {
    cost: { detected: true, text: "₹999/year", amount: 999 },
    renewal: { detected: true, autoRenewal: true }
  };
  const text = "Canceling your subscription requires contacting customer support via international phone call.";

  const flow = ConsequenceEngine.buildConsequenceFlow(mockAnalysis, snapshot, text, null);

  assert.ok(flow.advisories.length >= 2);
  assert.ok(flow.advisories.some(a => a.includes("Cancellation may require additional steps")));
  assert.ok(flow.advisories.some(a => a.includes("Your information may be shared with third parties")));
});

test("Returns fallback message when there is not enough information", () => {
  const mockAnalysis = { potential_pattern: null, evidence: [] };
  const snapshot = { cost: { detected: false }, renewal: { detected: false } };
  const text = "About Us. We are a creative digital studio.";

  const flow = ConsequenceEngine.buildConsequenceFlow(mockAnalysis, snapshot, text, null);

  assert.strictEqual(flow.hasFlow, false);
  assert.strictEqual(flow.fallbackMessage, "ClauseGuard does not have enough information to determine the next steps.");
  assert.strictEqual(flow.steps.length, 0);
});

console.log("\n==========================================");
console.log("TEST SUITE: AGREEMENT MEMORY");
console.log("==========================================");

test("Correctly flags first analysis for a new website", () => {
  const currentRecord = {
    domain: "example.com",
    price: "₹149/month",
    priceAmount: 149,
    autoRenewal: true,
    riskScore: 2.0,
    riskLevel: "LOW"
  };

  const diff = AgreementMemory.compareWithPrevious(currentRecord, null);

  assert.strictEqual(diff.isFirstAnalysis, true);
  assert.strictEqual(diff.hasChanged, false);
  assert.strictEqual(diff.changes.length, 0);
});

test("Detects no changes when consecutive analyses are identical", () => {
  const previousRecord = {
    domain: "example.com",
    price: "₹149/month",
    priceAmount: 149,
    autoRenewal: true,
    trial: "Trial ends after 7 days",
    riskScore: 2.0,
    riskLevel: "LOW",
    signals: ["AUTO_RENEWAL"]
  };
  const currentRecord = { ...previousRecord };

  const diff = AgreementMemory.compareWithPrevious(currentRecord, previousRecord);

  assert.strictEqual(diff.isFirstAnalysis, false);
  assert.strictEqual(diff.hasChanged, false);
  assert.strictEqual(diff.changes.length, 0);
});

test("Accurately detects and quantifies price increase", () => {
  const previousRecord = {
    domain: "netflix.com",
    price: "₹149/month",
    priceAmount: 149,
    currency: "₹",
    period: "month",
    autoRenewal: true,
    riskScore: 2.0,
    riskLevel: "LOW"
  };
  const currentRecord = {
    domain: "netflix.com",
    price: "₹199/month",
    priceAmount: 199,
    currency: "₹",
    period: "month",
    autoRenewal: true,
    riskScore: 2.0,
    riskLevel: "LOW"
  };

  const diff = AgreementMemory.compareWithPrevious(currentRecord, previousRecord);

  assert.strictEqual(diff.hasChanged, true);
  const priceChange = diff.changes.find(c => c.type === "PRICE_CHANGED");
  assert.ok(priceChange);
  assert.strictEqual(priceChange.title, "Price changed");
  assert.strictEqual(priceChange.detail, "₹149/month → ₹199/month");
  assert.strictEqual(priceChange.extra, "Increase: +₹50/month");
});

test("Detects trial change, new auto-renewal, and privacy sharing", () => {
  const previousRecord = {
    domain: "service.com",
    price: "₹499",
    trial: "Trial ends after 7 days",
    autoRenewal: false,
    signals: [],
    riskScore: 1.0,
    riskLevel: "LOW"
  };
  const currentRecord = {
    domain: "service.com",
    price: "₹499",
    trial: "Trial ends after 14 days",
    autoRenewal: true,
    signals: ["AUTO_RENEWAL", "DATA_SHARING"],
    privacyFindings: "Third-party advertising partners",
    riskScore: 4.5,
    riskLevel: "MEDIUM"
  };

  const diff = AgreementMemory.compareWithPrevious(currentRecord, previousRecord);

  assert.strictEqual(diff.hasChanged, true);
  assert.ok(diff.changes.some(c => c.type === "TRIAL_CHANGED"));
  assert.ok(diff.changes.some(c => c.type === "AUTORENEWAL_NEW"));
  assert.ok(diff.changes.some(c => c.type === "PRIVACY_NEW"));
  assert.ok(diff.changes.some(c => c.type === "RISK_SHIFT"));
});

test("Data safety guarantee: No sensitive form data stored", () => {
  const record = AgreementMemory.buildMemoryRecord("shop.com", "https://shop.com/checkout?promo=abc", {
    risk_score: 3.0,
    risk_level: "LOW"
  }, {
    cost: { detected: true, text: "₹499", amount: 499 },
    renewal: { detected: false },
    privacy: { detected: false },
    interface: { detected: false }
  }, null);

  const serialized = JSON.stringify(record);
  assert.ok(!serialized.includes("password"));
  assert.ok(!serialized.includes("credit_card"));
  assert.ok(!serialized.includes("cvv"));
  assert.strictEqual(record.url, "https://shop.com/checkout"); // Query parameters stripped
});

console.log("\n==========================================");
console.log("TEST SUITE: CONTRACT & SECURITY COMPLIANCE");
console.log("==========================================");

test("popup.html preserves all required contract IDs", () => {
  const html = fs.readFileSync(path.join(__dirname, "../extension/popup.html"), "utf-8");
  const requiredIds = [
    "analyzeBtn",
    "status",
    "result",
    "error",
    "icon",
    "resultTitle",
    "confidence",
    "modelVersion",
    "disclaimer",
    "askSection",
    "askForm",
    "askQuestion",
    // New feature IDs
    "decisionSnapshotSection",
    "consequenceSection",
    "agreementMemorySection"
  ];

  for (const id of requiredIds) {
    assert.ok(html.includes(`id="${id}"`), `Missing required id: ${id}`);
  }
});

test("popup.js complies strictly with security and MV3 requirements (no innerHTML, no eval)", () => {
  const js = fs.readFileSync(path.join(__dirname, "../extension/popup.js"), "utf-8");

  assert.ok(!js.includes("innerHTML"), "Violated security rule: innerHTML found in popup.js");
  assert.ok(!js.includes("eval("), "Violated security rule: eval( found in popup.js");
  assert.ok(!js.includes("new Function"), "Violated security rule: new Function found in popup.js");
  assert.ok(!js.includes("document.write"), "Violated security rule: document.write found in popup.js");

  // Essential functions and strings
  assert.ok(js.includes("analyzeText"));
  assert.ok(js.includes("validateResponse"));
  assert.ok(js.includes("showError"));
  assert.ok(js.includes("errorDiv.textContent"));
  assert.ok(js.includes("ASK_ENDPOINT"));
  assert.ok(js.includes("askQuestionAndRender"));
});

console.log("\n==========================================");
console.log(`TOTAL RESULTS: ${passed} passed, ${failed} failed`);
console.log("==========================================\n");

if (failed > 0) process.exit(1);
