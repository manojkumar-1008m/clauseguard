const fs = require("fs");
const path = require("path");

const DATASET_PATH = path.resolve(__dirname, "../../datasets/behavior_sessions/behavior_sessions.csv");
const REQUIRED_COLUMNS = [
	"session_id", "intent", "steps", "repeated_prompts", "retention_offers", "forced_action",
	"backtracking", "survey_required", "cancel_attempts", "unrelated_action", "flow_duration_seconds",
	"label", "dark_pattern_type"
];
const NUMERIC_COLUMNS = ["steps", "repeated_prompts", "retention_offers", "forced_action", "backtracking", "cancel_attempts", "unrelated_action", "flow_duration_seconds"];
const VALID_INTENTS = new Set(["SUBSCRIBE", "CANCEL", "DELETE_ACCOUNT", "CHANGE_PLAN", "CHECKOUT", "DECLINE_OFFER"]);
const VALID_LABELS = new Set(["NORMAL", "SUSPICIOUS", "DARK_PATTERN"]);
const VALID_PATTERN_TYPES = new Set(["NONE", "REPEATED_PROMPTS", "EXCESSIVE_STEPS", "FORCED_ACTION", "RETENTION_INTERFERENCE", "DIFFICULT_CANCELLATION", "OBSTRUCTION", "BACKTRACKING"]);

function parseCsvLine(line) {
	const fields = [];
	let field = "";
	let quoted = false;
	for (let index = 0; index < line.length; index += 1) {
		const character = line[index];
		if (character === '"' && line[index + 1] === '"' && quoted) {
			field += '"';
			index += 1;
		} else if (character === '"') {
			quoted = !quoted;
		} else if (character === "," && !quoted) {
			fields.push(field);
			field = "";
		} else {
			field += character;
		}
	}
	fields.push(field);
	return fields;
}

function parseCsv(text) {
	const lines = text.replace(/^\uFEFF/, "").split(/\r?\n/).filter(line => line.trim());
	if (!lines.length) return { headers: [], rows: [] };
	const headers = parseCsvLine(lines[0]);
	const rows = lines.slice(1).map(line => {
		const values = parseCsvLine(line);
		return headers.reduce((row, header, index) => {
			row[header] = values[index] ?? "";
			return row;
		}, {});
	});
	return { headers, rows };
}

function validateDataset(filePath = DATASET_PATH) {
	const { headers, rows } = parseCsv(fs.readFileSync(filePath, "utf8"));
	const missingColumns = REQUIRED_COLUMNS.filter(column => !headers.includes(column));
	const missingValues = rows.reduce((count, row) => count + REQUIRED_COLUMNS.filter(column => !String(row[column] ?? "").trim()).length, 0);
	const invalidNumbers = [];
	const invalidEnums = [];
	const ids = new Set();
	const duplicateIds = [];
	const classCounts = { NORMAL: 0, SUSPICIOUS: 0, DARK_PATTERN: 0 };

	rows.forEach((row, index) => {
		const line = index + 2;
		if (ids.has(row.session_id)) duplicateIds.push(row.session_id);
		ids.add(row.session_id);
		if (VALID_LABELS.has(row.label)) classCounts[row.label] += 1;
		if (!VALID_INTENTS.has(row.intent)) invalidEnums.push(`line ${line}: intent ${row.intent}`);
		if (!VALID_LABELS.has(row.label)) invalidEnums.push(`line ${line}: label ${row.label}`);
		if (!VALID_PATTERN_TYPES.has(row.dark_pattern_type)) invalidEnums.push(`line ${line}: dark_pattern_type ${row.dark_pattern_type}`);
		NUMERIC_COLUMNS.forEach(column => {
			if (!/^\d+(\.\d+)?$/.test(String(row[column] || ""))) invalidNumbers.push(`line ${line}: ${column}`);
		});
	});

	const passed = missingColumns.length === 0 && rows.length > 0 && missingValues === 0
		&& invalidNumbers.length === 0 && invalidEnums.length === 0 && duplicateIds.length === 0;
	return { passed, filePath, totalSessions: rows.length, headers, rows, missingColumns, missingValues, invalidNumbers, invalidEnums, duplicateIds, classCounts };
}

function printValidation(result) {
	console.log("Dataset Validation");
	console.log(`Total sessions: ${result.totalSessions}`);
	console.log(`NORMAL: ${result.classCounts.NORMAL}`);
	console.log(`SUSPICIOUS: ${result.classCounts.SUSPICIOUS}`);
	console.log(`DARK_PATTERN: ${result.classCounts.DARK_PATTERN}`);
	console.log(`Missing values: ${result.missingValues}`);
	console.log(`Duplicate IDs: ${result.duplicateIds.length}`);
	console.log(`Validation: ${result.passed ? "PASSED" : "FAILED"}`);
	if (!result.passed) console.log({ missingColumns: result.missingColumns, invalidNumbers: result.invalidNumbers, invalidEnums: result.invalidEnums });
}

if (require.main === module) printValidation(validateDataset(process.argv[2] || DATASET_PATH));

module.exports = { parseCsv, validateDataset, printValidation, DATASET_PATH };
