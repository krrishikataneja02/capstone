"""
Twin state router — GET /twin/state.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.deps import get_current_user, get_db
from app.models import User
from app.redis_client import cache_get, cache_set
from app.schemas import TwinStateResponse
from app.services.twin import get_twin_state

router = APIRouter(prefix="/twin", tags=["twin"])


@router.get("/state", response_model=TwinStateResponse)
def twin_state(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Per-building snapshot: latest energy, anomaly count, space occupancies."""
    cache_key = "twin:state:v1"
    cached_state = cache_get(cache_key)
    if cached_state is not None:
        return TwinStateResponse.model_validate(cached_state)

    state = get_twin_state(db)
    cache_set(cache_key, TwinStateResponse.model_validate(state).model_dump(mode="json"), ttl_seconds=5)
    return state
