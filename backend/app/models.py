"""
SQLAlchemy ORM models for the Digital Twin of a University.

All tables: InnoDB engine, utf8mb4 charset, utf8mb4_unicode_ci collation.
Foreign keys, CHECK constraints, UNIQUE constraints and composite indexes
are enforced at the database level.
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def utcnow() -> datetime:
    """Current UTC datetime without tzinfo (MySQL DATETIME)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


_TBL: dict = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_unicode_ci",
}


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class UserRole(str, enum.Enum):
    admin = "admin"
    faculty = "faculty"
    student = "student"
    facility_manager = "facility_manager"


class ClassroomKind(str, enum.Enum):
    classroom = "classroom"
    lab = "lab"
    library = "library"
    hostel = "hostel"


class AnomalyStatus(str, enum.Enum):
    detected = "detected"
    acknowledged = "acknowledged"
    resolved = "resolved"
    dismissed = "dismissed"


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# User
# ---------------------------------------------------------------------------

class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_user_email"),
        {**_TBL},
    )

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    email: str = Column(String(255), nullable=False)
    name: str = Column(String(255), nullable=False)
    hashed_password: str = Column(String(255), nullable=False)
    role = Column(SAEnum(UserRole), nullable=False)
    is_active: bool = Column(Boolean, default=True, nullable=False)
    created_at: datetime = Column(DateTime, default=utcnow, nullable=False)
    updated_at: datetime = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    faculty_profile = relationship("Faculty", back_populates="user", uselist=False)
    student_profile = relationship("Student", back_populates="user", uselist=False)
    simulations = relationship("SimulationScenario", back_populates="created_by_user")


# ---------------------------------------------------------------------------
# University
# ---------------------------------------------------------------------------

class University(Base):
    __tablename__ = "universities"
    __table_args__ = (
        UniqueConstraint("code", name="uq_university_code"),
        {**_TBL},
    )

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    name: str = Column(String(255), nullable=False)
    code: str = Column(String(50), nullable=False)
    address: str | None = Column(String(500))
    created_at: datetime = Column(DateTime, default=utcnow, nullable=False)

    departments = relationship("Department", back_populates="university")
    buildings = relationship("Building", back_populates="university")


# ---------------------------------------------------------------------------
# Department
# ---------------------------------------------------------------------------

class Department(Base):
    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("code", name="uq_department_code"),
        {**_TBL},
    )

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    name: str = Column(String(255), nullable=False)
    code: str = Column(String(50), nullable=False)
    university_id: int = Column(
        Integer, ForeignKey("universities.id", ondelete="CASCADE"), nullable=False
    )
    created_at: datetime = Column(DateTime, default=utcnow, nullable=False)

    university = relationship("University", back_populates="departments")
    faculty_members = relationship("Faculty", back_populates="department")
    courses = relationship("Course", back_populates="department")
    students = relationship("Student", back_populates="department")


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------

class Building(Base):
    __tablename__ = "buildings"
    __table_args__ = (
        UniqueConstraint("code", name="uq_building_code"),
        {**_TBL},
    )

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    name: str = Column(String(255), nullable=False)
    code: str = Column(String(50), nullable=False)
    university_id: int = Column(
        Integer, ForeignKey("universities.id", ondelete="CASCADE"), nullable=False
    )
    building_type: str = Column(String(50), nullable=False)  # academic, lab, library, hostel
    floors: int = Column(Integer, default=1, nullable=False)
    created_at: datetime = Column(DateTime, default=utcnow, nullable=False)

    university = relationship("University", back_populates="buildings")
    classrooms = relationship("Classroom", back_populates="building")
    energy_records = relationship("EnergyRecord", back_populates="building")


# ---------------------------------------------------------------------------
# Classroom (covers classrooms, labs, library spaces, hostel rooms)
# ---------------------------------------------------------------------------

class Classroom(Base):
    __tablename__ = "classrooms"
    __table_args__ = (
        UniqueConstraint("code", name="uq_classroom_code"),
        CheckConstraint("capacity > 0", name="ck_classroom_capacity"),
        {**_TBL},
    )

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    name: str = Column(String(255), nullable=False)
    code: str = Column(String(50), nullable=False)
    building_id: int = Column(
        Integer, ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False
    )
    kind = Column(SAEnum(ClassroomKind), nullable=False, default=ClassroomKind.classroom)
    capacity: int = Column(Integer, nullable=False)
    floor: int = Column(Integer, default=0, nullable=False)
    created_at: datetime = Column(DateTime, default=utcnow, nullable=False)

    building = relationship("Building", back_populates="classrooms")
    timetable_slots = relationship("Timetable", back_populates="classroom")
    occupancy_records = relationship("OccupancyRecord", back_populates="classroom")


