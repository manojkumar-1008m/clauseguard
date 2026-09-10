# Dark-Pattern Reference Data

This folder contains documentation and reference datasets for dark-pattern detection. Large public datasets are intentionally kept outside the Chrome extension package.

## Overview

Dark patterns are used to guide users toward actions they may not want to take. This folder contains:

- **princeton/**: Reference datasets from the Princeton "Dark Patterns at Scale" study
- **ui_dark_patterns/**: Additional UI/UX dark pattern references
- **behavior_sessions/**: Labeled click-session data for behavioral analysis

## How Reference Data is Used

### 1. **Taxonomy & Terminology**
The Princeton dataset provides an authoritative taxonomy of deceptive UI/UX patterns. This helps standardize terminology across our detection rules.

### 2. **Pattern Matching & Evidence**
When the analyzer detects behavioral patterns (excessive steps, repeated prompts, forced actions, etc.), it queries the Princeton reference to find semantically related pattern categories. This provides external validation context.

### 3. **NOT Direct Classification**
The reference material does NOT directly classify or "prove" that a live website is deceptive. Instead:
- Our analyzer detects **behavior patterns** from browser events
- The reference layer identifies **related taxonomy categories** from Princeton
- Users see both the detected behavior AND the reference context

### 4. **Data Flow**
```
Browser Click Events → Analyzer (Behavior Detection) → Matcher
                                                            ↓
                                                    Princeton Reference
                                                    (Pattern Taxonomy)
                                                            ↓
                                                    Dataset Matches
                                                    (Confidence-based)
```

## Reference vs. Behavioral Detection

| Aspect | Behavioral Detection | Reference Data |
|--------|---------------------|-----------------|
| Source | Live browser events | Princeton crawl (2019) |
| Scope | Single session | 11K websites (snapshot) |
| Purpose | Detect friction in user flow | Provide pattern taxonomy |
| Claim | "You experienced X steps" | "Similar patterns exist in literature" |
| Status | Real-time | Historical reference |

## Attribution

- Princeton reference data: [Dark Patterns at Scale](https://webtransparency.cs.princeton.edu/dark-patterns/) (Mathur et al., USENIX Security 2019)
- Dataset: [GitHub](https://github.com/aruneshmathur/dark-patterns)
- License: See princeton/README.md for details
