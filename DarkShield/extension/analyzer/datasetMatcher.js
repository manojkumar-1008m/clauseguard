// Import Princeton knowledge base
const princetonKnowledge = typeof require === "function" ? require("./princetonPatterns.js") : null;

const PATTERN_MAPPINGS = Object.freeze({
	EXCESSIVE_STEPS: { dataset_category: "OBSTRUCTION", description: "A flow required more meaningful steps than expected." },
	REPEATED_PROMPTS: { dataset_category: "REPEATED_PROMPTS", description: "Prompts or persuasive messages appeared repeatedly." },
	FORCED_ACTION: { dataset_category: "FORCED_ACTION", description: "An additional action appeared before the intended action could be completed." },
	RETENTION_INTERFERENCE: { dataset_category: "RETENTION_INTERFERENCE", description: "A retention offer appeared after cancellation intent." },
	DIFFICULT_CANCELLATION: { dataset_category: "OBSTRUCTION", description: "Several cancellation-friction signals occurred together." },
	BACKTRACKING: { dataset_category: "OBSTRUCTION", description: "The flow returned to an earlier route or state." },
	OBSTRUCTION: { dataset_category: "OBSTRUCTION", description: "An intended account action required several unrelated steps." }
});

function numberFrom(features, camelName, snakeName) {
	const value = features?.[camelName] ?? features?.[snakeName];
	return Number.isFinite(Number(value)) ? Number(value) : 0;
}

function isTrue(features, camelName, snakeName) {
	return Boolean(features?.[camelName] ?? features?.[snakeName]);
}

/**
 * Get representative Princeton reference patterns for a behavior type.
 * Returns a limited set (1-3) of representative patterns to avoid overwhelming output.
 * 
 * @param {string} behaviorType - Internal behavior type (e.g., "EXCESSIVE_STEPS")
 * @param {number} confidence - Rule-strength confidence (0.0-1.0)
 * @returns {array} Array of match objects with Princeton reference data
 */
function getPrincetonMatches(behaviorType, confidence) {
	// Gracefully handle missing Princeton knowledge
	if (!princetonKnowledge) return [];

	const mapping = princetonKnowledge.getBehaviorToPatternMapping(behaviorType);
	if (!mapping) return [];

	// Use Princeton categories and pattern types from the mapping
	const categories = mapping.categories || [];
	const patternTypes = mapping.pattern_types || [];

	// Combine confidence: use the behavior confidence as base,
	// modulated by the mapping's confidence factor
	const referenceConfidence = Math.min(0.99, confidence * mapping.confidence_factor);

	// Return representative matches (limit to 2-3 per behavior type)
	const matches = [];
	
	// First match: primary category + first pattern type
	if (categories.length > 0 && patternTypes.length > 0) {
		matches.push({
			type: behaviorType,
			dataset_category: categories[0],
			matched_pattern_type: patternTypes[0],
			matched_pattern_string: patternTypes[0],
			confidence: referenceConfidence,
			description: mapping.explanation,
			source: "Princeton Dark Patterns at Scale",
			reference_only: true
		});
	}

	// Second match: if available, use secondary pattern type
	if (patternTypes.length > 1 && matches.length < 2) {
		matches.push({
			type: behaviorType,
			dataset_category: categories[0],
			matched_pattern_type: patternTypes[1],
			matched_pattern_string: patternTypes[1],
			confidence: Math.max(0.70, referenceConfidence - 0.08),
			description: mapping.explanation,
			source: "Princeton Dark Patterns at Scale",
			reference_only: true
		});
	}

	// Third match: if available, use secondary category
	if (categories.length > 1 && patternTypes.length > 0 && matches.length < 3) {
		matches.push({
			type: behaviorType,
			dataset_category: categories[1],
			matched_pattern_type: patternTypes[0],
			matched_pattern_string: patternTypes[0],
			confidence: Math.max(0.65, referenceConfidence - 0.12),
			description: mapping.explanation,
			source: "Princeton Dark Patterns at Scale",
			reference_only: true
		});
	}

	return matches;
}

/**
 * Provide transparent explanation for a dataset match.
 * Carefully avoids claiming Princeton data proves deception.
 * 
 * @param {object} match - A dataset match object
 * @returns {string} Explanation string
 */
function getDatasetMatchExplanation(match) {
	if (!match) return "No explanation available.";

	const { type, description, reference_only, matched_pattern_type } = match;

	if (reference_only && matched_pattern_type) {
		return `Your observed ${type?.replace(/_/g, " ").toLowerCase() || "behavior"} contains signals related to the "${matched_pattern_type}" pattern category documented in the Princeton reference dataset. This comparison is informational and based on behavioral feature analysis.`;
	}

	return description || "This behavior pattern was detected.";
}

