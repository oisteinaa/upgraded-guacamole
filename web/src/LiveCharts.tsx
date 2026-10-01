import { memo, useMemo } from "react";
import type { Data, Layout } from "plotly.js";
import Chart from "./Chart";
import { number, type Live } from "./types";
const colors: [number, string][] = [
  [0, "#536b91"],
  [0.3, "#81a1c1"],
  [0.55, "#88c0d0"],
  [0.8, "#ebcb8b"],
  [1, "#d08770"],
];
export default memo(function LiveCharts({
  snapshot,
  normalized = false,
  maximum,
  selected,
  onChannel,
}: {
  snapshot: Live | null;
  normalized?: boolean;
  maximum: number;
  selected: number | null;
  onChannel: (channel: number) => void;
}) {
  const { profileData, heatData, profileLayout, heatLayout } = useMemo(() => {
    const p = normalized ? snapshot?.normalization?.profile : snapshot?.profile,
      h = normalized ? snapshot?.normalization?.heatmap : snapshot?.heatmap;
    const shapes: Partial<Layout>["shapes"] =
      selected == null
        ? []
        : [
            {
              type: "line",
              x0: selected,
              x1: selected,
              y0: 0,
              y1: 1,
              yref: "paper",
              line: { color: "#eceff4", width: 1, dash: "dot" },
            },
          ];
    const common: Partial<Layout> = {
      margin: { l: 56, r: 15, t: 8, b: 40 },
      shapes,
      uirevision: `${snapshot?.lid}-${snapshot?.unit}`,
      hovermode: "closest",
      xaxis: {
        title: { text: "Channel ID" },
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
              x: p.channels,
              y: p.values,
              connectgaps: false,
              line: { color: "#81a1c1", width: 1 },
              marker: {
                size: 3,
                color: p.values as number[],
                colorscale: colors,
                cmin: 0,
                cmax: maximum,
              },
              customdata: p.values?.map((_, i) => [
                p.raw?.[i],
                p.medians?.[i],
              ]) as number[][],
              hovertemplate: normalized
                ? "Channel %{x}<br>Calm score %{y:.4g}<br>Raw %{customdata[0]:.4g}<br>Calm median %{customdata[1]:.4g}<extra></extra>"
                : "Channel %{x}<br>AC RMS %{y:.4g}<extra></extra>",
            },
          ]
        : [];
    const heatData: Data[] =
      h?.status === "complete"
        ? [
            {
              type: "heatmap",
              x: h.channel_edges,
              y: h.time_edges,
              z: h.values,
              customdata: (normalized
                ? h.peak_channels?.map((row, r) =>
                    row.map((ch, c) => [ch, h.raw?.[r][c], h.medians?.[r][c]]),
                  )
                : h.peak_channels) as any,
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
  }, [snapshot, maximum, selected, normalized]);
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
            onPoint={(point) => onChannel(Number(point.x))}
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
