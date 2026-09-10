# Behavior Sessions Dataset

## Purpose

This dataset contains controlled behavioral sessions used to develop and evaluate the Behavior Analyzer.

These are synthetic/controlled examples and are not real user data. They contain aggregate interaction metadata only.

## Columns

- `session_id`: Unique synthetic session identifier.
- `intent`: Primary user goal, such as `CANCEL`, `SUBSCRIBE`, or `DELETE_ACCOUNT`.
- `steps`: Number of meaningful interaction steps.
- `repeated_prompts`: Count of repeated prompts or retention messages.
- `retention_offers`: Count of retention offers.
- `forced_action`: `0` or `1` indicating whether an unrelated required action appeared.
- `backtracking`: Count of meaningful backward route movements.
- `survey_required`: Whether a survey was required in the flow.
- `cancel_attempts`: Number of cancellation attempts.
- `unrelated_action`: `0` or `1` indicating an unrelated intermediate action.
- `flow_duration_seconds`: Synthetic flow duration.
- `label`: Controlled target label: `NORMAL`, `SUSPICIOUS`, or `DARK_PATTERN`.
- `dark_pattern_type`: Primary controlled taxonomy label, or `NONE`.

## Why behavioral data matters

A website may not contain an obviously suspicious button, but its interaction flow can still reveal manipulation. For example:

```text
Account
  -> Subscription
  -> Cancel
  -> Retention Offer
  -> Maybe Later
  -> Survey
  -> Confirm
  -> Cancel
```

The sequence itself provides evidence of possible obstruction or difficult cancellation.

This dataset is for prototype development and evaluation only. It is not a scientific benchmark and does not represent real users.
