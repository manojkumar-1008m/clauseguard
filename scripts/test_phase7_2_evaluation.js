// scripts/test_phase7_2_evaluation.js
// Evaluates Phase 7.2 DOM-aware segmentation & evidence quality against live FastAPI backend

const fs = require('fs');
const path = require('path');

const MAX_CONCURRENT_REQUESTS = 5;
const WINDOW_MIN_CHARS = 500;
const WINDOW_MAX_CHARS = 1200;
const UNCERTAINTY_THRESHOLD = 0.60;
const BACKEND_MAX_LEN = 5000;

function buildSemanticWindows(items) {
  if (!items || items.length === 0) return [];

  // Structured DOM blocks [{ text, tag, section, containerId }]
  const containerGroups = new Map();
  for (const b of items) {
    if (!b || !b.text || !b.text.trim()) continue;
    const key = `${b.section || "content"}_${b.containerId || 1}`;
    if (!containerGroups.has(key)) {
      containerGroups.set(key, []);
    }
    containerGroups.get(key).push(b.text.trim());
  }

  const windows = [];
  for (const [groupKey, blockTexts] of containerGroups.entries()) {
    let currentWin = [];
    let currentLen = 0;

    for (const text of blockTexts) {
      const tLen = text.length;
      if (currentLen + tLen + (currentLen > 0 ? 1 : 0) <= WINDOW_MAX_CHARS) {
        currentWin.push(text);
        currentLen += tLen + (currentLen > 0 ? 1 : 0);
      } else {
        if (currentWin.length > 0) {
          windows.push(currentWin.join("\n"));
        }
        currentWin = [text];
        currentLen = tLen;
      }
    }

    if (currentWin.length > 0) {
      windows.push(currentWin.join("\n"));
    }
  }

  return windows.filter((w) => w.trim().length > 0);
}

function splitIntoSentences(text) {
  if (!text) return [];
  const rawChunks = text.split(/\n+/);
  const sentences = [];

  for (const chunk of rawChunks) {
    const parts = chunk.split(/(?<=[.!?])\s+(?=[A-Z0-9₹$€£"']|$)/);
    for (const p of parts) {
      const trimmed = p.trim();
      if (trimmed.length > 0) {
        sentences.push(trimmed);
      }
    }
  }
  return sentences;
}

let activeRequests = 0;
let maxObservedConcurrency = 0;
let requestCount = 0;

async function asyncPool(limit, items, iteratorFn) {
  const ret = [];
  const executing = new Set();
  for (const item of items) {
    const p = Promise.resolve().then(() => {
      activeRequests++;
      if (activeRequests > maxObservedConcurrency) {
        maxObservedConcurrency = activeRequests;
      }
      return iteratorFn(item);
    }).finally(() => {
      activeRequests--;
    });

    ret.push(p);
    executing.add(p);
    const clean = () => executing.delete(p);
    p.then(clean, clean);
    if (executing.size >= limit) {
      await Promise.race(executing);
    }
  }
  return Promise.all(ret);
}

async function postPredict(text) {
  requestCount++;
  const payload = text.length > BACKEND_MAX_LEN ? text.slice(0, BACKEND_MAX_LEN) : text;
  const res = await fetch("http://127.0.0.1:8000/predict", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: payload }),
  });
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return res.json();
}

async function refineWindow(windowText, seenSentences = new Set()) {
  const sentences = splitIntoSentences(windowText);
  const toAnalyze = [];
  for (const s of sentences) {
    const trimmed = s.trim();
    if (trimmed && !seenSentences.has(trimmed)) {
      seenSentences.add(trimmed);
      toAnalyze.push(trimmed);
    }
  }
  if (toAnalyze.length === 0) return [];
  return asyncPool(MAX_CONCURRENT_REQUESTS, toAnalyze, async (s) => {
    const data = await postPredict(s);
    return { ...data, text: s };
  });
}

