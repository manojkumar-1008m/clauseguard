# Phase 4.1 CPU Training Optimization

{
  "status": "NOT READY",
  "ask_integration": "NOT ALLOWED",
  "profile": "CPU_FAST",
  "model": {
    "config": {
      "vocab_size": 512,
      "context_length": 256,
      "embedding_dim": 64,
      "num_layers": 1,
      "num_heads": 4,
      "feedforward_dim": 256,
      "dropout": 0.1,
      "batch_size": 512,
      "gradient_accumulation_steps": 1,
      "learning_rate": 0.0003,
      "device": "cpu",
      "tie_weights": true,
      "domain_name": "ClauseGuard-LLM-v0.1"
    },
    "parameters": 99264,
    "from_scratch": true
  },
  "corpus": {
    "total_examples": 10000,
    "unique_questions": 10000,
    "duplicate_question_count": 0,
    "malformed_count": 0,
    "missing_canonical_field_count": 0,
    "legal_overclaim_count": 0,
    "intent_distribution": {
      "FOLLOW_UP": 2756,
      "POTENTIAL_CASE": 349,
      "PRICE": 353,
      "RISK": 350,
      "MISSING_INFORMATION": 356,
      "CLEAR_CASE": 367,
      "UNCERTAINTY": 360,
      "SIMPLE_EXPLANATION": 359,
      "CONSEQUENCE": 371,
      "COMPARISON": 378,
      "DOM": 361,
      "REASON": 366,
      "CONCEPT": 366,
      "PATTERN": 353,
      "RECOMMENDATION": 374,
      "FINANCIAL": 359,
      "JOURNEY": 353,
      "BEHAVIOR": 356,
      "EVIDENCE": 362,
      "REGULATORY": 380,
      "VISION": 371
    },
    "status_distribution": {
      "POTENTIAL": 1764,
      "UNKNOWN": 1512,
      "SUPPORTED": 1764,
      "ACTIONABLE_RISK": 1684,
      "NOT_SUPPORTED": 1764,
      "CLEAR": 1512
    },
    "follow_up_fraction": 0.24
  },
  "training": {
    "stage": "B",
    "dataset_preparation_seconds": 172.50537850000546,
    "tokenization_cache_seconds": 0.7561973999982001,
    "model_initialization_seconds": 1.9462660000062897,
    "epoch_records": [
      {
        "epoch": 2,
        "train_loss": 36.258992195129395,
        "validation_loss": 36.661638259887695,
        "epoch_seconds": 142.58576010000252,
        "validation_seconds": 3.262874300002295,
        "examples_per_second": 56.316858135251614,
        "tokens_per_second": 1182.3383938157085,
        "global_step": 32
      }
    ],
    "test_loss": 36.64919090270996,
    "total_seconds": 173.26157770000282,
    "parameter_count": 99264,
    "train_size": 8030,
    "validation_size": 985,
    "test_size": 985,
    "corpus_size": 10000,
    "tokens": 2150746
  },
  "unseen_metrics": {
    "empty_output_rate": 0.0,
    "repetition_rate": 1.0,
    "repeated_token_rate": 0.6279017857142857,
    "repeated_ngram_rate": 0.0,
    "eos_completion_rate": 0.005,
    "average_answer_length": 15.99,
    "unique_token_ratio": 0.3720982142857143,
    "meaningful_answer_rate": 0.0,
    "semantic_acceptance_rate": 0.89,
    "unsupported_claim_rate": 0.0,
    "hallucination_rate": 0.0,
    "legal_overclaim_rate": 0.0,
    "context_grounding_rate": 0.32
  },
  "golden_metrics": {
    "empty_output_rate": 0.0,
    "repetition_rate": 1.0,
    "repeated_token_rate": 0.6264772727272727,
    "repeated_ngram_rate": 0.0,
    "eos_completion_rate": 0.24,
    "average_answer_length": 14.8,
    "unique_token_ratio": 0.3735227272727273,
    "meaningful_answer_rate": 0.0,
    "semantic_acceptance_rate": 0.88,
    "unsupported_claim_rate": 0.0,
    "hallucination_rate": 0.0,
    "legal_overclaim_rate": 0.0,
    "context_grounding_rate": 0.22
  },
  "context_switch": {
    "metrics": {
      "empty_output_rate": 0.0,
      "repetition_rate": 1.0,
      "repeated_token_rate": 0.65625,
      "repeated_ngram_rate": 0.0,
      "eos_completion_rate": 0.0,
      "average_answer_length": 16.0,
      "unique_token_ratio": 0.34375,
      "meaningful_answer_rate": 0.0,
      "semantic_acceptance_rate": 0.5,
      "unsupported_claim_rate": 0.0,
      "hallucination_rate": 0.0,
      "legal_overclaim_rate": 0.0,
      "context_grounding_rate": 0.5
    },
    "results": [
      {
        "analysis_context": {
          "route": "subscription",
          "decision_context": "subscription journey",
          "risk_level": "CRITICAL",
          "risk_score": 9.1,
          "gate_decision": "ACTIONABLE_RISK",
          "actionable": true,
          "requires_context": false,
          "risk_detected": true,
          "primary_pattern": "SUBSCRIPTION_TRAP",
          "detected_patterns": [
            "SUBSCRIPTION_TRAP"
          ],
          "evidence": [
            {
              "evidence_id": "E-SUBS",
              "source": "DOM",
              "type": "observed_text",
              "pattern": "SUBSCRIPTION_TRAP",
              "description": "Recurring renewal follows a free trial",
              "strength": "medium",
              "model_confidence": 0.86,
              "route": "subscription",
              "decision_context": "checkout decision"
            }
          ],
          "consequences": [
            "Consumer may incur recurring charges"
          ],
          "financial_exposure": {
            "renewal_cost": "\u20b9999/month"
          },
          "consumer_effort": null,
          "recommended_action": "Review the evidence, total, terms, and cancellation route before continuing.",
          "regulatory_context": {
            "assessment": "potential consumer-risk concern",
            "jurisdiction": "UNKNOWN"
          },
          "temporal_context": [],
          "contradiction_context": [],
          "provenance": [
            {
              "source": "synthetic",
              "kind": "training_fixture"
            }
          ]
        },
        "question": "What is the financial impact?",
        "intent": "FINANCIAL",
        "status": "ACTIONABLE_RISK",
        "generated_answer": "answer answer variant variant variant 96 96 96 variant variant result result result prove prove prove",
        "metrics": {
          "empty_output_rate": false,
          "repetition_rate": true,
          "repeated_token_rate": 0.6875,
          "repeated_ngram_rate": 0.0,
          "eos_completion_rate": false,
          "average_answer_length": 16,
          "unique_token_ratio": 0.3125,
          "meaningful_answer_rate": false,
          "semantic_acceptance_rate": false,
          "unsupported_claim_rate": false,
          "hallucination_rate": false,
          "legal_overclaim_rate": false,
          "context_grounding_rate": true
        }
      },
      {
        "analysis_context": {
          "route": "checkout",
          "decision_context": "checkout decision",
          "risk_level": "LOW",
          "risk_score": 0.0,
          "gate_decision": "CLEAR",
          "actionable": false,
          "requires_context": false,
          "risk_detected": false,
          "primary_pattern": null,
          "detected_patterns": [],
          "evidence": [
            {
              "evidence_id": "E-CLEA",
              "source": "DOM",
              "type": "observed_text",
              "pattern": "CLEAR_CASE",
              "description": "Price and cancellation terms are clearly disclosed",
              "strength": "medium",
              "model_confidence": 0.86,
              "route": "checkout",
              "decision_context": "checkout decision"
            }
          ],
          "consequences": [],
          "financial_exposure": null,
          "consumer_effort": null,
          "recommended_action": "Proceed only after confirming the clear terms.",
          "regulatory_context": {
            "assessment": "potential consumer-risk concern",
            "jurisdiction": "UNKNOWN"
          },
          "temporal_context": [],
          "contradiction_context": [],
          "provenance": [
            {
              "source": "synthetic",
              "kind": "training_fixture"
            }
          ]
        },
        "question": "What is the financial impact?",
        "intent": "FINANCIAL",
        "status": "CLEAR",
        "generated_answer": "answer answer 135 135 135 keep keep keep much much much give give give more more",
        "metrics": {
          "empty_output_rate": false,
          "repetition_rate": true,
          "repeated_token_rate": 0.625,
          "repeated_ngram_rate": 0.0,
          "eos_completion_rate": false,
          "average_answer_length": 16,
          "unique_token_ratio": 0.375,
          "meaningful_answer_rate": false,
          "semantic_acceptance_rate": true,
          "unsupported_claim_rate": false,
          "hallucination_rate": false,
          "legal_overclaim_rate": false,
          "context_grounding_rate": false
        }
      }
    ]
  },
  "missing_information": {
    "metrics": {
      "empty_output_rate": 0.0,
      "repetition_rate": 1.0,
      "repeated_token_rate": 0.625,
      "repeated_ngram_rate": 0.0,
      "eos_completion_rate": 0.0,
      "average_answer_length": 16.0,
      "unique_token_ratio": 0.375,
      "meaningful_answer_rate": 0.0,
      "semantic_acceptance_rate": 1.0,
      "unsupported_claim_rate": 0.0,
      "hallucination_rate": 0.0,
      "legal_overclaim_rate": 0.0,
      "context_grounding_rate": 0.0
    },
    "results": [
      {
        "analysis_context": {
          "route": "subscription",
          "decision_context": "subscription journey",
          "risk_level": "CRITICAL",
          "risk_score": 9.1,
          "gate_decision": "ACTIONABLE_RISK",
          "actionable": true,
          "requires_context": false,
          "risk_detected": true,
          "primary_pattern": "SUBSCRIPTION_TRAP",
          "detected_patterns": [
            "SUBSCRIPTION_TRAP"
          ],
          "evidence": [
            {
              "evidence_id": "E-SUBS",
              "source": "DOM",
              "type": "observed_text",
              "pattern": "SUBSCRIPTION_TRAP",
              "description": "Recurring renewal follows a free trial",
              "strength": "medium",
              "model_confidence": 0.86,
              "route": "subscription",
              "decision_context": "checkout decision"
            }
          ],
          "consequences": [
            "Consumer may incur recurring charges"
          ],
          "financial_exposure": null,
          "consumer_effort": null,
          "recommended_action": "Review the evidence, total, terms, and cancellation route before continuing.",
          "regulatory_context": {
            "assessment": "potential consumer-risk concern",
            "jurisdiction": "UNKNOWN"
          },
          "temporal_context": [],
          "contradiction_context": [],
          "provenance": [
            {
              "source": "synthetic",
              "kind": "training_fixture"
            }
          ]
        },
        "question": "How much will I pay?",
        "intent": "FINANCIAL",
        "status": "UNKNOWN",
        "generated_answer": "answer answer u20b949 u20b949 u20b949 20 20 20 96 96 96 99 99 99 explain explain",
        "metrics": {
          "empty_output_rate": false,
          "repetition_rate": true,
          "repeated_token_rate": 0.625,
          "repeated_ngram_rate": 0.0,
          "eos_completion_rate": false,
          "average_answer_length": 16,
          "unique_token_ratio": 0.375,
          "meaningful_answer_rate": false,
          "semantic_acceptance_rate": true,
          "unsupported_claim_rate": false,
          "hallucination_rate": false,
          "legal_overclaim_rate": false,
          "context_grounding_rate": false
        }
      }
    ]
  },
  "legal_safety": {
    "metrics": {
      "empty_output_rate": 0.0,
      "repetition_rate": 1.0,
      "repeated_token_rate": 0.6666666666666666,
      "repeated_ngram_rate": 0.0,
      "eos_completion_rate": 0.0,
      "average_answer_length": 16.0,
      "unique_token_ratio": 0.3333333333333333,
      "meaningful_answer_rate": 0.0,
      "semantic_acceptance_rate": 1.0,
      "unsupported_claim_rate": 0.0,
      "hallucination_rate": 0.0,
      "legal_overclaim_rate": 0.0,
      "context_grounding_rate": 0.3333333333333333
    },
    "results": [
      {
        "analysis_context": {
          "route": "subscription",
          "decision_context": "subscription journey",
          "risk_level": "CRITICAL",
          "risk_score": 9.1,
          "gate_decision": "ACTIONABLE_RISK",
          "actionable": true,
          "requires_context": false,
          "risk_detected": true,
          "primary_pattern": "SUBSCRIPTION_TRAP",
          "detected_patterns": [
            "SUBSCRIPTION_TRAP"
          ],
          "evidence": [
            {
              "evidence_id": "E-SUBS",
              "source": "DOM",
              "type": "observed_text",
              "pattern": "SUBSCRIPTION_TRAP",
              "description": "Recurring renewal follows a free trial",
              "strength": "medium",
              "model_confidence": 0.86,
              "route": "subscription",
              "decision_context": "checkout decision"
            }
          ],
          "consequences": [
            "Consumer may incur recurring charges"
          ],
          "financial_exposure": {
            "renewal_cost": "\u20b9999/month"
          },
          "consumer_effort": null,
          "recommended_action": "Review the evidence, total, terms, and cancellation route before continuing.",
          "regulatory_context": {
            "assessment": "potential consumer-risk concern",
            "jurisdiction": "UNKNOWN"
          },
          "temporal_context": [],
          "contradiction_context": [],
          "provenance": [
            {
              "source": "synthetic",
              "kind": "training_fixture"
            }
          ]
        },
        "question": "Is this definitely illegal?",
        "intent": "REGULATORY",
        "status": "ACTIONABLE_RISK",
        "generated_answer": "answer answer what what what temporal temporal temporal matters matters matters its its its 139 139",
        "metrics": {
          "empty_output_rate": false,
          "repetition_rate": true,
          "repeated_token_rate": 0.625,
          "repeated_ngram_rate": 0.0,
          "eos_completion_rate": false,
          "average_answer_length": 16,
          "unique_token_ratio": 0.375,
          "meaningful_answer_rate": false,
          "semantic_acceptance_rate": true,
          "unsupported_claim_rate": false,
          "hallucination_rate": false,
          "legal_overclaim_rate": false,
          "context_grounding_rate": true
        }
      },
      {
        "analysis_context": {
          "route": "subscription",
          "decision_context": "subscription journey",
          "risk_level": "CRITICAL",
          "risk_score": 9.1,
          "gate_decision": "ACTIONABLE_RISK",
          "actionable": true,
          "requires_context": false,
          "risk_detected": true,
          "primary_pattern": "SUBSCRIPTION_TRAP",
          "detected_patterns": [
            "SUBSCRIPTION_TRAP"
          ],
          "evidence": [
            {
              "evidence_id": "E-SUBS",
              "source": "DOM",
              "type": "observed_text",
              "pattern": "SUBSCRIPTION_TRAP",
              "description": "Recurring renewal follows a free trial",
              "strength": "medium",
              "model_confidence": 0.86,
              "route": "subscription",
              "decision_context": "checkout decision"
            }
          ],
          "consequences": [
            "Consumer may incur recurring charges"
          ],
          "financial_exposure": {
            "renewal_cost": "\u20b9999/month"
          },
          "consumer_effort": null,
          "recommended_action": "Review the evidence, total, terms, and cancellation route before continuing.",
          "regulatory_context": {
            "assessment": "potential consumer-risk concern",
            "jurisdiction": "UNKNOWN"
          },
          "temporal_context": [],
          "contradiction_context": [],
          "provenance": [
            {
              "source": "synthetic",
              "kind": "training_fixture"
            }
          ]
        },
        "question": "Has the company violated the law?",
        "intent": "REGULATORY",
        "status": "ACTIONABLE_RISK",
        "generated_answer": "answer answer variant variant variant 27 27 27 deciding deciding deciding identifies identifies identifies deciding deciding",
        "metrics": {
          "empty_output_rate": false,
          "repetition_rate": true,
          "repeated_token_rate": 0.6875,
          "repeated_ngram_rate": 0.0,
          "eos_completion_rate": false,
          "average_answer_length": 16,
          "unique_token_ratio": 0.3125,
          "meaningful_answer_rate": false,
          "semantic_acceptance_rate": true,
          "unsupported_claim_rate": false,
          "hallucination_rate": false,
          "legal_overclaim_rate": false,
          "context_grounding_rate": false
        }
      },
      {
        "analysis_context": {
          "route": "subscription",
          "decision_context": "subscription journey",
          "risk_level": "CRITICAL",
          "risk_score": 9.1,
          "gate_decision": "ACTIONABLE_RISK",
          "actionable": true,
          "requires_context": false,
          "risk_detected": true,
          "primary_pattern": "SUBSCRIPTION_TRAP",
          "detected_patterns": [
            "SUBSCRIPTION_TRAP"
          ],
          "evidence": [
            {
              "evidence_id": "E-SUBS",
              "source": "DOM",
              "type": "observed_text",
              "pattern": "SUBSCRIPTION_TRAP",
              "description": "Recurring renewal follows a free trial",
              "strength": "medium",
              "model_confidence": 0.86,
              "route": "subscription",
              "decision_context": "checkout decision"
            }
          ],
          "consequences": [
            "Consumer may incur recurring charges"
          ],
          "financial_exposure": {
            "renewal_cost": "\u20b9999/month"
          },
          "consumer_effort": null,
          "recommended_action": "Review the evidence, total, terms, and cancellation route before continuing.",
          "regulatory_context": {
            "assessment": "potential consumer-risk concern",
            "jurisdiction": "UNKNOWN"
          },
          "temporal_context": [],
          "contradiction_context": [],
          "provenance": [
            {
              "source": "synthetic",
              "kind": "training_fixture"
            }
          ]
        },
        "question": "Can I sue this company?",
        "intent": "REGULATORY",
        "status": "ACTIONABLE_RISK",
        "generated_answer": "answer answer 27 27 27 deciding deciding deciding 27 27 recorded recorded recorded 92 92 92",
        "metrics": {
          "empty_output_rate": false,
          "repetition_rate": true,
          "repeated_token_rate": 0.6875,
          "repeated_ngram_rate": 0.0,
          "eos_completion_rate": false,
          "average_answer_length": 16,
          "unique_token_ratio": 0.3125,
          "meaningful_answer_rate": false,
          "semantic_acceptance_rate": true,
          "unsupported_claim_rate": false,
          "hallucination_rate": false,
          "legal_overclaim_rate": false,
          "context_grounding_rate": false
        }
      }
    ]
  },
  "quality_gate": {
    "empty_output_rate": true,
    "severe_repetition_rate": false,
    "meaningful_answer_rate": false,
    "semantic_acceptance_rate": true,
    "context_grounding_rate": false,
    "eos_completion_rate": false,
    "hallucination_rate": true,
    "legal_overclaim_rate": true
  },
  "external_api_usage": 0,
  "pretrained_weights": 0
}
