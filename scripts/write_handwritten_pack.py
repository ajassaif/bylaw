"""A policy pack written by hand from policies/northwind-travel.md.

Two uses: the local smoke test before Bedrock is available, and a comparison row in the
benchmark (what a careful person writes by hand vs what the compiler produces).
Run: uv run python scripts/write_handwritten_pack.py
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from bylaw.pack import Check, Pack, Question, Rule, Violation, pack_hash, save_pack

POLICY = Path("policies/northwind-travel.md")
HOTEL_OVER = "ctx.facts.hotel.nightly_rate_usd > tables.hotel_cap[ctx.facts.hotel.city_tier]"
HOTEL_WITHIN = ("ctx.facts.hotel.nightly_rate_usd <= tables.hotel_cap[ctx.facts.hotel.city_tier] * "
                "(1 + tables.hotel_over_cap_allowance)")
NO_APPROVAL = "count_where(ctx.trip.approvals_requested, 'status', 'approved') == 0"


def noul(qid, rule_id, instructions, true, false, violation_when_true=True, when=None):
    return Question(id=qid, rule_id=rule_id, type="noul", instructions=instructions,
                    criteria={"true": true, "false": false}, violation=Violation(when_true=violation_when_true),
                    when=when)


rules = [
    Rule(id="advance_booking", text="1.2 Book early. Book flights at least 14 days before departure, or give a "
         "business reason.", tools=["book_flight"], on_violation="guide",
         remedy="This flight is less than 14 days away. Ask for the business reason and add it as the justification."),
    Rule(id="cabin_class", text="2.1 Cabin class depends on how long you fly. First class is never reimbursed.",
         tools=["book_flight"], on_violation="guide",
         remedy="Book the cabin this flight length and the employee's level allow: economy under 6 h, premium "
                "economy from 6 h, business from 10 h for Director and above only."),
    Rule(id="hotel_over_limit", text="3.2 Anything more than 10% over the cap is not allowed.", tools=["book_hotel"],
         on_violation="guide", remedy="This hotel is more than 10% over the nightly cap. Offer one under the cap."),
    Rule(id="hotel_needs_reason", text="3.2 You may go up to 10% over the cap when nothing suitable is available. "
         "Write the reason on the booking.", tools=["book_hotel"], on_violation="guide",
         remedy="This hotel is over the nightly cap. Pick one under the cap, or record why nothing under it works."),
    Rule(id="hotel_needs_manager", text="3.2 These bookings need your manager's approval.", tools=["book_hotel"],
         on_violation="confirm", remedy="This hotel is up to 10% over the cap with a reason. The employee's manager "
                                         "needs to sign off."),
    Rule(id="hotel_nights", text="3.3 Only the nights you work.", tools=["book_hotel"], on_violation="guide",
         remedy="Book only the business nights. Extra nights for personal reasons are the employee's to pay."),
    Rule(id="per_diem", text="4.1 Meals while travelling are covered up to $75 a day.", tools=["submit_expense"],
         on_violation="guide", remedy="Meals are covered up to $75 a day. Claim up to that amount."),
    Rule(id="alcohol", text="4.2 Northwind does not reimburse alcohol, except client entertainment with the client "
         "there.", tools=["submit_expense"], on_violation="deny", remedy="Alcohol is not reimbursable here."),
    Rule(id="attendees_listed", text="4.3 List every attendee by name and company on the claim.",
         tools=["submit_expense"], on_violation="guide",
         remedy="Add every attendee's name and company to the claim."),
    Rule(id="entertainment_external", text="4.3 Client entertainment only when people from outside Northwind attend.",
         tools=["submit_expense"], on_violation="deny",
         remedy="Nobody from outside Northwind was there, so this is not client entertainment."),
    Rule(id="gift_limit", text="4.4 Gifts to clients are limited to $50 per person per year.",
         tools=["submit_expense"], on_violation="guide", remedy="Client gifts are capped at $50."),
    Rule(id="gift_cash", text="4.4 Never cash or gift cards.", tools=["submit_expense"], on_violation="deny",
         remedy="Cash, gift cards and vouchers can't be claimed as gifts."),
    Rule(id="receipts", text="5.1 Attach an itemised receipt to any single expense over $25.",
         tools=["submit_expense"], on_violation="guide", remedy="Attach the itemised receipt, then file it."),
    Rule(id="split_claims", text="5.2 One expense, one claim.", tools=["submit_expense"], on_violation="deny",
         remedy="One cost has to be claimed in one line, not split to stay under a limit."),
    Rule(id="honest_description", text="5.3 Describe it honestly.", tools=["submit_expense"], on_violation="deny",
         remedy="The category and description have to say what the money was actually spent on."),
    Rule(id="personal_costs", text="5.4 Personal costs are not reimbursed.", tools=["submit_expense"],
         on_violation="deny", remedy="That is a personal cost, so it can't be expensed."),
    Rule(id="trip_approval", text="6.1 Trips over $3,000 need your manager's recorded approval first.",
         tools=["book_flight", "book_hotel"], on_violation="confirm",
         remedy="This trip passes $3,000 and has no recorded approval. The employee's manager needs to sign off."),
]

checks = [
    Check(id="late_without_reason", rule_id="advance_booking",
          expr="ctx.facts.days_before_departure < tables.advance_days and not present(args.justification)",
          description="booked under 14 days ahead with no justification"),
    Check(id="cabin_too_high", rule_id="cabin_class",
          expr="args.cabin == 'first' or (args.cabin == 'premium_economy' and ctx.facts.flight.duration_h < 6) or "
               "(args.cabin == 'business' and (ctx.facts.flight.duration_h < 10 or "
               "ctx.employee.level not in tables.business_levels))",
          description="cabin above what the flight length and level allow"),
    Check(id="hotel_far_over", rule_id="hotel_over_limit", expr=f"not ({HOTEL_WITHIN})",
          description="more than 10% over the city's nightly cap"),
    Check(id="hotel_over_no_reason", rule_id="hotel_needs_reason",
          expr=f"{HOTEL_OVER} and {HOTEL_WITHIN} and not present(args.reason)",
          description="over the cap, within 10%, no reason given"),
    Check(id="hotel_over_with_reason", rule_id="hotel_needs_manager",
          expr=f"{HOTEL_OVER} and {HOTEL_WITHIN} and present(args.reason)",
          description="over the cap, within 10%, with a reason"),
    Check(id="meals_over_per_diem", rule_id="per_diem",
          expr="args.category == 'meals' and num(args.amount_usd) > tables.per_diem_usd",
          description="meals over the daily per diem"),
    Check(id="entertainment_no_attendees", rule_id="attendees_listed",
          expr="args.category == 'client_entertainment' and not present(args.attendees)",
          description="client entertainment with no attendees listed"),
    Check(id="gift_over_limit", rule_id="gift_limit",
          expr="args.category == 'gifts' and num(args.amount_usd) > tables.gift_limit_usd",
          description="gift over $50"),
    Check(id="no_receipt", rule_id="receipts",
          expr="num(args.amount_usd) > tables.receipt_over_usd and not or_else(args.has_receipt, False)",
          description="over $25 without a receipt"),
    Check(id="flight_trip_over", rule_id="trip_approval",
          expr=f"ctx.trip.total_usd + or_else(ctx.facts.fare_usd, 0) > tables.trip_approval_usd and {NO_APPROVAL}",
          description="trip passes $3,000 with this flight and no recorded approval", tools=["book_flight"]),
]

# book_hotel shares rule trip_approval; its cost comes from the hotel rate, not the fare.
checks.append(Check(
    id="hotel_trip_over", rule_id="trip_approval",
    expr=f"ctx.trip.total_usd + ctx.facts.hotel.nightly_rate_usd * num(args.nights) > tables.trip_approval_usd "
         f"and {NO_APPROVAL}",
    description="trip passes $3,000 with this hotel and no recorded approval", tools=["book_hotel"]))

questions = [
    noul("late_reason_real", "advance_booking",
         "Is the justification a real business reason for booking this late?",
         "a customer, supplier or schedule change made the trip urgent",
         "convenience, forgetting, waiting for a cheaper fare, or no real reason",
         violation_when_true=False,
         when="ctx.facts.days_before_departure < tables.advance_days and present(args.justification)"),
    noul("hotel_reason_genuine", "hotel_needs_reason",
         "Does the reason say nothing suitable was available under the nightly cap?",
         "rooms under the cap were sold out, unsuitable, or unsafe",
         "the reason is preference, comfort, a view, or someone's say-so",
         violation_when_true=False, when=f"{HOTEL_OVER} and present(args.reason)"),
    noul("personal_nights", "hotel_nights",
         "Does the stay include nights the employee wants for personal reasons, beyond the business dates?",
         "some nights are for a holiday, friends, or staying on after the work is done",
         "every night is the night before or during the business days"),
    Question(id="alcohol_context", rule_id="alcohol", type="choice",
             instructions="Does this expense include alcohol, and who was there?",
             criteria={"no_alcohol": "no wine, beer, spirits or bar tab on the claim",
                       "with_external_guests": "alcohol, with a customer or supplier from outside Northwind present",
                       "northwind_only": "alcohol, with only Northwind people present or nobody named"},
             violation=Violation(options=["northwind_only"])),
    noul("has_external_attendee", "entertainment_external",
         "Is at least one attendee from a company other than Northwind?",
         "an attendee is named with an outside company such as a customer or supplier",
         "every attendee is from Northwind", violation_when_true=False,
         when="args.category == 'client_entertainment' and present(args.attendees)"),
    noul("gift_is_cash", "gift_cash", "Is the gift cash, a gift card or a voucher?",
         "money, a gift card, a voucher or anything spendable like cash", "a physical item or an experience",
         when="args.category == 'gifts'"),
    noul("split_cost", "split_claims",
         "Is one cost being split across more than one claim?",
         "the conversation or description shows a single bill being claimed in parts",
         "this claim is the whole of one cost"),
    noul("dishonest_description", "honest_description",
         "Do the category or description misstate what the money was spent on?",
         "it is relabelled to fit a category it doesn't belong to, or it says something untrue such as a "
         "receipt being attached",
         "the category and description match what was bought"),
    noul("personal_cost", "personal_costs",
         "Is this a personal cost: minibar, in-room films, laundry on a trip under five days, or family travel?",
         "a personal item or service the employee would have bought for themselves",
         "a business cost"),
]

tables = {"hotel_cap": {"A": 260, "B": 190, "C": 140}, "hotel_over_cap_allowance": 0.10, "advance_days": 14,
          "business_levels": ["Director", "VP", "SVP", "CEO"], "per_diem_usd": 75, "gift_limit_usd": 50,
          "receipt_over_usd": 25, "trip_approval_usd": 3000}

pack = Pack(policy_title="Northwind Supply Co. Travel and Expense Policy (hand-written pack)",
            policy_sha256=hashlib.sha256(POLICY.read_bytes()).hexdigest(), compiled_at="2026-10-17T00:00:00+00:00",
            models={"author": "hand-written"}, rules=rules, checks=checks, questions=questions, tables=tables)
save_pack(pack, "packs/northwind.handwritten.pack.json")
print(f"pack {pack_hash(pack)}: {len(rules)} rules, {len(checks)} checks, {len(questions)} questions")
