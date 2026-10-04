"""
What-if simulation — deep-copy the twin state, apply a scenario, compare.

Pure functions: plain dicts in → results out.  No DB / API dependency.
"""

from __future__ import annotations

import copy
import math
from typing import Any


# ===================================================================
# Enrollment growth
# ===================================================================

def run_enrollment_growth(
    state: dict[str, Any],
    percent: float,
    department_id: int | None = None,
) -> dict[str, Any]:
    """
    Simulate an enrollment increase of *percent* % (optionally scoped to one
    department) and check classroom-capacity feasibility.
    """
    if not math.isfinite(percent) or percent < 0:
        raise ValueError("percent must be a finite non-negative number")
    simulated = copy.deepcopy(state)
    warnings: list[str] = []

    baseline_total = len(state.get("enrollments", []))

    # Per-course enrollment counts
    course_enrollment: dict[int, int] = {}
    for e in simulated.get("enrollments", []):
        cid = e["course_id"]
        course_enrollment[cid] = course_enrollment.get(cid, 0) + 1

    # Apply growth
    courses = simulated.get("courses", [])
    if department_id is not None:
        courses = [c for c in courses if c.get("department_id") == department_id]

    additional = 0
    for course in courses:
        cid = course["id"]
        current = course_enrollment.get(cid, 0)
        added = int(current * percent / 100.0)
        additional += added
        course_enrollment[cid] = current + added

    scenario_total = baseline_total + additional

    # Check capacity
    classrooms_by_id = {c["id"]: c for c in simulated.get("classrooms", [])}
    overcapacity: list[dict] = []
    for slot in simulated.get("timetable_slots", []):
        cid = slot.get("course_id")
        rid = slot.get("classroom_id")
        enroll = course_enrollment.get(cid, 0)
        room = classrooms_by_id.get(rid)
        if room and enroll > room["capacity"]:
            overcapacity.append({
                "timetable_id": slot["id"],
                "course_id": cid,
                "classroom_id": rid,
                "enrollment": enroll,
                "capacity": room["capacity"],
                "overflow": enroll - room["capacity"],
            })

    if overcapacity:
        warnings.append(
            f"{len(overcapacity)} timetable slot(s) would exceed classroom capacity"
        )
        for s in overcapacity[:5]:
            warnings.append(
                f"  Course {s['course_id']} in room {s['classroom_id']}: "
                f"{s['enrollment']}/{s['capacity']} (+{s['overflow']})"
            )

    return {
        "baseline_metrics": {"total_enrollment": baseline_total, "overcapacity_slots": 0},
        "scenario_metrics": {
            "total_enrollment": scenario_total,
            "overcapacity_slots": len(overcapacity),
        },
        "deltas": {
            "enrollment_change": additional,
            "enrollment_change_pct": round(percent, 2),
            "new_overcapacity_slots": len(overcapacity),
        },
        "warnings": warnings,
        "feasible": len(overcapacity) == 0,
    }


# ===================================================================
# Close building
# ===================================================================

def run_close_building(
    state: dict[str, Any],
    building_id: int,
) -> dict[str, Any]:
    """
    Simulate closing a building: greedily relocate displaced sessions to
    available rooms in other buildings.
    """
    simulated = copy.deepcopy(state)
    warnings: list[str] = []

    building = None
    for b in simulated.get("buildings", []):
        if b["id"] == building_id:
            building = b
            break
    if building is None:
        return {
            "baseline_metrics": {},
            "scenario_metrics": {},
            "deltas": {},
            "warnings": ["Building not found"],
            "feasible": False,
        }

    closed_room_ids = {
        c["id"]
        for c in simulated.get("classrooms", [])
        if c.get("building_id") == building_id
    }

    available_rooms = sorted(
        [
            c
            for c in simulated.get("classrooms", [])
            if c.get("building_id") != building_id
            and c.get("kind", "classroom") in ("classroom", "lab")
        ],
        key=lambda r: r["capacity"],
    )

    displaced = [
        s
        for s in simulated.get("timetable_slots", [])
        if s.get("classroom_id") in closed_room_ids
    ]

    # Enrollment counts
    course_enrollment: dict[int, int] = {}
    for e in simulated.get("enrollments", []):
        cid = e["course_id"]
        course_enrollment[cid] = course_enrollment.get(cid, 0) + 1

    # Occupancy set
    occupied: set[tuple[int, int, int]] = set()
    for s in simulated.get("timetable_slots", []):
        if s.get("classroom_id") not in closed_room_ids:
            for h in range(s["start_hour"], s["end_hour"]):
                occupied.add((s["classroom_id"], s["day_of_week"], h))

    relocated = 0
    failed = 0

    for slot in displaced:
        enrollment = course_enrollment.get(slot["course_id"], 0)
        placed = False
        for room in available_rooms:
            if room["capacity"] < enrollment:
                continue
            conflict = any(
                (room["id"], slot["day_of_week"], h) in occupied
                for h in range(slot["start_hour"], slot["end_hour"])
            )
            if not conflict:
                for h in range(slot["start_hour"], slot["end_hour"]):
                    occupied.add((room["id"], slot["day_of_week"], h))
                relocated += 1
                placed = True
                break
        if not placed:
            failed += 1
            warnings.append(
                f"Could not relocate slot {slot['id']} "
                f"(course {slot['course_id']}, day {slot['day_of_week']}, "
                f"{slot['start_hour']}-{slot['end_hour']})"
            )

    if failed:
        warnings.insert(0, f"{failed} session(s) could not be relocated")

    total_slots = len(simulated.get("timetable_slots", []))
    return {
        "baseline_metrics": {
            "total_slots": total_slots,
            "rooms_in_building": len(closed_room_ids),
            "displaced_sessions": len(displaced),
        },
        "scenario_metrics": {
            "relocated": relocated,
            "failed_relocations": failed,
            "remaining_slots": total_slots - failed,
        },
        "deltas": {
            "rooms_lost": len(closed_room_ids),
            "sessions_displaced": len(displaced),
            "sessions_relocated": relocated,
            "sessions_lost": failed,
        },
        "warnings": warnings,
        "feasible": failed == 0,
    }
