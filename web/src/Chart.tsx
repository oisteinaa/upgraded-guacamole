import { useEffect, useRef } from "react";
import Plotly from "plotly.js-cartesian-dist-min";
import type { Data, Layout } from "plotly.js";
export default function Chart({
  data,
  layout = {},
  onZoom,
}: {
  data: Data[];
  layout?: Partial<Layout>;
  onZoom?: (a: number, b: number) => void;
}) {
  const el = useRef<HTMLDivElement>(null);
  const callback = useRef(onZoom);
  callback.current = onZoom;
  useEffect(() => {
    const node = el.current!;
    let active = true;
    Plotly.react(
      node,
      data,
      {
        paper_bgcolor: "#292f3a",
        plot_bgcolor: "#292f3a",
        font: { family: "IBM Plex Sans", color: "#9aa5b5", size: 11 },
        margin: { l: 62, r: 22, t: 20, b: 42 },
        autosize: true,
        showlegend: false,
        hovermode: "x unified",
        xaxis: {
          gridcolor: "#3b4252",
          zeroline: false,
          title: { text: "Time from recording start (s)" },
        },
        yaxis: { gridcolor: "#3b4252", zeroline: false },
        ...layout,
      },
      {
        responsive: true,
        displaylogo: false,
        modeBarButtonsToRemove: ["lasso2d", "select2d", "toImage"],
      },
    ).then(() => {
      if (!active) return;
      const gd = node as unknown as {
        removeAllListeners: (name: string) => void;
        on: (name: string, fn: (e: any) => void) => void;
      };
      gd.removeAllListeners("plotly_relayout");
      gd.on("plotly_relayout", (e) => {
        if (
          e["xaxis.range[0]"] !== undefined &&
          e["xaxis.range[1]"] !== undefined
        )
          callback.current?.(
            Number(e["xaxis.range[0]"]),
            Number(e["xaxis.range[1]"]),
          );
      });
    });
    return () => {
      active = false;
    };
  }, [data, layout]);
  useEffect(() => {
    const node = el.current!;
    const obs = new ResizeObserver(() => {
      if (node.offsetWidth) Plotly.Plots.resize(node);
    });
    obs.observe(node);
    return () => {
      obs.disconnect();
      Plotly.purge(node);
    };
  }, []);
  return <div className="chart" ref={el} />;
}
