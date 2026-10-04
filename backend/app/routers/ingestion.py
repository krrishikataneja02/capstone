"""
Ingestion router — CSV import, telemetry tick, energy and occupancy history.

- POST /ingestion/csv (admin): import CSV exports for students, courses, energy
- POST /telemetry/tick: simulate one round of sensor data
- GET /telemetry/energy: energy history per building
- GET /telemetry/occupancy: occupancy history per classroom
"""

from __future__ import annotations

import csv
import io
import logging
import math
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.deps import get_current_user, get_db, require_role
from app.models import (
    Anomaly,
    AnomalyStatus,
    Building,
    Classroom,
    ClassroomKind,
    Course,
    Department,
    Enrollment,
    EnergyRecord,
    OccupancyRecord,
    Student,
    Timetable,
    User,
    UserRole,
    utcnow,
)
from app.redis_client import invalidate_twin_state
from app.schemas import (
    CSVIngestionResult,
    EnergyRecordRead,
    OccupancyRecordRead,
    PaginatedResponse,
    TelemetryTickResponse,
)
from app.services.anomaly import detect_anomaly
from app.services.campus_data import (
    generate_energy_anomaly,
    generate_energy_reading,
    generate_occupancy_reading,
)
from app.ws import manager

logger = logging.getLogger("digital_twin.ingestion")

router = APIRouter(tags=["ingestion"])


# ===================================================================
# CSV Ingestion
# ===================================================================

