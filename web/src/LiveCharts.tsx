import { memo, useMemo } from "react";
import type { Data, Layout } from "plotly.js";
import Chart from "./Chart";
import { number, type Live, type MetricFrame } from "./types";
import {
  fibreAxis,
  geographicSections,
  profileOrder,
  heatOrder,
} from "./fibreAxis";
const colors: [number, string][] = [
  [0, "#536b91"],
  [0.3, "#81a1c1"],
  [0.55, "#88c0d0"],
  [0.8, "#ebcb8b"],
  [1, "#d08770"],
];
export default memo(function LiveCharts({
  snapshot,
  geography,
  normalized = false,
  maximum,
  selected,
  onChannel,
}: {
  snapshot: Live | null;
  geography?: MetricFrame | null;
  normalized?: boolean;
  maximum: number;
  selected: number | null;
  onChannel: (channel: number) => void;
}) {
  const { profileData, heatData, profileLayout, heatLayout } = useMemo(() => {
    const p = normalized ? snapshot?.normalization?.profile : snapshot?.profile,
      h = normalized ? snapshot?.normalization?.heatmap : snapshot?.heatmap;
    const sections = geographicSections(
      geography?.mapping.regions ?? [],
      geography?.data.features ?? [],
    );
    const axis = sections.length ? fibreAxis(sections) : null;
    const selectedX = axis ? axis.position(selected) : selected;
    const pi =
      axis && p?.channels
        ? profileOrder(p.channels, axis)
        : (p?.channels?.map((_, i) => i) ?? []);
    const heat =
      axis && h?.channel_edges ? heatOrder(h.channel_edges, axis) : null;
    const reorder = (row?: (number | null)[]) =>
      pi.map((i) => (i == null ? null : (row?.[i] ?? null)));
    const heatRows = (rows?: (number | null)[][]) =>
      rows?.map((row) =>
        heat ? heat.indices.map((i) => (i == null ? null : row[i])) : row,
      );
    const ticks = axis?.spans.flatMap((span) => {
      const step = 20000;
      const interior: number[] = [];
      for (
        let ch = Math.ceil(Math.min(span.start, span.end) / step) * step;
        ch < Math.max(span.start, span.end);
        ch += step
      )
        if (Math.abs(ch - span.start) > 5000 && Math.abs(ch - span.end) > 5000)
          interior.push(ch);
      return [span.start, ...interior, span.end].sort(
        (a, b) => span.direction * (a - b),
      );
    });
    const tickLabels = ticks?.flatMap((ch, i) => {
      if (i > 0 && axis!.section(ticks[i - 1]) !== axis!.section(ch)) return [];
      const next = ticks[i + 1];
      if (next != null && axis!.section(ch) !== axis!.section(next))
        return [
          {
            x: (axis!.position(ch)! + axis!.position(next)!) / 2,
            text: `${ch.toLocaleString("en-GB")} | ${next.toLocaleString("en-GB")}`,
          },
        ];
      return [{ x: axis!.position(ch)!, text: ch.toLocaleString("en-GB") }];
    });
    const shapes: Partial<Layout>["shapes"] =
      selectedX == null
        ? []
        : [
            {
              type: "line",
              x0: selectedX,
              x1: selectedX,
              y0: 0,
              y1: 1,
              yref: "paper",
              line: { color: "#eceff4", width: 1, dash: "dot" },
            },
          ];
    const common: Partial<Layout> = {
      margin: { l: 56, r: 15, t: 8, b: 65 },
      shapes,
      uirevision: `${snapshot?.lid}-${snapshot?.unit}-${sections.map((s) => `${s.start}:${s.end}`).join(",")}`,
      hovermode: "closest",
      xaxis: {
        title: {
          text: axis
            ? "Fibre order · south → north (channel ID)"
            : "Channel ID · geographic order unavailable",
        },
        ...(axis
          ? {
              tickmode: "array" as const,
              tickvals: tickLabels!.map((tick) => tick.x),
              ticktext: tickLabels!.map((tick) => tick.text),
              tickangle: -35,
              range: [-500, axis.extent + 500],
            }
          : {}),
        gridcolor: "#3b4252",
        zeroline: false,
      },
    };
    const profileData: Data[] =
      p?.status === "complete"
        ? [
            {
              type: "scatter",
              mode: "lines+markers",
              x: pi.map((i) =>
                i == null
                  ? null
                  : axis
                    ? axis.position(p.channels?.[i])
                    : (p.channels?.[i] ?? null),
              ),
              y: reorder(p.values),
              connectgaps: false,
              line: { color: "#81a1c1", width: 1 },
              marker: {
                size: 3,
                color: reorder(p.values) as number[],
                colorscale: colors,
                cmin: 0,
                cmax: maximum,
              },
              customdata: pi.map((i) =>
                i == null
                  ? [null, null, null]
                  : [p.channels?.[i], p.raw?.[i], p.medians?.[i]],
              ) as number[][],
              hovertemplate: normalized
                ? "Channel %{customdata[0]}<br>Calm score %{y:.4g}<br>Raw %{customdata[1]:.4g}<br>Calm median %{customdata[2]:.4g}<extra></extra>"
                : "Channel %{customdata[0]}<br>AC RMS %{y:.4g}<extra></extra>",
            },
          ]
        : [];
    const heatData: Data[] =
      h?.status === "complete"
        ? [
            {
              type: "heatmap",
              x: heat?.edges ?? h.channel_edges,
              y: h.time_edges,
              z: heatRows(h.values),
              customdata: (normalized
                ? h.peak_channels?.map((row, r) =>
                    (heat?.indices ?? row.map((_, i) => i)).map((c) =>
                      c == null
                        ? [null, null, null]
                        : [row[c], h.raw?.[r][c], h.medians?.[r][c]],
                    ),
                  )
                : heatRows(h.peak_channels)) as any,
              colorscale: colors,
              zmin: 0,
              zmax: maximum,
              hoverongaps: false,
              connectgaps: false,
              showscale: false,
              hovertemplate: normalized
                ? "Peak channel %{customdata[0]}<br>Time %{y:.3f} s<br>Calm score %{z:.4g}<br>Raw %{customdata[1]:.4g}<br>Median %{customdata[2]:.4g}<extra></extra>"
                : "Peak channel %{customdata}<br>Time %{y:.3f} s<br>Max AC RMS %{z:.4g}<extra></extra>",
            },
          ]
        : [];
    return {
      profileData,
      heatData,
      profileLayout: {
        ...common,
        yaxis: {
          title: { text: normalized ? "Calm score" : "AC RMS" },
          gridcolor: "#3b4252",
          rangemode: "tozero",
        },
      } as Partial<Layout>,
      heatLayout: {
        ...common,
        yaxis: { title: { text: "File time (s)" }, gridcolor: "#3b4252" },
      } as Partial<Layout>,
    };
  }, [snapshot, geography, maximum, selected, normalized]);
  const h = normalized ? snapshot?.normalization?.heatmap : snapshot?.heatmap,
    p = normalized ? snapshot?.normalization?.profile : snapshot?.profile;
  const edges = h?.time_edges;
  const resolution =
    edges && edges.length > 1
      ? (edges[edges.length - 1] - edges[0]) / (edges.length - 1)
      : null;
  return (
    <>
      <section className="live-card" aria-label="Activity along the fibre">
        <header>
          <h2>Activity along the fibre</h2>
          <span>{normalized ? "Calm score" : "AC RMS"}</span>
        </header>
        <p className="live-chart-caption">
          {snapshot
            ? `Map frame · ${number(p?.start)}–${number(p?.end)} s · ${normalized ? "calm score" : (snapshot.unit ?? "")}`
            : "Latest acquisition · same frame as the map"}
        </p>
        {profileData.length ? (
          <Chart
            data={profileData}
            layout={profileLayout}
            onPoint={(point) => {
              if (
                Array.isArray(point.customdata) &&
                typeof point.customdata[0] === "number"
              )
                onChannel(point.customdata[0]);
            }}
          />
        ) : (
          <div className="live-empty">
            {p?.note ??
              (snapshot
                ? "Activity summary unavailable for this capture"
                : "Waiting for current live signal")}
          </div>
        )}
      </section>
      <section className="live-card" aria-label="Activity through the file">
        <header>
          <h2>Activity through the file</h2>
          <span>WHOLE FILE</span>
        </header>
        <p className="live-chart-caption" title={h?.aggregation}>
          {normalized
            ? "Maximum calm score per ten-second frame/channel bin"
            : "Maximum AC RMS per time/channel bin"}
          {resolution != null ? ` · ≈${number(resolution)} s/bin` : ""}
        </p>
        {heatData.length ? (
          <Chart
            data={heatData}
            layout={heatLayout}
            onPoint={(point) => {
              if (
                Array.isArray(point.customdata) &&
                typeof point.customdata[0] === "number"
              )
                onChannel(point.customdata[0]);
              else if (typeof point.customdata === "number")
                onChannel(point.customdata);
            }}
          />
        ) : (
          <div className="live-empty">
            {h?.note ??
              (snapshot
                ? "Heatmap unavailable for this capture"
                : "Waiting for current live signal")}
          </div>
        )}
        <div className="live-amplitude-key">
          <span>0</span>
          <i />
          <span>
            {number(maximum)}{" "}
            {normalized ? "calm score" : (snapshot?.unit ?? "")}
          </span>
        </div>
      </section>
    </>
  );
});
