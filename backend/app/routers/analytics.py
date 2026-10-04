"""
Analytics router — predictions, anomalies, simulations, optimization.

- POST /predictions/energy/{building_id}
- POST /predictions/occupancy/{classroom_id}
- GET  /predictions
- GET  /anomalies
- PATCH /anomalies/{id}
- POST /simulations
- GET  /simulations
- GET  /simulations/{id}
- POST /optimization/classrooms
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db, require_role
from app.models import (
    Anomaly,
    AnomalyStatus,
    Building,
    Classroom,
    ClassroomKind,
    Course,
    Enrollment,
    EnergyRecord,
    OccupancyRecord,
    Prediction,
    SimulationResult,
    SimulationScenario,
    Timetable,
    User,
    utcnow,
)
from app.redis_client import invalidate_twin_state
from app.schemas import (
    AnomalyRead,
    AnomalyUpdate,
    OptimizationResult,
    PaginatedResponse,
    PredictionRead,
    SimulationCreate,
    SimulationDetailRead,
    SimulationResultRead,
    SimulationScenarioRead,
)
from app.services.forecast import train_and_predict
from app.services.optimization import optimize_classroom_allocation
from app.services.simulation import run_close_building, run_enrollment_growth

router = APIRouter(tags=["analytics"])


# ===================================================================
# Predictions
# ===================================================================

@router.post("/predictions/energy/{building_id}", response_model=list[PredictionRead])
def predict_energy(
    building_id: int,
    n_future: int = Query(24, ge=1, le=168),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Train a Random Forest on energy history and predict next *n_future* hours."""
    building = db.get(Building, building_id)
    if not building:
        raise HTTPException(status_code=404, detail="Building not found")

    records = (
        db.query(EnergyRecord)
        .filter(EnergyRecord.building_id == building_id)
        .order_by(EnergyRecord.ts)
        .all()
    )
    if len(records) < 10:
        raise HTTPException(status_code=422, detail="Not enough data points (need >=10)")

    data = [{"ts": r.ts, "value": r.kwh} for r in records]
    result = train_and_predict(data, n_future=n_future)

    # Persist predictions
    created: list[Prediction] = []
    for p in result["predictions"]:
        pred = Prediction(
            entity_type="building",
            entity_id=building_id,
            metric="energy",
            target_ts=datetime.fromisoformat(p["ts"]),
            value=p["value"],
            model_name=result["model_name"],
            mae=result["mae"],
        )
        db.add(pred)
        created.append(pred)
    db.commit()
    for p in created:
        db.refresh(p)
    return created


