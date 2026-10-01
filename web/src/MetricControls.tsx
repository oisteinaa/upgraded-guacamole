import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";
import {
  metricNames,
  number,
  type MetricName,
  type MetricFrame,
  type ColorScale,
  type Inspection,
  type Recording,
} from "./types";
export default function MetricControls({
  metric,
  setMetric,
  band,
  setBand,
  scale,
  setScale,
  data,
  busy,
  error,
  inspection,
  setInspection,
  recordings,
  lid,
  setLid,
  lids,
}: {
  metric: MetricName;
  setMetric: (m: MetricName) => void;
  band: [number, number];
  setBand: (b: [number, number]) => void;
  scale: ColorScale;
  setScale: (s: ColorScale) => void;
  data: MetricFrame | null;
  busy: boolean;
  error: string;
  inspection: Inspection;
  setInspection: (i: Inspection) => void;
  recordings: Recording[];
  lid: number;
  setLid: (id: number) => void;
  lids: number[];
}) {
  const [low, setLow] = useState(band[0]),
    [high, setHigh] = useState(band[1]);
  const [min, setMin] = useState(String(scale.min)),
    [max, setMax] = useState(String(scale.max)),
    [validation, setValidation] = useState("");
  useEffect(() => {
    setMin(String(Number(scale.min.toPrecision(5))));
    setMax(String(Number(scale.max.toPrecision(5))));
  }, [scale.min, scale.max]);
  const rec = recordings.find((r) => r.id === inspection.rid);
  const chronological = [...recordings].sort(
    (a, b) => a.acquisition_epoch - b.acquisition_epoch,
  );
  const index = chronological.findIndex((r) => r.id === inspection.rid);
  const frames = rec
    ? Math.ceil(rec.samples / Math.max(1, Math.round(10 / rec.dt)))
    : 1;
  function step(direction: number) {
    const next = inspection.frame + direction;
    if (next >= 0 && next < frames) {
      setInspection({ ...inspection, frame: next });
      return;
    }
    const nextRec = chronological[index + direction];
    if (nextRec)
      setInspection({
        rid: nextRec.id,
        channel: inspection.channel,
        frame:
          direction > 0
            ? 0
            : Math.ceil(nextRec.samples / Math.round(10 / nextRec.dt)) - 1,
      });
  }
  return (
    <div className="metric-controls">
      <div className="metric-main">
        <label>
          Signal layer
          <select
            aria-label="Map signal layer"
            value={metric}
            onChange={(e) => setMetric(e.target.value as MetricName)}
          >
            {Object.entries(metricNames).map(([k, v]) => (
              <option key={k} value={k}>
                {v}
              </option>
            ))}
          </select>
        </label>
        {lids.length > 1 && (
          <label>
            Instrument
            <select
              aria-label="Instrument mapping"
              value={lid}
              onChange={(e) => setLid(+e.target.value)}
            >
              {lids.map((id) => (
                <option value={id} key={id}>
                  LID {id}
                </option>
              ))}
            </select>
          </label>
        )}
        <div className="frame-nav">
          <button
            aria-label="Previous signal frame"
            disabled={!rec || (index === 0 && inspection.frame === 0)}
            onClick={() => step(-1)}
          >
            <ChevronLeft size={15} />
          </button>
          <span>
            {rec?.relative_path ?? "Select recording"}
            <small>
              {data
                ? `${number(data.start)}–${number(data.end)} s · ${data.complete ? "10 s analysis window" : "incomplete window"}`
                : "Fixed 10 s analysis windows"}
            </small>
          </span>
          <button
            aria-label="Next signal frame"
            disabled={
              !rec ||
              (index === chronological.length - 1 &&
                inspection.frame === frames - 1)
            }
            onClick={() => step(1)}
          >
            <ChevronRight size={15} />
          </button>
        </div>
      </div>
      {metric === "band_rms" && (
        <div className="band-controls">
          <label>
            Low (Hz)
            <input
              aria-label="Band low frequency"
              type="number"
              min="0.001"
              value={low}
              onChange={(e) => setLow(+e.target.value)}
            />
          </label>
          <label>
            High (Hz)
            <input
              aria-label="Band high frequency"
              type="number"
              value={high}
              onChange={(e) => setHigh(+e.target.value)}
            />
          </label>
          <button
            onClick={() => {
              if (low > 0 && high > low) {
                setBand([low, high]);
                setValidation("");
              } else setValidation("Enter 0 < low < high.");
            }}
          >
            Apply band
          </button>
          <small>Exploratory band · not an event classification</small>
        </div>
      )}
      <fieldset
        className="color-controls"
        disabled={data?.unit === "calm score"}
      >
        <label>
          Color min
          <input
            aria-label="Color minimum"
            type="number"
            value={min}
            onChange={(e) => setMin(e.target.value)}
          />
        </label>
        <label>
          Color max
          <input
            aria-label="Color maximum"
            type="number"
            value={max}
            onChange={(e) => setMax(e.target.value)}
          />
        </label>
        <button
          onClick={() => {
            const a = Number(min),
              b = Number(max);
            if (
              min !== "" &&
              max !== "" &&
              Number.isFinite(a) &&
              Number.isFinite(b) &&
              a >= 0 &&
              b > a &&
              (!scale.log || a > 0)
            ) {
              setScale({ ...scale, min: a, max: b });
              setValidation("");
            } else
              setValidation(
                "Use increasing finite limits; logarithmic minimum must be positive.",
              );
          }}
        >
          Set limits
        </button>
        <label>
          Scale
          <select
            aria-label="Color scale"
            value={scale.log ? "log" : "linear"}
            onChange={(e) => {
              const log = e.target.value === "log";
              setScale({
                ...scale,
                log,
                min: log ? Math.max(scale.min, scale.max / 1000) : 0,
              });
              setValidation("");
            }}
          >
            <option value="linear">Linear</option>
            <option value="log">Logarithmic</option>
          </select>
        </label>
        <button
          aria-label="Rescale colors"
          title="Use this frame’s 99th percentile; limits stay fixed during playback"
          disabled={!data}
          onClick={() => {
            const maximum = Math.max(data!.scale.max, 1e-12);
            setScale({
              min: scale.log ? maximum / 1000 : 0,
              max: maximum,
              log: scale.log,
            });
            setValidation("");
          }}
        >
          <RefreshCw size={13} />
        </button>
      </fieldset>
      <div className="color-legend">
        <div className="color-ramp" />
        <div>
          <span>{number(scale.min)}</span>
          <span>{data?.unit ?? "Signal amplitude"}</span>
          <span>≥ {number(scale.max)}</span>
        </div>
      </div>
      <div className="metric-status" role="status">
        {busy
          ? "Calculating full-resolution window…"
          : error ||
            validation ||
            (data
              ? `${number(data.mapping.exact)} exact + ${number(data.mapping.interpolated)} interpolated · color limits locked`
              : "Select a recording to show signal activity")}
      </div>
      {data?.mapping.status === "partial" && (
        <div className="mapping-notice">
          {number(data.mapping.unmatched_recording)} recorded channels are
          outside mapped bounds or across a gap. No endpoint extrapolation is
          used.
        </div>
      )}
    </div>
  );
}
