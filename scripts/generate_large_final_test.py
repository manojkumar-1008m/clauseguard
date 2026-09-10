"""scripts/generate_large_final_test.py
Generates data/clean_final_test_large.csv containing 200 genuinely unseen multi-domain samples.
"""
import csv
import pathlib

ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]

def build_clean_final_test():
    samples = []
    # 1. E-Commerce (20 samples: 10 Benign, 10 Dark)
    ecom_benign = [
        "Orders over $50 qualify for complimentary ground shipping with tracking.",
        "Estimated delivery date is October 15-18 via FedEx ground.",
        "You can modify or cancel your pending order before it enters fulfillment.",
        "A full itemized receipt has been sent to your registered email address.",
        "Standard returns are accepted within 30 days of delivery with tags attached.",
        "Select your preferred delivery speed at checkout: Economy or Next-Day Air.",
        "Gift wrapping is optional and can be added for an additional $4.00.",
        "We accept credit cards, debit cards, PayPal, and Apple Pay.",
        "Sales tax is calculated based on the shipping address destination.",
        "Product warranty information is included inside the manufacturer packaging."
    ]
    ecom_dark = [
        "A non-refundable handling fee of $6.50 was added to your order on the payment screen.",
        "Limited stock! 12 customers currently have this exact shirt in their cart!",
        "Order within 02:45 to secure your items before they are released to another buyer!",
        "Shipping protection $2.49 has been pre-selected for you. Uncheck to decline.",
        "No thanks, I don't care about saving money and prefer overpaying on my orders.",
        "An express fulfillment surcharge has been applied automatically to your cart.",
        "Low inventory alert: 98% of this item's stock has sold out in the last hour!",
        "To return an item you must pay a mandatory $15 administrative restocking fee.",
        "Your cart will expire in 60 seconds — complete your order now before price increases!",
        "Add warranty for $19.99? Decline offer: 'No, I want my product to break easily.'"
    ]

    # 2. Subscriptions (20 samples: 10 Benign, 10 Dark)
    sub_benign = [
        "Monthly subscription charges of $12.99 will occur on the 1st of every month.",
        "You can turn off automatic renewal anytime directly from your billing dashboard.",
        "We send an email reminder 5 days before your recurring payment is processed.",
        "Subscriptions may be paused for up to 3 months without losing saved preferences.",
        "Cancel online in your account settings with two clicks. No cancellation fees.",
        "Your subscription plan includes unlimited access across all your personal devices.",
        "Switch between annual and monthly payment cycles whenever you choose.",
        "Downgrading your subscription tier will take effect at the end of the current cycle.",
        "Billing statements and payment history are available for download as PDF.",
        "A prorated refund will be issued if you cancel within 48 hours of renewal."
    ]
    sub_dark = [
        "To cancel your subscription you must call customer support during weekday hours.",
        "Cancellation requires writing a formal cancellation letter to our corporate address.",
        "Subscription renews automatically at triple the promotional rate with no prior notice.",
        "Canceling online is disabled. You must speak with a cancellation retention specialist.",
        "Early cancellation fee of $150 applies if terminated before 12 consecutive months.",
        "The cancel button is concealed beneath multiple nested help center FAQs.",
        "Auto-renewal cannot be disabled online once your credit card has been charged.",
        "You must complete a mandatory 15-minute phone survey to process cancellation.",
        "Your subscription was renewed 14 days before your billing date without authorization.",
        "Canceling your plan requires a $35 account deactivation processing penalty."
    ]

    # 3. SaaS (20 samples: 10 Benign, 10 Dark)
    saas_benign = [
        "Try our Team tier free for 14 days. No credit card is needed to register.",
        "API usage is billed strictly by actual requests consumed at $0.002 per call.",
        "You can export all your project data in standard CSV or JSON format anytime.",
        "Seat licenses can be reassigned freely between team members in the admin console.",
        "Our free tier includes up to 3 projects and 5GB of encrypted cloud storage.",
        "Pricing is $20 per user/month, with transparent billing calculated monthly.",
        "We provide a 99.9% uptime service level agreement for all Enterprise accounts.",
        "Cancel your workspace anytime from organization settings; data retained for 30 days.",
        "Overages are capped and will prompt for confirmation before incurring extra charges.",
        "Security audit logs and compliance reports are accessible from the security tab."
    ]
    saas_dark = [
        "Free trial converts into an irrevocable $600 annual contract on day 15.",
        "To downgrade to the Free plan, you must request permission from your account rep.",
        "An unannounced per-seat administrative fee is added on the final checkout review.",
        "Data export is restricted and requires upgrading to our top-tier Enterprise plan.",
        "Your account has been locked into a 3-year term with automatic renewal clauses.",
        "Hidden charges for data bandwidth appear only after payment credentials are entered.",
        "Decline trial: 'No thanks, I don't want my team to be productive or successful.'",
        "Removing a seat license incurs an unexpected $45 contract modification penalty.",
        "Canceling your workspace requires contacting support via live chat during PST hours.",
        "Annual upfront payment is selected by default without indicating monthly alternative."
    ]

    # 4. Travel & Hospitality (20 samples: 10 Benign, 10 Dark)
    travel_benign = [
        "Total hotel stay price of $480 includes all room charges, taxes, and service fees.",
        "Free cancellation is available up to 48 hours before the scheduled check-in time.",
        "Flight ticket includes one carry-on bag and one personal item at no extra cost.",
        "Seat selection is optional; free random seat assignment is provided at check-in.",
        "Complimentary breakfast and Wi-Fi are provided with all standard room bookings.",
        "Shuttle service to the airport operates every 30 minutes free of charge.",
        "Clear breakdown: Room rate $120/night, City occupancy tax $14/night, Total $134/night.",
        "You can change your travel dates online with no change fee, fare difference may apply.",
        "Car rental includes unlimited mileage and 24/7 emergency roadside assistance.",
        "Check-in begins at 3:00 PM and check-out is at 11:00 AM local property time."
    ]
    travel_dark = [
        "Mandatory resort fees of $55/night are not included and must be paid upon arrival.",
        "Only 1 room remaining at this special rate! 19 travelers are viewing this right now!",
        "A surprise baggage handling surcharge of $35 was added during payment verification.",
        "Hurry! Flight fares for this route are predicted to rise by 40% in 10 minutes!",
        "Pre-selected travel insurance for $28.50 has been added to your reservation.",
        "Convenience fee of $18.00 will be added on the final booking confirmation step.",
        "Act fast! Someone in London just reserved a room at this exact hotel!",
        "Decline trip insurance: 'I acknowledge that I am risking financial disaster.'",
        "Taxes, airport facility fees, and carrier surcharges will be revealed after booking.",
        "The cheaper non-refundable rate is disguised to look identical to the flexible fare."
    ]

    # 5. Ticketing & Events (20 samples: 10 Benign, 10 Dark)
    ticket_benign = [
        "Concert ticket face value is $65.00 with all fees clearly disclosed prior to payment.",
        "Digital tickets will be delivered to your mobile wallet within 15 minutes of purchase.",
        "Accessible seating options are available across all orchestra and balcony sections.",
        "Doors open at 6:30 PM; performance commences promptly at 7:30 PM.",
        "Refunds are automatically issued to original payment methods if an event is canceled.",
        "Full pricing schedule and venue seating charts are viewable on this page.",
        "Ticket exchange for alternate dates is permitted up to 72 hours prior to showtime.",
        "Children under 3 years old are admitted free when sitting on a parent's lap.",
        "General admission entry does not require assigned seating or reservation fees.",
        "Merchandise vouchers can be optionally purchased during the checkout process."
    ]
    ticket_dark = [
        "Processing fees and venue surcharges of $24 per ticket are disclosed only at payment.",
        "Countdown timer: 03:00 remaining to complete purchase or your seats will be forfeited!",
        "Mandatory facility maintenance fee of $12.50 per ticket will be added at checkout.",
        "A non-optional order processing surcharge will appear on your credit card receipt.",
        "Skip event protection? 'No thanks, I don't care if I lose all my money on this ticket.'",
        "We pre-selected 2 souvenir concert programs for $25 in your checkout cart.",
        "Ticket demand is high! 340 people are currently attempting to purchase these seats!",
        "An unadvertised service charge of 28% has been applied to your ticket order total.",
        "Refund requests are subject to an arbitrary 50% ticketing cancellation deduction.",
        "Tickets are non-transferable and cannot be re-sold except through our paid portal."
    ]

    # 6. Marketplaces (20 samples: 10 Benign, 10 Dark)
    market_benign = [
        "Seller has maintained a 99.4% positive feedback rating over 1,500 reviews.",
        "Buyer protection guarantee covers items not received or not as described.",
        "Return postage is prepaid by the seller if an item arrives damaged.",
        "Bidding increments are fixed at $2.50 per bid according to auction rules.",
        "Payment is held in escrow until the buyer confirms safe delivery of goods.",
        "Detailed photos of product serial numbers and condition flaws are shown above.",
        "Shipping costs are calculated transparently using official postal service rates.",
        "You can message the seller directly through our secure platform before purchasing.",
        "Authenticity verification is conducted by independent certified appraisers.",
        "All seller terms, return policies, and dispatch timelines are visible on this listing."
    ]
    market_dark = [
        "Buyer protection fee of $4.99 has been automatically added to your bid.",
        "HURRY! 45 users are bidding against you right now! Place your bid immediately!",
        "Decline warranty: 'No, I don't care if this electronic device breaks tomorrow.'",
        "A mandatory marketplace facilitation surcharge will be added upon winning the auction.",
        "Dispute resolution is barred unless buyer pays an upfront $30 mediation deposit.",
        "Pre-checked donation to marketplace community fund of $2.00 added to checkout.",
        "Only 1 item available! 8 customers have this exact product in their checkout line!",
        "Seller disclaims all statutory consumer rights and prohibits refund requests.",
        "Bids placed cannot be retracted even if placing bid resulted from accidental touch.",
        "Hidden payment processing surcharges are revealed only after the auction concludes."
    ]

    # 7. News & Media (20 samples: 10 Benign, 10 Dark)
    news_benign = [
        "Read 5 free articles per month before choosing a digital subscription.",
        "Digital membership is $4 per month with cancellation available in account settings.",
        "Student discount of 50% is available with verification of university email.",
        "Access our archives, daily crosswords, and podcasts with your basic membership.",
        "Billing date and renewal amounts are clearly displayed on your account profile.",
        "You can unsubscribe from email newsletters anytime using the footer link.",
        "Print subscribers receive complimentary digital access on all mobile apps.",
        "We notify you 30 days before any changes to our subscription subscription rates.",
        "Standard subscription can be canceled online with immediate effect.",
        "Privacy policy explains how we protect subscriber data and reader privacy."
    ]
    news_dark = [
        "Introductory rate $1/month; automatically jumps to $45/month with no cancellation button.",
        "To stop recurring payments you must dial customer retention during limited hours.",
        "Canceling online is prohibited; subscribers must mail a notarized cancellation letter.",
        "Pre-checked checkbox enrolls reader into 15 third-party affiliate marketing lists.",
        "Decline subscription: 'No thanks, I prefer remaining uninformed and uneducated.'",
        "Hidden early termination penalty of $60 applies if subscription ends before one year.",
        "Unsubscribe link is intentionally rendered in invisible light-grey text on white.",
        "Account deletion is impossible without calling customer service in another country.",
        "Annual renewal fee will be deducted 21 days prior to contract expiration without alert.",
        "Promotional trial requires entering credit card and mandates 6-month retention minimum."
    ]

    # 8. Education & EdTech (20 samples: 10 Benign, 10 Dark)
    edu_benign = [
        "Audit course materials and video lectures for free without paying tuition.",
        "Verified certificate fee is $49, displayed clearly before enrollment completion.",
        "Financial aid is available for eligible students who submit an application.",
        "You have 14 days from enrollment date to request a full tuition refund.",
        "Course syllabus, grading criteria, and instructor credentials are shown below.",
        "Subscription renews monthly at $39 until course completion or manual cancellation.",
        "Cancel course specialization anytime from learning dashboard with one click.",
        "All assignments, peer reviews, and discussion forums are included in tuition.",
        "Institutional accreditation status is publicly documented on our university page.",
        "Student records and transcripts can be exported securely via academic portal."
    ]
    edu_dark = [
        "Free course preview requires entering credit card and auto-bills $399 upon completion.",
        "Canceling specialization requires completing a 45-minute mandatory exit survey.",
        "To drop the course and stop billing you must obtain written permission from support.",
        "Unannounced diploma graduation processing fees of $85 are revealed at final exam.",
        "Enrollment countdown: 'Only 2 seats remaining in this cohort! Enroll immediately!'",
        "Decline tutoring: 'No, I prefer failing this exam and falling behind in my career.'",
        "Pre-checked add-on of $29 for study guide has been added to your enrollment bill.",
        "Tuition installment plans charge undisclosed 25% administrative financing fees.",
        "Course certificate withheld unless student pays additional certification unlock fee.",
        "Subscription auto-renews even after all course modules have been completed."
    ]

    # 9. Finance & Banking (20 samples: 10 Benign, 10 Dark)
    fin_benign = [
        "Checking accounts have no monthly maintenance fee when minimum balance is met.",
        "Annual percentage yield (APY) is 4.50% and interest compounds monthly.",
        "ATM withdrawals are free at over 55,000 participating Allpoint network locations.",
        "Overdraft protection transfers funds automatically from your linked savings account.",
        "All loan origination fees and APR terms are disclosed on the initial loan estimate.",
        "You can freeze or unfreeze your debit card instantly via the mobile banking app.",
        "Wire transfer fee of $25 is clearly itemized on the transfer confirmation screen.",
        "Account statements are issued on the last calendar day of every month.",
        "FDIC insurance protects your deposits up to the standard limit of $250,000.",
        "Closing your account is free of charge and can be initiated online or by phone."
    ]
    fin_dark = [
        "Undisclosed monthly paper statement fee of $7.50 is deducted from your balance.",
        "To close your account you must appear in person at a branch located out of state.",
        "Loan approval requires buying pre-selected credit life insurance for $35/month.",
        "Decline overdraft service: 'No, I want my transactions declined when buying food.'",
        "Hidden inactivity penalty of $20/month is charged without sending an alert notice.",
        "Interest rate triples after 30 days unless customer cancels in writing by mail.",
        "Pre-checked box opts customer into expensive high-fee overdraft programs.",
        "Account transfer fee of $45 is hidden inside the terms and conditions hyperlink.",
        "To cancel credit monitoring you must call during limited 2-hour morning window.",
        "Promotional 0% APR quietly incurs retroactive 29% interest on entire original sum."
    ]

    # 10. Healthcare & Wellness (20 samples: 10 Benign, 10 Dark)
    health_benign = [
        "Prescription copay of $15 is calculated based on your insurance formulary tier.",
        "Telehealth consultation fee is $49, payable at the time of your appointment.",
        "You can review your medical records and lab test results securely in the patient portal.",
        "Doctor appointments can be rescheduled or canceled online up to 24 hours prior.",
        "Generic medication alternatives are presented with transparent pricing comparisons.",
        "Dental cleaning and routine preventive checkups are covered 100% by in-network plans.",
        "Notice of privacy practices explains how protected health information is handled.",
        "Medical supply orders over $35 qualify for standard home delivery.",
        "Itemized hospital bills can be requested at no charge from the billing office.",
        "You may revoke consent for non-essential medical research sharing at any time."
    ]
    health_dark = [
        "To cancel monthly vitamin delivery you must submit an in-person doctor's letter.",
        "Free wellness trial automatically enrols patient into a $99/month supplement plan.",
        "Decline prescription protection: 'No, I am willing to risk going without medication.'",
        "Mandatory facility surcharge of $85 is billed after the telehealth session ends.",
        "Unannounced auto-shipment renewal occurs 15 days before the monthly prescription ends.",
        "Cancellation of gym membership requires paying an extortionate $250 exit fee.",
        "Pre-checked opt-in shares private patient symptom logs with third-party advertisers.",
        "Free health assessment requires attending a high-pressure sales presentation.",
        "Recurring prescription deliveries cannot be cancelled once first shipment departs.",
        "Sneak-in-basket: $12 expedited prescription handling added without patient consent."
    ]

    domains_map = [
        ("ecommerce", ecom_benign, ecom_dark),
        ("subscriptions", sub_benign, sub_dark),
        ("saas", saas_benign, saas_dark),
        ("travel", travel_benign, travel_dark),
        ("ticketing", ticket_benign, ticket_dark),
        ("marketplaces", market_benign, market_dark),
        ("news", news_benign, news_dark),
        ("education", edu_benign, edu_dark),
        ("finance", fin_benign, fin_dark),
        ("healthcare", health_benign, health_dark)
    ]

    count = 1
    for domain, benign_list, dark_list in domains_map:
        for text in benign_list:
            samples.append({
                "test_id": f"CFT-{count:03d}",
                "domain": domain,
                "text": text,
                "expected_label": 0,
                "notes": f"Clean benign example in {domain}"
            })
            count += 1
        for text in dark_list:
            samples.append({
                "test_id": f"CFT-{count:03d}",
                "domain": domain,
                "text": text,
                "expected_label": 1,
                "notes": f"Clean dark pattern example in {domain}"
            })
            count += 1

    out_path = ROOT_DIR / "data" / "clean_final_test_large.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["test_id", "domain", "text", "expected_label", "notes"])
        writer.writeheader()
        writer.writerows(samples)

    print(f"Successfully created {out_path} with {len(samples)} clean multi-domain samples.")

if __name__ == "__main__":
    build_clean_final_test()