# ---------------------------------------------------------------------------
# Faculty
# ---------------------------------------------------------------------------

class Faculty(Base):
    __tablename__ = "faculty"
    __table_args__ = (
        UniqueConstraint("employee_id", name="uq_faculty_employee_id"),
        UniqueConstraint("user_id", name="uq_faculty_user_id"),
        {**_TBL},
    )

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    user_id: int = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    department_id: int = Column(
        Integer, ForeignKey("departments.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: str = Column(String(50), nullable=False)
    designation: str = Column(String(100), nullable=False)
    created_at: datetime = Column(DateTime, default=utcnow, nullable=False)

    user = relationship("User", back_populates="faculty_profile")
    department = relationship("Department", back_populates="faculty_members")
    timetable_slots = relationship("Timetable", back_populates="faculty")


# ---------------------------------------------------------------------------
# Student
# ---------------------------------------------------------------------------

class Student(Base):
    __tablename__ = "students"
    __table_args__ = (
        UniqueConstraint("roll_number", name="uq_student_roll_number"),
        UniqueConstraint("user_id", name="uq_student_user_id"),
        {**_TBL},
    )

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    user_id: int = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    department_id: int = Column(
        Integer, ForeignKey("departments.id", ondelete="CASCADE"), nullable=False
    )
    roll_number: str = Column(String(50), nullable=False)
    semester: int = Column(Integer, nullable=False)
    created_at: datetime = Column(DateTime, default=utcnow, nullable=False)

    user = relationship("User", back_populates="student_profile")
    department = relationship("Department", back_populates="students")
    enrollments = relationship("Enrollment", back_populates="student")
    attendances = relationship("Attendance", back_populates="student")


# ---------------------------------------------------------------------------
# Course
# ---------------------------------------------------------------------------

class Course(Base):
    __tablename__ = "courses"
    __table_args__ = (
        UniqueConstraint("code", name="uq_course_code"),
        {**_TBL},
    )

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    name: str = Column(String(255), nullable=False)
    code: str = Column(String(50), nullable=False)
    department_id: int = Column(
        Integer, ForeignKey("departments.id", ondelete="CASCADE"), nullable=False
    )
    credits: int = Column(Integer, nullable=False, default=3)
    semester: int = Column(Integer, nullable=False)
    created_at: datetime = Column(DateTime, default=utcnow, nullable=False)

    department = relationship("Department", back_populates="courses")
    enrollments = relationship("Enrollment", back_populates="course")
    timetable_slots = relationship("Timetable", back_populates="course")
    attendances = relationship("Attendance", back_populates="course")


# ---------------------------------------------------------------------------
# Enrollment  (Student ↔ Course many-to-many)
# ---------------------------------------------------------------------------

class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("student_id", "course_id", name="uq_enrollment_student_course"),
        {**_TBL},
    )

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    student_id: int = Column(
        Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False
    )
    course_id: int = Column(
        Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    enrolled_at: datetime = Column(DateTime, default=utcnow, nullable=False)

    student = relationship("Student", back_populates="enrollments")
    course = relationship("Course", back_populates="enrollments")


# ---------------------------------------------------------------------------
# Timetable
# ---------------------------------------------------------------------------

class Timetable(Base):
    __tablename__ = "timetables"
    __table_args__ = (
        CheckConstraint("day_of_week >= 0 AND day_of_week <= 6", name="ck_timetable_day"),
        CheckConstraint("end_hour > start_hour", name="ck_timetable_hours"),
        {**_TBL},
    )

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    course_id: int = Column(
        Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    classroom_id: int = Column(
        Integer, ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False
    )
    faculty_id: int = Column(
        Integer, ForeignKey("faculty.id", ondelete="CASCADE"), nullable=False
    )
    day_of_week: int = Column(Integer, nullable=False)       # 0=Mon … 6=Sun
    start_hour: int = Column(Integer, nullable=False)
    end_hour: int = Column(Integer, nullable=False)
    created_at: datetime = Column(DateTime, default=utcnow, nullable=False)

    course = relationship("Course", back_populates="timetable_slots")
    classroom = relationship("Classroom", back_populates="timetable_slots")
    faculty = relationship("Faculty", back_populates="timetable_slots")


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------

class Attendance(Base):
    __tablename__ = "attendances"
    __table_args__ = (
        UniqueConstraint(
            "student_id", "course_id", "date",
            name="uq_attendance_student_course_date",
        ),
        {**_TBL},
    )

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    student_id: int = Column(
        Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False
    )
    course_id: int = Column(
        Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False
    )
    date = Column(Date, nullable=False)
    present: bool = Column(Boolean, nullable=False)
    created_at: datetime = Column(DateTime, default=utcnow, nullable=False)

    student = relationship("Student", back_populates="attendances")
    course = relationship("Course", back_populates="attendances")


# ---------------------------------------------------------------------------
# EnergyRecord  (time-series per building)
# ---------------------------------------------------------------------------

class EnergyRecord(Base):
    __tablename__ = "energy_records"
    __table_args__ = (
        Index("ix_energy_building_ts", "building_id", "ts"),
        {**_TBL},
    )

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    building_id: int = Column(
        Integer, ForeignKey("buildings.id", ondelete="CASCADE"), nullable=False
    )
    ts: datetime = Column(DateTime, nullable=False)
    kwh: float = Column(Float, nullable=False)
    created_at: datetime = Column(DateTime, default=utcnow, nullable=False)

    building = relationship("Building", back_populates="energy_records")


# ---------------------------------------------------------------------------
# OccupancyRecord  (time-series per classroom)
# ---------------------------------------------------------------------------

class OccupancyRecord(Base):
    __tablename__ = "occupancy_records"
    __table_args__ = (
        Index("ix_occupancy_classroom_ts", "classroom_id", "ts"),
        {**_TBL},
    )

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    classroom_id: int = Column(
        Integer, ForeignKey("classrooms.id", ondelete="CASCADE"), nullable=False
    )
    ts: datetime = Column(DateTime, nullable=False)
    count: int = Column(Integer, nullable=False)
    created_at: datetime = Column(DateTime, default=utcnow, nullable=False)

    classroom = relationship("Classroom", back_populates="occupancy_records")


# ---------------------------------------------------------------------------
# Prediction
# ---------------------------------------------------------------------------

class Prediction(Base):
    __tablename__ = "predictions"
    __table_args__ = ({**_TBL},)

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    entity_type: str = Column(String(50), nullable=False)   # "building" | "classroom"
    entity_id: int = Column(Integer, nullable=False)
    metric: str = Column(String(50), nullable=False)         # "energy" | "occupancy"
    target_ts: datetime = Column(DateTime, nullable=False)
    value: float = Column(Float, nullable=False)
    model_name: str = Column(String(100), nullable=False)
    mae: float | None = Column(Float)
    created_at: datetime = Column(DateTime, default=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# Anomaly
# ---------------------------------------------------------------------------

class Anomaly(Base):
    __tablename__ = "anomalies"
    __table_args__ = ({**_TBL},)

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    entity_type: str = Column(String(50), nullable=False)    # "building"
    entity_id: int = Column(Integer, nullable=False)
    metric: str = Column(String(50), nullable=False)          # "energy"
    observed_value: float = Column(Float, nullable=False)
    expected_value: float = Column(Float, nullable=False)
    score: float = Column(Float, nullable=False)
    status = Column(
        SAEnum(AnomalyStatus), nullable=False, default=AnomalyStatus.detected
    )
    note: str | None = Column(Text)
    detected_at: datetime = Column(DateTime, default=utcnow, nullable=False)
    acknowledged_at: datetime | None = Column(DateTime)
    resolved_at: datetime | None = Column(DateTime)
    created_at: datetime = Column(DateTime, default=utcnow, nullable=False)


# ---------------------------------------------------------------------------
# SimulationScenario
# ---------------------------------------------------------------------------

class SimulationScenario(Base):
    __tablename__ = "simulation_scenarios"
    __table_args__ = ({**_TBL},)

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    name: str = Column(String(255), nullable=False)
    simulation_type: str = Column(String(50), nullable=False)  # enrollment_growth | close_building
    parameters = Column(JSON, nullable=False)
    created_by: int | None = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: datetime = Column(DateTime, default=utcnow, nullable=False)

    created_by_user = relationship("User", back_populates="simulations")
    results = relationship("SimulationResult", back_populates="scenario")


# ---------------------------------------------------------------------------
# SimulationResult
# ---------------------------------------------------------------------------

class SimulationResult(Base):
    __tablename__ = "simulation_results"
    __table_args__ = ({**_TBL},)

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    scenario_id: int = Column(
        Integer, ForeignKey("simulation_scenarios.id", ondelete="CASCADE"), nullable=False
    )
    baseline_metrics = Column(JSON, nullable=False)
    scenario_metrics = Column(JSON, nullable=False)
    deltas = Column(JSON, nullable=False)
    warnings = Column(JSON)
    feasible: bool = Column(Boolean, nullable=False)
    created_at: datetime = Column(DateTime, default=utcnow, nullable=False)

    scenario = relationship("SimulationScenario", back_populates="results")
