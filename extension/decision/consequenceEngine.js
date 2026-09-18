/**
 * extension/decision/consequenceEngine.js
 * ClauseGuard Consequence Engine: "What happens if I continue?"
 * 
 * Provides an evidence-grounded, neutral step-by-step projection of next steps,
 * consequences, and pre-commitment advisories.
 */

(function (root) {
  "use strict";

  const TRIAL_REGEX = /\b(\d+)\s*[- ]?day\s+free\s+trial\b/i;
  const TRIAL_DAYS_REGEX = /\b(\d+)\s*[- ]?day\s+trial\b/i;

  function extractTrialInfo(text, evidence) {
    if (typeof text === "string") {
      const match = text.match(TRIAL_REGEX) || text.match(TRIAL_DAYS_REGEX);
      if (match) {
        return {
          hasTrial: true,
          duration: `${match[1]} days`,
          label: `Trial ends after ${match[1]} days`
        };
      }
    }
    const evList = Array.isArray(evidence) ? evidence : [];
    for (const item of evList) {
      const desc = String(item?.description || "").toLowerCase();
      if (desc.includes("trial")) {
        const match = desc.match(TRIAL_DAYS_REGEX) || desc.match(TRIAL_REGEX);
        if (match) {
          return {
            hasTrial: true,
            duration: `${match[1]} days`,
            label: `Trial ends after ${match[1]} days`
          };
        }
        return {
          hasTrial: true,
          duration: "trial period",
          label: "Trial ends after designated period"
        };
      }
    }
    return { hasTrial: false, duration: null, label: null };
  }

  function extractCancellationFriction(analysisData, text, session) {
    const pattern = String(analysisData?.potential_pattern || analysisData?.dark_pattern || "").toLowerCase();
    if (pattern.includes("obstruction") || pattern.includes("difficult_cancellation")) {
      return "Cancellation may require additional steps based on the interaction observed.";
    }

    const evidence = Array.isArray(analysisData?.evidence) ? analysisData.evidence : [];
    for (const item of evidence) {
      const p = String(item?.pattern || item?.type || "").toLowerCase();
      const desc = String(item?.description || "").toLowerCase();
      if (p.includes("obstruction") || desc.includes("customer support") || desc.includes("phone call") || desc.includes("requires contacting")) {
        return "Cancellation may require additional steps based on the interaction observed.";
      }
    }

    if (typeof text === "string") {
      const lower = text.toLowerCase();
      if (lower.includes("canceling your subscription requires") || lower.includes("contact support to cancel") || lower.includes("call customer service to cancel")) {
        return "Cancellation may require additional steps based on the interaction observed.";
      }
    }

    return null;
  }

  function extractPrivacyDisclosure(analysisData, text) {
    const evidence = Array.isArray(analysisData?.evidence) ? analysisData.evidence : [];
    for (const item of evidence) {
      const desc = String(item?.description || "").toLowerCase();
      if (desc.includes("third-party") || desc.includes("third parties") || desc.includes("share your data")) {
        return "Your information may be shared with third parties according to the detected privacy disclosure.";
      }
    }

    if (typeof text === "string") {
      const lower = text.toLowerCase();
      if (lower.includes("third-party") || lower.includes("third parties") || lower.includes("share your personal data")) {
        return "Your information may be shared with third parties according to the detected privacy disclosure.";
      }
    }

    return null;
  }

  function buildConsequenceFlow(analysisData, snapshot, text, session) {
    const evidence = Array.isArray(analysisData?.evidence) ? analysisData.evidence : [];
    const trialInfo = extractTrialInfo(text, evidence);
    const cost = snapshot?.cost || { detected: false, text: "" };
    const renewal = snapshot?.renewal || { detected: false, autoRenewal: false };
    const cancellationFriction = extractCancellationFriction(analysisData, text, session);
    const privacyDisclosure = extractPrivacyDisclosure(analysisData, text);

    const steps = [];
    const advisories = [];
    const evidenceSummary = [];

    // Case 1: Free Trial detected
    if (trialInfo.hasTrial) {
      steps.push("Start the free trial");
      steps.push(trialInfo.label);

      if (cost.detected && cost.amount !== null) {
        steps.push(`Subscription may begin at ${cost.text}`);
      } else if (renewal.detected) {
        steps.push("Paid subscription begins after trial");
      }

      if (renewal.autoRenewal) {
        steps.push("Automatic renewal is indicated");
      }
    }
    // Case 2: Recurring subscription / pricing detected without trial
    else if (cost.detected && renewal.detected) {
      steps.push("Proceed with subscription");
      steps.push(`Billed at ${cost.text}`);
      if (renewal.autoRenewal) {
        steps.push("Automatic renewal is indicated");
      }
    }
    // Case 3: One-time payment or general purchase with price
    else if (cost.detected && cost.amount !== null) {
      steps.push("Proceed to checkout");
      steps.push(`Charge amount indicated: ${cost.text}`);
      steps.push("Confirm payment details before completing");
    }

    // Add specific advisories based on detected evidence
    if (cancellationFriction) {
      advisories.push(cancellationFriction);
    }
    if (privacyDisclosure) {
      advisories.push(privacyDisclosure);
    }

    // Collect relevant evidence snippets for the [View evidence] action
    if (Array.isArray(analysisData?.explanation?.evidence_summary)) {
      evidenceSummary.push(...analysisData.explanation.evidence_summary);
    }
    evidence.slice(0, 5).forEach(item => {
      if (item?.description && !evidenceSummary.includes(item.description)) {
        evidenceSummary.push(item.description);
      }
    });

    // Check if we have enough information to construct a meaningful journey
    if (steps.length < 2) {
      return {
        hasFlow: false,
        fallbackMessage: "ClauseGuard does not have enough information to determine the next steps.",
        steps: [],
        advisories,
        actionAdvice: "Review checkout details and terms before confirming.",
        evidenceSummary
      };
    }

    let actionAdvice = "Before continuing, check the renewal price and cancellation terms.";
    if (!renewal.detected && !trialInfo.hasTrial) {
      actionAdvice = "Before continuing, verify the total price and payment terms.";
    }

    return {
      hasFlow: true,
      fallbackMessage: null,
      steps,
      advisories,
      actionAdvice,
      evidenceSummary
    };
  }

  const ConsequenceEngineModule = {
    extractTrialInfo,
    extractCancellationFriction,
    extractPrivacyDisclosure,
    buildConsequenceFlow
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = ConsequenceEngineModule;
  }
  root.ConsequenceEngine = ConsequenceEngineModule;
})(typeof globalThis !== "undefined" ? globalThis : this);
