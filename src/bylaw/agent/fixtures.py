"""Deterministic inventory for the demo and the benchmark. Northwind Supply Co. is fictional;
so are its airline (Cascadia Air, code NW) and every hotel."""

from __future__ import annotations

TODAY = "2026-10-20"

EMPLOYEES: dict[str, dict] = {
    "maya": {"id": "maya", "name": "Maya Lindgren", "title": "Senior Analyst", "level": "IC3",
             "department": "Supply Planning", "home_airport": "SEA", "manager": "priya"},
    "priya": {"id": "priya", "name": "Priya Raman", "title": "Director of Supply Planning", "level": "Director",
              "department": "Supply Planning", "home_airport": "SEA", "manager": "sam"},
    "sam": {"id": "sam", "name": "Sam Okoro", "title": "VP, Operations", "level": "VP",
            "department": "Operations", "home_airport": "SEA", "manager": None},
}

# One row per flight; fares per cabin. Durations are scheduled block hours.
FLIGHTS: list[dict] = [
    {"id": "NW212", "origin": "SEA", "dest": "AUS", "date": "2026-11-04", "depart": "07:40", "duration_h": 4.4,
     "fares": {"economy": 412, "premium_economy": 689, "business": 1480}},
    {"id": "NW218", "origin": "SEA", "dest": "AUS", "date": "2026-11-04", "depart": "13:05", "duration_h": 4.5,
     "fares": {"economy": 371, "premium_economy": 640}},
    {"id": "NW480", "origin": "SEA", "dest": "LHR", "date": "2026-10-27", "depart": "19:20", "duration_h": 9.6,
     "fares": {"economy": 980, "premium_economy": 1650, "business": 4890}},
    {"id": "NW906", "origin": "SEA", "dest": "SIN", "date": "2026-11-16", "depart": "23:55", "duration_h": 16.2,
     "fares": {"economy": 1350, "premium_economy": 2440, "business": 6210}},
    {"id": "NW118", "origin": "SEA", "dest": "SFO", "date": "2026-10-23", "depart": "08:10", "duration_h": 2.1,
     "fares": {"economy": 189, "first": 640}},
]

HOTELS: list[dict] = [
    {"id": "aus-congress", "city": "Austin", "city_tier": "B", "name": "Congress Avenue Suites",
     "nightly_rate_usd": 179},
    {"id": "aus-lamar", "city": "Austin", "city_tier": "B", "name": "Lamar House", "nightly_rate_usd": 205},
    {"id": "aus-shore", "city": "Austin", "city_tier": "B", "name": "South Shore Lofts", "nightly_rate_usd": 349},
    {"id": "lon-bloomsbury", "city": "London", "city_tier": "A", "name": "Bloomsbury Row", "nightly_rate_usd": 238},
    {"id": "lon-thameside", "city": "London", "city_tier": "A", "name": "Thameside Grand", "nightly_rate_usd": 412},
    {"id": "sin-tanjong", "city": "Singapore", "city_tier": "A", "name": "Tanjong Pagar Rooms",
     "nightly_rate_usd": 251},
    {"id": "sfo-mission", "city": "San Francisco", "city_tier": "A", "name": "Mission Rooms", "nightly_rate_usd": 255},
    {"id": "sfo-nobhill", "city": "San Francisco", "city_tier": "A", "name": "Nob Hill Tower", "nightly_rate_usd": 389},
    {"id": "boi-grove", "city": "Boise", "city_tier": "C", "name": "Grove Street Inn", "nightly_rate_usd": 132},
]


def flight(flight_id: str) -> dict | None:
    return next((f for f in FLIGHTS if f["id"] == flight_id), None)


def hotel(hotel_id: str) -> dict | None:
    return next((h for h in HOTELS if h["id"] == hotel_id), None)
