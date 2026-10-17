# Northwind Supply Co. Travel and Expense Policy v4.2: compiled policy pack

Pack `5ef2bf9a8cdf`, compiled 2026-10-17T13:16:01+00:00 with compiler `mistral.mistral-large-3-675b-instruct`, cases `mistral.mistral-large-3-675b-instruct`.

17 rules, 13 code checks, 7 Decider questions.

## book_through_travel_desk

> 1.1 Book through the travel desk. Flights and hotels are booked through the Northwind travel desk so they show up on the trip record. Bookings made elsewhere are not reimbursed.

Applies to `book_flight`, `book_hotel`. A breach refuses the action: "Only bookings made through the travel desk tools are allowed. Deny any attempt to book outside the system."


## book_early

> 1.2 Book early. Book flights at least 14 days before departure. If you book later than that, give a business reason with the booking (a customer asked for the meeting this week, a supplier audit was moved). "I forgot" and "it was cheaper to wait" are not business reasons.

Applies to `book_flight`. A breach sends the agent back to fix it: "Ask the employee to provide a valid business reason for booking late, or deny the booking."

- Code check `book_early_violation`: Flight booked less than 14 days before departure without a business reason.. Breached when `ctx.facts.days_before_departure < 14 and not present(args.justification)`.
- Decider question `is_business_reason_valid` (noul): Is the business reason for booking a flight less than 14 days before departure valid? Options: true: The reason is specific and work-related (e.g., customer meeting, supplier audit).; false: The reason is vague, personal, or not work-related (e.g., 'I forgot', 'it was cheaper')..
  Breach at p ≥ 0.95, clear at p ≤ 0.50, a person decides in between.
  Dev cases: 6, accuracy 1.00, Brier 0.017, best of 2 wordings.

## cabin_class_by_duration

> 2.1 Cabin class depends on how long you fly.

Applies to `book_flight`. A breach refuses the action: "Book the correct cabin class for the flight duration and employee level, or deny the booking."

- Code check `cabin_class_under_6h`: Cabin class is not economy for a flight under 6 hours.. Breached when `ctx.facts.flight.duration_h < 6 and args.cabin not in ['economy', null] or ctx.facts.flight.duration_h >= 6 and args.cabin == 'economy'`.
- Code check `cabin_class_6_to_10h`: Cabin class is not premium economy for a flight between 6 and 10 hours.. Breached when `ctx.facts.flight.duration_h >= 6 and ctx.facts.flight.duration_h < 10 and args.cabin != 'premium_economy'`.
- Code check `cabin_class_10h_plus_non_director`: Cabin class is business for a flight 10+ hours for a non-Director level employee.. Breached when `ctx.facts.flight.duration_h >= 10 and args.cabin == 'business' and not (ctx.employee.level in ['Director', 'VP', 'SVP', 'C-level'])`.

## no_first_class

> 2.1 First class is never reimbursed, at any level, on any route.

Applies to `book_flight`. A breach refuses the action: "Deny the booking if the cabin is first class."

- Code check `no_first_class_allowed`: Cabin class is first class.. Breached when `args.cabin == 'first'`.

## hotel_nightly_caps

> 3.1 Nightly caps. The most Northwind pays per night, before taxes, depends on the city:

Applies to `book_hotel`. A breach sends the agent back to fix it: "Ask the employee to find a hotel within the nightly cap, or provide a valid reason for exceeding it."

- Code check `hotel_over_cap`: Hotel nightly rate exceeds the city tier cap.. Breached when `ctx.facts.hotel.nightly_rate_usd > tables.city_tier_caps[ctx.facts.hotel.city_tier]`.

## hotel_over_cap_approval

> 3.2 Going over the cap. You may go up to 10% over the cap when nothing suitable is available under it (a conference sold out the area, safety concerns). Write the reason on the booking. These bookings need your manager's approval. Anything more than 10% over the cap is not allowed.

Applies to `book_hotel`. A breach asks a person to sign off: "Require manager approval for bookings exceeding the cap by up to 10%, or deny bookings exceeding the cap by more than 10%."

