"""
Unit tests for pure service functions — no database or API required.

Tests cover: anomaly detection, forecast, simulation, optimization.
"""

from __future__ import annotations

import math
import random
from datetime import datetime, timedelta

import pytest

# ---------------------------------------------------------------------------
# Anomaly detection
# ---------------------------------------------------------------------------

from app.services.anomaly import detect_anomaly


class TestAnomalyDetection:
    def test_small_window_returns_no_anomaly(self):
        """With fewer than 10 data points, always returns no anomaly."""
        result = detect_anomaly(100.0, [10.0, 20.0, 30.0])
        assert result["is_anomaly"] is False
        assert result["score"] == 0.0

    def test_normal_value_in_window(self):
        """A value near the mean of a stable window should not be anomalous."""
        window = [50.0 + random.gauss(0, 1) for _ in range(50)]
        result = detect_anomaly(50.5, window)
        assert result["is_anomaly"] is False

    def test_extreme_value_flagged(self):
        """A value far outside the window should be flagged as anomaly."""
        window = [50.0 + random.gauss(0, 1) for _ in range(50)]
        result = detect_anomaly(500.0, window)  # 10x the mean
        assert result["is_anomaly"] is True
        assert result["z_score"] >= 3.0

    def test_result_keys(self):
        """Result dict should always contain the expected keys."""
        result = detect_anomaly(10.0, list(range(20)))
        assert "is_anomaly" in result
        assert "score" in result
        assert "z_score" in result
        assert "expected" in result

    def test_empty_window(self):
        """Empty window should return no anomaly and use observed as expected."""
        result = detect_anomaly(42.0, [])
        assert result["is_anomaly"] is False
        assert result["expected"] == 42.0

    def test_non_finite_history_is_ignored_and_non_finite_observation_is_safe(self):
        history = [float("nan"), float("inf"), *([10.0] * 10)]
        result = detect_anomaly(float("nan"), history)
        assert result == {"is_anomaly": False, "score": 0.0, "z_score": 0.0, "expected": 10.0}

    def test_invalid_detector_parameters_raise(self):
        with pytest.raises(ValueError, match="contamination"):
            detect_anomaly(10.0, list(range(12)), contamination=0)


# ---------------------------------------------------------------------------
# Forecast
# ---------------------------------------------------------------------------

from app.services.forecast import train_and_predict


class TestForecast:
    @pytest.fixture
    def sample_records(self):
        """Generate 72 hours of synthetic data."""
        base = datetime(2024, 6, 1, 0, 0, 0)
        records = []
        for i in range(72):
            ts = base + timedelta(hours=i)
            hour = ts.hour
            # Simple daily pattern
            value = 50.0 + 30.0 * math.sin(2 * math.pi * hour / 24) + random.gauss(0, 2)
            records.append({"ts": ts, "value": max(0, value)})
        return records

    def test_returns_predictions(self, sample_records):
        result = train_and_predict(sample_records, n_future=12)
        assert "predictions" in result
        assert len(result["predictions"]) == 12
        assert "mae" in result
        assert result["mae"] >= 0
        assert result["model_name"] == "RandomForestRegressor"

    def test_predictions_have_ts_and_value(self, sample_records):
        result = train_and_predict(sample_records, n_future=5)
        for p in result["predictions"]:
            assert "ts" in p
            assert "value" in p
            assert p["value"] >= 0

    def test_too_few_records_raises(self):
        records = [{"ts": datetime(2024, 1, 1, i), "value": float(i)} for i in range(5)]
        with pytest.raises(ValueError, match="at least 10"):
            train_and_predict(records)

    def test_custom_last_ts(self, sample_records):
        custom_ts = datetime(2024, 7, 1, 0, 0, 0)
        result = train_and_predict(sample_records, n_future=3, last_ts=custom_ts)
        # First prediction should be 1 hour after custom_ts
        first_ts = result["predictions"][0]["ts"]
        assert "2024-07-01T01" in first_ts

    def test_invalid_values_and_future_count_raise(self, sample_records):
        with pytest.raises(ValueError, match="n_future"):
            train_and_predict(sample_records, n_future=0)
        sample_records[0]["value"] = float("nan")
        with pytest.raises(ValueError, match="finite numeric"):
            train_and_predict(sample_records)


# ---------------------------------------------------------------------------
# Simulation — enrollment growth
# ---------------------------------------------------------------------------

from app.services.simulation import run_enrollment_growth, run_close_building


