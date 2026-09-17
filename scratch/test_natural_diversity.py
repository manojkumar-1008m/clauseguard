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

TIPS = [
    "Review the terms before completing your order.",
    "Verify this charge before continuing.",
    "Ensure this matches your intended purchase.",
    "Check the cancellation conditions if you do not want to renew.",
    "Be mindful of this charge before proceeding.",
    "Confirm this billing schedule before continuation.",
    "Keep this renewal condition in mind during the trial.",
    "Review your billing preferences carefully.",
    "Examine the payment breakdown before committing.",
    "Confirm the details on the final screen.",
    "Ensure no additional items were added.",
    "Review all disclosed terms before confirmation.",
    "Check that this aligns with your expectations.",
    "Verify the charges on your payment method.",
    "Keep a record of this transaction detail."
]

def test():
    rng = random.Random(42)
    answers = []
    questions = []

    for idx in range(12000):
        p_tuple = rng.choice(PATTERNS)
        p_name, default_risk, default_evidence, default_consequence, route = p_tuple
        status = rng.choice(STATUSES)
        is_clear = (status == "CLEAR")
        cost = f"₹{rng.choice(RUPEE_VALUES)}"
        trial = rng.choice(DURATIONS)
        period = rng.choice(PERIODS)
        disp = rng.choice([199, 299, 499])
        add = rng.choice([49, 79, 99])
        p_clean = p_name.lower().replace("_", " ")

        tip = rng.choice(TIPS) if (idx % 2 == 0) else ""
        tip_str = f" {tip}" if tip else ""

        cat = idx % 10
        if is_clear:
            q = f"Why was this considered clear in the {route} flow? (case #{idx+1})"
            a = f"The {route} flow is transparent with no dark pattern identified.{tip_str}"
        elif cat == 0:
            q = f"What is the renewal cost for this {route}? (case #{idx+1})"
            a = f"The renewal cost is {cost} for this subscription.{tip_str}"
        elif cat == 1:
            q = f"What will I pay after the trial in {route}? (case #{idx+1})"
            a = f"You will pay {cost} once the trial concludes.{tip_str}"
        elif cat == 2:
            q = f"What happens after the trial in {route}? (case #{idx+1})"
            a = f"After the {trial} trial, you will be billed {cost} on a {period} basis.{tip_str}"
        elif cat == 3:
            q = f"How much will I actually pay in total for {route}? (case #{idx+1})"
            a = f"The displayed price is ₹{disp}, but the total is ₹{disp + add} after an added ₹{add} fee.{tip_str}"
        elif cat == 4:
            q = f"How much will I be charged after the trial in {route}? (case #{idx+1})"
            a = f"The exact renewal cost is unknown and could not be determined from the evidence.{tip_str}"
        elif cat == 5:
            q = f"Why did ClauseGuard flag this {p_clean} finding? (case #{idx+1})"
            a = f"ClauseGuard flagged this because {default_evidence.lower()} was identified.{tip_str}"
        elif cat == 6:
            q = f"What evidence was observed in the {route} flow? (case #{idx+1})"
            a = f"Observation confirmed that {default_evidence.lower()} in the {route} journey.{tip_str}"
        elif cat == 7:
            q = f"What consequence could I face regarding {p_clean}? (case #{idx+1})"
            a = f"You may face {default_consequence.lower()}, including a charge of {cost}.{tip_str}"
        elif cat == 8:
            q = f"How serious is the risk level for this {route}? (case #{idx+1})"
            a = f"The flow presents a {default_risk.lower()} risk under status {status}.{tip_str}"
        else:
            q = f"Is this definitely illegal in the {route} flow? (case #{idx+1})"
            a = f"The analysis indicates potential consumer risk for {p_clean}, but this does not establish a statutory legal violation.{tip_str}"

        questions.append(q)
        answers.append(a)

    total = len(answers)
    uq_q = len(set(questions))
    uq_a = len(set(answers))
    norm_a = [re.sub(r"\b(?:the|a|an|this|that|is|are|may|could)\b", "X", a) for a in answers]
    tmpl_rate = sum(count > 1 for count in Counter(norm_a).values()) / total
    print(f"Total: {total}")
    print(f"Unique Q: {uq_q} ({uq_q/total:.3%})")
    print(f"Unique A: {uq_a} ({uq_a/total:.3%})")
    print(f"Template rate: {tmpl_rate:.3%}")

if __name__ == "__main__":
    test()
