from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import settings
from app.db import get_db
from app.models import InterventionLog, LandPlot, Role, User
from app.routers.farmers import get_farmer_for
from app.schemas import InterventionCreate, InterventionOut, PlotCreate, PlotOut
from app.security import get_current_user, require_roles
from app.services.geo import find_overlap, plot_geometry, polygon_area_acres
from app.services.weather import WeatherError, fetch_weather

router = APIRouter(tags=["plots"])


def get_plot_for(db: Session, plot_id: int, user: User) -> LandPlot:
    plot = db.get(LandPlot, plot_id)
    if not plot:
        raise HTTPException(404, "Plot not found")
    get_farmer_for(db, plot.farmer_id, user)  # enforces agent ownership
    return plot


def _validate_spatially(db: Session, body: PlotCreate, user: User) -> None:
    """Reject malformed polygons, acreage that contradicts the drawn area, and overlaps with other plots."""
    lat0 = body.latitude
    try:
        geom = plot_geometry(body.geojson, body.latitude, body.longitude, body.acreage, lat0)
        measured = polygon_area_acres(body.geojson, lat0)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    ratio = settings.max_acreage_mismatch_ratio
    if measured is not None and ratio > 0 and abs(measured - body.acreage) > ratio * max(measured, body.acreage):
        raise HTTPException(
            422, f"Declared acreage ({body.acreage}) does not match the drawn polygon (~{measured} acres)"
        )
    other, shared = find_overlap(db, geom, body.latitude, body.longitude, lat0, settings.max_plot_overlap_ratio)
    if other:
        # Agents must not learn about other agents' plots, so only reviewers get the conflicting id.
        detail = f"Plot overlaps an already registered plot ({shared:.0%} of the smaller footprint)"
        if user.role != Role.field_agent:
            detail += f" - plot #{other.id}"
        raise HTTPException(409, detail)


@router.post("/farmers/{farmer_id}/plots", response_model=PlotOut, status_code=201)
def register_plot(
    farmer_id: int,
    body: PlotCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.field_agent, Role.admin)),
):
    get_farmer_for(db, farmer_id, user)
    _validate_spatially(db, body, user)
    plot = LandPlot(farmer_id=farmer_id, **body.model_dump())
    db.add(plot)
    db.commit()
    return plot


@router.get("/farmers/{farmer_id}/plots", response_model=list[PlotOut])
def list_plots(farmer_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_farmer_for(db, farmer_id, user)
    return db.scalars(select(LandPlot).where(LandPlot.farmer_id == farmer_id)).all()


@router.get("/plots/{plot_id}", response_model=PlotOut)
def get_plot(plot_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return get_plot_for(db, plot_id, user)


@router.get("/plots/{plot_id}/weather")
def plot_weather(
    plot_id: int,
    start: date | None = Query(None, description="Default: 90 days ago"),
    end: date | None = Query(None, description="Default: 7 days ago (NASA POWER lags real time)"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    plot = get_plot_for(db, plot_id, user)
    end = end or date.today() - timedelta(days=7)
    start = start or end - timedelta(days=83)
    if start > end:
        raise HTTPException(422, "start must be on or before end")
    try:
        return fetch_weather(plot.latitude, plot.longitude, start, end)
    except WeatherError as exc:
        raise HTTPException(502, str(exc))


@router.post("/plots/{plot_id}/interventions", response_model=InterventionOut, status_code=201)
def log_intervention(
    plot_id: int,
    body: InterventionCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(Role.field_agent, Role.admin)),
):
    plot = get_plot_for(db, plot_id, user)
    item = InterventionLog(plot_id=plot.id, submitted_by_id=user.id, **body.model_dump())
    db.add(item)
    db.commit()
    return item


@router.get("/plots/{plot_id}/interventions", response_model=list[InterventionOut])
def list_plot_interventions(plot_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    get_plot_for(db, plot_id, user)
    q = select(InterventionLog).where(InterventionLog.plot_id == plot_id).options(selectinload(InterventionLog.evidence))
    return db.scalars(q).all()
