"""
Twin state aggregation — build the per-building snapshot served at GET /twin/state.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import (
    Anomaly,
    AnomalyStatus,
    Building,
    EnergyRecord,
    OccupancyRecord,
)


def get_twin_state(db: Session) -> dict:
    """
    Return a dict with one entry per building containing:
    - latest energy reading
    - open anomaly count
    - per-space latest occupancy + utilisation %
    """
    buildings = db.query(Building).all()
    result: list[dict] = []

    for building in buildings:
        # Latest energy
        latest_energy = (
            db.query(EnergyRecord)
            .filter(EnergyRecord.building_id == building.id)
            .order_by(EnergyRecord.ts.desc())
            .first()
        )

        # Open anomalies
        open_count: int = (
            db.query(func.count(Anomaly.id))
            .filter(
                Anomaly.entity_type == "building",
                Anomaly.entity_id == building.id,
                Anomaly.status.in_(
                    [AnomalyStatus.detected, AnomalyStatus.acknowledged]
                ),
            )
            .scalar()
        ) or 0

        # Spaces
        spaces: list[dict] = []
        for room in building.classrooms:
            latest_occ = (
                db.query(OccupancyRecord)
                .filter(OccupancyRecord.classroom_id == room.id)
                .order_by(OccupancyRecord.ts.desc())
                .first()
            )
            occ_count = latest_occ.count if latest_occ else None
            utilization = None
            if occ_count is not None and room.capacity > 0:
                utilization = round(occ_count / room.capacity * 100, 1)

            kind_val = room.kind.value if hasattr(room.kind, "value") else room.kind
            spaces.append({
                "classroom_id": room.id,
                "name": room.name,
                "kind": kind_val,
                "capacity": room.capacity,
                "latest_occupancy": occ_count,
                "utilization": utilization,
            })

        result.append({
            "building_id": building.id,
            "name": building.name,
            "building_type": building.building_type,
            "latest_energy_kwh": latest_energy.kwh if latest_energy else None,
            "open_anomaly_count": open_count,
            "spaces": spaces,
        })

    return {
        "buildings": result,
        "timestamp": datetime.now(timezone.utc).replace(tzinfo=None),
    }
