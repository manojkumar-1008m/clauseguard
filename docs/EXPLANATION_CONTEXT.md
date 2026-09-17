# ExplanationContext

`backend/schemas/explanation_context.py` defines the future explanation boundary. It carries only verified upstream information: risk result, pattern, evidence IDs and descriptions, consequence, known financial exposure, consumer effort, recommended action, decision context, regulatory assessment, context requirements, and provenance.

It deliberately has no authority field, score-calculation method, threshold override, or free-form risk decision. A future MiniLM component may summarize this context, but final risk remains upstream and deterministic.

`/analyze` constructs this context after canonical fusion and gate evaluation, then passes it to the deterministic explanation engine.