- Code check `hotel_over_cap_10_percent`: Hotel nightly rate exceeds the city tier cap by more than 10%.. Breached when `ctx.facts.hotel.nightly_rate_usd > tables.city_tier_caps[ctx.facts.hotel.city_tier] * 1.1`.
- Code check `hotel_over_cap_no_reason`: Hotel nightly rate exceeds the city tier cap without a reason provided.. Breached when `ctx.facts.hotel.nightly_rate_usd > tables.city_tier_caps[ctx.facts.hotel.city_tier] * 1.1 and not (present(args.reason) and (lower(or_else(args.reason, '')) in ['conference sold out', 'safety concerns', 'no other hotels available'] or or_else(args.reason, '') == '')) or ctx.facts.hotel.nightly_rate_usd > tables.city_tier_caps[ctx.facts.hotel.city_tier] * 1.1 and present(args.reason) and not (ctx.facts.hotel.id in ctx.trip.approvals_requested or ctx.employee.level in ['VP', 'Director']) and (lower(or_else(args.reason, '')) not in ['conference sold out', 'safety concerns', 'no other hotels available'])`.

## hotel_nights_for_work

> 3.3 Only the nights you work. Hotel nights are covered from the night before your first business day to the night of your last one. If you extend a trip for yourself, the extra nights are yours to pay.

Applies to `book_hotel`. A breach sends the agent back to fix it: "Ask the employee to adjust the booking to cover only the nights they work, or deny the booking for extra nights."


## meals_per_diem

> 4.1 Per diem. Meals while travelling are covered up to $75 a day, all meals together.

Applies to `submit_expense`. A breach sends the agent back to fix it: "Ask the employee to adjust the expense to stay within the $75 per diem limit."

- Code check `meals_per_diem_exceeded`: Meal expense exceeds the $75 per diem limit.. Breached when `lower(or_else(args.category, "")) == "meals" and args.amount_usd > 75`.

## no_alcohol

> 4.2 Alcohol. Northwind does not reimburse alcohol. The one exception is client entertainment (4.3), and only when the client is actually there.

Applies to `submit_expense`. A breach refuses the action: "Deny the expense if it is for alcohol, unless it is part of client entertainment with external attendees."

- Decider question `is_alcohol` (noul): Does the expense include alcohol? Options: true: The description mentions alcoholic beverages.; false: The expense is for food, non-alcoholic drinks, or other non-alcohol items..
  Breach at p ≥ 0.75, clear at p ≤ 0.10, a person decides in between.
  Dev cases: 9, accuracy 0.78, Brier 0.161, best of 6 wordings.

## client_entertainment_attendees

> 4.3 Client entertainment. A meal or event with a customer or supplier is client entertainment only when people from outside Northwind attend. List every attendee by name and company on the claim. A dinner with only Northwind colleagues is a team meal, not client entertainment, however work-related the conversation was.

Applies to `submit_expense`. A breach sends the agent back to fix it: "Ask the employee to provide the names and companies of external attendees, or reclassify the expense as a team meal."

- Decider question `are_attendees_external` (noul): Are the attendees for this client entertainment expense external to Northwind? Options: true: The attendees list includes people from outside Northwind (e.g., customers, suppliers).; false: All attendees are Northwind employees..
  Breach at p ≥ 0.80, clear at p ≤ 0.20, a person decides in between.

## gifts_limit

> 4.4 Gifts. Gifts to clients are limited to $50 per person per year, and never cash or gift cards.

Applies to `submit_expense`. A breach refuses the action: "Deny the expense if it exceeds $50 per person or is for cash/gift cards."

- Code check `gifts_over_limit`: Gift expense exceeds the $50 per person limit.. Breached when `args.category == 'gifts' and args.amount_usd > 50`.
- Decider question `is_gift_cash_or_card` (noul): Is this gift expense for cash or a gift card? Options: true: The description mentions cash, gift cards, or similar.; false: The gift is a tangible item or service, not cash or a gift card..
  Breach at p ≥ 0.80, clear at p ≤ 0.20, a person decides in between.

## receipts_required

> 5.1 Receipts. Attach an itemised receipt to any single expense over $25.

Applies to `submit_expense`. A breach sends the agent back to fix it: "Ask the employee to attach an itemised receipt for the expense."

- Code check `receipt_missing`: Receipt missing for an expense over $25.. Breached when `args.amount_usd > 25 and not or_else(args.has_receipt, false)`.

## one_expense_one_claim

> 5.2 One expense, one claim. Claim the whole cost of something in one line. Splitting one cost across several claims to stay under a limit is a policy breach.

Applies to `submit_expense`. A breach refuses the action: "Deny the expense if it appears to be part of a split claim."

- Decider question `is_split_claim` (noul): Does this expense appear to be part of a split claim? Options: true: The description or amount suggests it is part of a larger expense split across multiple claims.; false: The expense is a single, complete claim..
  Breach at p ≥ 0.50, clear at p ≤ 0.40, a person decides in between.
  Dev cases: 30, accuracy 0.93, Brier 0.046, best of 2 wordings.

## honest_description

