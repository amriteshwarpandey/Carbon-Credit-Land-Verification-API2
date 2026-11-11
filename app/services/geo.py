"""Spatial checks (pure Python via shapely; no PostGIS required).

Geometry is projected to local metres (equirectangular, fine at plot scale) so areas are meaningful.
Plots registered as a single point are modelled as a circle with the declared acreage.
"""
import math

from shapely.geometry import Point, shape
from shapely.affinity import affine_transform
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LandPlot

ACRE_M2 = 4046.8564224
SEARCH_RADIUS_DEG = 0.5  # candidate prefilter around the new plot


def _to_metres(geom, lat0: float):
    kx, ky = 111_320 * math.cos(math.radians(lat0)), 110_540
    return affine_transform(geom, [kx, 0, 0, ky, 0, 0])


def plot_geometry(geojson: dict | None, lat: float, lon: float, acreage: float, lat0: float):
    """Plot footprint in metres relative to the projection at ``lat0``. Raises ValueError if malformed."""
    if geojson and geojson.get("type") == "Polygon":
        try:
            geom = shape(geojson)
        except Exception as exc:  # shapely raises various errors for bad coordinates
            raise ValueError(f"Invalid polygon: {exc}") from exc
        if not geom.is_valid or geom.is_empty:
            raise ValueError("Invalid polygon (self-intersecting, unclosed or empty)")
        return _to_metres(geom, lat0)
    return _to_metres(Point(lon, lat), lat0).buffer(math.sqrt(acreage * ACRE_M2 / math.pi))


def polygon_area_acres(geojson: dict | None, lat0: float) -> float | None:
    if not geojson or geojson.get("type") != "Polygon":
        return None
    return round(plot_geometry(geojson, lat0, 0, 0, lat0).area / ACRE_M2, 3)


def find_overlap(db: Session, new_geom, lat: float, lon: float, lat0: float, max_ratio: float):
    """First existing plot whose overlap exceeds ``max_ratio`` of the smaller footprint, with the ratio."""
    lon_span = SEARCH_RADIUS_DEG / max(math.cos(math.radians(lat0)), 0.01)
    candidates = db.scalars(
        select(LandPlot).where(
            LandPlot.latitude.between(lat - SEARCH_RADIUS_DEG, lat + SEARCH_RADIUS_DEG),
            LandPlot.longitude.between(lon - lon_span, lon + lon_span),
        )
    )
    for other in candidates:
        try:
            other_geom = plot_geometry(other.geojson, other.latitude, other.longitude, other.acreage, lat0)
        except ValueError:
            continue
        if not new_geom.intersects(other_geom):
            continue
        shared = new_geom.intersection(other_geom).area
        smaller = min(new_geom.area, other_geom.area)
        if smaller > 0 and shared / smaller > max_ratio:
            return other, round(shared / smaller, 3)
    return None, 0.0
