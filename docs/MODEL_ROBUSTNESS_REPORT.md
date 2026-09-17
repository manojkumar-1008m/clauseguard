# Model Robustness Report

## Active artifact
- Version: `clauseguard-text-v3`
- Artifact: `clauseguard_model_v3.joblib`
- SHA-256: `13cc0cc5884b43a0e9e8826e357cf2be5c7c8edbe9d432ca04b607c3d0e9ca95`
- Loader preference: V3, then V2/V1 fallback.
- Inference: repository preprocessing followed by calibrated model prediction; existing confidence guard and thresholds were not changed.

## Hotstar finding
The benign JioHotstar fixture produced prediction `0`, confidence `0.46`, no pattern, and no context requirement. The prior false UI signal was caused by telemetry-to-evidence conversion, not the model.

## MiniLM
MiniLM is lazy explanation/evidence ranking only. It runs after fusion and gate evaluation and cannot set risk, pattern, regulatory status, or actionability. Existing invariance tests remain green.

## Measured contrast matrix

| Case | Prediction | Confidence | Pattern | Context |
|---|---:|---:|---|---:|
| Hotstar/video | 0 | 0.200 | none | false |
| YouTube-like | 0 | 0.247 | none | false |
| Netflix-like | 0 | 0.145 | none | false |
| Sports | 0 | 0.196 | none | false |
| News | 0 | 0.169 | none | false |
| Benign e-commerce | 0 | 0.148 | none | false |
| Normal subscription | 0 | 0.150 | none | false |
| Dark subscription wording | 1 | 0.750 | Obstruction | false |
| Ambiguous marketing | 1 | 0.965 | Urgency | true |
| Benign urgency wording | 1 | 0.944 | Other | false |
| Benign scarcity wording | 0 | 0.405 | none | false |
| Benign social proof wording | 1 | 0.944 | Other | false |
| Cancellation information | 0 | 0.150 | none | true |
| Legitimate fee disclosure | 0 | 0.144 | none | false |

The benign urgency and social-proof positives demonstrate why a model output is only a signal. They still require semantic evidence, supported pattern assessment, context, fusion, and the canonical gate before any user alert.

## Vision
MobileNetV3 is exposed through `/vision/predict` and is not automatically invoked by `/analyze` or the current unified extension request path. Vision evidence remains subject to the canonical fusion/gate path.

## Remaining work
A broader external corpus matrix covering video, sports, news, e-commerce, benign subscriptions, adversarial urgency/scarcity/social-proof, and multilingual/noisy text should be run before public deployment. No retraining was performed or justified by this audit.
