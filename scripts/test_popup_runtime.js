// scripts/test_popup_runtime.js
// Unit/Integration test for popup.js runtime execution in a simulated DOM

const fs = require('fs');
const path = require('path');
const vm = require('vm');

function createMockElement(id, tagName = 'div') {
  const classes = new Set();
  const children = [];
  const elementListeners = {};
  return {
    id,
    tagName: tagName.toUpperCase(),
    textContent: '',
    disabled: false,
    classList: {
      add: (c) => classes.add(c),
      remove: (c) => classes.delete(c),
      contains: (c) => classes.has(c),
    },
    get className() {
      return Array.from(classes).join(' ');
    },
    set className(val) {
      classes.clear();
      if (val) val.split(' ').forEach((c) => classes.add(c));
    },
    appendChild: (child) => {
      children.push(child);
      return child;
    },
    removeChild: (child) => {
      const idx = children.indexOf(child);
      if (idx >= 0) children.splice(idx, 1);
      return child;
    },
    addEventListener: (event, callback) => {
      elementListeners[event] = callback;
    },
    get firstChild() {
      return children[0] || null;
    },
    get children() {
      return children;
    },
    _classes: classes,
    _listeners: elementListeners,
  };
}

async function testPopupRuntime() {
  console.log("Starting popup.js runtime simulation test...");

  const elements = {
    analyzeBtn: createMockElement('analyzeBtn', 'button'),
    status: createMockElement('status'),
    result: createMockElement('result'),
    error: createMockElement('error'),
    icon: createMockElement('icon'),
    resultTitle: createMockElement('resultTitle', 'h2'),
    confidence: createMockElement('confidence', 'p'),
    modelVersion: createMockElement('modelVersion', 'p'),
    truncationNotice: createMockElement('truncationNotice', 'p'),
    chunksInfo: createMockElement('chunksInfo', 'p'),
    candidateInfo: createMockElement('candidateInfo', 'p'),
    progressInfo: createMockElement('progressInfo', 'p'),
    findingsList: createMockElement('findingsList'),
    statusText: createMockElement('statusText', 'p'),
    errorMsg: createMockElement('errorMsg', 'p'),
    retryBtn: createMockElement('retryBtn', 'button'),
    riskBadge: createMockElement('riskBadge', 'span'),
    resultSummary: createMockElement('resultSummary', 'p'),
    consumerConsequenceSection: createMockElement('consumerConsequenceSection'),
    consumerConsequence: createMockElement('consumerConsequence', 'p'),
    financialImpactSection: createMockElement('financialImpactSection'),
    financialConsequence: createMockElement('financialConsequence', 'p'),
    financialMetrics: createMockElement('financialMetrics'),
    recommendedActionSection: createMockElement('recommendedActionSection'),
    recommendedAction: createMockElement('recommendedAction', 'p'),
    evidenceSection: createMockElement('evidenceSection'),
    evidenceToggle: createMockElement('evidenceToggle', 'button'),
    evidenceContent: createMockElement('evidenceContent'),
    evidenceList: createMockElement('evidenceList'),
    additionalFindingsSection: createMockElement('additionalFindingsSection'),
    additionalFindingsToggle: createMockElement('additionalFindingsToggle', 'button'),
    additionalFindingsCount: createMockElement('additionalFindingsCount', 'span'),
    additionalFindingsContent: createMockElement('additionalFindingsContent'),
    additionalFindingsList: createMockElement('additionalFindingsList'),
    disclaimer: createMockElement('disclaimer', 'p'),
  };

  const listeners = {};

  const mockDocument = {
    getElementById: (id) => elements[id] || null,
    createElement: (tag) => createMockElement(undefined, tag),
    addEventListener: (event, cb) => {
      listeners[event] = cb;
    },
    body: {
      innerText: `
        Your free trial automatically renews at ₹999/month after 7 days.
        The processing fee is revealed after your payment details are entered.
        You can cancel your subscription at any time from Account Settings.
        Canceling your subscription requires contacting customer support.
        An extended warranty has already been selected for your order.
        Only three left — buy now before they disappear!
        Only three colors are currently available.
        Buy now
      `
    }
  };

  elements.analyzeBtn.addEventListener = (event, cb) => {
    listeners['btn_' + event] = cb;
  };

  const mockChrome = {
    storage: {
      local: {
        get: (defaults, callback) => callback(defaults),
      },
    },
    tabs: {
      query: async () => [{ id: 101, url: 'http://127.0.0.1:8080/tests/extension_test_page.html' }]
    },
    scripting: {
      executeScript: async ({ target, func }) => {
        return [{
          result: {
            text: mockDocument.body.innerText,
            title: 'ClauseGuard integration fixture',
            url: 'http://127.0.0.1:8000/tests/extension_test_page.html',
            truncated: false,
          },
        }];
      }
    }
  };

  // Build sandboxed context
  const sandbox = {
    document: mockDocument,
    chrome: mockChrome,
    fetch: (...args) => global.fetch(...args),
    console: console,
    Set: Set,
    Map: Map,
    Promise: Promise,
    Error: Error,
    JSON: JSON,
    Date: Date,
    AbortController: AbortController,
    setTimeout: setTimeout,
    clearTimeout: clearTimeout,
  };

  vm.createContext(sandbox);

  const code = fs.readFileSync(path.join(__dirname, '../extension/popup.js'), 'utf-8');
  vm.runInContext(code, sandbox);

  // Trigger DOMContentLoaded
  if (listeners['DOMContentLoaded']) {
    listeners['DOMContentLoaded']();
  }

  console.log("Initial state: analyzeBtn disabled?", elements.analyzeBtn.disabled);
  if (elements.analyzeBtn.disabled) {
    throw new Error("analyzeBtn should be enabled in idle state");
  }

  // Trigger Analyze click
  console.log("Triggering Analyze This Page click...");
  if (!listeners['btn_click']) {
    throw new Error("No click listener registered on analyzeBtn");
  }

  await listeners['btn_click']();
  const waitDeadline = Date.now() + 30000;
  while (
    elements.result._classes.has('hidden') &&
    elements.error._classes.has('hidden') &&
    Date.now() < waitDeadline
  ) {
    await new Promise(resolve => setTimeout(resolve, 250));
  }

  console.log("\n=== POST-ANALYSIS VERIFICATION ===");
  console.log("Result card visible?", !elements.result._classes.has('hidden'));
  console.log("Error card visible?", !elements.error._classes.has('hidden'));
  console.log("Error text:", elements.error.textContent);
  console.log("Result title:", elements.resultTitle.textContent);
  console.log("Confidence:", elements.confidence.textContent);
  console.log("Model Version:", elements.modelVersion.textContent);
  console.log("Chunks Info:", elements.chunksInfo.textContent);
  console.log("Findings count:", elements.findingsList.children.length);

  // Check assertions
  if (elements.result._classes.has('hidden')) {
    throw new Error("Result card should be visible after analysis");
  }
  if (!elements.error._classes.has('hidden')) {
    throw new Error("Error card should be hidden when analysis succeeds: " + elements.error.textContent);
  }
  if (!elements.resultTitle.textContent) {
    throw new Error("Unexpected result title: " + elements.resultTitle.textContent);
  }
  if (!elements.modelVersion.textContent.includes("clauseguard-text-v3")) {
    throw new Error("Unexpected model version: " + elements.modelVersion.textContent);
  }

  console.log("\nChild elements in findingsList:");
  elements.findingsList.children.forEach((c, idx) => {
    console.log(`  Item ${idx + 1} (${c.className}):`);
    c.children.forEach(sub => {
      console.log(`    ${sub.className}: ${sub.textContent}`);
    });
  });

  console.log("\nSUCCESS: All runtime DOM interactions and assertions passed!");
}

testPopupRuntime().catch(err => {
  console.error("Runtime test failed:", err);
  process.exit(1);
});
