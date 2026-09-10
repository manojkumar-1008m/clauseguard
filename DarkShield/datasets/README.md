# Dataset Strategy

## 1. Public Dark-Pattern Data

**Princeton Dark Patterns at Scale** provides taxonomy, examples, terminology, and a research reference for rule development and comparison. It is not a live browser event stream and does not directly control the extension.

## 2. Behavior Session Data

`behavior_sessions/behavior_sessions.csv` is a synthetic, controlled dataset created for Behavior Analyzer development and evaluation. It describes interaction-sequence features and labels, rather than real users.

## 3. UI Dark-Pattern Data

`ui_dark_patterns/` is reserved for a future visual dataset. Screenshot-oriented data can support detection of visual hierarchy, misdirection, and choice-presentation patterns that click sequences alone cannot determine.

Public datasets and the controlled behavior-session dataset serve different purposes: public data supports taxonomy and reference, while our session data supports feature-based rule development and prototype evaluation.

## Role in the system

The live pipeline is:

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

The public dataset does not control the user's browser. The live analyzer operates on current website behavior; dataset materials provide reference terminology, taxonomy mappings, and controlled evaluation data.
