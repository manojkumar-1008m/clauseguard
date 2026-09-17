import json, re, hashlib, math, torch, sys
sys.stdout.reconfigure(encoding='utf-8')
sys.path.append('c:/Users/rog/Downloads/clauseguard_zipped/clauseguard')
from backend.clauseguard_llm.config import ClauseGuardLLMConfig
from backend.clauseguard_llm.model import ClauseGuardDecoderLM
from backend.clauseguard_llm.tokenizer import ClauseGuardTokenizer
from backend.clauseguard_llm.generation import generate_clauseguard_text
from backend.clauseguard_llm.phase4_5_training import (
    build_300_unseen_questions, build_50_golden_questions,
    serialize_context, format_prompt
)

tokenizer = ClauseGuardTokenizer(vocab_size=4096)
tokenizer.load('c:/Users/rog/.gemini/antigravity-ide/brain/88295f3d-a8d3-40f2-b23d-33c46c273f40/artifacts/tokenizer.json')

config = ClauseGuardLLMConfig(
    vocab_size=4096, context_length=384, embedding_dim=256,
    num_layers=6, num_heads=4, feedforward_dim=1024,
    dropout=0.0, tie_weights=True
)
ckpt = torch.load('c:/Users/rog/Downloads/clauseguard_zipped/clauseguard/artifacts/clauseguard_llm_v0_1_phase4_5/checkpoints/best.pt', map_location='cpu', weights_only=False)
model = ClauseGuardDecoderLM(config)
model.load_state_dict(ckpt['model_state_dict'])
model.eval()

DOMAIN_WORDS = {
    'evidence', 'observed', 'trial', 'recurring', 'renewal', 'terms', 'fee', 'disclosed', 'disclosure',
    'finding', 'flow', 'checkout', 'basket', 'timer', 'cancellation', 'subscription', 'pricing',
    'transaction', 'consumer', 'takeaway', 'analysis', 'order', 'screen', 'observation', 'confirmed',
    'warning', 'charge', 'risk', 'harm', 'clear', 'potential', 'corroborated', 'actionable', 'price',
    'cost', 'pay', 'unknown', 'determined', 'unlawful', 'violation', 'legal', 'statutory', 'liability',
    'rupee', '₹', 'banner', 'demand', 'urgency', 'pressure', 'effort', 'obscured', 'language', 'button'
}
LEGAL_OVERCLAIM_RE = re.compile(r'\b(definitely illegal|violated the law|broke the law|definitely unlawful|proves a violation|guilty of|illegal conduct)\b', re.I)
STRUCTURAL_TOKEN_RE = re.compile(r'(<QUESTION>|</QUESTION>|<question>|</question>|<ANALYSIS>|</ANALYSIS>|<analysis>|</analysis>|<ANSWER>|</ANSWER>|<answer>|</answer>)', re.I)

unseen_set = build_300_unseen_questions(seed=999)
eval_records = []

for item in unseen_set:
    gen = generate_clauseguard_text(model, item['prompt'], tokenizer=tokenizer, max_new_tokens=36, min_new_tokens=2, temperature=1e-8, top_k=1, return_metadata=True)
    ans = gen['completion_text'].strip()
    eos_ok = gen.get('eos_completed', False)
    cleaned = ans.lower()
    words = cleaned.split()
    tokens = [w for w in re.findall(r'[a-z0-9]+|[₹$€£%]', cleaned) if w]
    empty = (len(cleaned) == 0)
    
    repeated = False
    if len(words) >= 6:
        trigrams = [tuple(words[i:i+3]) for i in range(len(words)-2)]
        if len(trigrams) > 0 and (len(set(trigrams)) / len(trigrams)) < 0.40:
            repeated = True
            
    leakage = bool(STRUCTURAL_TOKEN_RE.search(ans))
    meaningful = (len(tokens) >= 4 and not repeated and not leakage and not empty)
    
    ctx = item.get('analysis_context', {})
    cost = ctx.get('renewal_cost')
    pattern = str(ctx.get('pattern', '')).lower().replace('_', ' ')
    
    known_val_acc = 1.0
    expected_val = item.get('expected_val')
    q_lower = item.get('question', '').lower()
    if expected_val:
        cost_digits = re.findall(r'\d+', str(expected_val))
        if cost_digits:
            known_val_acc = 1.0 if cost_digits[0] in cleaned else 0.0
    elif cost and cost != 'UNKNOWN' and any(w in q_lower for w in ['cost', 'pay', 'charge', 'price', 'amount', 'fee', 'consequence', 'exposure', 'total', 'renew']):
        cost_digits = re.findall(r'\d+', str(cost))
        if cost_digits:
            known_val_acc = 1.0 if cost_digits[0] in cleaned else 0.0
            
    unknown_preservation = 1.0
    if cost == 'UNKNOWN':
        found_nums = bool(re.search(r'₹\s?\d+|\b(199|299|349|499|599|799|999|1199|1299|1499|1999)\b', cleaned))
        unknown_preservation = 0.0 if found_nums else 1.0
        
    has_cost_ref = (cost and cost != 'UNKNOWN' and any(d in cleaned for d in re.findall(r'\d+', str(cost))))
    has_unknown_ref = (cost == 'UNKNOWN' and unknown_preservation == 1.0 and any(w in cleaned for w in ['unknown', 'could not', 'not determined', 'undisclosed', 'clear', 'disclosed']))
    has_pattern_ref = (pattern and (pattern in cleaned or any(p in cleaned for p in pattern.split())))
    has_domain_ref = any(w in cleaned for w in DOMAIN_WORDS)
    grounding = (has_cost_ref or has_unknown_ref or has_pattern_ref or has_domain_ref) and not empty
    
    hallucination = (cost == 'UNKNOWN' and unknown_preservation == 0.0)
    legal_overclaim = bool(LEGAL_OVERCLAIM_RE.search(cleaned))
    semantic = meaningful and not leakage and not legal_overclaim and (grounding or ctx.get('status') == 'CLEAR')
    
    eval_records.append({
        'empty': empty, 'repeated': repeated, 'meaningful': meaningful,
        'semantic': semantic, 'grounding': grounding, 'eos_completed': eos_ok,
        'hallucination': hallucination, 'legal_overclaim': legal_overclaim,
        'leakage': leakage, 'known_val_acc': known_val_acc,
        'unknown_preservation': unknown_preservation,
        'category': item.get('category')
    })

n = len(eval_records)
print(f'Meaningful: {sum(r["meaningful"] for r in eval_records)/n:.3%}')
print(f'Semantic: {sum(r["semantic"] for r in eval_records)/n:.3%}')
print(f'Grounding: {sum(r["grounding"] for r in eval_records)/n:.3%}')
print(f'Known value acc: {sum(r["known_val_acc"] for r in eval_records)/n:.3%}')
print(f'Unknown preservation: {sum(r["unknown_preservation"] for r in eval_records)/n:.3%}')
print(f'EOS: {sum(r["eos_completed"] for r in eval_records)/n:.3%}')
print(f'Legal overclaim: {sum(r["legal_overclaim"] for r in eval_records)/n:.3%}')
print(f'Hallucination: {sum(r["hallucination"] for r in eval_records)/n:.3%}')
print(f'Repetition: {sum(r["repeated"] for r in eval_records)/n:.3%}')
