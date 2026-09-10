const {analyzeBehavior} = require('./extension/analyzer/analyzer.js');

console.log('\n=== VERIFICATION TESTS ===\n');

// TEST 1: Normal navigation should have NO dataset matches
console.log('TEST 1: Normal Long Navigation (8 total steps, 2 cancellation steps)');
let result = analyzeBehavior([
  {timestamp: '1', action: 'CLICK', element: 'BUTTON', text: 'Home', url: '#home'},
  {timestamp: '2', action: 'NAVIGATION', element: 'document', text: '', url: '#home'},
  {timestamp: '3', action: 'CLICK', element: 'BUTTON', text: 'Pricing', url: '#pricing'},
  {timestamp: '4', action: 'NAVIGATION', element: 'document', text: '', url: '#pricing'},
  {timestamp: '5', action: 'CLICK', element: 'BUTTON', text: 'Products', url: '#products'},
  {timestamp: '6', action: 'NAVIGATION', element: 'document', text: '', url: '#products'},
  {timestamp: '7', action: 'CLICK', element: 'BUTTON', text: 'Product Details', url: '#details'},
  {timestamp: '8', action: 'NAVIGATION', element: 'document', text: '', url: '#details'},
  {timestamp: '9', action: 'CLICK', element: 'BUTTON', text: 'Account', url: '#account'},
  {timestamp: '10', action: 'NAVIGATION', element: 'document', text: '', url: '#account'},
  {timestamp: '11', action: 'CLICK', element: 'BUTTON', text: 'Subscription', url: '#subscription'},
  {timestamp: '12', action: 'NAVIGATION', element: 'document', text: '', url: '#subscription'},
  {timestamp: '13', action: 'CLICK', element: 'BUTTON', text: 'Cancel Subscription', url: '#cancel'},
  {timestamp: '14', action: 'NAVIGATION', element: 'document', text: '', url: '#cancel'},
  {timestamp: '15', action: 'CLICK', element: 'BUTTON', text: 'Confirm Cancellation', url: '#confirm'}
]);
console.log('  Total steps:', result.features.totalSteps);
console.log('  Cancellation steps:', result.features.cancellationSteps);
console.log('  Behaviors detected:', result.behaviors.length);
console.log('  Dataset matches:', result.dataset_matches.length);
console.log('  RESULT:', result.behaviors.length === 0 && result.dataset_matches.length === 0 ? '✓ PASS' : '✗ FAIL');
console.log();

// TEST 2: Simple one-event cancellation should have NO matches
console.log('TEST 2: Simple One-Event Cancellation');
result = analyzeBehavior([
  {timestamp: '1', action: 'CLICK', element: 'BUTTON', text: 'Cancel', url: '#cancel'}
]);
console.log('  Total steps:', result.features.totalSteps);
console.log('  Cancellation steps:', result.features.cancellationSteps);
console.log('  Behaviors detected:', result.behaviors.length);
console.log('  Dataset matches:', result.dataset_matches.length);
console.log('  RESULT:', result.behaviors.length === 0 && result.dataset_matches.length === 0 ? '✓ PASS' : '✗ FAIL');
console.log();

// TEST 3: Excessive steps (7+) should trigger EXCESSIVE_STEPS behavior and dataset match
console.log('TEST 3: Excessive Cancellation Steps (7+ cancellation steps)');
result = analyzeBehavior([
  {timestamp: '1', action: 'CLICK', element: 'BUTTON', text: 'Cancel', url: '#cancel'},
  {timestamp: '2', action: 'NAVIGATION', element: 'document', text: '', url: '#cancel'},
  {timestamp: '3', action: 'CLICK', element: 'BUTTON', text: 'Offer', url: '#offer'},
  {timestamp: '4', action: 'NAVIGATION', element: 'document', text: '', url: '#offer'},
  {timestamp: '5', action: 'CLICK', element: 'BUTTON', text: 'Decline', url: '#decline'},
  {timestamp: '6', action: 'NAVIGATION', element: 'document', text: '', url: '#decline'},
  {timestamp: '7', action: 'CLICK', element: 'BUTTON', text: 'Help', url: '#help'},
  {timestamp: '8', action: 'NAVIGATION', element: 'document', text: '', url: '#help'},
  {timestamp: '9', action: 'CLICK', element: 'BUTTON', text: 'FAQ', url: '#faq'},
  {timestamp: '10', action: 'NAVIGATION', element: 'document', text: '', url: '#faq'},
  {timestamp: '11', action: 'CLICK', element: 'BUTTON', text: 'Confirm', url: '#confirm'}
]);
console.log('  Total steps:', result.features.totalSteps);
console.log('  Cancellation steps:', result.features.cancellationSteps);
console.log('  Behaviors detected:', result.behaviors.length);
console.log('  Dataset matches:', result.dataset_matches.length);
let hasExcessiveInBehaviors = result.behaviors.some(b => b.type === 'EXCESSIVE_STEPS');
let hasExcessiveInMatches = result.dataset_matches.some(m => m.type === 'EXCESSIVE_STEPS');
console.log('  Has EXCESSIVE_STEPS behavior:', hasExcessiveInBehaviors);
console.log('  Has EXCESSIVE_STEPS dataset match:', hasExcessiveInMatches);
console.log('  RESULT:', (hasExcessiveInBehaviors || hasExcessiveInMatches) ? '✓ PASS' : '✗ FAIL');
console.log();

console.log('=== ALL TESTS COMPLETE ===\n');
