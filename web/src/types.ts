export type Normalization = {
  status: string; note?: string; baseline_id?: string; available_channels: number;
  total_channels?: number; training_start?: number; training_end?: number;
  illustrative?: boolean; training_reference?: boolean; training_frames?: boolean[];
  channels?: number[]; times?: number[]; starts?: number[]; ends?: number[];
  scores?: Record<MetricName, (number | null)[][]>;
  raw?: Record<MetricName, number[][]>; medians?: Record<MetricName, (number | null)[]>;
  profile?: Live["profile"]; heatmap?: Live["heatmap"];
};
export type EventLocation = {
  lid: number; channel: number; channel_start: number; channel_end: number;
  latitude: number; longitude: number; mapping: string;
  lower_channel: number; upper_channel: number;
  located_channels: number; total_channels: number; basis: string; note: string;
  routes: string[];
  spans: { span_id: number; route: string; from_mast: string; to_mast: string }[];
  nearest_masts: { id: number; route: string; mast: string; distance_m: number }[];
};
export type EventRow = {
  location?: EventLocation | null;
  id: number;
  time: string;
  type: number;
  value: number | null;
  comment: string | null;
  classid: number | null;
  class_name: string | null;
  metric: string;
  route: string | null;
  alignment_verified: boolean | null;
  channel: number | null;
  lid: number | null;
  revision: number;
};
export type Review = {
  id: number;
  reviewer: string;
  note: string;
  class_name: string | null;
  reviewed_at: string;
};
export type EventDetail = EventRow & {
  reviews: Review[];
  context: null | {
    recording_id: number;
    source_linked?: boolean;
    alignment_verified: boolean;
    start_sample: number;
    stop_sample: number;
    channel: number;
  };
};
export type Overview = {
  mapping_lids: number[];
  counts: {
    events: number;
    unclassified: number;
    first_event: string;
    last_event: string;
    masts: number;
    spans: number;
    recordings: number;
    aligned: number;
  };
  classes: { classid: number; name: string }[];
  routes: { route: string; name: string }[];
  stations: { lid: number; name: string }[];
  environment: string;
  write_enabled: boolean;
  legacy_time_note: string;
};
export type Recording = {
  id: number;
  relative_path: string;
  acquisition_epoch: number;
  dt: number;
  samples: number;
  unit: string;
  channel_count: number;
  first_channel: number;
  time_verified: boolean;
  mapping_verified: boolean;
  processing: string;
};
export type Signal = {
  normalization?: Normalization;
  truncated?: boolean;
  requested_start?: number;
  requested_end?: number;
  stitch_note?: string;
  source_files?: { recording_id: number; relative_path: string; start: number; end: number }[];
  source_note?: string | null;
  recording_id: number;
  channel: number;
  unit: string;
  processing: string;
  time_verified: boolean;
  start: number;
  end: number;
  duration: number;
  sample_rate: number;
  acquisition_epoch: number;
  source_samples: number;
  display_points: number;
  x: number[];
  y: number[];
  trend_time: number[];
  trend_start: number;
  trend_window_seconds: number;
  channel_rms: number[][];
  channel_variance: number[][];
  rms: number[];
  variance: number[];
  heat_time: number[];
  heat_channels: number[];
  channel_bounds: number[] | null;
  heat: number[][];
  frequency: number[];
  power: number[];
  event_start?: number;
  event_end?: number;
};
export type Feature = {
  type: "Feature";
  id: number;
  geometry: { type: string; coordinates: any };
  properties: Record<string, any>;
};
export type Collection = { type: "FeatureCollection"; features: Feature[] };
export type Geography = { masts: Collection; spans: Collection };
export type Live = {
  normalization?: Normalization;
  demo?: boolean;
  demo_token?: string;
  demo_has_metric?: boolean;
  demo_source?: string;
  demo_position?: number;
  demo_count?: number;
  demo_cycle?: number;
  demo_preparing?: boolean;
  demo_mapping_note?: string;
  note?: string;
  summary_version?: number;
  filename?: string;
  lid?: number | null;
  duration?: number;
  published_at?: number;
  metric_processing?: string;
  profile?: { status: string; note?: string; start?: number; end?: number; channels?: (number | null)[]; values?: (number | null)[]; raw?: (number | null)[]; medians?: (number | null)[] };
  heatmap?: { status: string; note?: string; channel_edges?: number[]; time_edges?: number[]; values?: (number | null)[][]; peak_channels?: (number | null)[][]; aggregation?: string; raw?: (number | null)[][]; medians?: (number | null)[][] };
  detection?: { status: string; note?: string | null; evaluated_channels?: number; requested_channels?: number; total_channels?: number; candidate_count?: number; metric?: string; unit?: string; candidates?: { channel: number; value: number; threshold: number; rule: string; ratio: number }[] };
  frame?: number;
  frame_count?: number;
  status: string;
  age_seconds?: number;
  source_points?: number;
  display_points?: number;
  rms_min?: number;
  rms_max?: number;
  acquisition_epoch?: number;
  recording_id?: number;
  channel_count?: number;
  points: Record<string, number>[];
  mapping_verified?: boolean;
  unit?: string;
};
export const classColors: Record<number, string> = {
  0: "#9aa5b5",
  1: "#a3be8c",
  2: "#88c0d0",
  3: "#b48ead",
  4: "#d08770",
};
export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const r = await fetch("/api" + path, options);
  if (!r.ok) {
    const e = await r.json().catch(() => ({ detail: r.statusText }));
    throw new Error(
      typeof e.detail === "string"
        ? e.detail
        : "Please check the entered values.",
    );
  }
  return r.json();
}
export const number = (v: number | null | undefined) =>
  v == null ? "—" : v.toLocaleString(undefined, { maximumFractionDigits: 2 });
export const storedTime = (s: string) => s.replace("T", " ").slice(0, 19);
export const utcTime = (n: number) =>
  new Date(n * 1000).toISOString().replace("T", " ").slice(0, 19) + " UTC";

export type MetricName = "ac_rms" | "band_rms" | "peak" | "variance";
export const metricNames: Record<MetricName, string> = {
  ac_rms: "Mean-removed RMS",
  band_rms: "Band-limited RMS",
  peak: "Peak amplitude",
  variance: "Variance (advanced)",
};
export type Inspection = { rid: number; channel: number; frame: number };
export type MetricFrame = {
  normalization?: Normalization;
  acquisition_epoch: number;
  time_verified: boolean;
  recording_id: number;
  lid: number;
  metric: MetricName;
  unit: string;
  frame: number;
  frame_count: number;
  start: number;
  end: number;
  start_sample: number;
  stop_sample: number;
  actual_duration: number;
  complete: boolean;
  processing: string;
  band: number[];
  resolution_hz: number;
  data: Collection;
  scale: { min: number; max: number };
  mapping: {
    status: string;
    matched: number;
    recording_channels: number;
    unmatched_recording: number;
    exact: number;
    interpolated: number;
    outside: number;
    gap: number;
    unresolved: number;
    note: string;
  };
};
export type ColorScale = { min: number; max: number; log: boolean };
