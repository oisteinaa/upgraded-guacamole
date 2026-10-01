import { number, utcTime, type MetricFrame, type Normalization } from "./types";

export type CalmPreference = "auto" | "raw" | "calm";
export const useCalm = (preference: CalmPreference, data?: Normalization) =>
  preference === "calm" ||
  (preference === "auto" && (data?.available_channels ?? 0) > 0);

export function calmMetric(
  frame: MetricFrame | null,
  enabled: boolean,
): MetricFrame | null {
  if (!frame || !enabled) return frame;
  return {
    ...frame,
    unit: "calm score",
    scale: { min: 0, max: 10 },
    data: {
      ...frame.data,
      features: frame.data.features
        .filter((f) => f.properties.calm_score != null)
        .map((f) => ({
          ...f,
          properties: {
            ...f.properties,
            raw_value: f.properties.value,
            value: f.properties.calm_score,
          },
        })),
    },
  };
}

export default function CalmControls({
  preference,
  onChange,
  data,
}: {
  preference: CalmPreference;
  onChange: (value: CalmPreference) => void;
  data?: Normalization;
}) {
  const enabled = useCalm(preference, data);
  return (
    <div className="calm-controls">
      <label>
        Activity display{" "}
        <select
          aria-label="Activity normalization"
          value={enabled ? "calm" : "raw"}
          onChange={(e) => onChange(e.target.value as CalmPreference)}
        >
          <option value="raw">Raw</option>
          <option value="calm">Calm baseline</option>
        </select>
      </label>
      <span className="small muted">
        {data?.available_channels ? (
          <>
            {enabled
              ? "Departure from calm reference · colours 0–10 · "
              : "Calm reference available · "}
            {number(data.available_channels)}/{number(data.total_channels)}{" "}
            channels
            {data.training_start != null && data.training_end != null && (
              <>
                {" "}
                · {utcTime(data.training_start).slice(0, 10)}–
                {utcTime(data.training_end).slice(0, 10)}
              </>
            )}
            {data.training_reference || data.training_frames?.some(Boolean)
              ? " · training reference"
              : ""}
            {data.illustrative ? " · illustrative alignment" : ""}
          </>
        ) : (
          (data?.note ?? "Calm reference unavailable")
        )}
      </span>
    </div>
  );
}
