// Detection policy is kept separate from feature extraction so it can be tuned
// without changing the analyzer's core logic.
// Detection policy is kept separate from analysis logic so thresholds and
// keyword groups can be tuned without changing the analyzer's core logic.
const ANALYZER_RULES = Object.freeze({
	thresholds: Object.freeze({
		cancellationStepsMedium: 5,
		cancellationStepsHigh: 7,
		repeatedPromptsMedium: 2,
		repeatedPromptsHigh: 3,
		backtrackingMedium: 1,
		backtrackingHigh: 2,
		difficultSignalCount: 2,
		obstructionSteps: 5,
		unclearChoiceGap: 2
	}),
	weights: Object.freeze({
		EXCESSIVE_STEPS: 20,
		REPEATED_PROMPTS: 20,
		FORCED_ACTION: 25,
		DIFFICULT_CANCELLATION: 25,
		BACKTRACKING: 10,
		RETENTION_INTERFERENCE: 15,
		CONFIRM_SHAMING: 15,
		FORCED_CONTINUITY: 25,
		OBSTRUCTION: 20,
		URGENCY_PRESSURE: 10,
		SCARCITY_PRESSURE: 10,
		UNCLEAR_CHOICE: 10,
		REPEATED_RETENTION: 20
	}),
	keywords: Object.freeze({
		cancellation: Object.freeze(["cancel", "cancel subscription", "unsubscribe", "terminate", "end subscription", "stop subscription"]),
		deleteAccount: Object.freeze(["delete account", "close account", "remove account"]),
		optOut: Object.freeze(["unsubscribe", "opt out", "opt-out", "turn off"]),
		subscription: Object.freeze(["subscription", "membership", "plan", "billing"]),
		subscribe: Object.freeze(["start free trial", "subscribe", "join"]),
		purchase: Object.freeze(["buy now", "purchase", "place order", "checkout"]),
		changePlan: Object.freeze(["change plan", "switch plan", "downgrade", "upgrade plan"]),
		retention: Object.freeze(["discount", "offer", "save", "special offer", "stay", "keep", "upgrade", "deal", "30%", "50%"]),
		decline: Object.freeze(["no thanks", "maybe later", "continue cancelling", "continue", "decline", "skip", "not interested"]),
		survey: Object.freeze(["survey", "feedback", "questionnaire", "reason", "why are you leaving"]),
		confirmation: Object.freeze(["confirm", "confirm cancellation", "yes, cancel", "finish", "done"]),
		prompt: Object.freeze(["are you sure", "wait", "don't leave", "before you go", "last chance", "special offer"]),
		completion: Object.freeze(["cancellation complete", "cancelled successfully", "canceled successfully"]),
		confirmShaming: Object.freeze(["i don't want to save money", "i hate saving", "pay full price", "prefer paying more", "skip savings", "stay unprotected", "give up my discount", "keep paying more"]),
		freeTrial: Object.freeze(["free trial", "trial period", "trial starts", "7-day trial", "7 day trial"]),
		paidAfterTrial: Object.freeze(["after trial", "trial ends", "starts at ₹", "starts at $", "paid subscription", "subscription starts", "/month after"]),
		autoRenewal: Object.freeze(["automatically renews", "auto-renew", "auto renew", "charged after trial", "renews automatically"]),
		urgency: Object.freeze(["minutes left", "offer ends", "act now", "limited time", "hurry", "expires soon", "last chance", "ends today", "ends tonight"]),
		scarcity: Object.freeze(["remaining", "almost sold out", "few seats", "available", "limited stock", "limited availability"]),
		alternative: Object.freeze(["no thanks", "decline", "skip", "cancel", "manage settings", "not interested", "opt out", "continue without"]),
		primary: Object.freeze(["accept", "continue", "subscribe", "start free trial", "buy now", "upgrade", "stay", "keep"])
	}),
	categories: Object.freeze({
		PERSUASION: Object.freeze(["CONFIRM_SHAMING", "URGENCY_PRESSURE", "SCARCITY_PRESSURE", "RETENTION_INTERFERENCE", "REPEATED_RETENTION"]),
		OBSTRUCTION: Object.freeze(["EXCESSIVE_STEPS", "FORCED_ACTION", "DIFFICULT_CANCELLATION", "OBSTRUCTION", "BACKTRACKING"]),
		CHOICE: Object.freeze(["UNCLEAR_CHOICE"]),
		SUBSCRIPTION: Object.freeze(["FORCED_CONTINUITY"])
	})
});

if (typeof module !== "undefined" && module.exports) {
	module.exports = { ANALYZER_RULES };
}