@router.post("/predictions/occupancy/{classroom_id}", response_model=list[PredictionRead])
def predict_occupancy(
    classroom_id: int,
    n_future: int = Query(24, ge=1, le=168),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Train a Random Forest on occupancy history and predict next *n_future* hours."""
    classroom = db.get(Classroom, classroom_id)
    if not classroom:
        raise HTTPException(status_code=404, detail="Classroom not found")

    # Students can only predict library/hostel
    role_value = user.role.value if hasattr(user.role, "value") else user.role
    kind_value = classroom.kind.value if hasattr(classroom.kind, "value") else classroom.kind
    if role_value == "student" and kind_value not in ("library", "hostel"):
        raise HTTPException(status_code=403, detail="Students may only predict library/hostel occupancy")

    records = (
        db.query(OccupancyRecord)
        .filter(OccupancyRecord.classroom_id == classroom_id)
        .order_by(OccupancyRecord.ts)
        .all()
    )
    if len(records) < 10:
        raise HTTPException(status_code=422, detail="Not enough data points (need >=10)")

    data = [{"ts": r.ts, "value": float(r.count)} for r in records]
    result = train_and_predict(data, n_future=n_future)

    created: list[Prediction] = []
    for p in result["predictions"]:
        pred = Prediction(
            entity_type="classroom",
            entity_id=classroom_id,
            metric="occupancy",
            target_ts=datetime.fromisoformat(p["ts"]),
            value=p["value"],
            model_name=result["model_name"],
            mae=result["mae"],
        )
        db.add(pred)
        created.append(pred)
    db.commit()
    for p in created:
        db.refresh(p)
    return created


@router.get("/predictions", response_model=PaginatedResponse)
def list_predictions(
    entity_type: str | None = None,
    entity_id: int | None = None,
    page: int = 1,
    page_size: int = 50,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List stored predictions."""
    q = db.query(Prediction)
    if entity_type:
        q = q.filter(Prediction.entity_type == entity_type)
    if entity_id:
        q = q.filter(Prediction.entity_id == entity_id)
    total = q.count()
    items = q.order_by(Prediction.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedResponse(
        items=[PredictionRead.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


# ===================================================================
# Anomalies
# ===================================================================

@router.get("/anomalies", response_model=PaginatedResponse)
def list_anomalies(
    status: str | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(require_role("admin", "facility_manager")),
    db: Session = Depends(get_db),
):
    """List anomalies with optional filters. Facility Manager and Admin only."""
    q = db.query(Anomaly)
    if status:
        q = q.filter(Anomaly.status == status)
    if entity_type:
        q = q.filter(Anomaly.entity_type == entity_type)
    if entity_id:
        q = q.filter(Anomaly.entity_id == entity_id)
    total = q.count()
    items = q.order_by(Anomaly.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedResponse(
        items=[AnomalyRead.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.patch("/anomalies/{anomaly_id}", response_model=AnomalyRead)
def update_anomaly(
    anomaly_id: int,
    body: AnomalyUpdate,
    user: User = Depends(require_role("admin", "facility_manager")),
    db: Session = Depends(get_db),
):
    """
    Update anomaly status following lifecycle:
    DETECTED -> ACKNOWLEDGED -> RESOLVED
    DETECTED/ACKNOWLEDGED -> DISMISSED
    """
    anom = db.get(Anomaly, anomaly_id)
    if not anom:
        raise HTTPException(status_code=404, detail="Anomaly not found")

    current = anom.status.value if hasattr(anom.status, "value") else anom.status
    new_status = body.status

    # Validate lifecycle transitions
    valid_transitions = {
        "detected": {"acknowledged", "dismissed"},
        "acknowledged": {"resolved", "dismissed"},
    }
    allowed = valid_transitions.get(current, set())
    if new_status not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot transition from '{current}' to '{new_status}'. Allowed: {allowed or 'none (terminal state)'}",
        )

    anom.status = AnomalyStatus(new_status)
    if body.note is not None:
        anom.note = body.note

    now = utcnow()
    if new_status == "acknowledged":
        anom.acknowledged_at = now
    elif new_status in ("resolved", "dismissed"):
        anom.resolved_at = now

    db.commit()
    invalidate_twin_state()
    db.refresh(anom)
    return anom


# ===================================================================
# Simulations (admin only)
# ===================================================================

@router.post("/simulations", response_model=SimulationDetailRead, status_code=201)
def create_simulation(
    body: SimulationCreate,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """
    Run a what-if simulation. Types: 'enrollment_growth', 'close_building'.
    Deep-copies state (never mutates live data).
    """
    if body.simulation_type not in ("enrollment_growth", "close_building"):
        raise HTTPException(
            status_code=422,
            detail="simulation_type must be 'enrollment_growth' or 'close_building'",
        )

    # Build the twin state snapshot for the simulation
    state = _build_simulation_state(db)

    # Run simulation
    if body.simulation_type == "enrollment_growth":
        percent = body.parameters.get("percent")
        if percent is None or not isinstance(percent, (int, float)) or percent <= 0:
            raise HTTPException(status_code=422, detail="'percent' must be a positive number")
        department_id = body.parameters.get("department_id")
        sim_result = run_enrollment_growth(state, percent, department_id)

    elif body.simulation_type == "close_building":
        building_id = body.parameters.get("building_id")
        if building_id is None:
            raise HTTPException(status_code=422, detail="'building_id' is required")
        # Validate building exists
        if not db.get(Building, building_id):
            raise HTTPException(status_code=422, detail=f"Building {building_id} not found")
        sim_result = run_close_building(state, building_id)

    # Persist scenario + result atomically
    scenario = SimulationScenario(
        name=body.name,
        simulation_type=body.simulation_type,
        parameters=body.parameters,
        created_by=user.id,
    )
    db.add(scenario)
    db.flush()

    result = SimulationResult(
        scenario_id=scenario.id,
        baseline_metrics=sim_result["baseline_metrics"],
        scenario_metrics=sim_result["scenario_metrics"],
        deltas=sim_result["deltas"],
        warnings=sim_result["warnings"],
        feasible=sim_result["feasible"],
    )
    db.add(result)
    db.commit()
    db.refresh(scenario)
    db.refresh(result)

    return SimulationDetailRead(
        scenario=SimulationScenarioRead.model_validate(scenario),
        results=[SimulationResultRead.model_validate(result)],
    )


@router.get("/simulations", response_model=PaginatedResponse)
def list_simulations(
    page: int = 1,
    page_size: int = 20,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """List all simulation scenarios."""
    q = db.query(SimulationScenario).order_by(SimulationScenario.id.desc())
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedResponse(
        items=[SimulationScenarioRead.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/simulations/{scenario_id}", response_model=SimulationDetailRead)
def get_simulation(
    scenario_id: int,
    user: User = Depends(require_role("admin")),
    db: Session = Depends(get_db),
):
    """Get a simulation scenario with its results."""
    scenario = db.get(SimulationScenario, scenario_id)
    if not scenario:
        raise HTTPException(status_code=404, detail="Simulation not found")
    results = db.query(SimulationResult).filter(SimulationResult.scenario_id == scenario_id).all()
    return SimulationDetailRead(
        scenario=SimulationScenarioRead.model_validate(scenario),
        results=[SimulationResultRead.model_validate(r) for r in results],
    )


def _build_simulation_state(db: Session) -> dict:
    """Build a plain-dict snapshot of the twin state for simulation."""
    buildings = db.query(Building).all()
    classrooms = db.query(Classroom).all()
    courses = db.query(Course).all()
    enrollments = db.query(Enrollment).all()
    timetable_slots = db.query(Timetable).all()

    return {
        "buildings": [
            {"id": b.id, "name": b.name, "code": b.code, "building_type": b.building_type}
            for b in buildings
        ],
        "classrooms": [
            {
                "id": c.id,
                "name": c.name,
                "code": c.code,
                "building_id": c.building_id,
                "kind": c.kind.value if hasattr(c.kind, "value") else c.kind,
                "capacity": c.capacity,
            }
            for c in classrooms
        ],
        "courses": [
            {"id": c.id, "name": c.name, "code": c.code, "department_id": c.department_id}
            for c in courses
        ],
        "enrollments": [
            {"student_id": e.student_id, "course_id": e.course_id}
            for e in enrollments
        ],
        "timetable_slots": [
            {
                "id": t.id,
                "course_id": t.course_id,
                "classroom_id": t.classroom_id,
                "faculty_id": t.faculty_id,
                "day_of_week": t.day_of_week,
                "start_hour": t.start_hour,
                "end_hour": t.end_hour,
            }
            for t in timetable_slots
        ],
    }


# ===================================================================
# Optimization
# ===================================================================

@router.post("/optimization/classrooms", response_model=OptimizationResult)
def optimize_classrooms(
    apply: bool = False,
    user: User = Depends(require_role("admin", "facility_manager")),
    db: Session = Depends(get_db),
):
    """
    Recommend classroom allocation changes to minimize wasted seats.
    With apply=true (admin only), write changes to the timetable.
    """
    role_value = user.role.value if hasattr(user.role, "value") else user.role
    if apply and role_value != "admin":
        raise HTTPException(status_code=403, detail="Only admins can apply optimization changes")

    # Build input
    timetable_slots = db.query(Timetable).all()
    classrooms = db.query(Classroom).all()

    # Enrollment count per course
    enrollment_counts: dict[int, int] = {}
    for slot in timetable_slots:
        if slot.course_id not in enrollment_counts:
            enrollment_counts[slot.course_id] = db.query(Enrollment).filter(
                Enrollment.course_id == slot.course_id
            ).count()

    slots_data = []
    for t in timetable_slots:
        kind_val = None
        classroom = db.get(Classroom, t.classroom_id)
        if classroom:
            kind_val = classroom.kind.value if hasattr(classroom.kind, "value") else classroom.kind
        slots_data.append({
            "id": t.id,
            "course_id": t.course_id,
            "classroom_id": t.classroom_id,
            "enrollment": enrollment_counts.get(t.course_id, 0),
            "day_of_week": t.day_of_week,
            "start_hour": t.start_hour,
            "end_hour": t.end_hour,
            "kind": kind_val or "classroom",
        })

    classrooms_data = [
        {
            "id": c.id,
            "capacity": c.capacity,
            "kind": c.kind.value if hasattr(c.kind, "value") else c.kind,
        }
        for c in classrooms
    ]

    result = optimize_classroom_allocation(slots_data, classrooms_data)

    # Apply changes if requested
    if apply and result["changes"]:
        for change in result["changes"]:
            slot = db.get(Timetable, change["timetable_id"])
            if slot:
                slot.classroom_id = change["new_classroom_id"]
        db.commit()
        invalidate_twin_state()

    return OptimizationResult(**result)
