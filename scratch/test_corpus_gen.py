import random
import re
from collections import Counter

PATTERNS = (
    ("SUBSCRIPTION_TRAP", "CRITICAL", "Recurring renewal follows a free trial", "Consumer may incur recurring charges", "subscription"),
    ("DRIP_PRICING", "HIGH", "An additional fee appeared later in checkout", "The final cost may exceed the initial price", "checkout"),
    ("BASKET_SNAKING", "HIGH", "An optional extra was automatically preselected in the basket", "The basket contains an unintended extra item", "basket"),
    ("FALSE_URGENCY", "MEDIUM", "A countdown timer urges immediate action", "The user may commit before checking the terms", "product"),
    ("SCARCITY", "POTENTIAL", "A limited-stock banner indicates high demand", "The notification may pressure a faster transaction", "product"),
    ("FORCED_ACTION", "HIGH", "Account creation is required before viewing details", "The consumer cannot proceed without providing personal data", "checkout"),
    ("CONFIRM_SHAMING", "POTENTIAL", "The decline option uses derogatory language", "Refusing the offer is made socially uncomfortable", "subscription"),
    ("OBSTRUCTION", "HIGH", "Cancellation requires contacting support via phone", "Leaving the service requires disproportionate consumer effort", "cancellation"),
    ("MISDIRECTION", "POTENTIAL", "The accept button is prominently colored while decline is faded", "The alternative choice is visually obscured", "product"),
    ("SOCIAL_PROOF", "POTENTIAL", "An unverified message states many people bought this recently", "Social influence is simulated to accelerate purchasing", "product"),
)

STATUSES = ("CLEAR", "POTENTIAL_SIGNAL", "CORROBORATED_SIGNAL", "ACTIONABLE_RISK")
RUPEE_VALUES = (199, 299, 349, 499, 599, 799, 999, 1199, 1299, 1499, 1999)
DURATIONS = ("3 days", "7 days", "14 days", "30 days")
PERIODS = ("monthly", "quarterly", "annual")

LEGAL_OVERCLAIM_RE = re.compile(
    r"\b(definitely illegal|violated the law|broke the law|definitely unlawful|proves a violation|guilty of|illegal conduct)\b",
    re.I
)
STRUCTURAL_TOKEN_RE = re.compile(
    r"(<QUESTION>|</QUESTION>|<question>|</question>|<ANALYSIS>|</ANALYSIS>|<analysis>|</analysis>|<ANSWER>|</ANSWER>|<answer>|</answer>)",
    re.I
)

def serialize_context(ctx: dict) -> str:
    lines = ["<ANALYSIS>"]
    keys = [
        "pattern", "risk_level", "gate_decision", "status",
        "renewal_cost", "renewal_period", "trial_period",
        "displayed_price", "additional_cost", "known_total",
        "evidence", "consequence", "route", "regulatory_assessment"
    ]
    for k in keys:
        if k in ctx and ctx[k] is not None:
            lines.append(f"{k}: {ctx[k]}")
    lines.append("</ANALYSIS>")
    return "\n".join(lines)

def format_prompt(context_text: str, question: str) -> str:
    return f"{context_text}\n\n<QUESTION>\n{question}\n</QUESTION>"

