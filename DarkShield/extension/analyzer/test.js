const analyze = typeof module !== "undefined" && module.exports
  ? require("./analyzer.js").analyzeBehavior
  : (typeof analyzeBehavior === "function" ? analyzeBehavior : window.analyzeBehavior);

const getDatasetMatchExplanation = typeof module !== "undefined" && module.exports
  ? require("./datasetMatcher.js").getDatasetMatchExplanation
  : (typeof getDatasetMatchExplanation === "function" ? getDatasetMatchExplanation : () => "");

function createEvent(text, hash) {
  return {
    timestamp: new Date().toISOString(),
    action: "CLICK",
    element: "BUTTON",
    text,
    url: `http://127.0.0.1:5500/${hash}`
  };
}

function createNavigation(hash) {
  return {
    timestamp: new Date().toISOString(),
    action: "NAVIGATION",
    element: "document",
    text: "",
    url: `http://127.0.0.1:5500/${hash}`
  };
}

function printScenario(name, events) {
  console.log(`\n==============================\n${name}\n==============================`);
  const result = analyze(events);
  
  console.log("Core Analysis Results:");
  console.log(JSON.stringify({
    riskScore: result.riskScore,
    overallSeverity: result.overallSeverity,
    summary: result.summary,
    whatHappened: result.whatHappened,
    whyThisMatters: result.whyThisMatters
  }, null, 2));
  
  console.log("\nDetected Behaviors:");
  if (result.behaviors && result.behaviors.length > 0) {
    result.behaviors.forEach(behavior => {
      console.log(`  - ${behavior.type}: ${behavior.description}`);
    });
  } else {
    console.log("  (none)");
  }
  
  console.log("\nDataset Matches (Princeton Reference):");
  if (result.dataset_matches && result.dataset_matches.length > 0) {
    result.dataset_matches.forEach((match, idx) => {
      console.log(`  [${idx + 1}] ${match.type} → ${match.matched_pattern_type}`);
      console.log(`      Confidence: ${match.confidence}`);
      console.log(`      Category: ${match.dataset_category}`);
      if (typeof getDatasetMatchExplanation === "function") {
        const explanation = getDatasetMatchExplanation(match);
        if (explanation) console.log(`      Explanation: ${explanation}`);
      }
    });
  } else {
    console.log("  (no reference patterns matched)");
  }
  
  console.log("\nFeatures:");
  console.log(JSON.stringify(result.features, null, 2));
}

printScenario("1. NORMAL CANCELLATION", [
  createEvent("Account", "#account"),
  createNavigation("#account"),
  createEvent("Subscription", "#subscription"),
  createNavigation("#subscription"),
  createEvent("Cancel Subscription", "#cancel")
]);

printScenario("2. EXCESSIVE STEPS (Obstruction)", [
  createEvent("Delete Account", "#account"),
  createNavigation("#account"),
  createEvent("Help", "#help"),
  createNavigation("#help"),
  createEvent("FAQ", "#faq"),
  createNavigation("#faq"),
  createEvent("Contact", "#contact"),
  createNavigation("#contact"),
  createEvent("Request", "#request"),
  createNavigation("#request"),
  createEvent("Confirm", "#confirm")
]);

printScenario("3. REPEATED PROMPTS (Nagging)", [
  createEvent("Cancel Subscription", "#cancel"),
  createNavigation("#cancel"),
  createEvent("Discount Offer", "#offer"),
  createNavigation("#offer"),
  createEvent("No Thanks", "#skip"),
  createNavigation("#skip"),
  createEvent("Another Discount", "#offer2"),
  createNavigation("#offer2"),
  createEvent("No Thanks", "#skip2"),
  createNavigation("#skip2"),
  createEvent("Wait, Last Chance!", "#offer3"),
  createNavigation("#offer3"),
  createEvent("No Thanks", "#skip3")
]);

printScenario("4. FORCED ACTION", [
  createEvent("Cancel Subscription", "#cancel"),
  createNavigation("#cancel"),
  createEvent("Survey (Required)", "#survey"),
  createNavigation("#survey"),
  createEvent("Submit Survey", "#submit"),
  createNavigation("#submit"),
  createEvent("Confirm Cancellation", "#confirm")
]);

printScenario("5. RETENTION INTERFERENCE", [
  createEvent("Cancel Subscription", "#cancel"),
  createNavigation("#cancel"),
  createEvent("Are you sure?", "#warning"),
  createNavigation("#warning"),
  createEvent("Offer: 50% Off", "#offer"),
  createNavigation("#offer"),
  createEvent("No, Cancel Anyway", "#cancel2"),
  createNavigation("#cancel2"),
  createEvent("Another Offer Appeared", "#offer2"),
  createNavigation("#offer2"),
  createEvent("Confirm Cancellation", "#confirm")
]);

