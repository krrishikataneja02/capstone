"""
Classroom allocation optimization — Hungarian algorithm (scipy).

Pure function: timetable slots + classrooms in → optimized assignment out.
No DB / API dependency.
"""

from __future__ import annotations

import numpy as np
from scipy.optimize import linear_sum_assignment


def optimize_classroom_allocation(
    timetable_slots: list[dict],
    classrooms: list[dict],
) -> dict:
    """
    Minimize total wasted seats across all timetable time-blocks by solving
    each independent block as an assignment problem.

    Parameters
    ----------
    timetable_slots : each has ``id``, ``course_id``, ``classroom_id``,
        ``enrollment``, ``day_of_week``, ``start_hour``, ``end_hour``, ``kind``.
    classrooms : each has ``id``, ``capacity``, ``kind``.

    Returns
    -------
    dict with ``before_total_waste``, ``after_total_waste``,
    ``improvement_pct``, ``changes``.
    """
    if not timetable_slots or not classrooms:
        return {
            "before_total_waste": 0,
            "after_total_waste": 0,
            "improvement_pct": 0.0,
            "changes": [],
        }

    classroom_by_id = {c["id"]: c for c in classrooms}

    # Group by (day, start, end) → independent assignment sub-problems
    time_blocks: dict[tuple, list[dict]] = {}
    for slot in timetable_slots:
        key = (slot["day_of_week"], slot["start_hour"], slot["end_hour"])
        time_blocks.setdefault(key, []).append(slot)

    all_changes: list[dict] = []
    total_waste_before = 0
    total_waste_after = 0

    INF = 10**9

    for _key, slots in time_blocks.items():
        assignable = [
            s for s in slots if s.get("kind", "classroom") in ("classroom", "lab")
        ]
        non_assignable = [s for s in slots if s not in assignable]

        # Account for non-assignable waste
        for s in non_assignable:
            room = classroom_by_id.get(s["classroom_id"])
            if room:
                w = max(0, room["capacity"] - s["enrollment"])
                total_waste_before += w
                total_waste_after += w

        if not assignable:
            continue

        used_rooms = {s["classroom_id"] for s in non_assignable}
        eligible = [
            c
            for c in classrooms
            if c["id"] not in used_rooms
            and c.get("kind", "classroom") in ("classroom", "lab")
            and c["capacity"] > 0
        ]

        n_slots = len(assignable)
        n_rooms = len(eligible)

        if n_rooms == 0:
            for s in assignable:
                room = classroom_by_id.get(s["classroom_id"])
                if room:
                    w = max(0, room["capacity"] - s["enrollment"])
                    total_waste_before += w
                    total_waste_after += w
            continue

        size = max(n_slots, n_rooms)
        cost = np.full((size, size), float(INF))

        for i, slot in enumerate(assignable):
            s_kind = slot.get("kind", "classroom")
            enroll = slot["enrollment"]
            for j, room in enumerate(eligible):
                r_kind = room.get("kind", "classroom")
                # Kind matching
                if s_kind == "lab" and r_kind != "lab":
                    continue
                if s_kind == "classroom" and r_kind not in ("classroom", "lab"):
                    continue
                if room["capacity"] < enroll:
                    continue
                cost[i][j] = room["capacity"] - enroll

        row_ind, col_ind = linear_sum_assignment(cost)

        for i, slot in enumerate(assignable):
            old_room = classroom_by_id.get(slot["classroom_id"])
            wb = max(0, old_room["capacity"] - slot["enrollment"]) if old_room else 0
            total_waste_before += wb

            j = col_ind[i] if i < len(col_ind) else -1
            if 0 <= j < n_rooms and cost[i][j] < INF:
                new_room = eligible[j]
                wa = new_room["capacity"] - slot["enrollment"]
                total_waste_after += wa
                if new_room["id"] != slot["classroom_id"]:
                    all_changes.append({
                        "timetable_id": slot["id"],
                        "course_id": slot["course_id"],
                        "old_classroom_id": slot["classroom_id"],
                        "new_classroom_id": new_room["id"],
                        "wasted_before": wb,
                        "wasted_after": wa,
                    })
            else:
                total_waste_after += wb

    improvement_pct = 0.0
    if total_waste_before > 0:
        improvement_pct = round(
            (total_waste_before - total_waste_after) / total_waste_before * 100, 2
        )

    return {
        "before_total_waste": total_waste_before,
        "after_total_waste": total_waste_after,
        "improvement_pct": improvement_pct,
        "changes": all_changes,
    }
