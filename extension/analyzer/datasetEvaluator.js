const fs = require("fs");
const { analyzeBehavior } = require("./analyzer.js");
const { parseCsv, validateDataset, DATASET_PATH } = require("./datasetValidator.js");

function event(text, route) {
	return { action: "CLICK", element: "BUTTON", text, url: `http://dataset.local/${route}` };
}

function sessionToEvents(row) {
	const events = [];
	const intentText = { CANCEL: "Cancel Subscription", DELETE_ACCOUNT: "Delete Account", SUBSCRIBE: "Start Free Trial", CHANGE_PLAN: "Change Plan", CHECKOUT: "Buy Now", DECLINE_OFFER: "No Thanks" };
	const route = row.intent.toLowerCase();
	events.push(event(intentText[row.intent] || row.intent, `#${route}`));
	const steps = Math.max(1, Number(row.steps));
	const repeated = Number(row.repeated_prompts);
	const offers = Number(row.retention_offers);
	for (let index = 1; index < steps; index += 1) {
		let text = "Continue";
		let stepRoute = `#${route}`;
		if (index <= offers) { text = "Discount Offer"; stepRoute = "#offer"; }
		else if (index <= offers + repeated) { text = "Are you sure?"; stepRoute = "#prompt"; }
		else if (row.survey_required === "true" && index === steps - 2) { text = "Cancellation Survey"; stepRoute = "#survey"; }
		else if (Number(row.unrelated_action) === 1 && index === 1) { text = "Help"; stepRoute = "#help"; }
		else if (index === steps - 1) { text = "Confirm"; stepRoute = "#confirm"; }
		events.push(event(text, stepRoute));
	}
	return events;
}

function predictedLabel(result) {
	if (result.riskScore >= 60) return "DARK_PATTERN";
	if (result.riskScore >= 15 || result.behaviors.length > 0) return "SUSPICIOUS";
	return "NORMAL";
}

function evaluateDataset(filePath = DATASET_PATH) {
	const validation = validateDataset(filePath);
	if (!validation.passed) throw new Error("Dataset validation failed before evaluation.");
	const rows = parseCsv(fs.readFileSync(filePath, "utf8")).rows;
	const confusionMatrix = { NORMAL: { NORMAL: 0, SUSPICIOUS: 0, DARK_PATTERN: 0 }, SUSPICIOUS: { NORMAL: 0, SUSPICIOUS: 0, DARK_PATTERN: 0 }, DARK_PATTERN: { NORMAL: 0, SUSPICIOUS: 0, DARK_PATTERN: 0 } };
	let correct = 0;
	rows.forEach(row => {
		const originalLog = console.log;
		console.log = () => {};
		const result = analyzeBehavior(sessionToEvents(row));
		console.log = originalLog;
		const prediction = predictedLabel(result);
		confusionMatrix[row.label][prediction] += 1;
		if (prediction === row.label) correct += 1;
	});
	const total = rows.length;
	const truePositive = confusionMatrix.DARK_PATTERN.DARK_PATTERN;
	const falsePositive = confusionMatrix.NORMAL.DARK_PATTERN + confusionMatrix.SUSPICIOUS.DARK_PATTERN;
	const falseNegative = confusionMatrix.DARK_PATTERN.NORMAL + confusionMatrix.DARK_PATTERN.SUSPICIOUS;
	const precision = truePositive / (truePositive + falsePositive || 1);
	const recall = truePositive / (truePositive + falseNegative || 1);
	const f1 = (2 * precision * recall) / (precision + recall || 1);
	return { total, accuracy: correct / total, precision, recall, f1, confusionMatrix };
}

if (require.main === module) {
	const result = evaluateDataset(process.argv[2] || DATASET_PATH);
	console.log("Prototype evaluation on controlled synthetic dataset");
	console.log(`Accuracy: ${(result.accuracy * 100).toFixed(2)}%`);
	console.log(`Precision: ${(result.precision * 100).toFixed(2)}%`);
	console.log(`Recall: ${(result.recall * 100).toFixed(2)}%`);
	console.log(`F1-score: ${(result.f1 * 100).toFixed(2)}%`);
	console.log("Confusion matrix:", result.confusionMatrix);
}

module.exports = { evaluateDataset, sessionToEvents, predictedLabel };