function matchBehaviorToDataset(features = {}) {
	const matches = [];
	const cancellationSteps = numberFrom(features, "cancellationSteps", "cancellation_steps");
	const repeatedPrompts = numberFrom(features, "repeatedPromptCount", "repeated_prompts");
	const retention = features.retentionInterference || features.retention_interference;
	const retentionCount = numberFrom(retention, "count", "count");
	const backtracking = numberFrom(features, "meaningfulBacktracking", "backtracking");
	const forced = isTrue(features, "forcedActionDetected", "forced_action");
	const obstructed = isTrue(features, "obstructionDetected", "obstruction");
	const confirmShaming = isTrue(features, "confirmShamingDetected", "confirm_shaming");
	const forcedContinuityData = features.forcedContinuity;
	const urgencyPresent = (features.urgencySignals?.length || 0) > 0;
	const scarcityPresent = (features.scarcitySignals?.length || 0) > 0;
	const unclearChoice = isTrue(features, "unclearChoiceDetected", "unclear_choice");
	const repeatedRetention = isTrue(features, "repeatedRetentionDetected", "repeated_retention");

	const difficult = cancellationSteps >= 7
		|| (forced && retentionCount > 0)
		|| (repeatedPrompts >= 2 && retentionCount > 0)
		|| (backtracking > 0 && cancellationSteps >= 5);

	// Helper function to add a behavior match with Princeton reference lookups
	const addBehaviorMatch = (type, confidence) => {
		const mapping = PATTERN_MAPPINGS[type];
		const baseMatch = {
			type,
			dataset_category: mapping?.dataset_category || "UNKNOWN",
			confidence,
			description: mapping?.description || "No description available."
		};

		// Add Princeton reference matches
		const princetonMatches = getPrincetonMatches(type, confidence);
		
		// If we have Princeton reference data, use it; otherwise use base internal mapping
		if (princetonMatches.length > 0) {
			matches.push(...princetonMatches);
		} else {
			// Fallback: use internal mapping without Princeton reference
			matches.push(baseMatch);
		}
	};

	// These are transparent rule-strength values, not learned probabilities.
	// Confidence represents how strongly the observed features indicate the behavior type.
	//
	// EXCESSIVE_STEPS: Match ONLY if cancellation flow has >= 7 steps (indicating friction in the cancellation process).
	// Total page navigation steps (e.g., Home → Pricing → Products) are normal and should NOT trigger this match.
	// This prevents false positives for normal website browsing with a short cancellation flow.
	if (cancellationSteps >= 7) {
		addBehaviorMatch("EXCESSIVE_STEPS", 0.86);
	}
	if (repeatedPrompts >= 2) {
		addBehaviorMatch("REPEATED_PROMPTS", repeatedPrompts >= 3 ? 0.92 : 0.78);
	}
	if (forced) {
		addBehaviorMatch("FORCED_ACTION", 0.91);
	}
	if (retentionCount > 0) {
		addBehaviorMatch("RETENTION_INTERFERENCE", retentionCount >= 2 ? 0.94 : 0.82);
	}
	if (difficult) {
		addBehaviorMatch("DIFFICULT_CANCELLATION", 0.88);
	}
	if (backtracking > 0) {
		addBehaviorMatch("BACKTRACKING", backtracking >= 2 ? 0.9 : 0.75);
	}
	if (obstructed) {
		addBehaviorMatch("OBSTRUCTION", 0.84);
	}
	if (confirmShaming) {
		addBehaviorMatch("CONFIRM_SHAMING", 0.92);
	}
	if (forcedContinuityData?.detected) {
		addBehaviorMatch("FORCED_CONTINUITY", 0.89);
	}
	if (urgencyPresent) {
		addBehaviorMatch("URGENCY_PRESSURE", 0.80);
	}
	if (scarcityPresent) {
		addBehaviorMatch("SCARCITY_PRESSURE", 0.81);
	}
	if (unclearChoice) {
		addBehaviorMatch("UNCLEAR_CHOICE", 0.74);
	}
	if (repeatedRetention) {
		addBehaviorMatch("REPEATED_RETENTION", 0.85);
	}

	return matches;
}

function getPatternDescription(patternType) {
	return PATTERN_MAPPINGS[patternType]?.description || "No dataset taxonomy description is available for this pattern.";
}

if (typeof module !== "undefined" && module.exports) {
	module.exports = {
		matchBehaviorToDataset,
		getPatternDescription,
		getDatasetMatchExplanation,
		getPrincetonMatches,
		PATTERN_MAPPINGS
	};
}

// Make available globally in browser environment
if (typeof window !== "undefined") {
	window.datasetMatcher = {
		matchBehaviorToDataset,
		getPatternDescription,
		getDatasetMatchExplanation,
		getPrincetonMatches,
		PATTERN_MAPPINGS
	};
}
