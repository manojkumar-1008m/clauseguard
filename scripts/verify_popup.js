const fs = require('fs');
const path = require('path');

const code = fs.readFileSync(path.join(__dirname, '../extension/popup.js'), 'utf-8');

const requiredFns = [
  'setIdleState',
  'setAnalyzingState',
  'setErrorState',
  'validateResponse',
  'asyncPool',
  'extractVisibleText',
  'normalizeAndDedup',
  'splitIntoSentences',
  'buildSemanticWindows',
  'refineWindow',
  'analyzeText',
  'aggregateFindings',
  'setResultState',
];

console.log('--- Checking Function Definitions ---');
let allExactlyOne = true;
for (const fn of requiredFns) {
  const regex = new RegExp(`(function\\s+${fn}\\b|const\\s+${fn}\\s*=\\s*\\()`, 'g');
  const matches = code.match(regex) || [];
  console.log(`${fn}: ${matches.length}`);
  if (matches.length !== 1) {
    allExactlyOne = false;
  }
}

const addEventListenerMatches = code.match(/analyzeBtn\.addEventListener/g) || [];
console.log(`analyzeBtn.addEventListener: ${addEventListenerMatches.length}`);

const keywordsCheck = ['CANDIDATE_KEYWORDS', 'MAX_CANDIDATES', 'REQUIRED_PATTERNS'];
for (const kw of keywordsCheck) {
  console.log(`Contains ${kw}: ${code.includes(kw)}`);
}

console.log(`All functions defined exactly once: ${allExactlyOne}`);