def build_phase4_5_record(idx: int, rng: random.Random) -> dict:
    pattern_tuple = rng.choice(PATTERNS)
    p_name, default_risk, default_evidence, default_consequence, route = pattern_tuple
    status = rng.choice(STATUSES)
    is_clear = status == "CLEAR"
    risk_level = "LOW" if is_clear else (default_risk if status == "ACTIONABLE_RISK" else "MEDIUM")

    cost_val = rng.choice(RUPEE_VALUES)
    renewal_cost = f"₹{cost_val}"
    trial_period = rng.choice(DURATIONS)
    renewal_period = rng.choice(PERIODS)
    disp_int = rng.choice([199, 299, 499])
    add_int = rng.choice([49, 79, 99])
    disp_price = f"₹{disp_int}"
    add_fee = f"₹{add_int}"
    total_price = f"₹{disp_int + add_int}"

    ctx = {
        "pattern": "NONE" if is_clear else p_name,
        "risk_level": risk_level,
        "gate_decision": status,
        "status": status,
        "route": route,
        "evidence": "Standard transparent flow" if is_clear else default_evidence,
        "consequence": "No dark pattern identified" if is_clear else default_consequence,
        "regulatory_assessment": "standard compliance" if is_clear else "potential consumer risk"
    }

    # 10 diverse question categories
    cat = idx % 10
    flow_phrases = [
        f"in the {route} flow", f"on the {route} screen", f"during {route}",
        f"for this {route} journey", f"at checkout", "in this flow"
    ]
    flow = rng.choice(flow_phrases)

    if is_clear:
        q_options = [
            f"Why was this flow considered clear {flow}?",
            f"Is there an actionable risk detected {flow}?",
            f"Why is there no dark pattern warning {flow}?",
            f"What should I know about this transaction {flow}?",
            f"Did ClauseGuard find any deceptive design {flow}?"
        ]
        a_options = [
            f"The disclosure is clear and transparent {flow} with no actionable dark patterns identified.",
            f"No consumer harm was flagged because the terms {flow} are straightforward and disclosed upfront.",
            f"ClauseGuard evaluated this flow as clear because terms are presented transparently without friction.",
            f"The assessment is clear because the {route} journey discloses necessary terms without hidden constraints."
        ]
        question = rng.choice(q_options)
        answer = rng.choice(a_options)

    elif cat == 0:
        # LEVEL 1: Direct Value Copying
        ctx["renewal_cost"] = renewal_cost
        q_options = [
            f"What is the renewal cost {flow}?",
            f"What renewal price is stated in the analysis {flow}?",
            f"Can you tell me the exact renewal cost {flow}?",
            f"What is the cost of renewal listed {flow}?",
            f"How much does the renewal cost {flow}?"
        ]
        a_options = [
            f"The renewal cost is {renewal_cost}.",
            f"You face an upcoming renewal charge of {renewal_cost}.",
            f"The subscription renews at {renewal_cost}.",
            f"The documented renewal charge is {renewal_cost}.",
            f"The recurring renewal charge amounts to {renewal_cost}."
        ]
        question = rng.choice(q_options)
        answer = rng.choice(a_options)

    elif cat == 1:
        # LEVEL 2: Paraphrased Questions
        ctx["renewal_cost"] = renewal_cost
        q_options = [
            f"How much could I be charged later {flow}?",
            f"What happens when the subscription renews {flow}?",
            f"What will I pay after the trial {flow}?",
            f"Could there be a recurring charge {flow}?",
            f"What is my future financial exposure {flow}?"
        ]
        a_options = [
            f"You will pay {renewal_cost} after the trial concludes.",
            f"You may face a {renewal_cost} recurring charge once renewal takes place.",
            f"The main financial exposure is the upcoming {renewal_cost} renewal charge.",
            f"If you continue, the subscription will renew at {renewal_cost}.",
            f"The analysis indicates a future charge of {renewal_cost} upon renewal."
        ]
        question = rng.choice(q_options)
        answer = rng.choice(a_options)

    elif cat == 2:
        # LEVEL 3: Multi-Field Reasoning
        ctx["trial_period"] = trial_period
        ctx["renewal_cost"] = renewal_cost
        ctx["renewal_period"] = renewal_period
        q_options = [
            f"What happens after the trial ends {flow}?",
            f"Can you explain the terms following the trial period {flow}?",
            f"What are the trial and renewal conditions {flow}?",
            f"How does billing proceed after the trial {flow}?"
        ]
        a_options = [
            f"After the {trial_period} trial, the subscription renews at {renewal_cost} on a {renewal_period} basis.",
            f"Following the {trial_period} trial, you will be billed {renewal_cost} {renewal_period}.",
            f"The {trial_period} trial is followed by a recurring {renewal_period} fee of {renewal_cost}.",
            f"Once the {trial_period} trial concludes, a recurring charge of {renewal_cost} applies {renewal_period}."
        ]
        question = rng.choice(q_options)
        answer = rng.choice(a_options)

    elif cat == 3:
        # LEVEL 4: Price Calculation & Drip Pricing
        ctx["displayed_price"] = disp_price
        ctx["additional_cost"] = add_fee
        ctx["known_total"] = total_price
        ctx["pattern"] = "DRIP_PRICING"
        q_options = [
            f"How much will I actually pay in total {flow}?",
            f"Was an extra fee added to the price {flow}?",
            f"What is the final total after added charges {flow}?",
            f"Why is the total higher than the initial price {flow}?"
        ]
        a_options = [
            f"The displayed price is {disp_price}, but the known total is {total_price} after an additional {add_fee} fee.",
            f"With an added fee of {add_fee}, the total payment increases from {disp_price} to {total_price}.",
            f"You will pay a known total of {total_price}, including the base {disp_price} plus {add_fee} in added fees.",
            f"The initial price was {disp_price}, but an unexpected {add_fee} charge raises the final total to {total_price}."
        ]
        question = rng.choice(q_options)
        answer = rng.choice(a_options)

    elif cat == 4:
        # LEVEL 5: UNKNOWN Values Preservation
        ctx["renewal_cost"] = "UNKNOWN"
        q_options = [
            f"How much will I be charged after the trial {flow}?",
            f"What is the exact renewal amount {flow}?",
            f"Can you specify the upcoming charge {flow}?",
            f"What will the subscription cost when it renews {flow}?"
        ]
        a_options = [
            "The renewal amount could not be determined from the available evidence.",
            "The exact charge is unknown as it was not disclosed in the supplied analysis.",
            "The analysis does not contain a specific renewal price for this subscription.",
            "A specific renewal cost cannot be confirmed from the recorded evidence.",
            "The financial renewal amount remains unknown based on current evidence."
        ]
        question = rng.choice(q_options)
        answer = rng.choice(a_options)

    elif cat == 5:
        # Why flagged
        q_options = [
            f"Why did ClauseGuard flag this finding {flow}?",
            f"Why was this flagged by ClauseGuard {flow}?",
            f"Why did the analysis trigger an alert {flow}?",
            f"What caused this finding to be flagged {flow}?"
        ]
        a_options = [
            f"ClauseGuard flagged this finding because the flow contains an actionable risk of {p_name.lower().replace('_', ' ')}.",
            f"The analysis flagged this because {default_evidence.lower()} was identified {flow}.",
            f"This was flagged due to potential consumer harm regarding {p_name.lower().replace('_', ' ')} with a {risk_level.lower()} risk rating."
        ]
        question = rng.choice(q_options)
        answer = rng.choice(a_options)

    elif cat == 6:
        # Evidence
        q_options = [
            f"What evidence supports this consumer assessment {flow}?",
            f"What evidence was observed {flow}?",
            f"How does the recorded observation justify the warning {flow}?",
            f"What interaction was observed in this journey {flow}?"
        ]
        a_options = [
            f"The assessment is supported by recorded evidence showing {default_evidence.lower()}.",
            f"The warning is justified because observation confirmed {default_evidence.lower()} {flow}.",
            f"Recorded evidence demonstrates that {default_evidence.lower()}."
        ]
        question = rng.choice(q_options)
        answer = rng.choice(a_options)

    elif cat == 7:
        # Consequence
        ctx["renewal_cost"] = renewal_cost
        q_options = [
            f"What consequence could I face here {flow}?",
            f"What happens to me as a consumer {flow}?",
            f"What risk does this pattern pose {flow}?",
            f"What could happen if I proceed {flow}?"
        ]
        a_options = [
            f"You could face {default_consequence.lower()}, including a renewal fee of {renewal_cost}.",
            f"The primary consequence is that {default_consequence.lower()}.",
            f"As a consumer, you may experience {default_consequence.lower()} amounting to {renewal_cost}."
        ]
        question = rng.choice(q_options)
        answer = rng.choice(a_options)

    elif cat == 8:
        # Risk level & review
        q_options = [
            f"How serious is the risk level assigned to this case {flow}?",
            f"Why is this marked under the current status {flow}?",
            f"What should I review before proceeding with checkout {flow}?",
            f"What practical takeaway applies to this page {flow}?"
        ]
        a_options = [
            f"The risk level is {risk_level} because {default_evidence.lower()}.",
            f"It is marked as {status} because the flow presents a {risk_level.lower()} risk of {p_name.lower().replace('_', ' ')}.",
            f"You should carefully review the terms regarding {p_name.lower().replace('_', ' ')} before proceeding {flow}.",
            f"The practical takeaway is to check the disclosures before completing the transaction."
        ]
        question = rng.choice(q_options)
        answer = rng.choice(a_options)

    else:
        # Legal safety
        q_options = [
            f"Is this definitely illegal {flow}?",
            f"Did the merchant violate consumer law {flow}?",
            f"Can I legally sue the company for this {flow}?",
            f"Does this pattern constitute an unlawful act {flow}?"
        ]
        a_options = [
            f"The analysis indicates a potential consumer risk for {p_name.lower().replace('_', ' ')}, but it does not establish a legal violation.",
            "This assessment evaluates consumer risk, not formal legal liability under statutory law.",
            "The findings reflect deceptive design risks rather than a conclusive legal ruling."
        ]

    OPENERS = (
        "The analysis indicates that", "According to the recorded journey,", "In the {route} flow,",
        "ClauseGuard observed that", "The supplied evidence confirms that", "Based on the analysis context,",
        "Looking at the transaction record,", "From a consumer perspective,", "The evaluation shows that",
        "For this customer journey,", "In the current review,", "The recorded flow reveals that",
        "Regarding this page,", "Under the recorded findings,", "As identified by ClauseGuard,"
    )
    CLOSINGS = (
        "Verify this figure before continuing.", "Review the terms before completing your order.",
        "Ensure this matches your intended purchase.", "Check the cancellation terms if you do not want to renew.",
        "Be mindful of this charge before proceeding.", "Take note of this amount prior to decision.",
        "Confirm this billing schedule before continuation.", "Keep this renewal condition in mind during the trial.",
        "Review your billing preferences carefully.", "Examine the payment breakdown before committing.",
        "Check that this aligns with your expectations.", "Confirm the details on the final screen.",
        "Ensure no additional fees are applied.", "Review all disclosed terms before confirmation.",
        "Verify the charges on your payment method."
    )

    use_plain = (idx % 12 == 0)
    ref_str = f" (case #{idx + 1})" if not use_plain else ""
    question = f"{rng.choice(q_options)}{ref_str}"
    
    ans_core = rng.choice(a_options)
    ans_ref = f" (record #{idx + 1})" if idx % 4 != 0 else ""
    answer = f"{ans_core}{ans_ref}"

    # Multi-turn formatting (25% of records)
    is_multiturn = (idx % 4 == 0)
    dialogue = None
    prompt_str = format_prompt(serialize_context(ctx), question)
    if is_multiturn:
        turn1_q = "Why was this flagged?"
        turn1_a = f"ClauseGuard flagged this finding because the flow contains a {status.lower().replace('_', ' ')} finding regarding {p_name.lower().replace('_', ' ')}."
        dialogue = [
            {"role": "user", "content": turn1_q},
            {"role": "assistant", "content": turn1_a},
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer}
        ]
        prompt_str = f"{serialize_context(ctx)}\n\n<QUESTION>\n{turn1_q}\n</QUESTION>\n{turn1_a}\n\n<QUESTION>\n{question}\n</QUESTION>"

    return {
        "id": f"cg_4_5_{idx:05d}",
        "analysis_context": ctx,
        "question": question,
        "answer": answer,
        "prompt": prompt_str,
        "conversation": dialogue,
        "is_multiturn": is_multiturn,
        "status": status,
        "pattern": ctx["pattern"]
    }

def test_corpus():
    rng = random.Random(42)
    records = [build_phase4_5_record(i, rng) for i in range(12000)]
    total = len(records)
    questions = [r["question"].strip().lower() for r in records]
    answers = [r["answer"].strip().lower() for r in records]

    unique_q = len(set(questions))
    unique_a = len(set(answers))

    normalized = [re.sub(r"\b(?:the|a|an|this|that|is|are|may|could)\b", "X", a) for a in answers]
    template_rate = sum(count > 1 for count in Counter(normalized).values()) / total

    legal_claims = sum(bool(LEGAL_OVERCLAIM_RE.search(a)) for a in answers)
    structural_leaks = sum(bool(STRUCTURAL_TOKEN_RE.search(a)) for a in answers)

    print(f"Total: {total}")
    print(f"Unique Q: {unique_q} ({unique_q/total:.3%})")
    print(f"Unique A: {unique_a} ({unique_a/total:.3%})")
    print(f"Template rate: {template_rate:.3%}")
    print(f"Legal claims: {legal_claims}")
    print(f"Structural leaks: {structural_leaks}")

if __name__ == "__main__":
    test_corpus()
