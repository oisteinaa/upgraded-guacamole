import { useState } from "react";
import Chart from "./Chart";
import { type Signal, type MetricName, number } from "./types";

export default function CalmSignalChart({
  signal,
  tab,
  cursor,
  onZoom,
}: {
  signal: Signal;
  tab: string;
  cursor: number;
  onZoom?: (a: number, b: number) => void;
}) {
  const [trend, setTrend] = useState(false);
  const n = signal.normalization;
  if (!n?.scores || !n.times?.length || !n.available_channels)
    return (
      <div className="empty">
        {n?.note ?? "No calm reference for this signal"}
      </div>
    );
  const metric: MetricName =
    tab === "variance"
      ? "variance"
      : tab === "peak"
        ? "peak"
        : tab === "band_rms"
          ? "band_rms"
          : "ac_rms";
  const frame = Math.max(
    0,
    n.starts!.findIndex((a, i) => a <= cursor && n.ends![i] > cursor),
  );
  const channels = n.channels!;
  const column = Math.max(0, channels.indexOf(signal.channel));
  const heat = tab === "heatmap";
  const custom = (f: number, c: number) => [
    n.raw?.[metric][f][c],
    n.medians?.[metric][c],
    n.training_frames?.[f] ? "training reference" : "",
  ];
  const spatialX: (number | null)[] = [],
    spatialY: (number | null)[] = [],
    spatialCustom: unknown[] = [];
  const step = Math.min(
    ...channels
      .slice(1)
      .map((ch, i) => Math.abs(ch - channels[i]))
      .filter((d) => d > 0),
  );
  channels.forEach((ch, c) => {
    if (c && Math.abs(ch - channels[c - 1]) > step) {
      spatialX.push(null);
      spatialY.push(null);
      spatialCustom.push(null);
    }
    spatialX.push(ch);
    spatialY.push(n.scores![metric][frame][c]);
    spatialCustom.push(custom(frame, c));
  });
  const data: any[] = heat
    ? [
        {
          type: "heatmap",
          x: n.starts!.concat(n.ends![n.ends!.length - 1]),
          y: channels.map(String),
          z: channels.map((_, c) => n.scores![metric].map((row) => row[c])),
          customdata: channels.map((_, c) =>
            n.times!.map((_, f) => custom(f, c)),
          ),
          zmin: 0,
          zmax: 10,
          hoverongaps: false,
          connectgaps: false,
          colorscale: [
            [0, "#2e3440"],
            [0.35, "#81a1c1"],
            [0.7, "#88c0d0"],
            [1, "#ebcb8b"],
          ],
          colorbar: { thickness: 10, title: { text: "Calm score" } },
          hovertemplate:
            "Channel %{y}<br>Time %{x:.3f} s<br>Score %{z:.4g}<br>Raw %{customdata[0]:.4g}<br>Median %{customdata[1]:.4g}<br>%{customdata[2]}<extra></extra>",
        },
      ]
    : [
        {
          type: "scatter",
          mode: "lines+markers",
          connectgaps: false,
          x: trend ? n.times : spatialX,
          y: trend ? n.scores[metric].map((row) => row[column]) : spatialY,
          customdata: trend
            ? n.times.map((_, f) => custom(f, column))
            : spatialCustom,
          marker: { size: 4, color: "#88c0d0" },
          line: { color: "#88c0d0", width: 1 },
          hovertemplate:
            "%{x}<br>Score %{y:.4g}<br>Raw %{customdata[0]:.4g}<br>Median %{customdata[1]:.4g}<br>%{customdata[2]}<extra></extra>",
        },
      ];
  return (
    <>
      {!heat && (
        <div className="calm-controls">
          <label>
            <input
              type="checkbox"
              checked={trend}
              onChange={(e) => setTrend(e.target.checked)}
            />
            Selected-channel time trend
          </label>
        </div>
      )}
      <Chart
        data={data}
        onZoom={heat || trend ? onZoom : undefined}
        layout={{
          uirevision: `${signal.recording_id}-${metric}-${trend}-${heat}`,
          xaxis: {
            title: {
              text: heat || trend ? "File time (s)" : "Recorded channel ID",
            },
            gridcolor: "#3b4252",
          },
          yaxis: {
            title: {
              text: heat
                ? "Recorded channel ID"
                : "Departure from calm reference",
            },
            type: heat ? "category" : "linear",
            gridcolor: "#3b4252",
          },
        }}
      />
      <div className="provenance">
        Complete ten-second source frames ·{" "}
        {trend
          ? `channel ${signal.channel}`
          : `${number(n.starts![frame])}–${number(n.ends![frame])} s`}{" "}
        · scores are not probabilities
      </div>
    </>
  );
}
