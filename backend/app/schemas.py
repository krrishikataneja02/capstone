"""
Pydantic v2 request / response schemas.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ===================================================================
# Auth
# ===================================================================

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    email: str = Field(pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$", max_length=255)
    name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=72)
    role: Literal["admin", "faculty", "student", "facility_manager"]

    @field_validator("password")
    @classmethod
    def password_within_bcrypt_limit(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 72:
            raise ValueError("Password must not exceed 72 UTF-8 bytes")
        return value


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str
    role: str
    is_active: bool
    created_at: datetime


# ===================================================================
# University
# ===================================================================

class UniversityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    address: str | None = None
    created_at: datetime


# ===================================================================
# Department
# ===================================================================

class DepartmentCreate(BaseModel):
    name: str
    code: str
    university_id: int


class DepartmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    university_id: int
    created_at: datetime


# ===================================================================
# Building
# ===================================================================

class BuildingCreate(BaseModel):
    name: str
    code: str
    university_id: int
    building_type: str
    floors: int = 1


class BuildingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    university_id: int
    building_type: str
    floors: int
    created_at: datetime


# ===================================================================
# Classroom
# ===================================================================

class ClassroomCreate(BaseModel):
    name: str
    code: str
    building_id: int
    kind: str = "classroom"
    capacity: int = Field(gt=0)
    floor: int = 0


class ClassroomRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    building_id: int
    kind: str
    capacity: int
    floor: int
    created_at: datetime


# ===================================================================
# Faculty
# ===================================================================

class FacultyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    department_id: int
    employee_id: str
    designation: str
    created_at: datetime


# ===================================================================
# Student
# ===================================================================

class StudentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    department_id: int
    roll_number: str
    semester: int
    created_at: datetime


# ===================================================================
# Course
# ===================================================================

class CourseCreate(BaseModel):
    name: str
    code: str
    department_id: int
    credits: int = 3
    semester: int


class CourseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    department_id: int
    credits: int
    semester: int
    created_at: datetime


# ===================================================================
# Timetable
# ===================================================================

class TimetableCreate(BaseModel):
    course_id: int
    classroom_id: int
    faculty_id: int
    day_of_week: int = Field(ge=0, le=6)
    start_hour: int = Field(ge=0, le=23)
    end_hour: int = Field(ge=1, le=24)


class TimetableRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    course_id: int
    classroom_id: int
    faculty_id: int
    day_of_week: int
    start_hour: int
    end_hour: int
    created_at: datetime


# ===================================================================
# EnergyRecord
# ===================================================================

class EnergyRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    building_id: int
    ts: datetime
    kwh: float


# ===================================================================
# OccupancyRecord
# ===================================================================

class OccupancyRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    classroom_id: int
    ts: datetime
    count: int


# ===================================================================
# Prediction
# ===================================================================

class PredictionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_type: str
    entity_id: int
    metric: str
    target_ts: datetime
    value: float
    model_name: str
    mae: float | None = None
    created_at: datetime


# ===================================================================
# Anomaly
# ===================================================================

class AnomalyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    entity_type: str
    entity_id: int
    metric: str
    observed_value: float
    expected_value: float
    score: float
    status: str
    note: str | None = None
    detected_at: datetime
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None
    created_at: datetime


class AnomalyUpdate(BaseModel):
    status: str
    note: str | None = None


# ===================================================================
# Simulation
# ===================================================================

class SimulationCreate(BaseModel):
    name: str
    simulation_type: str
    parameters: dict[str, Any]


class SimulationScenarioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    simulation_type: str
    parameters: Any
    created_by: int | None = None
    created_at: datetime


class SimulationResultRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scenario_id: int
    baseline_metrics: Any
    scenario_metrics: Any
    deltas: Any
    warnings: Any | None = None
    feasible: bool
    created_at: datetime


class SimulationDetailRead(BaseModel):
    scenario: SimulationScenarioRead
    results: list[SimulationResultRead]


# ===================================================================
# Twin state
# ===================================================================

class SpaceState(BaseModel):
    classroom_id: int
    name: str
    kind: str
    capacity: int
    latest_occupancy: int | None = None
    utilization: float | None = None


class BuildingState(BaseModel):
    building_id: int
    name: str
    building_type: str
    latest_energy_kwh: float | None = None
    open_anomaly_count: int
    spaces: list[SpaceState]


class TwinStateResponse(BaseModel):
    buildings: list[BuildingState]
    timestamp: datetime


# ===================================================================
# Optimization
# ===================================================================

class OptimizationChange(BaseModel):
    timetable_id: int
    course_id: int
    old_classroom_id: int
    new_classroom_id: int
    wasted_before: int
    wasted_after: int


class OptimizationResult(BaseModel):
    before_total_waste: int
    after_total_waste: int
    improvement_pct: float
    changes: list[OptimizationChange]


# ===================================================================
# Attendance
# ===================================================================

class AttendanceSummary(BaseModel):
    course_id: int
    course_name: str
    course_code: str
    total_classes: int
    present_count: int
    percentage: float


# ===================================================================
# Telemetry
# ===================================================================

class TelemetryTickResponse(BaseModel):
    timestamp: datetime
    energy_readings: int
    occupancy_readings: int
    anomalies_detected: int


# ===================================================================
# CSV ingestion
# ===================================================================

class CSVIngestionResult(BaseModel):
    entity_type: str
    total_rows: int
    imported: int
    errors: list[dict[str, Any]]


# ===================================================================
# Generic paginated response
# ===================================================================

class PaginatedResponse(BaseModel):
    items: list[Any]
    total: int
    page: int
    page_size: int