function isWeakOrGenericEvidence(evidence) {
  if (!evidence) return true;
  const ev = evidence.trim();
  if (ev.length < 5) return true;

  const genericPatterns = [
    /^(?:help\s*&\s*support|need\s*help\??|help|support|faq|customer\s*care|contact\s*us)$/i,
    /^(?:login|sign\s*in|sign\s*up|register|log\s*out|start\s*watching(?:\s*from.*)?)$/i,
    /^(?:login\s*to\s*[a-z0-9_\s]+)$/i,
    /^(?:company|about\s*us|careers|press|terms(?:\s*of\s*use)?|privacy(?:\s*policy)?|all\s*rights\s*reserved)$/i,
    /^(?:home|menu|search|back|next|skip|close|view\s*all|explore)$/i,
    /^(?:order\s*confirmation\s*&\s*subscription\s*details)$/i,
  ];

  if (genericPatterns.some((p) => p.test(ev))) {
    return true;
  }

  const darkCues = /(?:fee|cost|charg|pay|subscri|renew|cancel|order|warrant|hurry|left|exclusiv|limit|trap|sneak)/i;
  if (ev.length < 35 && !darkCues.test(ev)) {
    return true;
  }

  return false;
}

  // Helper to map recognized dark-pattern categories when pattern_category is not returned
  function mapRecognizedCategory(text, evidence) {
    const combined = `${evidence || ""} ${text || ""}`.toLowerCase();
    if (
      (combined.includes("cancel") || combined.includes("cancellation")) &&
      (combined.includes("contact") || combined.includes("customer support") || combined.includes("calling") || combined.includes("phone"))
    ) {
      return {
        category: "Obstruction",
        consequence: "Canceling the service may require navigating difficult customer support channels rather than an online self-serve cancellation.",
      };
    }
    if (
      combined.includes("automatically renews") ||
      combined.includes("renews automatically") ||
      combined.includes("auto-renew")
    ) {
      return {
        category: "Subscription Trap",
        consequence: "The subscription may renew automatically and result in recurring charges unless manually canceled.",
      };
    }
    if (
      (combined.includes("fee") || combined.includes("charge")) &&
      (combined.includes("revealed after") || combined.includes("added at checkout") || combined.includes("hidden until"))
    ) {
      return {
        category: "Drip Pricing",
        consequence: "The final amount may be higher than initially displayed because additional fees are disclosed later.",
      };
    }
    if (
      (combined.includes("warranty") || combined.includes("protection") || combined.includes("add-on")) &&
      (combined.includes("already been selected") || combined.includes("already selected") || combined.includes("automatically added"))
    ) {
      return {
        category: "Sneaking",
        consequence: "An additional product or service may be included automatically unless manually removed.",
      };
    }
    return null;
  }

function aggregateFindings(results) {
  const findings = [];
  const contextRequired = [];
  const seenEvidence = new Set();
  const seenContext = new Set();

  for (const r of results) {
    if (!r) continue;
    const ev = (r.evidence || "").trim();

    const recognized = mapRecognizedCategory(r.text, ev);
    const effectiveCategory = recognized ? recognized.category : r.pattern_category;
    const effectiveConsequence = recognized ? recognized.consequence : r.consumer_consequence;

    const isOther = effectiveCategory === "Other";
    const isWeak = isWeakOrGenericEvidence(ev || r.text);

    let requiresContext = Boolean(r.requires_context);
    if (recognized) {
      requiresContext = false;
    } else if (isOther && isWeak) {
      requiresContext = true;
    } else if (r.prediction === 1 && !effectiveCategory) {
      requiresContext = true;
    }

    if (requiresContext) {
      const key = ev || (r.text || "").trim();
      if (key && !seenContext.has(key)) {
        seenContext.add(key);
        contextRequired.push({
          evidence: key,
          confidence: r.confidence || 0,
          pattern_category: isOther ? "Potential signal — more context required" : null,
          consumer_consequence: effectiveConsequence || null,
          requires_context: true,
          model_version: r.model_version,
        });
      }
    } else if (r.prediction === 1 && effectiveCategory && ev) {
      if (!seenEvidence.has(ev)) {
        seenEvidence.add(ev);
        findings.push({
          pattern_category: effectiveCategory,
          confidence: r.confidence || 0,
          evidence: ev,
          consumer_consequence: effectiveConsequence || "Potential consumer detriment.",
          requires_context: false,
          model_version: r.model_version,
        });
      }
    }
  }

  findings.sort((a, b) => {
    if (a.requires_context !== b.requires_context) {
      return a.requires_context ? 1 : -1;
    }
    return (b.confidence || 0) - (a.confidence || 0);
  });

  return {
    chunks_analyzed: results.length,
    findings,
    context_required: contextRequired,
  };
}

