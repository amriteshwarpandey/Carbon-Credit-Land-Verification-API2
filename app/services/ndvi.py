"""Satellite check: Sentinel-2 L2A NDVI for a plot, via a public STAC API (Earth Search) and COG reads.

Intended as a verification *signal* for auditors (did vegetation change after the practice?), not as
proof of sequestration. It picks the least-cloudy scene in a window using the scene-level cloud cover
(no per-pixel cloud mask), so treat values from partly cloudy scenes with care.

Needs `rasterio` (imported lazily) and outbound internet access.
"""
import math
from datetime import date, timedelta

import httpx

from app.config import settings
from app.services.geo import ACRE_M2


class NdviError(Exception):
    pass


def plot_bbox(geojson: dict | None, lat: float, lon: float, acreage: float) -> list[float]:
    """[west, south, east, north]: the polygon's bounds, or a square around the point sized by acreage."""
    if geojson and geojson.get("type") == "Polygon":
        xs = [p[0] for p in geojson["coordinates"][0]]
        ys = [p[1] for p in geojson["coordinates"][0]]
        return [min(xs), min(ys), max(xs), max(ys)]
    half_m = max(math.sqrt(acreage * ACRE_M2) / 2, 15)  # at least ~1.5 Sentinel-2 pixels
    dlat = half_m / 110_540
    dlon = half_m / (111_320 * max(math.cos(math.radians(lat)), 0.01))
    return [lon - dlon, lat - dlat, lon + dlon, lat + dlat]


def find_scene(bbox: list[float], start: date, end: date) -> dict | None:
    body = {
        "collections": ["sentinel-2-l2a"],
        "bbox": bbox,
        "datetime": f"{start.isoformat()}T00:00:00Z/{end.isoformat()}T23:59:59Z",
        "limit": 1,
        "query": {"eo:cloud_cover": {"lt": settings.ndvi_max_cloud_cover}},
        "sortby": [{"field": "properties.eo:cloud_cover", "direction": "asc"}],
    }
    try:
        resp = httpx.post(f"{settings.stac_url}/search", json=body, timeout=30)
        resp.raise_for_status()
        features = resp.json().get("features", [])
    except (httpx.HTTPError, ValueError) as exc:
        raise NdviError(f"STAC search failed: {exc}") from exc
    return features[0] if features else None


def mean_ndvi(scene: dict, bbox: list[float]) -> float | None:
    try:
        import numpy as np
        import rasterio
        from rasterio.warp import transform_bounds
        from rasterio.windows import from_bounds
    except ImportError as exc:
        raise NdviError("rasterio is not installed (pip install rasterio)") from exc

    def band(key: str):
        asset = scene["assets"][key]
        info = (asset.get("raster:bands") or [{}])[0]
        scale, offset = info.get("scale", 0.0001), info.get("offset", 0.0)
        with rasterio.open(asset["href"]) as src:
            window = from_bounds(*transform_bounds("EPSG:4326", src.crs, *bbox), transform=src.transform)
            data = src.read(1, window=window, boundless=False).astype("float64")
            nodata = src.nodata
        valid = data > 0 if nodata is None else data != nodata
        return data * scale + offset, valid

    try:
        with rasterio.Env(AWS_NO_SIGN_REQUEST="YES", GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR"):
            red, vr = band("red")
            nir, vn = band("nir")
    except (rasterio.errors.RasterioError, KeyError, ValueError) as exc:
        raise NdviError(f"Could not read satellite imagery: {exc}") from exc

    n = min(red.size, nir.size)
    red, nir, ok = red.ravel()[:n], nir.ravel()[:n], (vr.ravel()[:n] & vn.ravel()[:n])
    denom = nir + red
    ok &= denom > 0
    if not ok.any():
        return None
    return round(float(np.mean((nir[ok] - red[ok]) / denom[ok])), 4)


def ndvi_for_window(geojson, lat, lon, acreage, start: date, end: date) -> dict | None:
    bbox = plot_bbox(geojson, lat, lon, acreage)
    scene = find_scene(bbox, start, end)
    if not scene:
        return None
    props = scene.get("properties", {})
    return {
        "scene_id": scene.get("id"),
        "scene_date": (props.get("datetime") or "")[:10],
        "cloud_cover": props.get("eo:cloud_cover"),
        "mean_ndvi": mean_ndvi(scene, bbox),
    }


def ndvi_change(geojson, lat, lon, acreage, performed_on: date) -> dict:
    """NDVI from the best scene in the 60 days before the practice vs the 120 days after (capped at today)."""
    after_end = min(performed_on + timedelta(days=120), date.today())
    before = ndvi_for_window(geojson, lat, lon, acreage, performed_on - timedelta(days=60), performed_on)
    after = (
        ndvi_for_window(geojson, lat, lon, acreage, performed_on + timedelta(days=1), after_end)
        if after_end > performed_on
        else None
    )
    delta = None
    if before and after and before["mean_ndvi"] is not None and after["mean_ndvi"] is not None:
        delta = round(after["mean_ndvi"] - before["mean_ndvi"], 4)
    return {"source": "Sentinel-2 L2A (Earth Search)", "before": before, "after": after, "delta": delta}