printScenario("6. DIFFICULT CANCELLATION (Combined Obstruction)", [
  createEvent("Cancel Subscription", "#cancel"),
  createNavigation("#cancel"),
  createEvent("Discount Offer", "#offer"),
  createNavigation("#offer"),
  createEvent("No Thanks", "#skip"),
  createNavigation("#skip"),
  createEvent("Help", "#help"),
  createNavigation("#help"),
  createEvent("FAQ", "#faq"),
  createNavigation("#faq"),
  createEvent("Back to Cancellation", "#cancel2"),
  createNavigation("#cancel2"),
  createEvent("Confirm", "#confirm")
]);

printScenario("7. BACKTRACKING", [
  createEvent("Account", "#account"),
  createNavigation("#account"),
  createEvent("Cancel Subscription", "#cancel"),
  createNavigation("#cancel"),
  createEvent("Discount Offer", "#offer"),
  createNavigation("#offer"),
  createEvent("Back to Cancellation", "#cancel"),
  createNavigation("#cancel"),
  createEvent("Discount Offer Again", "#offer"),
  createNavigation("#offer"),
  createEvent("Back to Cancellation", "#cancel"),
  createNavigation("#cancel"),
  createEvent("Confirm Cancellation", "#confirm")
]);

printScenario("8. CONFIRM SHAMING", [
  createEvent("Cancel", "#cancel"),
  createNavigation("#cancel"),
  createEvent("No, I want to keep paying", "#shame"),
  createNavigation("#shame"),
  createEvent("Confirm Cancellation", "#confirm")
]);

printScenario("9. URGENCY PRESSURE", [
  createEvent("View Product", "#product"),
  createNavigation("#product"),
  createEvent("Only 10 minutes left!", "#timer"),
  createNavigation("#timer"),
  createEvent("Limited offer", "#urgency"),
  createNavigation("#urgency"),
  createEvent("Buy Now", "#checkout")
]);

printScenario("10. SCARCITY PRESSURE", [
  createEvent("View Product", "#product"),
  createNavigation("#product"),
  createEvent("Only 2 left in stock", "#scarcity"),
  createNavigation("#scarcity"),
  createEvent("Last one available", "#scarcity2"),
  createNavigation("#scarcity2"),
  createEvent("Buy Now", "#checkout")
]);

printScenario("11. FORCED CONTINUITY (Free Trial)", [
  createEvent("Start Free Trial", "#trial"),
  createNavigation("#trial"),
  createEvent("7-day free trial", "#offer"),
  createNavigation("#offer"),
  createEvent("₹999/month after trial", "#price"),
  createNavigation("#price"),
  createEvent("Automatically renews", "#auto"),
  createNavigation("#auto"),
  createEvent("Sign Up", "#signup")
]);

printScenario("12. UNCLEAR CHOICE", [
  createEvent("Start Free Trial", "#home"),
  createNavigation("#home"),
  createEvent("Learn More", "#details"),
  createNavigation("#details"),
  createEvent("See Pricing", "#pricing"),
  createNavigation("#pricing"),
  createEvent("No Thanks", "#decline")
]);

printScenario("13. REPEATED RETENTION (Subscription Resistance)", [
  createEvent("Cancel Subscription", "#cancel"),
  createNavigation("#cancel"),
  createEvent("Discount 10%", "#offer1"),
  createNavigation("#offer1"),
  createEvent("No Thanks", "#decline1"),
  createNavigation("#decline1"),
  createEvent("Discount 20%", "#offer2"),
  createNavigation("#offer2"),
  createEvent("No Thanks", "#decline2"),
  createNavigation("#decline2"),
  createEvent("Discount 50%", "#offer3"),
  createNavigation("#offer3"),
  createEvent("No Thanks", "#decline3"),
  createNavigation("#decline3"),
  createEvent("Confirm Cancellation", "#confirm")
]);

printScenario("14. NORMAL LONG NAVIGATION (No Dark Pattern)", [
  createEvent("Home", "#home"),
  createNavigation("#home"),
  createEvent("Pricing", "#pricing"),
  createNavigation("#pricing"),
  createEvent("Products", "#products"),
  createNavigation("#products"),
  createEvent("Product Details", "#product-details"),
  createNavigation("#product-details"),
  createEvent("Account", "#account"),
  createNavigation("#account"),
  createEvent("Subscription", "#subscription"),
  createNavigation("#subscription"),
  createEvent("Cancel Subscription", "#cancel"),
  createNavigation("#cancel"),
  createEvent("Confirm Cancellation", "#confirm")
]);

console.log("\n\n========== TEST SUITE COMPLETE ==========");
