import type { LayerSpecification, SourceSpecification } from "maplibre-gl";

// OpenFreeMap vector tiles; a small local style keeps the map in the house palette.
// Source: https://openfreemap.org/quick_start/ (no application API key required).
export const basemapSource: SourceSpecification = {
  type: "vector",
  url: "https://tiles.openfreemap.org/planet",
  attribution:
    '<a href="https://openfreemap.org/">OpenFreeMap</a> © <a href="https://openmaptiles.org/">OpenMapTiles</a> © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
};
export const basemapLayers: LayerSpecification[] = [
  {
    id: "base-water",
    type: "fill",
    source: "basemap",
    "source-layer": "water",
    paint: { "fill-color": "#1d2732" },
  },
  {
    id: "base-wood",
    type: "fill",
    source: "basemap",
    "source-layer": "landcover",
    filter: ["==", ["get", "class"], "wood"],
    paint: { "fill-color": "#34413f", "fill-opacity": 0.35 },
  },
  {
    id: "base-landuse",
    type: "fill",
    source: "basemap",
    "source-layer": "landuse",
    filter: ["==", ["get", "class"], "residential"],
    paint: { "fill-color": "#414957", "fill-opacity": 0.45 },
  },
  {
    id: "base-roads",
    type: "line",
    source: "basemap",
    "source-layer": "transportation",
    filter: [
      "in",
      ["get", "class"],
      ["literal", ["motorway", "trunk", "primary", "secondary", "tertiary"]],
    ],
    paint: {
      "line-color": "#59616e",
      "line-opacity": 0.6,
      "line-width": ["interpolate", ["linear"], ["zoom"], 7, 0.5, 13, 2],
    },
  },
  {
    id: "base-buildings",
    type: "fill",
    source: "basemap",
    "source-layer": "building",
    minzoom: 13,
    paint: { "fill-color": "#475160", "fill-opacity": 0.7 },
  },
  {
    id: "base-places",
    type: "symbol",
    source: "basemap",
    "source-layer": "place",
    filter: [
      "in",
      ["get", "class"],
      ["literal", ["city", "town", "village", "hamlet"]],
    ],
    layout: {
      "text-field": ["coalesce", ["get", "name:latin"], ["get", "name"]],
      "text-font": ["Noto Sans Regular"],
      "text-size": ["interpolate", ["linear"], ["zoom"], 8, 10, 13, 13],
      "text-max-width": 8,
    },
    paint: {
      "text-color": "#9aa5b5",
      "text-halo-color": "#242933",
      "text-halo-width": 1.5,
    },
  },
];
