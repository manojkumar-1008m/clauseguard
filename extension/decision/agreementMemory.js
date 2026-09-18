/**
 * extension/decision/agreementMemory.js
 * ClauseGuard Agreement Memory Module
 * 
 * Securely persists per-domain non-sensitive assessment records in chrome.storage.local
 * and detects meaningful contractual/pricing/privacy changes between visits.
 */

(function (root) {
  "use strict";

  const STORAGE_KEY = "clauseguard_agreement_memory";
  const MAX_HISTORY_PER_DOMAIN = 10;

  function buildMemoryRecord(domain, url, analysisData, snapshot, consequence) {
    const cost = snapshot?.cost || {};
    const renewal = snapshot?.renewal || {};
    const privacy = snapshot?.privacy || {};
    const iface = snapshot?.interface || {};

    const signals = [];
    if (iface.detected && iface.pattern) signals.push(String(iface.pattern).toUpperCase());
    if (renewal.detected && renewal.autoRenewal) signals.push("AUTO_RENEWAL");
    if (renewal.detected && !signals.includes("AUTO_RENEWAL")) signals.push("RECURRING_BILLING");
    if (privacy.detected && privacy.hasSharing) signals.push("DATA_SHARING");
    if (cost.detected) signals.push("PRICING_DISCLOSED");

    let trial = null;
    if (consequence?.steps) {
      for (const step of consequence.steps) {
        if (step.toLowerCase().includes("trial")) {
          trial = step;
          break;
        }
      }
    }

    let cancellation = null;
    if (consequence?.advisories) {
      for (const adv of consequence.advisories) {
        if (adv.toLowerCase().includes("cancellation")) {
          cancellation = adv;
          break;
        }
      }
    }

    return {
      domain: domain || "current-site",
      url: url ? String(url).split("?")[0] : null,
      analyzedAt: new Date().toISOString(),
      riskScore: typeof analysisData?.risk_score === "number" ? analysisData.risk_score : 0,
      riskLevel: analysisData?.risk_level || "LOW",
      signals,
      price: cost.detected ? cost.text : null,
      priceAmount: typeof cost.amount === "number" ? cost.amount : null,
      currency: cost.currency || null,
      period: cost.period || null,
      autoRenewal: Boolean(renewal.detected && renewal.autoRenewal),
      trial,
      cancellation,
      privacyFindings: privacy.detected ? privacy.text : null,
      termsFindings: analysisData?.explanation?.title || null
    };
  }

  function formatChangeDate(isoString) {
    if (!isoString) return "previous session";
    try {
      const d = new Date(isoString);
      return d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
    } catch {
      return "previous session";
    }
  }

  function compareWithPrevious(current, previous) {
    if (!previous || typeof previous !== "object") {
      return {
        isFirstAnalysis: true,
        hasChanged: false,
        changes: [],
        previousRecord: null,
        currentRecord: current
      };
    }

    const changes = [];

    // 1. Price comparison
    if (current.price && previous.price && current.price !== previous.price) {
      let extra = "";
      if (typeof current.priceAmount === "number" && typeof previous.priceAmount === "number") {
        const diff = current.priceAmount - previous.priceAmount;
        const symbol = current.currency || "";
        const period = current.period ? `/${current.period}` : "";
        if (diff > 0) {
          extra = `Increase: +${symbol}${diff.toFixed(2).replace(/\.00$/, "")}${period}`;
        } else if (diff < 0) {
          extra = `Decrease: -${symbol}${Math.abs(diff).toFixed(2).replace(/\.00$/, "")}${period}`;
        }
      }
      changes.push({
        type: "PRICE_CHANGED",
        title: "Price changed",
        detail: `${previous.price} → ${current.price}`,
        extra
      });
    } else if (current.price && !previous.price) {
      changes.push({
        type: "PRICE_NEW",
        title: "Price newly detected",
        detail: current.price,
        extra: ""
      });
    }

    // 2. Trial period comparison
    if (current.trial && previous.trial && current.trial !== previous.trial) {
      changes.push({
        type: "TRIAL_CHANGED",
        title: "Trial terms changed",
        detail: `${previous.trial} → ${current.trial}`,
        extra: ""
      });
    } else if (current.trial && !previous.trial) {
      changes.push({
        type: "TRIAL_NEW",
        title: "Free trial newly detected",
        detail: current.trial,
        extra: ""
      });
    }

    // 3. Auto-renewal comparison
    if (!previous.autoRenewal && current.autoRenewal) {
      changes.push({
        type: "AUTORENEWAL_NEW",
        title: "Auto-renewal newly detected",
        detail: "Automatic subscription renewal was not previously noted",
        extra: ""
      });
    }

    // 4. Recurring billing newly detected
    const prevHadRecurring = (previous.signals || []).includes("RECURRING_BILLING");
    const currHasRecurring = (current.signals || []).includes("RECURRING_BILLING");
    if (!prevHadRecurring && currHasRecurring && !current.autoRenewal) {
      changes.push({
        type: "RECURRING_NEW",
        title: "Recurring billing newly detected",
        detail: "Page now indicates ongoing subscription billing",
        extra: ""
      });
    }

    // 5. Cancellation difficulty / obstruction
    if (current.cancellation && !previous.cancellation) {
      changes.push({
        type: "CANCELLATION_CHANGED",
        title: "Cancellation information changed",
        detail: current.cancellation,
        extra: ""
      });
    }

    // 6. Privacy / data sharing newly detected
    const prevHadPrivacy = (previous.signals || []).includes("DATA_SHARING");
    const currHasPrivacy = (current.signals || []).includes("DATA_SHARING");
    if (!prevHadPrivacy && currHasPrivacy) {
      changes.push({
        type: "PRIVACY_NEW",
        title: "Data-sharing signal newly detected",
        detail: current.privacyFindings || "Third-party sharing disclosure observed",
        extra: ""
      });
    }

    // 7. Significant risk score or level shift
    const scoreDiff = (current.riskScore || 0) - (previous.riskScore || 0);
    const levelChanged = current.riskLevel && previous.riskLevel && current.riskLevel !== previous.riskLevel;
    if (Math.abs(scoreDiff) >= 1.5 || levelChanged) {
      const direction = scoreDiff > 0 ? "Increased" : "Decreased";
      changes.push({
        type: "RISK_SHIFT",
        title: "Risk level changed",
        detail: `${previous.riskLevel} (${previous.riskScore.toFixed(1)}/10) → ${current.riskLevel} (${current.riskScore.toFixed(1)}/10)`,
        extra: `${direction} by ${Math.abs(scoreDiff).toFixed(1)} points`
      });
    }

    return {
      isFirstAnalysis: false,
      hasChanged: changes.length > 0,
      changes,
      previousRecord: previous,
      currentRecord: current
    };
  }

  async function getDomainMemory(domain) {
    if (!domain || typeof chrome === "undefined" || !chrome.storage?.local) return null;
    return new Promise(resolve => {
      chrome.storage.local.get([STORAGE_KEY], result => {
        const memory = result?.[STORAGE_KEY] || {};
        resolve(memory[domain] || null);
      });
    });
  }

  async function saveDomainMemory(domain, record) {
    if (!domain || !record || typeof chrome === "undefined" || !chrome.storage?.local) return;
    return new Promise(resolve => {
      chrome.storage.local.get([STORAGE_KEY], result => {
        const memory = result?.[STORAGE_KEY] || {};
        const domainData = memory[domain] || { latest: null, history: [] };
        
        const history = Array.isArray(domainData.history) ? domainData.history : [];
        if (domainData.latest) {
          history.unshift(domainData.latest);
        }
        
        memory[domain] = {
          latest: record,
          history: history.slice(0, MAX_HISTORY_PER_DOMAIN)
        };

        chrome.storage.local.set({ [STORAGE_KEY]: memory }, () => resolve(true));
      });
    });
  }

  const AgreementMemoryModule = {
    STORAGE_KEY,
    buildMemoryRecord,
    compareWithPrevious,
    formatChangeDate,
    getDomainMemory,
    saveDomainMemory
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = AgreementMemoryModule;
  }
  root.AgreementMemory = AgreementMemoryModule;
})(typeof globalThis !== "undefined" ? globalThis : this);