@router.post("/ingestion/csv", response_model=CSVIngestionResult)
async def ingest_csv(
    entity_type: str = Query(..., description="students | courses | energy"),
    file: UploadFile = File(...),
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    Import CSV exports for students, courses, and energy readings.
    Returns per-row error report. Rejects duplicates.
    """
    if entity_type not in ("students", "courses", "energy"):
        raise HTTPException(status_code=422, detail="entity_type must be 'students', 'courses', or 'energy'")

    content = await file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="CSV file exceeds the 5 MiB limit")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="CSV file must use UTF-8 encoding")
    reader = csv.DictReader(io.StringIO(text))

    required_columns = {
        "students": {"roll_number", "name", "email", "department_code", "semester"},
        "courses": {"code", "name", "department_code", "credits", "semester"},
        "energy": {"building_code", "timestamp", "kwh"},
    }[entity_type]
    if reader.fieldnames is None or not required_columns.issubset(reader.fieldnames):
        raise HTTPException(status_code=400, detail="CSV is missing required columns")

    imported = 0
    errors: list[dict] = []
    rows = list(reader)

    if entity_type == "students":
        for idx, row in enumerate(rows, 1):
            try:
                roll = row.get("roll_number", "").strip()
                name = row.get("name", "").strip()
                email = row.get("email", "").strip()
                dept_code = row.get("department_code", "").strip()
                semester = int(row.get("semester", 1))

                if not all([roll, name, email, dept_code]) or semester < 1:
                    errors.append({"row": idx, "error": "Missing required field"})
                    continue

                dept = db.query(Department).filter(Department.code == dept_code).first()
                if not dept:
                    errors.append({"row": idx, "error": f"Department '{dept_code}' not found"})
                    continue

                # Check duplicate
                if db.query(Student).filter(Student.roll_number == roll).first():
                    errors.append({"row": idx, "error": f"Duplicate roll_number '{roll}'"})
                    continue
                if db.query(User).filter(User.email == email).first():
                    errors.append({"row": idx, "error": f"Duplicate email '{email}'"})
                    continue

                from app.security import hash_password
                u = User(
                    email=email, name=name,
                    hashed_password=hash_password("student123"),
                    role=UserRole.student, is_active=True,
                )
                db.add(u)
                db.flush()
                s = Student(
                    user_id=u.id, department_id=dept.id,
                    roll_number=roll, semester=semester,
                )
                db.add(s)
                db.flush()
                imported += 1
            except (TypeError, ValueError, OverflowError):
                errors.append({"row": idx, "error": "Invalid student row values"})
            except Exception:
                errors.append({"row": idx, "error": "Student row could not be imported"})

    elif entity_type == "courses":
        for idx, row in enumerate(rows, 1):
            try:
                code = row.get("code", "").strip()
                name = row.get("name", "").strip()
                dept_code = row.get("department_code", "").strip()
                credits = int(row.get("credits", 3))
                semester = int(row.get("semester", 1))

                if not all([code, name, dept_code]) or credits < 1 or semester < 1:
                    errors.append({"row": idx, "error": "Missing required field"})
                    continue

                dept = db.query(Department).filter(Department.code == dept_code).first()
                if not dept:
                    errors.append({"row": idx, "error": f"Department '{dept_code}' not found"})
                    continue

                if db.query(Course).filter(Course.code == code).first():
                    errors.append({"row": idx, "error": f"Duplicate course code '{code}'"})
                    continue

                c = Course(
                    name=name, code=code, department_id=dept.id,
                    credits=credits, semester=semester,
                )
                db.add(c)
                db.flush()
                imported += 1
            except (TypeError, ValueError, OverflowError):
                errors.append({"row": idx, "error": "Invalid course row values"})
            except Exception:
                errors.append({"row": idx, "error": "Course row could not be imported"})

    elif entity_type == "energy":
        for idx, row in enumerate(rows, 1):
            try:
                building_code = row.get("building_code", "").strip()
                ts_str = row.get("timestamp", "").strip()
                kwh = float(row.get("kwh", 0))

                if not all([building_code, ts_str]) or not math.isfinite(kwh) or kwh < 0:
                    errors.append({"row": idx, "error": "Missing required field"})
                    continue

                building = db.query(Building).filter(Building.code == building_code).first()
                if not building:
                    errors.append({"row": idx, "error": f"Building '{building_code}' not found"})
                    continue

                ts = datetime.fromisoformat(ts_str)

                # Duplicate check
                existing = db.query(EnergyRecord).filter(
                    EnergyRecord.building_id == building.id,
                    EnergyRecord.ts == ts,
                ).first()
                if existing:
                    errors.append({"row": idx, "error": "Duplicate energy record"})
                    continue

                er = EnergyRecord(building_id=building.id, ts=ts, kwh=kwh)
                db.add(er)
                db.flush()
                imported += 1
            except (TypeError, ValueError, OverflowError):
                errors.append({"row": idx, "error": "Invalid energy row values"})
            except Exception:
                errors.append({"row": idx, "error": "Energy row could not be imported"})

    db.commit()
    invalidate_twin_state()
    return CSVIngestionResult(
        entity_type=entity_type,
        total_rows=len(rows),
        imported=imported,
        errors=errors,
    )


# ===================================================================
# Telemetry Tick
# ===================================================================

def _perform_tick(
    inject_anomaly: bool = False,
    db: Session | None = None,
) -> dict:
    """
    Simulate one round of sensor data. Used by the endpoint and the background loop.
    Returns counts for energy, occupancy, anomalies_detected.
    """
    close_db = False
    if db is None:
        db = SessionLocal()
        close_db = True

    try:
        now = utcnow()
        buildings = db.query(Building).all()
        classrooms = db.query(Classroom).all()
        timetable_slots = db.query(Timetable).all()

        # Build timetable lookup
        current_day = now.weekday()
        current_hour = now.hour
        active_slots: dict[int, Timetable] = {}
        for slot in timetable_slots:
            if slot.day_of_week == current_day and slot.start_hour <= current_hour < slot.end_hour:
                active_slots[slot.classroom_id] = slot

        energy_count = 0
        occupancy_count = 0
        anomaly_count = 0

        # Energy readings
        anomaly_injected = False
        for building in buildings:
            if inject_anomaly and not anomaly_injected:
                kwh = generate_energy_anomaly(building.building_type, now)
                anomaly_injected = True
            else:
                kwh = generate_energy_reading(building.building_type, now)

            er = EnergyRecord(building_id=building.id, ts=now, kwh=kwh)
            db.add(er)
            energy_count += 1

            # Anomaly detection
            window = [
                r.kwh for r in
                db.query(EnergyRecord)
                .filter(EnergyRecord.building_id == building.id)
                .order_by(EnergyRecord.ts.desc())
                .limit(50)
                .all()
            ]

            result = detect_anomaly(kwh, window)
            if result["is_anomaly"]:
                # Avoid duplicate open anomaly within the same hour
                one_hour_ago = now - timedelta(hours=1)
                existing = db.query(Anomaly).filter(
                    Anomaly.entity_type == "building",
                    Anomaly.entity_id == building.id,
                    Anomaly.metric == "energy",
                    Anomaly.status.in_([AnomalyStatus.detected, AnomalyStatus.acknowledged]),
                    Anomaly.detected_at >= one_hour_ago,
                ).first()

                if not existing:
                    anom = Anomaly(
                        entity_type="building",
                        entity_id=building.id,
                        metric="energy",
                        observed_value=kwh,
                        expected_value=result["expected"],
                        score=result["score"],
                        status=AnomalyStatus.detected,
                        detected_at=now,
                    )
                    db.add(anom)
                    anomaly_count += 1

        # Occupancy readings
        enrollment_counts: dict[int, int] = {}
        for classroom in classrooms:
            kind_val = classroom.kind.value if hasattr(classroom.kind, "value") else classroom.kind
            slot = active_slots.get(classroom.id)
            has_class = slot is not None

            enrollment = 0
            if has_class and slot is not None:
                course_id = slot.course_id
                if course_id not in enrollment_counts:
                    enrollment_counts[course_id] = db.query(Enrollment).filter(
                        Enrollment.course_id == course_id
                    ).count()
                enrollment = enrollment_counts[course_id]

            count = generate_occupancy_reading(
                classroom.capacity, kind_val, now,
                has_class=has_class, enrollment=enrollment,
            )
            occ = OccupancyRecord(classroom_id=classroom.id, ts=now, count=count)
            db.add(occ)
            occupancy_count += 1

        db.commit()
        invalidate_twin_state()

        return {
            "timestamp": now,
            "energy_readings": energy_count,
            "occupancy_readings": occupancy_count,
            "anomalies_detected": anomaly_count,
        }
    finally:
        if close_db:
            db.close()


@router.post("/telemetry/tick", response_model=TelemetryTickResponse)
async def telemetry_tick(
    inject_anomaly: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Simulate one round of sensor data. Optional inject_anomaly spikes one building."""
    result = _perform_tick(inject_anomaly=inject_anomaly, db=db)

    # Broadcast via WebSocket
    import asyncio
    asyncio.ensure_future(manager.broadcast({
        "type": "tick",
        "data": {
            "timestamp": result["timestamp"].isoformat(),
            "energy_readings": result["energy_readings"],
            "occupancy_readings": result["occupancy_readings"],
            "anomalies_detected": result["anomalies_detected"],
        },
    }))

    return TelemetryTickResponse(**result)


# ===================================================================
# Energy / Occupancy History
# ===================================================================

@router.get("/telemetry/energy", response_model=PaginatedResponse)
def energy_history(
    building_id: int,
    page: int = 1,
    page_size: int = 100,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Energy reading history for a building (newest first)."""
    q = db.query(EnergyRecord).filter(EnergyRecord.building_id == building_id).order_by(EnergyRecord.ts.desc())
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedResponse(
        items=[EnergyRecordRead.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/telemetry/occupancy", response_model=PaginatedResponse)
def occupancy_history(
    classroom_id: int,
    page: int = 1,
    page_size: int = 100,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Occupancy history for a classroom (newest first).
    Students may only query library and hostel classrooms.
    """
    classroom = db.get(Classroom, classroom_id)
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")

    role_value = user.role.value if hasattr(user.role, "value") else user.role
    kind_value = classroom.kind.value if hasattr(classroom.kind, "value") else classroom.kind
    if role_value == "student" and kind_value not in ("library", "hostel"):
        raise HTTPException(status_code=403, detail="Students may only view library/hostel occupancy")

    q = db.query(OccupancyRecord).filter(OccupancyRecord.classroom_id == classroom_id).order_by(OccupancyRecord.ts.desc())
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedResponse(
        items=[OccupancyRecordRead.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )
