import { lazy, Suspense, useEffect, useState } from "react";
import {
  Activity,
  ChevronDown,
  ChevronUp,
  Play,
  Pause,
  RotateCcw,
  ArrowRight,
} from "lucide-react";
import {
  api,
  number,
  utcTime,
  type Recording,
  type Signal,
  type EventDetail,
  type Overview,
  type Inspection,
  type Geography,
} from "./types";
const Chart = lazy(() => import("./Chart"));
const line = (
  x: number[] | string[],
  y: number[],
  color = "#88c0d0",
  name = "Signal",
) => ({
  x,
  y,
  type: "scatter" as const,
  mode: x.length===1 ? "markers" as const : "lines" as const,
  marker:{color,size:6},
  line: { color, width: 1.2 },
  name,
});
export default function SignalPanel({
  open,
  setOpen,
  recordings,
  geography,
  event,
  overview,
  requestedRecording,
  mapLoading,
  inspection,
  onInspection,
}: {
  open: boolean;
  setOpen: (open: boolean) => void;
  recordings: Recording[];
  geography: Geography | null;
  event: EventDetail | null;
  overview: Overview | null;
  requestedRecording: number | null;
  mapLoading: boolean;
  inspection: Inspection;
  onInspection: (i: Inspection) => void;
}) {
  const [source, setSource] = useState("archive"),
    [tab, setTab] = useState("waveform");
  const [start, setStart] = useState(0),
    [duration, setDuration] = useState(10),
    [signal, setSignal] = useState<Signal | null>(null),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [playing, setPlaying] = useState(false),
    [cursor, setCursor] = useState(0),
    [revision, setRevision] = useState(0);
  const [station, setStation] = useState(1),
    [weather, setWeather] = useState<any>(null),
    [before, setBefore] = useState(5),
    [after, setAfter] = useState(5),
    [weatherVar, setWeatherVar] = useState("temp");
  const [channelCount, setChannelCount] = useState(500);
  const [spanId, setSpanId] = useState("");
  const { rid, channel } = inspection;
  const rec = recordings.find((r) => r.id === rid);
  const frameWidth = rec ? Math.round(10 / rec.dt) * rec.dt : 10;
  const selectionKey = `${rid}:${inspection.frame}`;
  const [view, setView] = useState<{
    key: string;
    start: number;
    duration: number;
  } | null>(null);
  const windowStart =
    view?.key === selectionKey ? view.start : inspection.frame * frameWidth;
  const windowDuration =
    view?.key === selectionKey ? view.duration : frameWidth;
  const setChannel = (channel: number) => {
    setSpanId("");
    onInspection({ ...inspection, channel });
  };
  useEffect(() => {
    setStart(inspection.frame * frameWidth);
    setDuration(frameWidth);
  }, [selectionKey, frameWidth]);
  useEffect(() => {
    if (requestedRecording) {
      onInspection({ ...inspection, rid: requestedRecording, frame: 0 });
      setSource("archive");
      setOpen(true);
      setRevision((n) => n + 1);
    }
  }, [requestedRecording]);
  useEffect(() => {
    if (event) {
      setSource("event");
      setPlaying(false);
      setSignal(null);
      setError("");
    } else setSource("archive");
  }, [event?.id]);
  useEffect(() => {
    if (!open || tab === "weather") return;
    const abort = new AbortController();
    setSignal(null);
    setError("");
    setBusy(false);
    if (source === "event" && !event?.context?.source_linked) return;
    if (source === "archive" && !rid) return;
    setBusy(true);
    const url =
      source === "event"
        ? `/events/${event!.id}/signal?before=${before}&after=${after}`
        : `/recordings/${rid}/signal?channel=${channel}&start=${windowStart}&duration=${windowDuration}&channel_count=${channelCount}`;
    api<Signal>(url, { signal: abort.signal })
      .then((d) => {
        setSignal(d);
        setCursor(d.start);
        const eventRec = recordings.find((r) => r.id === d.recording_id);
        if (source === "event" && eventRec) {
          const frame = Math.max(0, Math.floor(
            (d.event_start ?? d.start) /
              (Math.round(10 / eventRec.dt) * eventRec.dt),
          ));
          if (d.recording_id !== rid || frame !== inspection.frame)
            onInspection({ rid: d.recording_id, channel: d.channel, frame });
        }
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      })
      .finally(() => {
        if (!abort.signal.aborted) setBusy(false);
      });
    return () => abort.abort();
  }, [
    open,
    source,
    rid,
    channel,
    windowStart,
    windowDuration,
    channelCount,
    spanId,
    event?.id,
    revision,
    tab === "weather",
  ]);
  useEffect(() => {
    if (!open || tab !== "weather" || !event) return;
    const abort = new AbortController();
    setWeather(null);
    setError("");
    api(`/weather?station=${station}&at=${event.time}`, {
      signal: abort.signal,
    })
      .then(setWeather)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => abort.abort();
  }, [open, tab, station, event?.id]);
  useEffect(() => {
    if (!open || !playing || busy || mapLoading || !signal) return;
    // Hold each loaded recording briefly, then advance. Never skip files while loading.
    const timer = setTimeout(() => {
      const chronological = [...recordings].sort(
        (a, b) => a.acquisition_epoch - b.acquisition_epoch || a.id - b.id,
      );
      const next = chronological[chronological.findIndex(r => r.id === rid) + 1];
      if (!next) {
        setPlaying(false);
        return;
      }
      setSource("archive");
      setView(null);
      setStart(0);
      setDuration(Math.round(10 / next.dt) * next.dt);
      onInspection({ rid: next.id, channel, frame: 0 });
    }, 2000);
    return () => clearTimeout(timer);
  }, [open, playing, busy, mapLoading, signal, recordings, rid, channel]);
  useEffect(() => {
    if (error) setPlaying(false);
  }, [error]);
  function chooseRecording(value: number) {
    const r = recordings.find((v) => v.id === value);
    onInspection({ rid: value, channel: r?.first_channel ?? 0, frame: 0 });
    setView(null);
    setStart(0);
    setDuration(Math.min(10, (r?.samples ?? 1) * (r?.dt ?? 1)));
    setPlaying(false);
  }
  function zoom(a: number, b: number) {
    if (source !== "archive" || !rec || b <= a) return;
    const first = Math.max(0, a),
      last = Math.min(signal?.end ?? rec.samples * rec.dt, b);
    if (last - first < 8 * rec.dt) return;
    setStart(first);
    setDuration(Math.min(600, last - first));
    setView({
      key: selectionKey,
      start: first,
      duration: Math.min(600, last - first),
    });
  }
  const spatialMetric = tab === "rms" || tab === "variance";
  const metricFrame = signal ? Math.max(0, Math.min(
    signal.trend_time.length - 1,
    Math.floor((cursor - signal.trend_start) / signal.trend_window_seconds),
  )) : 0;
  const common: any = {
    uirevision: `${signal?.recording_id}-${signal?.channel}-${signal?.start}-${signal?.end}`,
    shapes: signal
      ? [
          {
            type: "line",
            x0: cursor,
            x1: cursor,
            y0: 0,
            y1: 1,
            yref: "paper",
            line: { color: "#ebcb8b", width: 1, dash: "dot" },
          },
          ...(signal.event_start != null
            ? [
                {
                  type: "rect",
                  x0: signal.event_start,
                  x1: signal.event_end,
                  y0: 0,
                  y1: 1,
                  yref: "paper",
                  fillcolor: "#b48ead",
                  opacity: 0.15,
                  line: { width: 0 },
                },
              ]
            : []),
        ]
      : [],
  };
  const weatherNames: Record<string, string> = {
    temp: "Temperature · °C",
    wspd: "Wind speed · m/s",
    wdir: "Wind direction · °",
    humidity: "Humidity · %",
  };
  const weatherItems =
    weather?.items.filter((w: any) => w.abv === weatherVar) ?? [];
  if (!open) return null;
  return (
    <section id="signal-investigation" className="signal-panel">
      <div className="signal-heading">
        <button className="plain section-toggle" aria-label="Hide signal investigation" aria-expanded={open} onClick={() => setOpen(!open)}>
          <Activity size={17} />
          <strong>Signal investigation</strong>
          {open ? <ChevronDown size={16} /> : <ChevronUp size={16} />}
        </button>
        <div className="segmented">
          <button
            className={source === "event" ? "active" : ""}
            onClick={() => setSource("event")}
            disabled={!event}
          >
            Event window
          </button>
          <button
            className={source === "archive" ? "active" : ""}
            onClick={() => setSource("archive")}
          >
            Recording browser
          </button>
        </div>
        <span className="muted small">
          {source === "archive"
            ? "Independent archive · no event association"
            : event
              ? `Event #${event.id}`
              : "Select an event"}
        </span>
      </div>
      {open && (
        <>
          <div className="signal-controls">
            {source === "archive" ? (
              <>
                <label>
                  Recording
                  <select
                    aria-label="Recording"
                    value={rid}
                    onChange={(e) => chooseRecording(+e.target.value)}
                  >
                    {recordings.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.relative_path} · {number(r.samples * r.dt)} s
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Channel ID
                  <input
                    aria-label="Channel ID"
                    type="number"
                    step="0.5"
                    value={channel}
                    onChange={(e) => setChannel(+e.target.value)}
                  />
                </label>
                <label>
                  Number of channels
                  <input
                    aria-label="Number of channels"
                    type="number"
                    min="1"
                    step="1"
                    value={channelCount}
                    onChange={(e) => {
                      setSpanId("");
                      setChannelCount(Math.max(1, Math.round(+e.target.value)));
                    }}
                  />
                </label>
                <label>
                  Mast span
                  <select aria-label="Mast span" value={spanId} onChange={(e) => {
                    const id = e.target.value;
                    setSpanId(id);
                    const span = geography?.spans.features.find((f) => String(f.id) === id);
                    if (!span) return;
                    const { from_channel: from, to_channel: to } = span.properties;
                    if (!Number.isFinite(from) || !Number.isFinite(to)) return;
                    setChannelCount(Math.max(1, Math.abs(to - from)));
                    onInspection({ ...inspection, channel: (from + to) / 2 });
                    setPlaying(false);
                    setRevision((n) => n + 1);
                  }}>
                    <option value="">Centered channel range</option>
                    {geography?.spans.features.map(({ id, properties: p }) => (
                      <option key={id} value={id} disabled={!Number.isFinite(p.from_channel) || !Number.isFinite(p.to_channel)}>
                        {p.route} · {p.from_mast}–{p.to_mast} · {p.from_channel}–{p.to_channel}
                      </option>
                    ))}
                  </select>
                </label>
                <span className="small muted">
                  {`Channels ${channel - channelCount / 2}–${channel + channelCount / 2}`}
                  {" · range shown in Heatmap, AC RMS and Variance"}
                </span>
                <label>
                  Start (s)
                  <input
                    aria-label="Window start"
                    type="number"
                    min="0"
                    step="0.1"
                    value={start}
                    onChange={(e) => setStart(+e.target.value)}
                  />
                </label>
                <label>
                  Duration (s)
                  <input
                    aria-label="Window duration"
                    type="number"
                    min="0.01"
                    max="600"
                    step="0.1"
                    value={duration}
                    onChange={(e) => setDuration(+e.target.value)}
                  />
                </label>
                <button
                  className="secondary"
                  onClick={() => {
                    setPlaying(false);
                    const frame = Math.max(0, Math.min(Math.ceil((rec?.samples ?? 1) * (rec?.dt ?? 1) / frameWidth) - 1, Math.floor(start / frameWidth)));
                    onInspection({ ...inspection, frame });
                    setView({ key: `${rid}:${frame}`, start, duration });
                    setRevision((n) => n + 1);
                  }}
                >
                  Load window <ArrowRight size={14} />
                </button>
              </>
            ) : (
              <>
                <span className="muted small">
                  Context around the selected event
                </span>
                <label>
                  Before (s)
                  <input
                    type="number"
                    min="0"
                    max="120"
                    value={before}
                    onChange={(e) => setBefore(+e.target.value)}
                  />
                </label>
                <label>
                  After (s)
                  <input
                    type="number"
                    min="0"
                    max="120"
                    value={after}
                    onChange={(e) => setAfter(+e.target.value)}
                  />
                </label>
                <button onClick={() => setRevision((n) => n + 1)}>Apply</button>
              </>
            )}
            <div className="tabs signal-tabs">
              {[
                "waveform",
                "rms",
                "variance",
                "heatmap",
                "spectrum",
                "weather",
              ].map((t) => (
                <button
                  key={t}
                  className={tab === t ? "active" : ""}
                  onClick={() => setTab(t)}
                >
                  {t === "rms" ? "AC RMS" : t[0].toUpperCase() + t.slice(1)}
                </button>
              ))}
            </div>
          </div>
          {error && (
            <div role="alert" className="inline-error">
              {error}
            </div>
          )}
          {signal?.truncated && !busy && tab !== "weather" && (
            <div className="notice" role="status" aria-label="Recording coverage limit">
              <div>
                <strong>Requested window exceeds available continuous recordings.</strong>
                {source === "event" && signal.event_start != null && signal.event_end != null ? (
                  <div>Before: {before} s requested, {Math.max(0, signal.event_start - signal.start).toFixed(2)} s available.
                    {" "}After: {after} s requested, {Math.max(0, signal.end - signal.event_end).toFixed(2)} s available.</div>
                ) : <div>Showing {(signal.end - signal.start).toFixed(2)} s of the requested {((signal.requested_end ?? signal.end) - (signal.requested_start ?? signal.start)).toFixed(2)} s.</div>}
                <div>{signal.stitch_note}</div>
              </div>
            </div>
          )}
          {tab === "weather" ? (
            <div className="weather-section">
              <div className="weather-controls">
                <label>
                  Weather station
                  <select
                    value={station}
                    onChange={(e) => setStation(+e.target.value)}
                  >
                    {overview?.stations.map((s) => (
                      <option key={s.lid} value={s.lid}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                </label>
                <select
                  aria-label="Weather variable"
                  value={weatherVar}
                  onChange={(e) => setWeatherVar(e.target.value)}
                >
                  {Object.entries(weatherNames).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
                <span className="small muted">
                  {weather?.note ??
                    "Select an event to review weather at its stored time."}
                </span>
              </div>
              {weatherItems.length ? (
                <Suspense
                  fallback={<div className="empty">Loading charts…</div>}
                >
                  <Chart
                    data={[
                      line(
                        weatherItems.map((w: any) => w.time),
                        weatherItems.map((w: any) => w.value),
                      ),
                    ]}
                    layout={{
                      xaxis: {
                        title: { text: "Stored weather time" },
                        gridcolor: "#3b4252",
                      },
                      yaxis: {
                        title: { text: weatherNames[weatherVar] },
                        gridcolor: "#3b4252",
                      },
                    }}
                  />
                </Suspense>
              ) : (
                <div className="empty">
                  {weatherVar === "humidity"
                    ? "Humidity is not defined in the source database."
                    : "No weather values in this event window."}
                </div>
              )}
              {weather?.stale && (
                <div className="provenance">
                {signal?.source_note && <div>{signal.source_note}</div>}
                {signal?.stitch_note && <div>{signal.stitch_note}</div>}
                  Weather is missing or older than two hours.
                </div>
              )}
            </div>
          ) : busy ? (
            <div className="empty">
              <span className="loading-dot" />
              Reading signal window…
            </div>
          ) : signal ? (
            <>
              <Suspense fallback={<div className="empty">Loading charts…</div>}>
                <Chart
                  onZoom={
                    ["waveform", "heatmap"].includes(tab)
                      ? zoom
                      : undefined
                  }
                  data={
                    tab === "heatmap"
                      ? [
                          {
                            type: "heatmap",
                            x: signal.heat_time,
                            y: signal.heat_channels.map(String),
                            z: signal.heat,
                            colorscale: [
                              [0, "#2e3440"],
                              [0.35, "#81a1c1"],
                              [0.7, "#88c0d0"],
                              [1, "#ebcb8b"],
                            ],
                            colorbar: { thickness: 10, title: { text: "RMS" } },
                          },
                        ]
                      : tab === "spectrum"
                        ? [line(signal.frequency, signal.power, "#b48ead")]
                        : [
                            line(
                              tab === "waveform" ? signal.x : signal.heat_channels,
                              tab === "waveform"
                                ? signal.y
                                : tab === "rms"
                                  ? signal.channel_rms[metricFrame]
                                  : signal.channel_variance[metricFrame],
                            ),
                          ]
                  }
                  layout={
                    tab === "spectrum"
                      ? {
                          xaxis: {
                            title: { text: "Frequency (Hz)" },
                            gridcolor: "#3b4252",
                          },
                          yaxis: {
                            title: { text: `PSD (${signal.unit})²/Hz` },
                            type: "log",
                            gridcolor: "#3b4252",
                          },
                        }
                      : tab === "heatmap"
                        ? {
                            ...common,
                            yaxis: {
                              title: { text: "Recorded channel ID" },
                              type: "category",
                              gridcolor: "#3b4252",
                            },
                          }
                        : {
                            ...(spatialMetric ? {
                              uirevision: `${signal.recording_id}-${signal.heat_channels.join(",")}`,
                              xaxis: { title: { text: "Recorded channel ID" }, gridcolor: "#3b4252" },
                            } : common),
                            yaxis: {
                              title: {
                                text:
                                  tab === "variance"
                                    ? `(${signal.unit})²`
                                    : signal.unit,
                              },
                              gridcolor: "#3b4252",
                            },
                          }
                  }
                />
              </Suspense>
              <div className="playback">
                <span className="muted small">Recording playback · 2 s per file</span>
                <button
                  aria-label={playing ? "Pause playback" : "Play playback"}
                  title="Play consecutive recordings · 2 seconds per file"
                  onClick={() => {
                    if (!playing) {
                      setSource("archive");
                      setView(null);
                      onInspection({ ...inspection, frame: 0 });
                    }
                    setPlaying(!playing);
                  }}
                >
                  {playing ? <Pause size={15} /> : <Play size={15} />}
                </button>
                <button
                  aria-label="Reset signal window"
                  onClick={() => {
                    setCursor(signal.start);
                    setPlaying(false);
                    onInspection({ ...inspection, frame: 0 });
                    setView(null);
                    setStart(0);
                    setDuration(frameWidth);
                    setRevision((n) => n + 1);
                  }}
                >
                  <RotateCcw size={14} />
                </button>
                <input
                  aria-label="Playback position"
                  type="range"
                  min={signal.start}
                  max={signal.end}
                  step="0.01"
                  value={cursor}
                  onChange={(e) => setCursor(+e.target.value)}
                />
                <span className="mono">{cursor.toFixed(2)} s</span>
                <span className="muted small">
                  {number(signal.source_samples)} samples →{" "}
                  {number(signal.display_points)} display points
                </span>
              </div>
              <div className="provenance">
                {signal?.source_note && <div>{signal.source_note}</div>}
                {signal?.stitch_note && <div>{signal.stitch_note}</div>}
                Channel {signal.channel} · {signal.processing} ·{" "}
                {number(signal.sample_rate)} Hz ·{" "}
                {utcTime(signal.acquisition_epoch)}{" "}
                {!signal.time_verified &&
                  "· header time interpretation unverified"}
                {(tab === "heatmap" || spatialMetric) &&
                  ` · ${signal.heat_channels.length} recorded channels · ${signal.channel_bounds?.join("–") ?? "adjacent columns"}${spanId ? " · inferred span endpoint bounds" : ""}`}
                {tab === "spectrum" && " · Welch PSD from full window samples"}
                {["rms", "variance"].includes(tab) &&
                  ` · per-channel values for ${number(signal.trend_start + metricFrame * signal.trend_window_seconds)}–${number(Math.min(signal.duration, signal.trend_start + (metricFrame + 1) * signal.trend_window_seconds))} s · fixed analysis window`}
              </div>
            </>
          ) : (
            <div className="empty">
              <Activity size={26} />
              <strong>
                {source === "event"
                  ? "No source recording linked to this event"
                  : "Open a recording to inspect its signal"}
              </strong>
              <span>
                {source === "event"
                  ? "This event has no validated source samples. Browse the archive independently below."
                  : "Select a recording and channel, then load a bounded window."}
              </span>
              {source === "event" && (
                <button onClick={() => setSource("archive")}>
                  Browse recordings <ArrowRight size={14} />
                </button>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
