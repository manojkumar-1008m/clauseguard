// scripts/test_pipeline_e2e.js
// Tests the exact pipeline logic from extension/popup.js against FastAPI backend

const fs = require('fs');
const path = require('path');

const MAX_CONCURRENT_REQUESTS = 5;
const WINDOW_MIN_CHARS = 500;
const WINDOW_MAX_CHARS = 1200;
const UNCERTAINTY_THRESHOLD = 0.60;
const BACKEND_MAX_LEN = 5000;

function normalizeAndDedup(text) {
  if (!text) return "";
  const lines = text.split(/\r?\n/);
  const seenCount = new Map();
  const cleaned = [];

  for (let rawLine of lines) {
    const line = rawLine.replace(/\s+/g, " ").trim();
    if (!line) continue;
    const count = seenCount.get(line) || 0;
    if (count < 2) {
      cleaned.push(line);
      seenCount.set(line, count + 1);
    }
  }
  return cleaned.join("\n");
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

function buildSemanticWindows(sentences) {
  if (!sentences || sentences.length === 0) return [];

  const totalChars = sentences.reduce((acc, s) => acc + s.length + 1, 0);
  if (totalChars < WINDOW_MIN_CHARS) {
    const singleUnit = sentences.join(" ").trim();
    return singleUnit ? [singleUnit] : [];
  }

  const windows = [];
  let currentWindow = [];
  let currentLen = 0;

  for (const sentence of sentences) {
    const sLen = sentence.length;
    if (currentLen + sLen + (currentLen > 0 ? 1 : 0) <= WINDOW_MAX_CHARS) {
      currentWindow.push(sentence);
      currentLen += sLen + (currentLen > 0 ? 1 : 0);
    } else {
      if (currentLen >= WINDOW_MIN_CHARS) {
        windows.push(currentWindow.join(" "));
        currentWindow = [sentence];
        currentLen = sLen;
      } else if (currentWindow.length === 0) {
        windows.push(sentence);
        currentWindow = [];
        currentLen = 0;
      } else {
        windows.push(currentWindow.join(" "));
        currentWindow = [sentence];
        currentLen = sLen;
      }
    }
  }

  if (currentWindow.length > 0) {
    const trailing = currentWindow.join(" ").trim();
    if (
      windows.length > 0 &&
      trailing.length < WINDOW_MIN_CHARS &&
      windows[windows.length - 1].length + 1 + trailing.length <= WINDOW_MAX_CHARS
    ) {
      windows[windows.length - 1] += " " + trailing;
    } else if (trailing.length > 0) {
      windows.push(trailing);
    }
  }

  return windows.filter((w) => w.trim().length > 0);
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

function aggregateFindings(results) {
  const findings = [];
  const contextRequired = [];
  const seenEvidence = new Set();
  const seenContext = new Set();

  for (const r of results) {
    if (!r) continue;
    const ev = (r.evidence || "").trim();

    if (r.requires_context) {
      const key = ev || (r.text || "").trim();
      if (key && !seenContext.has(key)) {
        seenContext.add(key);
        contextRequired.push({
          evidence: key,
          confidence: r.confidence || 0,
          pattern_category: null,
          consumer_consequence: r.consumer_consequence || null,
          requires_context: true,
          model_version: r.model_version,
        });
      }
    } else if (r.prediction === 1) {
      const key = ev || (r.pattern_category || "") + String(r.confidence || 0);
      if (key && !seenEvidence.has(key)) {
        seenEvidence.add(key);
        findings.push({
          pattern_category: r.pattern_category || "Potential Dark Pattern Detected",
          confidence: r.confidence || 0,
          evidence: ev || "Identified in page text",
          consumer_consequence: r.consumer_consequence || "Potential consumer detriment.",
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

async function runTest(name, rawText) {
  console.log(`\n========================================`);
  console.log(`TEST: ${name}`);
  console.log(`========================================`);
  
  activeRequests = 0;
  maxObservedConcurrency = 0;
  requestCount = 0;
  
  const startTime = Date.now();
  const extractedChars = rawText.length;
  const normalized = normalizeAndDedup(rawText);
  const sentences = splitIntoSentences(normalized);
  const windows = buildSemanticWindows(sentences);
  
  console.log(`Extracted characters: ${extractedChars}`);
  console.log(`Sentence count: ${sentences.length}`);
  console.log(`Window count: ${windows.length}`);

  const startReq = requestCount;
  // First pass
  const windowOutputs = await asyncPool(MAX_CONCURRENT_REQUESTS, windows, async (win) => {
    const data = await postPredict(win);
    return { window: win, data: { ...data, text: win } };
  });
  const firstPassRequests = requestCount - startReq;

  // Refinement identification
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

  const startRefineReq = requestCount;
  const refinedResults = [];
  const seenSentences = new Set();
  for (let i = 0; i < flaggedWindows.length; i++) {
    const refRes = await refineWindow(flaggedWindows[i], seenSentences);
    refinedResults.push(...refRes);
  }
  const refinementRequests = requestCount - startRefineReq;

  const allResults = [...directResults, ...refinedResults];
  const summary = aggregateFindings(allResults);
  const totalScanTimeMs = Date.now() - startTime;

  console.log(`First-pass requests: ${firstPassRequests}`);
  console.log(`Refinement requests: ${refinementRequests}`);
  console.log(`Total requests: ${requestCount}`);
  console.log(`Maximum observed concurrency: ${maxObservedConcurrency}`);
  console.log(`Total scan time: ${totalScanTimeMs} ms`);
  console.log(`Findings count: ${summary.findings.length}`);
  console.log(`Context-required count: ${summary.context_required.length}`);

  if (summary.findings.length > 0) {
    console.log(`\nDetected Findings:`);
    summary.findings.forEach((f, idx) => {
      console.log(`  [${idx + 1}] Pattern: ${f.pattern_category}`);
      console.log(`      Confidence: ${(f.confidence * 100).toFixed(1)}%`);
      console.log(`      Evidence: ${f.evidence}`);
      console.log(`      Consequence: ${f.consumer_consequence}`);
    });
  }

  if (summary.context_required.length > 0) {
    console.log(`\nContext Required:`);
    summary.context_required.forEach((c, idx) => {
      console.log(`  [${idx + 1}] Evidence: ${c.evidence}`);
    });
  }

  return {
    name,
    extractedChars,
    sentenceCount: sentences.length,
    windowCount: windows.length,
    firstPassRequests,
    refinementRequests,
    totalRequests: requestCount,
    maxConcurrency: maxObservedConcurrency,
    totalScanTimeMs,
    findingsCount: summary.findings.length,
    contextRequiredCount: summary.context_required.length,
  };
}

async function main() {
  // 1. Controlled test page
  const controlledHtml = fs.readFileSync(path.join(__dirname, '../tests/extension_test_page.html'), 'utf-8');
  // Strip tags for text extraction simulation
  const controlledText = controlledHtml.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
  await runTest("Controlled Test Page (tests/extension_test_page.html)", controlledText);

  // 2. Example.com
  const exampleText = "Example Domain. This domain is for use in illustrative examples in documents. You may use this domain in literature without prior coordination or asking for permission. More information...";
  await runTest("Example.com", exampleText);

  // 3. Content-heavy page (Terms of Service / E-commerce Privacy & Subscription Policy)
  const heavyParagraphs = [
    "Terms of Service and Subscription Agreement. Welcome to our online digital services.",
    "By accessing or using our service, you agree to be bound by these terms. If you do not agree, please do not use our services.",
    "Accounts and Registration. You must be at least 18 years old to register an account with us. You agree to provide true, accurate, current, and complete information about yourself during registration.",
    "Free Trial and Auto-Renewal. Your free trial automatically renews at ₹999/month after 7 days unless canceled prior to the trial expiration date.",
    "Billing and Payment. We accept credit card, debit card, and digital payment methods. The processing fee is revealed after your payment details are entered.",
    "Cancellation Policy. Canceling your subscription requires contacting customer support via international phone call during business hours.",
    "Add-on Services. An extended warranty has already been selected for your order at checkout.",
    "Limited Stock and Urgency. Only three left — buy now before they disappear! This exclusive discount is valid for today only.",
    "Return and Refund Policy. Items purchased on clearance or with promotional codes are strictly non-refundable and cannot be exchanged.",
    "Intellectual Property Rights. All materials provided through the service, including text, graphics, logos, icons, and software, are the property of the company or its content suppliers.",
    "Limitation of Liability. Under no circumstances shall our company be liable for any indirect, incidental, special, consequential, or punitive damages arising from the use of our services.",
    "Termination. We reserve the right to terminate or suspend your access to our services immediately, without prior notice or liability, for any reason whatsoever.",
    "Governing Law and Dispute Resolution. These terms shall be governed by and construed in accordance with the laws of the jurisdiction, without regard to its conflict of law provisions.",
    "Modifications. We reserve the right to modify these terms at any time. Changes will become effective immediately upon posting to the website. Your continued use of the service constitutes acceptance of the modified terms.",
    "Contact Information. If you have any questions or concerns regarding these terms of service, please reach out to our legal department via our official contact portal."
  ];
  const heavyText = heavyParagraphs.join("\n\n");
  await runTest("Content-Heavy Webpage (Terms of Service & Subscription Page)", heavyText);
}

main().catch(err => {
  console.error("Test failed:", err);
  process.exit(1);
});
