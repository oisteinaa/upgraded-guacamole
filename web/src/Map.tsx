import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
maplibregl.setWorkerUrl(workerUrl);
import { basemapSource, basemapLayers } from "./basemap";
import { Layers, Maximize, MapPin } from "lucide-react";
import {
  metricNames,
  type Geography,
  type Feature,
  type Collection,
  type MetricFrame,
  type ColorScale,
} from "./types";
import { reduceFibre, colorPosition } from "./mapReduction";
const empty = { type: "FeatureCollection", features: [] } as Collection;
const routeColor = [
  "match",
  ["get", "route"],
  "R06",
  "#88c0d0",
  "R12",
  "#a3be8c",
  "R13",
  "#b48ead",
  "R14",
  "#ebcb8b",
  "#9aa5b5",
] as any;
export default function Map({
  geo,
  events,
  route,
  selected,
  onSelect,
  onEvent,
  fibre,
  metricData,
  scale,
  onChannel,
}: {
  geo: Geography | null;
  events: Collection;
  route: string;
  selected: Feature | null;
  onSelect: (f: Feature) => void;
  onEvent: (id: number) => void;
  fibre: Collection;
  metricData: MetricFrame | null;
  scale: ColorScale;
  onChannel: (f: Feature) => void;
}) {
  const container = useRef<HTMLDivElement>(null),
    map = useRef<maplibregl.Map | null>(null);
  const [ready, setReady] = useState(false),
    [basemap, setBasemap] = useState(true),
    [masts, setMasts] = useState(true),
    [water, setWater] = useState(false),
    [spansVisible, setSpansVisible] = useState(false),
    [displayCount, setDisplayCount] = useState(0),
    [error, setError] = useState("");
  const selectRef = useRef(onSelect);
  selectRef.current = onSelect;
  const channelRef = useRef(onChannel);
  channelRef.current = onChannel;
  const metricRef = useRef(metricData);
  metricRef.current = metricData;
  const eventRef = useRef(onEvent);
  eventRef.current = onEvent;
  useEffect(() => {
    let m: maplibregl.Map;
    try {
      m = new maplibregl.Map({
        container: container.current!,
        center: [14.02, 68.18],
        zoom: 8.5,
        attributionControl: false,
        style: {
          version: 8,
          sources: {},
          glyphs: "https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf",
          layers: [
            {
              id: "background",
              type: "background",
              paint: { "background-color": "#2b333f" },
            },
          ],
        },
      });
    } catch {
      setError(
        "Map graphics are unavailable. Event and recording review remain available.",
      );
      return;
    }
    map.current = m;
    m.addControl(
      new maplibregl.NavigationControl({ showCompass: false }),
      "bottom-right",
    );
    m.addControl(new maplibregl.ScaleControl(), "bottom-left");
    m.addControl(
      new maplibregl.AttributionControl({ compact: true }),
      "bottom-right",
    );
    m.on("error", () =>
      setError("Basemap unavailable · asset layers remain available"),
    );
    m.on("load", () => {
      m.addSource("basemap", basemapSource);
      for (const layer of basemapLayers) m.addLayer(layer);
      for (const id of [
        "spans",
        "masts",
        "events",
        "selected",
        "live",
        "fibre",
      ])
        m.addSource(id, {
          type: "geojson",
          data: empty as any,
          ...(id === "events" ? { cluster: true, clusterRadius: 35 } : {}),
        });
      m.addLayer({
        id: "span-glow",
        type: "line",
        source: "spans",
        paint: {
          "line-color": routeColor,
          "line-width": 7,
          "line-opacity": 0.12,
        },
      });
      m.addLayer({
        id: "spans",
        type: "line",
        source: "spans",
        paint: {
          "line-color": routeColor,
          "line-width": 2,
          "line-opacity": 0.8,
          "line-dasharray": [3, 1],
        },
      });
      m.addLayer({
        id: "water",
        type: "line",
        source: "spans",
        filter: [
          "in",
          ["get", "water_status"],
          ["literal", ["map_candidate", "confirmed_water"]],
        ],
        paint: {
          "line-color": "#88c0d0",
          "line-width": 6,
          "line-opacity": 0.8,
        },
        layout: { visibility: "none" },
      });
      m.addLayer({
        id: "masts",
        type: "circle",
        source: "masts",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, 2, 13, 5],
          "circle-color": routeColor,
          "circle-stroke-color": "#242933",
          "circle-stroke-width": 1,
        },
      });
      m.addLayer({
        id: "fibre",
        type: "circle",
        source: "fibre",
        paint: {
          "circle-radius": 2,
          "circle-color": "#647080",
          "circle-opacity": 0.6,
        },
      });
      m.addLayer({
        id: "live",
        type: "circle",
        source: "live",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 8, 3, 14, 4],
          "circle-opacity": 0.95,
          "circle-color": [
            "interpolate",
            ["linear"],
            ["get", "color_value"],
            0,
            "#536b91",
            0.3,
            "#81a1c1",
            0.55,
            "#88c0d0",
            0.8,
            "#ebcb8b",
            1,
            "#d08770",
          ],
        },
      });
      const tooltip = new maplibregl.Popup({
        closeButton: false,
        closeOnClick: false,
      });
      m.on("mousemove", "live", (e) => {
        const f = e.features?.[0];
        if (!f) return;
        const p = f.properties;
        tooltip
          .setLngLat((f.geometry as any).coordinates)
          .setText(
            `Channel ${p.recording_channel} · ${Number(p.value).toPrecision(4)} ${metricRef.current?.unit ?? ""} · ${p.bucket_count} channel(s) in display group`,
          )
          .addTo(m);
      });
      m.on("mouseleave", "live", () => tooltip.remove());
      m.addLayer({
        id: "events",
        type: "circle",
        source: "events",
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-radius": 8,
          "circle-stroke-color": "#242933",
          "circle-stroke-width": 2,
          "circle-color": [
            "match",
            ["get", "classid"],
            1,
            "#a3be8c",
            2,
            "#88c0d0",
            3,
            "#b48ead",
            4,
            "#d08770",
            "#9aa5b5",
          ],
        },
      });
      m.addLayer({
        id: "clusters",
        type: "circle",
        source: "events",
        filter: ["has", "point_count"],
        paint: {
          "circle-color": "#88c0d0",
          "circle-radius": [
            "step",
            ["get", "point_count"],
            14,
            20,
            19,
            100,
            24,
          ],
          "circle-opacity": 0.85,
          "circle-stroke-width": 2,
          "circle-stroke-color": "#242933",
        },
      });
      m.addLayer({
        id: "selected-line",
        type: "line",
        source: "selected",
        filter: ["==", ["geometry-type"], "LineString"],
        paint: { "line-color": "#eceff4", "line-width": 5 },
      });
      m.addLayer({
        id: "selected-point",
        type: "circle",
        source: "selected",
        filter: ["==", ["geometry-type"], "Point"],
        paint: {
          "circle-radius": 10,
          "circle-color": "transparent",
          "circle-stroke-color": "#eceff4",
          "circle-stroke-width": 3,
        },
      });
      m.on("click", async (e) => {
        const features = m.queryRenderedFeatures(e.point, {
          layers: ["clusters", "events", "live", "masts", "spans"],
        });
        const f = features[0];
        if (!f) return;
        if (f.layer.id === "clusters") {
          const z = await (
            m.getSource("events") as maplibregl.GeoJSONSource
          ).getClusterExpansionZoom(f.properties.cluster_id);
          m.easeTo({ center: (f.geometry as any).coordinates, zoom: z });
        } else if (f.layer.id === "events")
          eventRef.current(Number(f.properties.id));
        else if (f.layer.id === "live")
          channelRef.current({
            type: "Feature",
            id: Number(f.id),
            geometry: f.geometry as any,
            properties: f.properties,
          });
        else
          selectRef.current({
            type: "Feature",
            id: Number(f.id),
            geometry: f.geometry as any,
            properties: f.properties,
          });
      });
      for (const id of ["masts", "spans", "events", "clusters", "live"]) {
        m.on("mouseenter", id, () => (m.getCanvas().style.cursor = "pointer"));
        m.on("mouseleave", id, () => (m.getCanvas().style.cursor = ""));
      }
      setReady(true);
    });
    const resize = new ResizeObserver(() => m.resize());
    resize.observe(container.current!);
    return () => {
      resize.disconnect();
      m.remove();
      map.current = null;
    };
  }, []);
  useEffect(() => {
    if (!ready || !geo) return;
    const m = map.current!;
    for (const id of ["masts", "spans"] as const)
      (m.getSource(id) as maplibregl.GeoJSONSource).setData(geo[id] as any);
    const bounds = new maplibregl.LngLatBounds();
    geo.masts.features.forEach((f) => bounds.extend(f.geometry.coordinates));
    m.fitBounds(bounds, { padding: 65, duration: 0 });
  }, [geo, ready]);
  useEffect(() => {
    if (!ready) return;
    (map.current!.getSource("events") as maplibregl.GeoJSONSource).setData(
      events as any,
    );
  }, [events, ready]);
  useEffect(() => {
    if (!ready) return;
    const m = map.current!;
    for (const id of ["spans", "span-glow", "masts"])
      m.setFilter(id, route ? ["==", ["get", "route"], route] : null);
    m.setFilter("water", [
      "all",
      [
        "in",
        ["get", "water_status"],
        ["literal", ["map_candidate", "confirmed_water"]],
      ],
      ...(route ? [["==", ["get", "route"], route]] : []),
    ] as any);
  }, [route, ready]);
  useEffect(() => {
    if (!ready) return;
    for (const layer of basemapLayers)
      map.current!.setLayoutProperty(
        layer.id,
        "visibility",
        basemap ? "visible" : "none",
      );
    map.current!.setLayoutProperty(
      "masts",
      "visibility",
      masts ? "visible" : "none",
    );
    map.current!.setLayoutProperty(
      "water",
      "visibility",
      water ? "visible" : "none",
    );
    for (const id of ["spans", "span-glow"])
      map.current!.setLayoutProperty(
        id,
        "visibility",
        spansVisible ? "visible" : "none",
      );
  }, [ready, basemap, masts, water, spansVisible]);
  useEffect(() => {
    if (!ready) return;
    const m = map.current!;
    (m.getSource("selected") as maplibregl.GeoJSONSource).setData({
      type: "FeatureCollection",
      features: selected ? [selected] : [],
    } as any);
    if (selected) {
      const c =
        selected.geometry.type === "Point"
          ? selected.geometry.coordinates
          : selected.geometry.coordinates[0];
      m.easeTo({ center: c, zoom: Math.max(m.getZoom(), 11), duration: 600 });
    }
  }, [ready, selected]);
  useEffect(() => {
    if (!ready) return;
    const m = map.current!;
    const update = () => {
      const canvas = m.getCanvas();
      const cell = m.getZoom() >= 14 ? 1 : 6;
      const background = reduceFibre(
        fibre.features,
        (c) => m.project(c),
        canvas.clientWidth,
        canvas.clientHeight,
        cell,
      );
      const colored = reduceFibre(
        metricData?.data.features ?? [],
        (c) => m.project(c),
        canvas.clientWidth,
        canvas.clientHeight,
        cell,
      ).map((f) => ({
        ...f,
        properties: {
          ...f.properties,
          color_value: colorPosition(
            f.properties.value,
            scale.min,
            scale.max,
            scale.log,
          ),
        },
      }));
      (m.getSource("fibre") as maplibregl.GeoJSONSource).setData({
        type: "FeatureCollection",
        features: background,
      } as any);
      (m.getSource("live") as maplibregl.GeoJSONSource).setData({
        type: "FeatureCollection",
        features: colored,
      } as any);
      setDisplayCount(colored.length);
    };
    update();
    m.on("moveend", update);
    m.on("resize", update);
    return () => {
      m.off("moveend", update);
      m.off("resize", update);
    };
  }, [ready, fibre, metricData, scale]);
  const fit = () => {
    if (!geo || !map.current) return;
    const b = new maplibregl.LngLatBounds();
    geo.masts.features
      .filter((f) => !route || f.properties.route === route)
      .forEach((f) => b.extend(f.geometry.coordinates));
    if (!b.isEmpty()) map.current.fitBounds(b, { padding: 65 });
  };
  return (
    <section
      data-ready={ready}
      className="map-wrap"
      aria-label="Cable network map"
    >
      <div ref={container} className="map-canvas" />
      <div className="map-label">
        <span className="eyebrow">NETWORK OVERVIEW</span>
        <strong>Lofoten, Norway</strong>
        <span>4 routes · WGS84</span>
      </div>
      <div className="map-tools">
        <button onClick={fit} title="Fit network" aria-label="Fit network">
          <Maximize size={16} />
        </button>
        <button
          onClick={() => setBasemap(!basemap)}
          className={basemap ? "active" : ""}
          title="Toggle basemap"
          aria-label="Toggle basemap"
        >
          <Layers size={16} />
        </button>
        <button
          onClick={() => setMasts(!masts)}
          className={masts ? "active" : ""}
          title="Toggle masts"
          aria-label="Toggle masts"
        >
          <MapPin size={16} />
        </button>
      </div>
      <div className="map-legend">
        <div>
          {["R06", "R12", "R13", "R14"].map((r, i) => (
            <span key={r}>
              <i
                style={{
                  background: ["#88c0d0", "#a3be8c", "#b48ead", "#ebcb8b"][i],
                }}
              />
              {r}
            </span>
          ))}
        </div>
        <small>Dashed spans are inferred connections</small>
        {metricData && (
          <small>
            {metricNames[metricData.metric]} · {displayCount} display points
            <br />
            Gray: mapped fibre without displayed signal
          </small>
        )}
        <label>
          <input
            type="checkbox"
            checked={spansVisible}
            onChange={(e) => setSpansVisible(e.target.checked)}
          />{" "}
          Inferred mast spans
        </label>
        <label>
          <input
            type="checkbox"
            checked={water}
            onChange={(e) => setWater(e.target.checked)}
          />{" "}
          Water crossing candidates
        </label>
      </div>
      {error && <div className="map-warning">{error}</div>}
    </section>
  );
}
