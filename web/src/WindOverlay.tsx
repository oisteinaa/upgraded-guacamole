import { useEffect, useState } from "react";
import * as maplibregl from "maplibre-gl";
import { api, type MetricFrame } from "./types";
import { windArrow, type WindStation } from "./wind";

export default function WindOverlay({ map, mode, metricData }: {
  map: maplibregl.Map; mode: "live" | "investigate"; metricData: MetricFrame | null;
}) {
  const at = mode === "investigate" && metricData ? metricData.acquisition_epoch + metricData.start : null;
  const [loading, setLoading] = useState(false);
  const [stations, setStations] = useState<WindStation[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    setStations([]);
    setError("");
    if (mode === "investigate" && at === null) return;
    const update = async () => {
      setLoading(true);
      try {
        const data = await api<{ stations: WindStation[] }>(
          at === null ? "/map/wind" : `/map/wind?at=${at}`, { signal: abort.signal });
        if (!abort.signal.aborted) { setStations(data.stations); setError(""); }
      } catch (e) {
        if (!abort.signal.aborted) { setStations([]); setError("Wind forecast unavailable"); }
      } finally {
        if (!abort.signal.aborted) { setLoading(false); timer = setTimeout(update, 60000); }
      }
    };
    update();
    return () => { abort.abort(); clearTimeout(timer); };
  }, [mode, at, metricData]);
  useEffect(() => {
    const markers = stations.map(station => {
      const arrow = windArrow(station.speed, station.direction);
      const element = document.createElement("div");
      element.className = "wind-station";
      const note = station.stale ? " · stale / time unverified" : "";
      element.title = `${station.name} · ${station.speed ?? "unknown"} m/s · from ${station.direction ?? "unknown"}°\nForecast valid: ${station.source_time ?? station.time ?? "unknown"}${note}`;
      element.setAttribute("aria-label", element.title);
      if (arrow) {
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        const length = arrow.length;
        const head = 10;
        svg.setAttribute("viewBox", `0 0 24 ${length + 4}`);
        svg.setAttribute("width", "24");
        svg.setAttribute("height", String(length + 4));
        svg.classList.add("wind-arrow");
        const path = document.createElementNS(svg.namespaceURI, "path");
        path.setAttribute("d", `M12 2 L22 ${head + 2} L15 ${head + 2} L15 ${length + 2} L9 ${length + 2} L9 ${head + 2} L2 ${head + 2} Z`);
        path.setAttribute("stroke", "#16212d");
        path.setAttribute("stroke-width", "2");
        path.setAttribute("stroke-linejoin", "round");
        path.setAttribute("fill", arrow.color);
        svg.append(path);
        element.append(svg);
      }
      if (station.stale) element.classList.add("wind-station-stale");
      return new maplibregl.Marker({
        element, rotation: arrow?.rotation ?? 0,
        rotationAlignment: "map", pitchAlignment: "viewport",
      }).setLngLat([station.longitude, station.latitude]).addTo(map);
    });
    return () => markers.forEach(marker => marker.remove());
  }, [map, stations]);
  return <div className="wind-key">
    <strong>{mode === "live" ? "Latest wind forecast" : "Recording-time wind forecast"}</strong>
    {mode === "investigate" && <span>{at === null ? "Load a recording to see matching weather." : new Date(at * 1000).toISOString().replace("T", " ").replace("Z", " UTC")}</span>}
    {mode === "investigate" && metricData && !metricData.time_verified && <span>Recording time unverified; alignment is provisional.</span>}
    {loading && <span>Updating weather…</span>}
    {!loading && !error && stations.length > 0 && stations.every(s => s.speed === null) && <span>No matching weather within two hours.</span>}
    <span><b style={{ color: "#8ee06b" }}>≤8</b> · <b style={{ color: "#ffd15c" }}>&gt;8–18</b> · <b style={{ color: "#ff6b72" }}>&gt;18 m/s</b></span>
    <span>Blows toward arrowhead · length capped at 30 m/s</span>
    <span>Calm / missing: dot only · dashed dot: stale · hover for details</span>
    {error && <span role="alert">{error}</span>}
  </div>;
}
