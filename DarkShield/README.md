# Behavior Analyzer Demo Website

This is a small intentionally-designed website for testing a browser Behavior Analyzer.

## Behaviors intentionally included

1. Excessive cancellation steps
2. Repeated cancellation/retention prompts
3. Retention discount offer
4. Required cancellation survey
5. Multiple confirmation screens

## How to run

No server is required.

1. Extract the folder.
2. Open `index.html` in Chrome.
3. Click `My Account`.
4. Click `Cancel Subscription`.
5. Follow the cancellation flow.
6. Later, our Chrome extension will record this interaction sequence.

This is a controlled demo environment, not a real commercial website.

## Dataset Strategy

The project uses a rule-based behavior analyzer plus three complementary data roles:

- Public dark-pattern reference material supports taxonomy, terminology, examples, and rule design.
- `datasets/behavior_sessions/behavior_sessions.csv` is a synthetic controlled dataset for development and prototype evaluation.
- `datasets/ui_dark_patterns/` is reserved for future screenshot and visual-pattern data.

The Princeton reference dataset does not directly control the browser or contain the extension's click-session sequence. The live analyzer operates on current interaction metadata, while the controlled session dataset supports evaluation.

## DATA PIPELINE

```text
Website
	-> Interaction Events
	-> Behavior Logger
	-> Feature Extraction
	-> Behavior Analyzer
	-> Dataset Pattern Matcher
	-> Evidence Fusion
	-> Risk Score
	-> User Explanation
```

The dataset matcher maps extracted behavioral features to transparent taxonomy categories. It does not use machine learning or dataset keyword search, and its confidence values are rule-strength indicators rather than learned probabilities.

## Dataset Tools

Run these commands from the project root:

```powershell
node extension/analyzer/datasetValidator.js
node extension/analyzer/datasetEvaluator.js
node extension/analyzer/test.js
```

The evaluator reports prototype metrics on the controlled synthetic dataset. These metrics are not a scientific benchmark.
