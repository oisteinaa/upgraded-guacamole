import type { ActivityHistory, Live } from "./types";

// Acquisition timestamps remain cell edges. Add blank cells for missing intervals,
// rather than extending a neighbouring row across a recording gap.
export function historyHeatmap(
  history: ActivityHistory | undefined,
  normalized: boolean,
): Live["heatmap"] {
  if (!history?.rows.length)
    return {
      status: "unavailable",
      note: "Collecting 10-second activity frames…",
    };
  const time_edges: number[] = [],
    values: (number | null)[][] = [],
    peak_channels: (number | null)[][] = [],
    raw: (number | null)[][] = [],
    medians: (number | null)[][] = [];
  const blank = () => Array(history.channel_edges.length - 1).fill(null);
  for (const row of history.rows) {
    if (!time_edges.length) time_edges.push(row.start);
    const last = time_edges[time_edges.length - 1];
    if (row.start > last + Math.max(1e-6, history.sample_interval ?? 0)) {
      time_edges.push(row.start);
      values.push(blank());
      peak_channels.push(blank());
      raw.push(blank());
      medians.push(blank());
    }
    // A sub-sample timestamp discrepancy is one shared display boundary, not
    // a missing frame. Original start/end timestamps remain in the snapshot.
    if (
      Math.abs(row.start - time_edges[time_edges.length - 1]) <=
      Math.max(1e-6, history.sample_interval ?? 0)
    )
      time_edges[time_edges.length - 1] = row.start;
    time_edges.push(row.end);
    values.push(normalized ? row.calm : row.raw);
    peak_channels.push(normalized ? row.calm_channels : row.raw_channels);
    raw.push(row.calm_raw);
    medians.push(row.medians);
  }
  return {
    status: "complete",
    channel_edges: history.channel_edges,
    time_edges,
    values,
    peak_channels,
    raw,
    medians,
    aggregation:
      "Maximum per-channel value within each native channel bin; one complete 10-second acquisition frame per row",
  };
}
