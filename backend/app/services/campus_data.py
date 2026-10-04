"""
Simulated campus sensor data generators.

Each function returns a single reading given a building/room type and timestamp.
No DB dependency — used by the telemetry tick endpoint and the seed script.
"""

from __future__ import annotations

import math
import random
from datetime import datetime


# ===================================================================
# Energy
# ===================================================================

def generate_energy_reading(building_type: str, ts: datetime) -> float:
    """
    Realistic kWh reading: Gaussian daily peak at ~13 h, weekend dampening,
    building-type base load, plus noise.
    """
    hour = ts.hour + ts.minute / 60.0
    is_weekend = ts.weekday() >= 5

    base_loads = {"academic": 50.0, "lab": 80.0, "library": 40.0, "hostel": 30.0}
    base = base_loads.get(building_type, 50.0)

    # Daily pattern (peak at 13:00)
    daily = 0.3 + 0.7 * math.exp(-0.5 * ((hour - 13) / 4) ** 2)
    weekend = 0.4 if is_weekend else 1.0
    noise = random.gauss(0, base * 0.05)

    return round(max(5.0, base * daily * weekend + noise), 2)


def generate_energy_anomaly(building_type: str, ts: datetime) -> float:
    """Return a clearly anomalous energy spike (3×–5× normal)."""
    normal = generate_energy_reading(building_type, ts)
    return round(normal * random.uniform(3.0, 5.0), 2)


# ===================================================================
# Occupancy
# ===================================================================

def generate_occupancy_reading(
    capacity: int,
    kind: str,
    ts: datetime,
    *,
    has_class: bool = False,
    enrollment: int = 0,
) -> int:
    """
    Realistic occupancy count driven by room kind, time-of-day, weekday
    and (for classrooms/labs) the current timetable.
    """
    hour = ts.hour
    is_weekend = ts.weekday() >= 5

    if kind == "hostel":
        if hour >= 22 or hour <= 6:
            factor = random.uniform(0.70, 0.95)
        elif 8 <= hour <= 17:
            factor = random.uniform(0.10, 0.30)
        else:
            factor = random.uniform(0.40, 0.60)
        return max(0, min(capacity, int(capacity * factor)))

    if kind == "library":
        if is_weekend:
            factor = random.uniform(0.10, 0.30)
        elif 9 <= hour <= 17:
            factor = random.uniform(0.30, 0.80)
        elif 17 < hour <= 21:
            factor = random.uniform(0.20, 0.50)
        else:
            factor = random.uniform(0.0, 0.10)
        return max(0, min(capacity, int(capacity * factor)))

    # Classroom / Lab
    if has_class and not is_weekend:
        base_occ = int(enrollment * random.uniform(0.70, 0.95))
        return max(0, min(capacity, base_occ))

    if is_weekend:
        return max(0, int(capacity * random.uniform(0.0, 0.05)))
    if 8 <= hour <= 17:
        return max(0, int(capacity * random.uniform(0.0, 0.15)))
    return 0