class TestEnrollmentGrowth:
    @pytest.fixture
    def campus_state(self):
        return {
            "buildings": [{"id": 1, "name": "Block A", "code": "A", "building_type": "academic"}],
            "classrooms": [
                {"id": 1, "name": "R101", "code": "R101", "building_id": 1, "kind": "classroom", "capacity": 60},
                {"id": 2, "name": "R102", "code": "R102", "building_id": 1, "kind": "classroom", "capacity": 40},
            ],
            "courses": [
                {"id": 1, "name": "CS101", "code": "CS101", "department_id": 1},
                {"id": 2, "name": "CS102", "code": "CS102", "department_id": 1},
            ],
            "enrollments": [
                {"student_id": i, "course_id": 1} for i in range(1, 51)
            ] + [
                {"student_id": i, "course_id": 2} for i in range(1, 36)
            ],
            "timetable_slots": [
                {"id": 1, "course_id": 1, "classroom_id": 1, "faculty_id": 1, "day_of_week": 0, "start_hour": 9, "end_hour": 10},
                {"id": 2, "course_id": 2, "classroom_id": 2, "faculty_id": 2, "day_of_week": 0, "start_hour": 9, "end_hour": 10},
            ],
        }

    def test_no_growth_is_feasible(self, campus_state):
        result = run_enrollment_growth(campus_state, percent=0.0)
        assert result["feasible"] is True
        assert result["deltas"]["enrollment_change"] == 0

    def test_small_growth_feasible(self, campus_state):
        result = run_enrollment_growth(campus_state, percent=10.0)
        assert result["deltas"]["enrollment_change"] > 0
        # With 10% growth (50→55, 35→38), both still fit their rooms
        assert result["feasible"] is True

    def test_large_growth_infeasible(self, campus_state):
        result = run_enrollment_growth(campus_state, percent=100.0)
        assert result["feasible"] is False
        assert len(result["warnings"]) > 0

    def test_department_scoped_growth(self, campus_state):
        result = run_enrollment_growth(campus_state, percent=50.0, department_id=999)
        # Department 999 has no courses, so no growth applied
        assert result["deltas"]["enrollment_change"] == 0

    def test_never_mutates_original(self, campus_state):
        import copy
        original = copy.deepcopy(campus_state)
        run_enrollment_growth(campus_state, percent=200.0)
        assert campus_state == original

    def test_negative_or_non_finite_growth_is_rejected(self, campus_state):
        with pytest.raises(ValueError, match="finite non-negative"):
            run_enrollment_growth(campus_state, percent=-1)
        with pytest.raises(ValueError, match="finite non-negative"):
            run_enrollment_growth(campus_state, percent=float("nan"))


# ---------------------------------------------------------------------------
# Simulation — close building
# ---------------------------------------------------------------------------

class TestCloseBuilding:
    @pytest.fixture
    def campus_state(self):
        return {
            "buildings": [
                {"id": 1, "name": "Block A", "code": "A", "building_type": "academic"},
                {"id": 2, "name": "Block B", "code": "B", "building_type": "academic"},
            ],
            "classrooms": [
                {"id": 1, "name": "A-101", "code": "A101", "building_id": 1, "kind": "classroom", "capacity": 60},
                {"id": 2, "name": "B-101", "code": "B101", "building_id": 2, "kind": "classroom", "capacity": 60},
                {"id": 3, "name": "B-102", "code": "B102", "building_id": 2, "kind": "classroom", "capacity": 40},
            ],
            "courses": [
                {"id": 1, "name": "CS101", "code": "CS101", "department_id": 1},
            ],
            "enrollments": [
                {"student_id": i, "course_id": 1} for i in range(1, 31)
            ],
            "timetable_slots": [
                {"id": 1, "course_id": 1, "classroom_id": 1, "faculty_id": 1, "day_of_week": 0, "start_hour": 9, "end_hour": 10},
            ],
        }

    def test_close_building_with_available_room(self, campus_state):
        result = run_close_building(campus_state, building_id=1)
        assert result["feasible"] is True
        assert result["deltas"]["sessions_relocated"] == 1
        assert result["deltas"]["sessions_lost"] == 0

    def test_close_nonexistent_building(self, campus_state):
        result = run_close_building(campus_state, building_id=999)
        assert result["feasible"] is False
        assert "not found" in result["warnings"][0].lower()

    def test_never_mutates_original(self, campus_state):
        import copy
        original = copy.deepcopy(campus_state)
        run_close_building(campus_state, building_id=1)
        assert campus_state == original


# ---------------------------------------------------------------------------
# Optimization
# ---------------------------------------------------------------------------

from app.services.optimization import optimize_classroom_allocation


