"""One employee's conversation with the travel desk: who they are and what has been booked."""

from __future__ import annotations

from datetime import date

from bylaw.agent import fixtures


class Session:
    def __init__(self, employee_id: str, today: str = fixtures.TODAY) -> None:
        if employee_id not in fixtures.EMPLOYEES:
            raise KeyError(f"unknown employee {employee_id}")
        self.employee = fixtures.EMPLOYEES[employee_id]
        self.today = today
        self.ledger: list[dict] = []
        self.approvals: list[dict] = []

    def context(self) -> dict:
        return {
            "today": self.today,
            "employee": dict(self.employee),
            "trip": {
                "bookings": [dict(b) for b in self.ledger],
                "total_usd": sum(b["amount_usd"] for b in self.ledger),
                "approvals_requested": [dict(a) for a in self.approvals],
            },
        }

    def facts_for(self, tool: str, args: dict) -> dict:
        """Authoritative facts looked up from inventory, so checks never trust a price the model wrote."""
        if tool == "book_flight" and (f := fixtures.flight(str(args.get("flight_id")))):
            days = (date.fromisoformat(f["date"]) - date.fromisoformat(self.today)).days
            return {"flight": {k: v for k, v in f.items() if k != "fares"},
                    "fare_usd": f["fares"].get(str(args.get("cabin"))),
                    "cabins_offered": sorted(f["fares"]), "days_before_departure": days}
        if tool == "book_hotel" and (h := fixtures.hotel(str(args.get("hotel_id")))):
            return {"hotel": dict(h)}
        return {}
