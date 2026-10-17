"""The travel desk's tools. Bad ids or mismatched prices come back as an error string the model
can read; tools never raise into the agent loop."""

from __future__ import annotations

from strands import tool

from bylaw.agent import fixtures
from bylaw.agent.session import Session

# What the compiler is told about each tool, including the looked-up facts a check may read.
TOOL_DESCRIPTIONS = {
    "search_flights": "search_flights(origin, dest, date): read-only flight search. Never gate it.",
    "book_flight": "book_flight(flight_id, cabin, fare_usd?, justification?): books a seat. Checks can read "
                   "ctx.facts.flight.{origin,dest,date,duration_h}, ctx.facts.fare_usd, ctx.facts.cabins_offered, "
                   "ctx.facts.days_before_departure, and args.cabin, args.justification.",
    "search_hotels": "search_hotels(city, check_in, nights): read-only hotel search. Never gate it.",
    "book_hotel": "book_hotel(hotel_id, check_in, nights, reason?): books a hotel. Checks can read "
                  "ctx.facts.hotel.{city,city_tier,name,nightly_rate_usd}, args.nights, args.check_in, args.reason.",
    "submit_expense": "submit_expense(category, amount_usd, date, description, attendees?, has_receipt?): files a "
                      "claim. category is one of meals, client_entertainment, ground_transport, gifts, other.",
    "request_approval": "request_approval(approver, reason): asks a named person; approval stays pending. "
                        "Never gate it.",
}


def make_tools(session: Session) -> list:
    @tool
    def search_flights(origin: str, dest: str, date: str) -> str:
        """Find Cascadia Air flights for one day.

        Args:
            origin: Departure airport code, e.g. "SEA".
            dest: Arrival airport code, e.g. "AUS".
            date: Departure date, YYYY-MM-DD.
        """
        rows = [f for f in fixtures.FLIGHTS
                if f["origin"] == origin.upper() and f["dest"] == dest.upper() and f["date"] == date]
        if not rows:
            return f"No flights from {origin} to {dest} on {date}."
        return "\n".join(
            f"id={f['id']} departs {f['date']} {f['depart']}, {f['duration_h']} h, NW fares: "
            + ", ".join(f"{cabin} ${fare}" for cabin, fare in f["fares"].items())
            for f in rows)

    @tool
    def book_flight(flight_id: str, cabin: str, fare_usd: float | None = None, justification: str = "") -> str:
        """Book a seat on a flight found with search_flights.

        Args:
            flight_id: The id from search_flights, e.g. "NW212".
            cabin: One of the cabins listed for that flight.
            fare_usd: The fare shown in the search results, if you want it double-checked.
            justification: Business reason, needed for late bookings or premium cabins.
        """
        f = fixtures.flight(flight_id)
        if f is None:
            return f"Error: no flight {flight_id}. Search first."
        if cabin not in f["fares"]:
            return f"Error: {flight_id} has no {cabin} cabin. Offered: {', '.join(f['fares'])}."
        fare = f["fares"][cabin]
        if fare_usd is not None and abs(float(fare_usd) - fare) > 0.5:
            return f"Error: the {cabin} fare on {flight_id} is ${fare}, not ${fare_usd}."
        session.ledger.append({"kind": "flight", "ref": flight_id, "detail": f"{f['origin']}-{f['dest']} {cabin}",
                               "date": f["date"], "amount_usd": fare})
        return f"Booked {flight_id} {f['origin']}-{f['dest']} on {f['date']} in {cabin}, ${fare}."

    @tool
    def search_hotels(city: str, check_in: str, nights: int) -> str:
        """List hotels in a city with their nightly rates.

        Args:
            city: City name, e.g. "Austin".
            check_in: Check-in date, YYYY-MM-DD.
            nights: Number of nights.
        """
        rows = [h for h in fixtures.HOTELS if h["city"].lower() == city.lower()]
        if not rows:
            return f"No hotels on file in {city}."
        return "\n".join(f"id={h['id']} {h['name']}, ${h['nightly_rate_usd']}/night (city tier {h['city_tier']})"
                         for h in rows)

    @tool
    def book_hotel(hotel_id: str, check_in: str, nights: int, reason: str = "") -> str:
        """Book a hotel found with search_hotels.

        Args:
            hotel_id: The id from search_hotels.
            check_in: Check-in date, YYYY-MM-DD.
            nights: Number of nights.
            reason: Why this hotel, needed when it is over the nightly cap.
        """
        h = fixtures.hotel(hotel_id)
        if h is None:
            return f"Error: no hotel {hotel_id}. Search first."
        total = h["nightly_rate_usd"] * int(nights)
        session.ledger.append({"kind": "hotel", "ref": hotel_id, "detail": f"{h['name']} x{nights}",
                               "date": check_in, "amount_usd": total})
        return f"Booked {h['name']} from {check_in} for {nights} nights, ${total} total."

    @tool
    def submit_expense(category: str, amount_usd: float, date: str, description: str, attendees: str = "",
                       has_receipt: bool = False) -> str:
        """File an expense claim.

        Args:
            category: meals, client_entertainment, ground_transport, gifts, or other.
            amount_usd: Amount in US dollars.
            date: Date of the expense, YYYY-MM-DD.
            description: What it was for, in the employee's words.
            attendees: Names and companies of everyone present, for meals and entertainment.
            has_receipt: Whether an itemised receipt is attached.
        """
        session.ledger.append({"kind": "expense", "ref": category, "detail": description, "date": date,
                               "amount_usd": float(amount_usd)})
        return f"Filed a {category} expense of ${amount_usd} for {date}."

    @tool
    def request_approval(approver: str, reason: str) -> str:
        """Ask a named person to approve something. Approval is not granted until they reply.

        Args:
            approver: Employee id of the approver, e.g. "priya".
            reason: What needs approving and why.
        """
        session.approvals.append({"approver": approver, "reason": reason, "status": "pending"})
        return f"Approval request sent to {approver}. Status: pending."

    return [search_flights, book_flight, search_hotels, book_hotel, submit_expense, request_approval]


def _schemas() -> dict[str, dict]:
    from bylaw.agent.session import Session

    return {t.tool_name: t.tool_spec["inputSchema"]["json"] for t in make_tools(Session("maya"))}


# The tools' own input schemas, as Strands sends them to the model. Generated cases are checked
# against these so a case never uses an argument name the live agent couldn't send.
TOOL_SCHEMAS: dict[str, dict] = _schemas()


def args_problem(tool: str, args: dict) -> str | None:
    """None when `args` fits the tool's schema, else what's wrong."""
    schema = TOOL_SCHEMAS.get(tool)
    if schema is None:
        return f"unknown tool {tool}"
    props, required = schema.get("properties", {}), schema.get("required", [])
    unknown = [k for k in args if k not in props]
    missing = [k for k in required if k not in args]
    problems = ([f"unknown argument {', '.join(unknown)}"] if unknown else []) +                ([f"missing {', '.join(missing)}"] if missing else [])
    return "; ".join(problems) or None


def signatures() -> str:
    """One line per tool with exact argument names and types; optional ones end in '?'."""
    lines = []
    for name, schema in TOOL_SCHEMAS.items():
        required = set(schema.get("required", []))
        params = ", ".join(f"{k}{'' if k in required else '?'}: {v.get('type', 'any')}"
                           for k, v in schema.get("properties", {}).items())
        lines.append(f"{name}({params})")
    return "\n".join(lines)