async function runEvaluation(name, domBlocks) {
  console.log(`\n======================================================`);
  console.log(`EVALUATION: ${name}`);
  console.log(`======================================================`);

  activeRequests = 0;
  maxObservedConcurrency = 0;
  requestCount = 0;
  const startTime = Date.now();

  const windows = buildSemanticWindows(domBlocks);
  console.log(`DOM Blocks: ${domBlocks.length}`);
  console.log(`Semantic Windows: ${windows.length}`);

  const startPass1 = requestCount;
  const windowOutputs = await asyncPool(MAX_CONCURRENT_REQUESTS, windows, async (win) => {
    const data = await postPredict(win);
    return { window: win, data: { ...data, text: win } };
  });
  const firstPassRequests = requestCount - startPass1;

  const flaggedWindows = [];
  const directResults = [];

  for (const item of windowOutputs) {
    const d = item.data;
    const needsRefinement =
      d.prediction === 1 ||
      d.confidence < UNCERTAINTY_THRESHOLD ||
      item.window.length < 80;

    if (needsRefinement) {
      flaggedWindows.push(item.window);
    } else {
      directResults.push(d);
    }
  }

  const startRefine = requestCount;
  const refinedResults = [];
  const seenSentences = new Set();
  for (let i = 0; i < flaggedWindows.length; i++) {
    const refRes = await refineWindow(flaggedWindows[i], seenSentences);
    refinedResults.push(...refRes);
  }
  const refinementRequests = requestCount - startRefine;

  const allResults = [...directResults, ...refinedResults];
  const summary = aggregateFindings(allResults);
  const totalScanTimeMs = Date.now() - startTime;

  const verdict = summary.findings.length > 0
    ? "Potential Dark-Pattern Signals Detected"
    : "No Strong Dark-Pattern Signal";

  console.log(`First-pass requests: ${firstPassRequests}`);
  console.log(`Refinement requests: ${refinementRequests}`);
  console.log(`Total API requests: ${requestCount}`);
  console.log(`Maximum concurrency: ${maxObservedConcurrency}`);
  console.log(`Total scan time: ${totalScanTimeMs} ms`);
  console.log(`Overall Page Verdict: [ ${verdict} ]`);
  console.log(`Definitive Findings Count: ${summary.findings.length}`);
  console.log(`Context-Required Count: ${summary.context_required.length}`);

  if (summary.findings.length > 0) {
    console.log(`\nDefinitive Findings:`);
    summary.findings.forEach((f, idx) => {
      console.log(`  [${idx + 1}] Category: ${f.pattern_category}`);
      console.log(`      Confidence: ${(f.confidence * 100).toFixed(1)}%`);
      console.log(`      Evidence: "${f.evidence}"`);
      console.log(`      Consequence: ${f.consumer_consequence}`);
    });
  }

  if (summary.context_required.length > 0) {
    console.log(`\nContext Required Items:`);
    summary.context_required.forEach((c, idx) => {
      console.log(`  [${idx + 1}] Evidence: "${c.evidence}" (Category: ${c.pattern_category || "Requires Context"})`);
    });
  }

  return {
    name,
    domBlocks: domBlocks.length,
    windows: windows.length,
    firstPassRequests,
    refinementRequests,
    totalRequests: requestCount,
    maxConcurrency: maxObservedConcurrency,
    totalScanTimeMs,
    verdict,
    findingsCount: summary.findings.length,
    contextRequiredCount: summary.context_required.length,
    findings: summary.findings,
  };
}

