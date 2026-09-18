/**
 * extension/decision/decisionSnapshot.js
 * ClauseGuard Decision Snapshot Generator
 * 
 * Synthesizes page and analysis data into 4 easily scannable consumer indicators:
 * 1. Cost (💰)
 * 2. Renewal (🔄)
 * 3. Privacy (🔐)
 * 4. Interface (🎯)
 * Along with a 1-3 point pre-action checklist.
 */

(function (root) {
  "use strict";

  const PRICE_REGEX = /(?:₹|Rs\.?|INR|\$|€|£)\s*[\d,]+(?:\.\d+)?(?:\s*\/\s*(?:month|mo|year|yr|week|day|mth))?/gi;
  const TRIAL_REGEX = /\b(\d+)\s*[- ]?day\s+free\s+trial\b/i;

  function extractPrice(analysisData, text) {
    // 1. Check financial impact if available
    const fi = analysisData?.financial_impact;
    if (fi?.known_total !== null && fi?.known_total !== undefined && fi?.currency) {
      const period = fi.billing_period ? `/${fi.billing_period}` : "";
      return {
        detected: true,
        text: `${fi.currency}${fi.known_total}${period}`,
        amount: Number(fi.known_total),
        currency: fi.currency,
        period: fi.billing_period || null
      };
    }
    if (fi?.renewal_price !== null && fi?.renewal_price !== undefined && fi?.currency) {
      const period = fi.billing_period ? `/${fi.billing_period}` : "";
      return {
        detected: true,
        text: `${fi.currency}${fi.renewal_price}${period}`,
        amount: Number(fi.renewal_price),
        currency: fi.currency,
        period: fi.billing_period || null
      };
    }

    // 2. Check evidence items
    const evidence = Array.isArray(analysisData?.evidence) ? analysisData.evidence : [];
    for (const item of evidence) {
      if (item?.type === "price" || item?.type === "renewal_price" || item?.type === "monetary_entity") {
        if (item.value && item.currency) {
          return {
            detected: true,
            text: `${item.currency}${item.value}`,
            amount: typeof item.value === "number" ? item.value : parseFloat(String(item.value).replace(/[^0-9.]/g, "")),
            currency: item.currency,
            period: null
          };
        }
        if (typeof item.description === "string") {
          const match = item.description.match(PRICE_REGEX);
          if (match && match[0]) {
            return {
              detected: true,
              text: match[0].trim(),
              amount: parseFloat(match[0].replace(/[^0-9.]/g, "")),
              currency: match[0].charAt(0),
              period: match[0].includes("/") ? match[0].split("/")[1].trim() : null
            };
          }
        }
      }
    }

    // 3. Fallback scan on visible text
    if (typeof text === "string" && text.trim()) {
      const match = text.match(PRICE_REGEX);
      if (match && match[0]) {
        const cleaned = match[0].trim();
        return {
          detected: true,
          text: cleaned,
          amount: parseFloat(cleaned.replace(/[^0-9.]/g, "")),
          currency: cleaned.charAt(0),
          period: cleaned.includes("/") ? cleaned.split("/")[1].trim() : null
        };
      }
    }

    return {
      detected: false,
      text: "Cost: Not detected",
      amount: null,
      currency: null,
      period: null
    };
  }

  function extractRenewal(analysisData, text) {
    const fi = analysisData?.financial_impact;
    if (fi?.auto_renewal === true || fi?.billing_period) {
      return {
        detected: true,
        text: "Automatic renewal detected",
        autoRenewal: true
      };
    }

    const evidence = Array.isArray(analysisData?.evidence) ? analysisData.evidence : [];
    for (const item of evidence) {
      const pattern = String(item?.pattern || item?.type || "").toLowerCase();
      const desc = String(item?.description || "").toLowerCase();
      if (pattern.includes("subscription_trap") || pattern.includes("auto_renewal") || desc.includes("automatically renews") || desc.includes("auto-renew")) {
        return {
          detected: true,
          text: "Automatic renewal detected",
          autoRenewal: true
        };
      }
      if (desc.includes("recurring") || desc.includes("subscription")) {
        return {
          detected: true,
          text: "Recurring subscription detected",
          autoRenewal: false
        };
      }
    }

    if (typeof text === "string") {
      const lower = text.toLowerCase();
      if (lower.includes("automatically renews") || lower.includes("renews automatically") || lower.includes("auto-renew") || lower.includes("auto renew")) {
        return {
          detected: true,
          text: "Automatic renewal detected",
          autoRenewal: true
        };
      }
      if (lower.includes("recurring billing") || lower.includes("billed monthly") || lower.includes("billed annually") || lower.includes("per month") || lower.includes("/month")) {
        return {
          detected: true,
          text: "Recurring billing detected",
          autoRenewal: false
        };
      }
    }

    return {
      detected: false,
      text: "Renewal: Not detected",
      autoRenewal: false
    };
  }

  function extractPrivacy(analysisData, text) {
    const evidence = Array.isArray(analysisData?.evidence) ? analysisData.evidence : [];
    for (const item of evidence) {
      const pattern = String(item?.pattern || item?.type || "").toLowerCase();
      const desc = String(item?.description || "").toLowerCase();
      if (pattern.includes("privacy") || pattern.includes("tracking") || desc.includes("third-party") || desc.includes("third parties") || desc.includes("share your data") || desc.includes("partners")) {
        return {
          detected: true,
          text: "Third-party sharing mentioned",
          hasSharing: true
        };
      }
    }

    if (typeof text === "string") {
      const lower = text.toLowerCase();
      if (lower.includes("third-party") || lower.includes("third parties") || lower.includes("advertising partners") || lower.includes("share your personal data") || lower.includes("share your information")) {
        return {
          detected: true,
          text: "Third-party sharing mentioned",
          hasSharing: true
        };
      }
      if (lower.includes("privacy policy") || lower.includes("collect personal information") || lower.includes("cookies are used")) {
        return {
          detected: true,
          text: "Standard data collection disclosed",
          hasSharing: false
        };
      }
    }

    return {
      detected: false,
      text: "Privacy: No relevant signal detected",
      hasSharing: false
    };
  }

  function extractInterface(analysisData) {
    const pattern = analysisData?.potential_pattern
      || analysisData?.dark_pattern
      || analysisData?.primary_pattern
      || analysisData?.explanation?.pattern
      || null;

    if (!pattern || pattern === "none" || pattern === "standard") {
      return {
        detected: false,
        text: "Standard interface detected",
        pattern: null
      };
    }

    const norm = String(pattern).toLowerCase();
    let label = "Potentially influential design";
    if (norm.includes("social_proof")) label = "Social-proof signal detected";
    else if (norm.includes("urgency")) label = "Urgency pressure detected";
    else if (norm.includes("scarcity")) label = "Scarcity pressure detected";
    else if (norm.includes("obstruction")) label = "Obstruction pattern detected";
    else if (norm.includes("confirm_shaming")) label = "Confirm-shaming signal detected";
    else if (norm.includes("subscription_trap") || norm.includes("forced_continuity")) label = "Subscription trap signal detected";
    else if (norm.includes("drip_pricing") || norm.includes("hidden")) label = "Drip pricing signal detected";
    else if (norm.includes("sneaking")) label = "Sneaking signal detected";

    return {
      detected: true,
      text: label,
      pattern: pattern
    };
  }

  function buildChecklist(cost, renewal, privacy, iface, text) {
    const checklist = [];

    if (renewal.detected && renewal.autoRenewal) {
      checklist.push("Renewal price");
      checklist.push("Cancellation terms");
    } else if (renewal.detected) {
      checklist.push("Subscription terms");
    }

    if (privacy.detected && privacy.hasSharing) {
      checklist.push("Data-sharing information");
    }

    if (typeof text === "string" && TRIAL_REGEX.test(text)) {
      checklist.push("Trial expiration date");
    }

    if (cost.detected) {
      checklist.push("Total checkout price including taxes/fees");
    }

    if (iface.detected && iface.pattern && String(iface.pattern).toLowerCase().includes("obstruction")) {
      if (!checklist.includes("Cancellation terms")) {
        checklist.push("Cancellation terms");
      }
    }

    // Ensure 1-3 bullet points max for clarity
    const unique = Array.from(new Set(checklist));
    if (unique.length === 0) {
      return ["Final checkout amount before confirming", "Account terms & conditions"];
    }
    return unique.slice(0, 3);
  }

  function extractDecisionSnapshot(analysisData, text, session) {
    const cost = extractPrice(analysisData, text);
    const renewal = extractRenewal(analysisData, text);
    const privacy = extractPrivacy(analysisData, text);
    const iface = extractInterface(analysisData);
    const checklist = buildChecklist(cost, renewal, privacy, iface, text);

    return {
      cost,
      renewal,
      privacy,
      interface: iface,
      checklist
    };
  }

  const DecisionSnapshotModule = {
    extractPrice,
    extractRenewal,
    extractPrivacy,
    extractInterface,
    buildChecklist,
    extractDecisionSnapshot
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = DecisionSnapshotModule;
  }
  root.DecisionSnapshot = DecisionSnapshotModule;
})(typeof globalThis !== "undefined" ? globalThis : this);