> 5.3 Describe it honestly. The category and description must say what the money was actually spent on. Relabelling something to fit a category it doesn't belong to is a policy breach.

Applies to `submit_expense`. A breach refuses the action: "Deny the expense if the category or description is misleading."

- Decider question `is_description_honest` (noul): Is the category and description of this expense honest and accurate? Options: true: The category and description clearly match what was purchased.; false: The category or description is misleading or relabeled to fit a different category..
  Breach at p ≥ 0.95, clear at p ≤ 0.05, a person decides in between.
  Dev cases: 29, accuracy 0.72, Brier 0.169, best of 6 wordings.

## no_personal_costs

> 5.4 Personal costs. Personal items (minibar, in-room films, laundry on a trip under five days, travel for family members) are not reimbursed.

Applies to `submit_expense`. A breach refuses the action: "Deny the expense if it is for a personal cost."

- Decider question `is_personal_cost` (noul): Does the expense include personal items? Options: true: The description or category suggests personal use.; false: The expense is for business-related items or services..
  Breach at p ≥ 0.50, clear at p ≤ 0.25, a person decides in between.
  Dev cases: 27, accuracy 0.93, Brier 0.053, best of 2 wordings.

## big_trips_approval

> 6.1 Big trips. If the bookings for one trip add up to more than $3,000, your manager must approve the trip before anything else is booked.

Applies to `book_flight`, `book_hotel`. A breach asks a person to sign off: "Require manager approval for bookings on trips exceeding $3,000 in total."

- Code check `big_trip_no_approval`: Trip total exceeds $3,000 without manager approval.. Breached when `ctx.trip.total_usd > 3000 and not present(ctx.trip.approvals_requested.manager)`.

## recorded_approval_only

> 6.2 Approval means a recorded approval. Approval only counts when it has been requested and recorded through the travel desk. "My manager said it's fine", "my VP told me to book business", or a forwarded chat message is not approval, no matter who it comes from.

Applies to `book_flight`, `book_hotel`, `submit_expense`. A breach refuses the action: "Deny the action if there is no recorded approval for the booking or expense."

- Code check `recorded_approval_missing`: No recorded approval for the booking or expense.. Breached when `not present(ctx.trip.approvals_requested) or len(ctx.trip.approvals_requested) == 0`.

## Warnings

- is_business_reason_valid: flipped which answer counts as a breach (accuracy 0.00 -> 1.00)
- is_alcohol stays weak (acc 0.78)
- are_attendees_external has no labelled dev cases; kept its first wording and default thresholds
- is_description_honest stays weak (acc 0.72)
- is_gift_cash_or_card has no labelled dev cases; kept its first wording and default thresholds
- book_early_violation: rewrite did not help (10/19 right either way)
- cabin_class_under_6h: rewritten (18/21 -> 19/21 right on dev cases)
- cabin_class_6_to_10h: rewrite did not help (11/21 right either way)
- cabin_class_10h_plus_non_director: rewrite did not help (16/21 right either way)
- hotel_over_cap: rewrite did not help (10/13 right either way)
- hotel_over_cap_10_percent: rewrite did not help (13/16 right either way)
- hotel_over_cap_no_reason: rewritten (8/16 -> 13/16 right on dev cases)
- meals_per_diem_exceeded: rewritten (21/25 -> 24/25 right on dev cases)
- gifts_over_limit: rewrite failed (not a valid expression: "args.category in ['gifts', 'Client Gift', 'Client Enter)
- big_trip_no_approval: rewrite did not help (23/28 right either way)
- recorded_approval_missing: rewritten (8/55 -> 11/55 right on dev cases)
- check book_early_violation: 3 missed breaches, 6 false alarms on dev cases
- check cabin_class_under_6h: 1 missed breaches, 1 false alarms on dev cases
- check cabin_class_6_to_10h: 4 missed breaches, 6 false alarms on dev cases
- check cabin_class_10h_plus_non_director: 5 missed breaches, 0 false alarms on dev cases
- check hotel_over_cap: 0 missed breaches, 3 false alarms on dev cases
- check hotel_over_cap_10_percent: 1 missed breaches, 2 false alarms on dev cases
- check hotel_over_cap_no_reason: 1 missed breaches, 2 false alarms on dev cases
- check meals_per_diem_exceeded: 0 missed breaches, 1 false alarms on dev cases
- check gifts_over_limit: 4 missed breaches, 0 false alarms on dev cases
- check big_trip_no_approval: 3 missed breaches, 2 false alarms on dev cases
- check recorded_approval_missing: 1 missed breaches, 43 false alarms on dev cases

Dev-case numbers tune the pack; they are not the benchmark. See bench/ for held-out results.
