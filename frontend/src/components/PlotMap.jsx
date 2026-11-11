import { useEffect, useRef } from "react";
import L from "leaflet";

// Leaflet's default marker icons break under bundlers; use circle markers instead.
const MARK = { radius: 8, color: "#166534", fillColor: "#22c55e", fillOpacity: 0.8 };

/**
 * Map for viewing a plot or picking a location.
 *  - `point` {lat, lon}: marker to show
 *  - `geojson`: polygon/point geometry to draw
 *  - `onPick(lat, lon)`: when provided, clicking the map picks a location
 */
export default function PlotMap({ point, geojson, onPick, height = 280 }) {
  const el = useRef(null);
  const map = useRef(null);
  const layer = useRef(null);
  const pickRef = useRef(onPick);
  pickRef.current = onPick;

  useEffect(() => {
    map.current = L.map(el.current).setView(point ? [point.lat, point.lon] : [20, 78], point ? 14 : 4);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(map.current);
    layer.current = L.layerGroup().addTo(map.current);
    map.current.on("click", (e) => pickRef.current?.(e.latlng.lat, e.latlng.lng));
    return () => map.current.remove();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    layer.current.clearLayers();
    let bounds;
    if (geojson?.type === "Polygon") {
      const poly = L.geoJSON(geojson, { style: { color: "#166534", weight: 2 } }).addTo(layer.current);
      bounds = poly.getBounds();
    }
    if (point) {
      L.circleMarker([point.lat, point.lon], MARK).addTo(layer.current);
      if (!bounds) map.current.setView([point.lat, point.lon], Math.max(map.current.getZoom(), 14));
    }
    if (bounds?.isValid()) map.current.fitBounds(bounds, { maxZoom: 17 });
  }, [point?.lat, point?.lon, geojson]);

  return <div ref={el} className="map" style={{ height, cursor: onPick ? "crosshair" : undefined }} />;
}
