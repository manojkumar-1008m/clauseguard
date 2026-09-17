# ClauseGuard LLM v0.1 Phase 2 Report

## Run metrics
- Corpus: 3000 records ({'synthetic_canonical': 2500, 'observed_dataset': 500})
- Splits: train=2527, validation=232, test=241
- Vocabulary: 1414; unknown-token rate: 0.000000
- Parameters: 5853184
- Configuration: 6 layers, 256 dimensions, 4 heads, context 256, batch 8, accumulation 4
- Epochs: 1; train loss: 21.173665; validation loss: 5.371203; test loss: 5.647627
- Training duration: 147.867 seconds; device: cpu; torch threads: 4

## Raw locked generation outputs
- Q: What is social proof? | raw: what is social proof claim claim : a confirm shaming concept is being reviewed . a permitted example signal is additional additional additional additional additional additional additional additional additional additional additional additional additional additional additional additional additional additional additional additional additional additional additional additional | empty=False | repetitive=True
- Q: Why did ClauseGuard flag this? | raw: why did clauseguard this 2 : clauseguard dataset dataset concept is being reviewed . a permitted example signal is | empty=False | repetitive=False
- Q: What evidence supports the finding? | raw: what evidence supports the finding 2 : clauseguard sees sees concept is being reviewed . a permitted example signal is selecting selecting selecting selecting selecting selecting selecting selecting selecting selecting selecting selecting selecting selecting selecting selecting selecting selecting selecting selecting selecting selecting selecting selecting selecting | empty=False | repetitive=True
- Q: How can this affect me? | raw: how can this affect me in an ecommerce ecommerce ecommerce ecommerce ecommerce ecommerce ecommerce ecommerce ecommerce ecommerce ecommerce ecommerce ecommerce | empty=False | repetitive=True
- Q: Could this cost me more? | raw: could this cost me more 2 : a stronger claim is being reviewed . a permitted example signal is unknown unknown . status under review : identify identify identify identify identify identify identify identify identify identify identify identify 228 228 228 228 228 228 228 | empty=False | repetitive=True
- Q: What should I check before buying? | raw: what should i check before buying : clauseguard sees a stronger claim . status under review : this is unknown unknown tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler | empty=False | repetitive=True
- Q: Is this definitely a dark pattern? | raw: is this definitely a : a drip pricing concept is being reviewed . a permitted example signal is additional additional additional additional additional additional additional additional additional additional additional additional additional additional additional additional additional additional additional additional additional additional additional additional additional additional | empty=False | repetitive=True
- Q: What does the evidence mean? | raw: what does the evidence mean 2 : clauseguard sees a stronger claim . status under review : unknown is visual visual visual visual visual visual visual visual visual visual visual visual visual visual visual visual visual visual visual visual visual visual visual visual visual visual | empty=False | repetitive=True
- Q: Why should I be careful? | raw: why should i be careful 2 : a misdirection concept is being reviewed . a permitted example signal is visual visual visual visual visual visual visual visual visual visual visual visual visual visual visual visual visual visual visual visual visual visual visual visual visual visual | empty=False | repetitive=True
- Q: Explain this in simple words. | raw: explain this in simple words . : clauseguard tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler tyler | empty=False | repetitive=True
- Q: What happens if I cancel the subscription? | raw: what if i cancel the subscription | empty=False | repetitive=False

## Interpretation
- Empty outputs: 0; repetitive outputs: 9.
- These outputs are raw tokenizer-decoded model output and were not replaced with templates.
- This checkpoint is not ready for /ask integration: generation is incomplete or degenerate on the locked questions.
- The existing risk engine and production Ask behavior were not changed by this Phase 2 pipeline.
