// scripts/test_user_scenarios.js
// Validates the exact user scenarios A, B, C, D, E and JioHotstar against live FastAPI backend

const fs = require('fs');
const path = require('path');
const vm = require('vm');

function createMockElement(id, tagName = 'div') {
  const classes = new Set();
  const children = [];
  return {
    id, tagName: tagName.toUpperCase(), textContent: '', disabled: false,
    classList: { add: (c) => classes.add(c), remove: (c) => classes.delete(c), contains: (c) => classes.has(c) },
    get className() { return Array.from(classes).join(' '); },
    set className(val) { classes.clear(); if (val) val.split(' ').forEach((c) => classes.add(c)); },
    appendChild: (child) => { children.push(child); return child; },
    removeChild: (child) => { const idx = children.indexOf(child); if (idx >= 0) children.splice(idx, 1); return child; },
    get firstChild() { return children[0] || null; },
    get children() { return children; },
    _classes: classes,
  };
}

async function runScenario(name, domBlocks) {
  const elements = {
    analyzeBtn: createMockElement('analyzeBtn', 'button'),
    status: createMockElement('status'), result: createMockElement('result'),
    error: createMockElement('error'), icon: createMockElement('icon'),
    resultTitle: createMockElement('resultTitle', 'h2'), confidence: createMockElement('confidence', 'p'),
    modelVersion: createMockElement('modelVersion', 'p'), truncationNotice: createMockElement('truncationNotice', 'p'),
    chunksInfo: createMockElement('chunksInfo', 'p'), candidateInfo: createMockElement('candidateInfo', 'p'),
    progressInfo: createMockElement('progressInfo', 'p'), findingsList: createMockElement('findingsList'),
  };
  const listeners = {};
  const mockDocument = {
    getElementById: (id) => elements[id] || null,
    createElement: (tag) => createMockElement(undefined, tag),
    addEventListener: (event, cb) => { listeners[event] = cb; },
    body: {
      nodeType: 1,
      tagName: 'BODY',
      innerText: domBlocks.map(b => b.text).join('\n'),
      children: []
    }
  };
  elements.analyzeBtn.addEventListener = (event, cb) => { listeners['btn_' + event] = cb; };
  const mockChrome = {
    tabs: { query: async () => [{ id: 101, url: 'http://127.0.0.1:8080/test.html' }] },
    scripting: {
      executeScript: async () => [{ result: domBlocks }]
    }
  };
  const sandbox = {
    document: mockDocument, chrome: mockChrome, fetch: global.fetch,
    console, Set, Map, WeakMap, Promise, Error, JSON, Date, setTimeout,
  };
  vm.createContext(sandbox);
  const code = fs.readFileSync(path.join(__dirname, '../extension/popup.js'), 'utf-8');
  vm.runInContext(code, sandbox);
  if (listeners['DOMContentLoaded']) listeners['DOMContentLoaded']();
  await listeners['btn_click']();

  console.log(`\n========================================`);
  console.log(`SCENARIO: ${name}`);
  console.log(`========================================`);
  console.log(`Title: ${elements.resultTitle.textContent}`);
  console.log(`Confidence text: "${elements.confidence.textContent}"`);
  console.log(`Findings list child count: ${elements.findingsList.children.length}`);

  const findingCards = elements.findingsList.children.filter(c => c.className.includes('finding-item'));
  const contextNotes = elements.findingsList.children.filter(c => c.className.includes('context-note'));

  console.log(`Genuine Finding Cards: ${findingCards.length}`);
  findingCards.forEach((c, idx) => {
    const pat = c.children.find(s => s.className.includes('finding-pattern'))?.textContent || '';
    const ev = c.children.find(s => s.className.includes('finding-evidence'))?.textContent || '';
    const conf = c.children.find(s => s.className.includes('finding-confidence'))?.textContent || '';
    console.log(`  [${idx + 1}] ${pat} | ${conf} | ${ev}`);
  });

  console.log(`Context Notes: ${contextNotes.length}`);
  contextNotes.forEach(n => {
    console.log(`  Note: "${n.textContent}"`);
  });

  return {
    title: elements.resultTitle.textContent,
    findingsCount: findingCards.length,
    contextNotesCount: contextNotes.length,
    findings: findingCards.map(c => ({
      pat: c.children.find(s => s.className.includes('finding-pattern'))?.textContent || '',
      ev: c.children.find(s => s.className.includes('finding-evidence'))?.textContent || '',
    }))
  };
}

async function main() {
  // Scenario A
  const resA = await runScenario("Case A: Free trial auto-renew", [
    { text: "Your free trial automatically renews at ₹999/month after 7 days.", tag: "p", section: "content", containerId: 1 }
  ]);

  // Scenario B
  const resB = await runScenario("Case B: Clear fee before payment", [
    { text: "The processing fee is displayed clearly before payment.", tag: "p", section: "content", containerId: 1 }
  ]);

  // Scenario C
  const resC = await runScenario("Case C: Fee revealed after payment details entered", [
    { text: "The processing fee is revealed after your payment details are entered.", tag: "p", section: "content", containerId: 1 }
  ]);

  // Scenario D
  const resD = await runScenario("Case D: Help & Support", [
    { text: "Help & Support", tag: "a", section: "nav", containerId: 1 }
  ]);

  // Scenario E
  const resE = await runScenario("Case E: Buy now", [
    { text: "Buy now", tag: "button", section: "content", containerId: 1 }
  ]);

  // Scenario F: JioHotstar Login Page
  const resF = await runScenario("JioHotstar Login Page", [
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
  ]);

  console.log(`\n========================================`);
  console.log(`ALL SCENARIOS VALIDATION SUMMARY`);
  console.log(`========================================`);
  console.log(`Case A -> ${resA.findings[0]?.pat} (Expected: Subscription Trap)`);
  console.log(`Case B -> ${resB.title} (Expected: No Strong Dark-Pattern Signal)`);
  console.log(`Case C -> ${resC.findings[0]?.pat} (Expected: Drip Pricing)`);
  console.log(`Case D -> ${resD.title} (Expected: No Strong Dark-Pattern Signal, 0 findings)`);
  console.log(`Case E -> ${resE.title} (Expected: No Strong Dark-Pattern Signal, 0 findings)`);
  console.log(`JioHotstar -> ${resF.title} (Findings: ${resF.findingsCount}, Context Notes: ${resF.contextNotesCount})`);
}

main().catch(err => {
  console.error("Test failed:", err);
  process.exit(1);
});
