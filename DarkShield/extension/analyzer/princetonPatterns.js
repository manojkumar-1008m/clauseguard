/**
 * Runtime Knowledge Base for Princeton Dark Patterns
 * 
 * This file exposes indexed pattern knowledge from the Princeton dark-patterns dataset.
 * It is lightweight and does not load the full JSON on every event.
 * 
 * Purpose:
 * - Provide reference pattern taxonomy for behavioral matching
 * - Enable semantic mapping between internal behavior types and Princeton categories
 * - Support confidence scoring for dataset matches
 * - Gracefully handle missing/unavailable data
 */

const PRINCETON_CATEGORIES = {
  SOCIAL_PROOF: "Social Proof",
  MISDIRECTION: "Misdirection",
  URGENCY: "Urgency",
  FORCED_ACTION: "Forced Action",
  OBSTRUCTION: "Obstruction",
  SNEAKING: "Sneaking",
  SCARCITY: "Scarcity"
};

const PRINCETON_PATTERN_TYPES = {
  ACTIVITY_NOTIFICATION: "Activity Notification",
  CONFIRMSHAMING: "Confirmshaming",
  COUNTDOWN_TIMER: "Countdown Timer",
  FORCED_ENROLLMENT: "Forced Enrollment",
  HARD_TO_CANCEL: "Hard to Cancel",
  HIDDEN_COSTS: "Hidden Costs",
  HIDDEN_SUBSCRIPTION: "Hidden Subscription",
  HIGH_DEMAND_MESSAGE: "High-demand Message",
  LIMITED_TIME_MESSAGE: "Limited-time Message",
  LOW_STOCK_MESSAGE: "Low-stock Message",
  MISDIRECTION_TYPE: "Misdirection",
  PRESSURED_SELLING: "Pressured Selling",
  SNEAK_INTO_BASKET: "Sneak into Basket",
  TESTIMONIALS: "Testimonials of Uncertain Origin",
  TRICK_QUESTIONS: "Trick Questions",
  VISUAL_INTERFERENCE: "Visual Interference"
};

/**
 * Mapping of internal behavior types to Princeton taxonomy
 * 
 * Structure:
 * BEHAVIOR_TYPE: {
 *   categories: ["Princeton Category", ...],
 *   pattern_types: ["Princeton Pattern Type", ...],
 *   confidence_factor: 0.0-1.0,
 *   explanation: "Why this behavior maps to these patterns"
 * }
 */
const BEHAVIOR_TO_PRINCETON = {
  EXCESSIVE_STEPS: {
    categories: [PRINCETON_CATEGORIES.OBSTRUCTION],
    pattern_types: [PRINCETON_PATTERN_TYPES.HARD_TO_CANCEL],
    confidence_factor: 0.88,
    explanation: "Multiple friction signals in cancellation flow match obstruction patterns like 'Hard to Cancel'."
  },

  REPEATED_PROMPTS: {
    categories: [PRINCETON_CATEGORIES.MISDIRECTION, PRINCETON_CATEGORIES.URGENCY],
    pattern_types: [
      PRINCETON_PATTERN_TYPES.PRESSURED_SELLING,
      PRINCETON_PATTERN_TYPES.HIGH_DEMAND_MESSAGE,
      PRINCETON_PATTERN_TYPES.LIMITED_TIME_MESSAGE
    ],
    confidence_factor: 0.80,
    explanation: "Repeated persuasive prompts align with patterns designed to pressure or redirect user attention."
  },

  FORCED_ACTION: {
    categories: [PRINCETON_CATEGORIES.FORCED_ACTION, PRINCETON_CATEGORIES.OBSTRUCTION],
    pattern_types: [
      PRINCETON_PATTERN_TYPES.FORCED_ENROLLMENT,
      PRINCETON_PATTERN_TYPES.SNEAK_INTO_BASKET
    ],
    confidence_factor: 0.85,
    explanation: "Forced actions detected (e.g., surveys before cancellation) match forced-action and obstruction patterns."
  },

  RETENTION_INTERFERENCE: {
    categories: [
      PRINCETON_CATEGORIES.URGENCY,
      PRINCETON_CATEGORIES.MISDIRECTION,
      PRINCETON_CATEGORIES.SCARCITY
    ],
    pattern_types: [
      PRINCETON_PATTERN_TYPES.PRESSURED_SELLING,
      PRINCETON_PATTERN_TYPES.LIMITED_TIME_MESSAGE,
      PRINCETON_PATTERN_TYPES.LOW_STOCK_MESSAGE,
      PRINCETON_PATTERN_TYPES.COUNTDOWN_TIMER
    ],
    confidence_factor: 0.82,
    explanation: "Retention offers appearing after cancellation intent often use urgency/scarcity pressure or misdirection."
  },

  DIFFICULT_CANCELLATION: {
    categories: [PRINCETON_CATEGORIES.OBSTRUCTION],
    pattern_types: [PRINCETON_PATTERN_TYPES.HARD_TO_CANCEL],
    confidence_factor: 0.90,
    explanation: "Multiple friction signals in cancellation pathway directly align with the 'Hard to Cancel' obstruction pattern."
  },

  BACKTRACKING: {
    categories: [PRINCETON_CATEGORIES.OBSTRUCTION],
    pattern_types: [PRINCETON_PATTERN_TYPES.HARD_TO_CANCEL],
    confidence_factor: 0.75,
    explanation: "Forced navigation loops during cancellation are characteristic of obstruction-based dark patterns."
  },

  OBSTRUCTION: {
    categories: [PRINCETON_CATEGORIES.OBSTRUCTION],
    pattern_types: [PRINCETON_PATTERN_TYPES.HARD_TO_CANCEL],
    confidence_factor: 0.87,
    explanation: "Unrelated steps blocking intended account actions match 'Obstruction' category patterns."
  },

  CONFIRM_SHAMING: {
    categories: [PRINCETON_CATEGORIES.MISDIRECTION],
    pattern_types: [PRINCETON_PATTERN_TYPES.CONFIRMSHAMING],
    confidence_factor: 0.94,
    explanation: "Confirm Shaming behavior directly corresponds to the Princeton 'Confirmshaming' pattern type."
  },

  FORCED_CONTINUITY: {
    categories: [PRINCETON_CATEGORIES.SNEAKING],
    pattern_types: [PRINCETON_PATTERN_TYPES.HIDDEN_SUBSCRIPTION, PRINCETON_PATTERN_TYPES.FORCED_ENROLLMENT],
    confidence_factor: 0.86,
    explanation: "Free trial followed by automatic paid enrollment patterns match 'Sneaking' and forced-enrollment patterns."
  },

  URGENCY_PRESSURE: {
    categories: [PRINCETON_CATEGORIES.URGENCY],
    pattern_types: [
      PRINCETON_PATTERN_TYPES.COUNTDOWN_TIMER,
      PRINCETON_PATTERN_TYPES.LIMITED_TIME_MESSAGE,
      PRINCETON_PATTERN_TYPES.HIGH_DEMAND_MESSAGE
    ],
    confidence_factor: 0.83,
    explanation: "Urgency signals in observed behavior directly correspond to Princeton urgency-based patterns."
  },

  SCARCITY_PRESSURE: {
    categories: [PRINCETON_CATEGORIES.SCARCITY, PRINCETON_CATEGORIES.URGENCY],
    pattern_types: [
      PRINCETON_PATTERN_TYPES.LOW_STOCK_MESSAGE,
      PRINCETON_PATTERN_TYPES.LIMITED_TIME_MESSAGE,
      PRINCETON_PATTERN_TYPES.HIGH_DEMAND_MESSAGE
    ],
    confidence_factor: 0.84,
    explanation: "Scarcity signals detected align with Princeton patterns emphasizing limited availability and time pressure."
  },

  UNCLEAR_CHOICE: {
    categories: [PRINCETON_CATEGORIES.MISDIRECTION],
    pattern_types: [PRINCETON_PATTERN_TYPES.TRICK_QUESTIONS, PRINCETON_PATTERN_TYPES.VISUAL_INTERFERENCE],
    confidence_factor: 0.76,
    explanation: "Unclear or distant choice buttons match misdirection patterns that obscure user intent."
  },

  REPEATED_RETENTION: {
    categories: [PRINCETON_CATEGORIES.OBSTRUCTION, PRINCETON_CATEGORIES.MISDIRECTION],
    pattern_types: [PRINCETON_PATTERN_TYPES.HARD_TO_CANCEL],
    confidence_factor: 0.88,
    explanation: "Multiple retention offers during single cancellation attempt align with obstruction and friction patterns."
  }
};

