import torch
import torch.nn.functional as F
import random
from backend.clauseguard_llm.config import ClauseGuardLLMConfig
from backend.clauseguard_llm.model import ClauseGuardDecoderLM
from backend.clauseguard_llm.tokenizer import ClauseGuardTokenizer
from backend.clauseguard_llm.generation import generate_clauseguard_text

def run():
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    print("Testing value copy attention...")
    config = ClauseGuardLLMConfig(
        vocab_size=4096, context_length=384, embedding_dim=256,
        num_layers=6, num_heads=4, feedforward_dim=1024,
        dropout=0.0, tie_weights=True, learning_rate=1e-3
    )
    tokenizer = ClauseGuardTokenizer(vocab_size=4096)
    
    # Train tokenizer on diverse examples
    train_corpus = []
    prices = [199, 299, 349, 499, 599, 799, 999, 1199, 1299, 1499, 1999]
    for p in prices:
        train_corpus.append(f"<ANALYSIS>\npattern: SUBSCRIPTION_TRAP\nrenewal_cost: ₹{p}\nstatus: ACTIONABLE_RISK\n</ANALYSIS>\n\n<QUESTION>\nWhat will I pay after the trial?\n</QUESTION>\nYou will pay ₹{p} after the trial.")
        train_corpus.append(f"<ANALYSIS>\npattern: SUBSCRIPTION_TRAP\nrenewal_cost: ₹{p}\nstatus: ACTIONABLE_RISK\n</ANALYSIS>\n\n<QUESTION>\nWhat is the renewal cost?\n</QUESTION>\nThe renewal cost is ₹{p}.")
    
    tokenizer.train(train_corpus)
    print("Tokenizer vocab size:", len(tokenizer.vocab))
    
    # Build dataset
    records = []
    for _ in range(50):
        for p in prices:
            q = random.choice(["What will I pay after the trial?", "What is the renewal cost?"])
            ans = f"You will pay ₹{p} after the trial." if "pay" in q else f"The renewal cost is ₹{p}."
            prompt = f"<ANALYSIS>\npattern: SUBSCRIPTION_TRAP\nrenewal_cost: ₹{p}\nstatus: ACTIONABLE_RISK\n</ANALYSIS>\n\n<QUESTION>\n{q}\n</QUESTION>"
            records.append((prompt, ans))
    
    # Cache
    seqs = []
    for prompt, ans in records:
        p_ids = tokenizer.encode(prompt, add_special_tokens=False)
        a_ids = tokenizer.encode(ans, add_special_tokens=False)
        full = [tokenizer.encoder["<bos>"]] + p_ids + a_ids + [tokenizer.encoder["<eos>"]]
        inp = full[:-1]
        lab = full[1:]
        p_len = len(p_ids)
        masked_lab = [-100 if i < p_len else l for i, l in enumerate(lab)]
        seqs.append((inp, masked_lab))
        
    max_len = max(len(inp) for inp, _ in seqs)
    pad_id = tokenizer.encoder["<pad>"]
    in_t = torch.tensor([s[0] + [pad_id]*(max_len - len(s[0])) for s in seqs], dtype=torch.long)
    lab_t = torch.tensor([s[1] + [-100]*(max_len - len(s[1])) for s in seqs], dtype=torch.long)
    
    model = ClauseGuardDecoderLM(config)
    opt = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=0.01)
    
    # Train until loss < 0.05
    model.train()
    for step in range(120):
        idx = torch.randint(0, len(seqs), (16,))
        b_in = in_t[idx]
        b_lab = lab_t[idx]
        opt.zero_grad(set_to_none=True)
        logits = model(b_in)
        loss = F.cross_entropy(logits.view(-1, logits.size(-1)), b_lab.view(-1), ignore_index=-100)
        loss.backward()
        opt.step()
        if step % 20 == 0 or loss.item() < 0.05:
            print(f"Step {step}: loss = {loss.item():.4f}")
            if loss.item() < 0.05:
                break
            
    # Test generation for 499, 999, 1499
    model.eval()
    for p in [499, 999, 1499]:
        prompt = f"<ANALYSIS>\npattern: SUBSCRIPTION_TRAP\nrenewal_cost: ₹{p}\nstatus: ACTIONABLE_RISK\n</ANALYSIS>\n\n<QUESTION>\nWhat will I pay after the trial?\n</QUESTION>"
        gen = generate_clauseguard_text(model, prompt, tokenizer=tokenizer, max_new_tokens=20, temperature=1e-8, top_k=1, return_metadata=True)
        print(f"P={p} -> Gen: '{gen['completion_text']}'")

if __name__ == "__main__":
    run()