class TestOptimization:
    def test_empty_input(self):
        result = optimize_classroom_allocation([], [])
        assert result["before_total_waste"] == 0
        assert result["after_total_waste"] == 0
        assert result["changes"] == []

    def test_already_optimal(self):
        """A single slot in a perfectly-sized room should have no changes."""
        slots = [{"id": 1, "course_id": 1, "classroom_id": 1, "enrollment": 40,
                  "day_of_week": 0, "start_hour": 9, "end_hour": 10, "kind": "classroom"}]
        rooms = [{"id": 1, "capacity": 40, "kind": "classroom"}]
        result = optimize_classroom_allocation(slots, rooms)
        assert result["changes"] == []
        assert result["before_total_waste"] == 0

    def test_optimization_reduces_waste(self):
        """Two slots swapped between rooms should reduce waste."""
        slots = [
            {"id": 1, "course_id": 1, "classroom_id": 1, "enrollment": 30,
             "day_of_week": 0, "start_hour": 9, "end_hour": 10, "kind": "classroom"},
            {"id": 2, "course_id": 2, "classroom_id": 2, "enrollment": 80,
             "day_of_week": 0, "start_hour": 9, "end_hour": 10, "kind": "classroom"},
        ]
        rooms = [
            {"id": 1, "capacity": 100, "kind": "classroom"},  # big room for small class
            {"id": 2, "capacity": 40, "kind": "classroom"},   # small room for big class — doesn't fit!
        ]
        # Room 2 can't hold 80, so only room 1 works for course 2.
        # The optimizer should assign course2→room1 and course1→room2
        result = optimize_classroom_allocation(slots, rooms)
        assert result["after_total_waste"] <= result["before_total_waste"]

    def test_lab_kind_matching(self):
        """Lab courses should only be assigned to lab rooms."""
        slots = [
            {"id": 1, "course_id": 1, "classroom_id": 1, "enrollment": 25,
             "day_of_week": 0, "start_hour": 9, "end_hour": 10, "kind": "lab"},
        ]
        rooms = [
            {"id": 1, "capacity": 30, "kind": "lab"},
            {"id": 2, "capacity": 100, "kind": "classroom"},
        ]
        result = optimize_classroom_allocation(slots, rooms)
        # Should stay in (or go to) the lab room, not the classroom
        for change in result["changes"]:
            assert change["new_classroom_id"] == 1

    def test_result_shape(self):
        slots = [{"id": 1, "course_id": 1, "classroom_id": 1, "enrollment": 20,
                  "day_of_week": 0, "start_hour": 9, "end_hour": 10, "kind": "classroom"}]
        rooms = [{"id": 1, "capacity": 40, "kind": "classroom"}]
        result = optimize_classroom_allocation(slots, rooms)
        assert "before_total_waste" in result
        assert "after_total_waste" in result
        assert "improvement_pct" in result
        assert "changes" in result

    def test_no_compatible_or_available_room_keeps_assignment_unchanged(self):
        slots = [{"id": 1, "course_id": 1, "classroom_id": 99, "enrollment": 25,
                  "day_of_week": 0, "start_hour": 9, "end_hour": 10, "kind": "lab"}]
        rooms = [{"id": 1, "capacity": 30, "kind": "classroom"}]
        result = optimize_classroom_allocation(slots, rooms)
        assert result["changes"] == []
        assert result["after_total_waste"] == result["before_total_waste"] == 0


# ---------------------------------------------------------------------------
# Campus data generators
# ---------------------------------------------------------------------------

from app.services.campus_data import (
    generate_energy_reading,
    generate_energy_anomaly,
    generate_occupancy_reading,
)


class TestCampusData:
    def test_energy_reading_positive(self):
        ts = datetime(2024, 6, 5, 13, 0)  # Wednesday 1pm
        kwh = generate_energy_reading("academic", ts)
        assert kwh > 0

    def test_energy_anomaly_is_higher(self):
        ts = datetime(2024, 6, 5, 13, 0)
        readings = [generate_energy_reading("academic", ts) for _ in range(20)]
        anomaly = generate_energy_anomaly("academic", ts)
        assert anomaly > max(readings)  # Anomaly should be much higher

    def test_occupancy_within_capacity(self):
        ts = datetime(2024, 6, 5, 10, 0)
        for _ in range(50):
            count = generate_occupancy_reading(100, "classroom", ts, has_class=True, enrollment=80)
            assert 0 <= count <= 100

    def test_hostel_night_occupancy_higher(self):
        night_ts = datetime(2024, 6, 5, 23, 0)
        day_ts = datetime(2024, 6, 5, 12, 0)
        night_vals = [generate_occupancy_reading(100, "hostel", night_ts) for _ in range(20)]
        day_vals = [generate_occupancy_reading(100, "hostel", day_ts) for _ in range(20)]
        # On average, night should be higher than day
        assert sum(night_vals) / len(night_vals) > sum(day_vals) / len(day_vals)

    def test_generators_are_repeatable_with_fixed_random_seed(self):
        ts = datetime(2024, 6, 5, 13, 0)
        random.seed(1234)
        first = (generate_energy_reading("academic", ts), generate_occupancy_reading(100, "library", ts))
        random.seed(1234)
        second = (generate_energy_reading("academic", ts), generate_occupancy_reading(100, "library", ts))
        assert first == second