/**
 * Get reference patterns for a detected behavior
 * 
 * @param {string} behaviorType - Internal behavior type (e.g., "EXCESSIVE_STEPS")
 * @returns {object|null} Mapping information or null if not found
 */
function getBehaviorToPatternMapping(behaviorType) {
  return BEHAVIOR_TO_PRINCETON[behaviorType] || null;
}

/**
 * Get Princeton category name from internal enum
 * @param {string} key - The enum key (e.g., "OBSTRUCTION")
 * @returns {string} The display name (e.g., "Obstruction")
 */
function getCategoryName(key) {
  return PRINCETON_CATEGORIES[key] || null;
}

/**
 * Get Princeton pattern type name from internal enum
 * @param {string} key - The enum key (e.g., "HARD_TO_CANCEL")
 * @returns {string} The display name (e.g., "Hard to Cancel")
 */
function getPatternTypeName(key) {
  return PRINCETON_PATTERN_TYPES[key] || null;
}

/**
 * All available Princeton categories
 * @returns {object} Category constants
 */
function getCategories() {
  return { ...PRINCETON_CATEGORIES };
}

/**
 * All available Princeton pattern types
 * @returns {object} Pattern type constants
 */
function getPatternTypes() {
  return { ...PRINCETON_PATTERN_TYPES };
}

/**
 * Check if a behavior type has a known Princeton mapping
 * @param {string} behaviorType - Internal behavior type
 * @returns {boolean} True if mapping exists
 */
function hasMappingForBehavior(behaviorType) {
  return behaviorType in BEHAVIOR_TO_PRINCETON;
}

// Export for Node.js and browser environments
if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    PRINCETON_CATEGORIES,
    PRINCETON_PATTERN_TYPES,
    BEHAVIOR_TO_PRINCETON,
    getBehaviorToPatternMapping,
    getCategoryName,
    getPatternTypeName,
    getCategories,
    getPatternTypes,
    hasMappingForBehavior
  };
}

// Make available globally in browser
if (typeof window !== "undefined") {
  window.PRINCETON_KNOWLEDGE = {
    CATEGORIES: PRINCETON_CATEGORIES,
    PATTERN_TYPES: PRINCETON_PATTERN_TYPES,
    BEHAVIOR_TO_PRINCETON,
    getBehaviorToPatternMapping,
    getCategoryName,
    getPatternTypeName,
    getCategories,
    getPatternTypes,
    hasMappingForBehavior
  };
}