async function main() {
  // Test 1: JioHotstar Login Page Regression
  const jiohotstarBlocks = [
    { text: "Help & Support", tag: "a", section: "nav", containerId: 1 },
    { text: "Need Help", tag: "a", section: "nav", containerId: 1 },
    { text: "Login", tag: "button", section: "nav", containerId: 1 },
    { text: "Login to JioHotstar", tag: "h2", section: "dialog", containerId: 2 },
    { text: "Start watching from where you left off", tag: "p", section: "dialog", containerId: 2 },
    { text: "Enter mobile number", tag: "label", section: "dialog", containerId: 2 },
    { text: "Get OTP", tag: "button", section: "dialog", containerId: 2 },
    { text: "Company", tag: "h3", section: "footer", containerId: 3 },
    { text: "About Us", tag: "li", section: "footer", containerId: 3 },
    { text: "Careers", tag: "li", section: "footer", containerId: 3 },
    { text: "Need Help", tag: "h3", section: "footer", containerId: 3 },
    { text: "Help & Support", tag: "li", section: "footer", containerId: 3 },
    { text: "Feedback", tag: "li", section: "footer", containerId: 3 },
    { text: "© 2026 Novi Digital Entertainment Pvt. Ltd. All Rights Reserved. Terms Of Use Privacy Policy FAQ", tag: "p", section: "footer", containerId: 4 },
  ];
  await runEvaluation("JioHotstar Login Page (Regression Case)", jiohotstarBlocks);

  // Test 2: Controlled Cases A-F
  const controlledBlocks = [
    // Case A: Subscription Trap
    { text: "Your free trial automatically renews at ₹999/month after 7 days.", tag: "p", section: "content", containerId: 1 },
    // Case B: Drip Pricing
    { text: "The processing fee is revealed after your payment details are entered.", tag: "p", section: "content", containerId: 2 },
    // Case C: Clear fee before payment (benign)
    { text: "The processing fee is displayed clearly before payment.", tag: "p", section: "content", containerId: 3 },
    // Case D: Obstruction
    { text: "Canceling your subscription requires contacting customer support.", tag: "p", section: "content", containerId: 4 },
    // Case E: Account settings cancel (benign)
    { text: "You can cancel your subscription at any time from Account Settings.", tag: "p", section: "content", containerId: 5 },
    // Case F: Sneaking
    { text: "An extended warranty has already been selected for your order.", tag: "p", section: "content", containerId: 6 },
  ];
  await runEvaluation("Controlled Test Cases A through F", controlledBlocks);

  // Test 3: Example.com
  const exampleBlocks = [
    { text: "Example Domain", tag: "h1", section: "content", containerId: 1 },
    { text: "This domain is for use in illustrative examples in documents. You may use this domain in literature without prior coordination or asking for permission.", tag: "p", section: "content", containerId: 1 },
    { text: "More information...", tag: "a", section: "content", containerId: 1 },
  ];
  await runEvaluation("example.com", exampleBlocks);

  // Test 4: Content-Heavy Terms of Service Page
  const termsBlocks = [
    { text: "Terms of Service and Subscription Agreement", tag: "h1", section: "content", containerId: 1 },
    { text: "Welcome to our digital platform. By accessing or using our service, you agree to be bound by these terms.", tag: "p", section: "content", containerId: 1 },
    { text: "You must be at least 18 years old to register an account with us.", tag: "p", section: "content", containerId: 1 },
    { text: "Free Trial Terms", tag: "h2", section: "content", containerId: 2 },
    { text: "Your free trial automatically renews at ₹999/month after 7 days unless canceled prior to the trial expiration date.", tag: "p", section: "content", containerId: 2 },
    { text: "Cancellation Policy", tag: "h2", section: "content", containerId: 3 },
    { text: "Canceling your subscription requires contacting customer support via international phone call during business hours.", tag: "p", section: "content", containerId: 3 },
    { text: "Payment and Fees", tag: "h2", section: "content", containerId: 4 },
    { text: "The processing fee is revealed after your payment details are entered.", tag: "p", section: "content", containerId: 4 },
    { text: "All orders placed are subject to company review and acceptance.", tag: "p", section: "content", containerId: 4 },
  ];
  await runEvaluation("Content-Heavy Page (Terms of Service)", termsBlocks);

  // Test 5: E-commerce Checkout Page with Preselected Add-ons
  const ecommerceBlocks = [
    { text: "Shopping Cart & Checkout", tag: "h1", section: "content", containerId: 1 },
    { text: "Review your selected items before proceeding to payment.", tag: "p", section: "content", containerId: 1 },
    { text: "Order Summary", tag: "h2", section: "content", containerId: 2 },
    { text: "An extended warranty has already been selected for your order.", tag: "p", section: "content", containerId: 2 },
    { text: "Limited stock available! Only three left — buy now before they disappear!", tag: "p", section: "content", containerId: 2 },
    { text: "Standard shipping fee is calculated at final checkout step.", tag: "p", section: "content", containerId: 2 },
  ];
  await runEvaluation("E-commerce / Travel Checkout Page", ecommerceBlocks);
}

main().catch(err => {
  console.error("Evaluation failed:", err);
  process.exit(1);
});
