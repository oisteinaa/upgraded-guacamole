import CalmControls, {
  calmMetric,
  useCalm,
  type CalmPreference,
} from "./CalmControls";
import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import Map from "./Map";
import {
  api,
  number,
  utcTime,
  type Geography,
  type Overview,
  type Live,
  type MetricFrame,
  type Collection,
} from "./types";
const LiveCharts = lazy(() => import("./LiveCharts"));
const empty: Collection = { type: "FeatureCollection", features: [] };
const detectionLabels: Record<string, string> = {
  disabled: "Disabled in demo",
  not_configured: "Not configured",
  processing: "Processing",
  complete: "Complete",
  failed: "Failed",
  unavailable: "Unavailable",
};
export default function LiveMonitor({
  geo,
  overview,
}: {
  geo: Geography | null;
  overview: Overview | null;
}) {
  const [current, setCurrent] = useState<{
    snapshot: Live;
    metric: MetricFrame | null;
    metricError: string;
  } | null>(null);
  const [calmPreference, setCalmPreference] = useState<CalmPreference>("auto");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [clock, setClock] = useState(Date.now());
  const [selectedChannel, setSelectedChannel] = useState<number | null>(null);
  const [lockedScale, setLockedScale] = useState<{
    key: string;
    max: number;
  } | null>(null);
  useEffect(() => {
    const timer = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    let cached: { key: string; metric: MetricFrame } | null = null;
    async function poll() {
      try {
        const next = await api<Live>("/live", { signal: abort.signal });
        if (abort.signal.aborted) return;
        let metric: MetricFrame | null = null,
          metricError = "";
        setLoading(true);
        if (
          (next.status === "live" || next.status === "demo") &&
          next.recording_id != null
        ) {
          const lid =
            next.lid ??
            next.points[0]?.lid ??
            (overview?.mapping_lids.length === 1
              ? overview.mapping_lids[0]
              : null);
          const demo = next.status === "demo" && next.demo === true;
          if (demo && !next.demo_has_metric)
            metricError =
              next.demo_mapping_note ?? "Demo geography is unavailable.";
          else if (!demo && (!next.mapping_verified || lid == null))
            metricError =
              "Live instrument mapping is unverified; signal locations are unavailable.";
          else {
            const key = `${next.recording_id}:${next.frame ?? 0}:${lid}:${next.acquisition_epoch}:${next.normalization?.baseline_id}`;
            try {
              metric =
                cached?.key === key
                  ? cached.metric
                  : await api<MetricFrame>(
                      demo
                        ? `/demo/metrics/${next.demo_token}`
                        : `/recordings/${next.recording_id}/metrics?lid=${lid}&frame=${next.frame ?? 0}&metric=ac_rms&low=1&high=10`,
                      { signal: abort.signal },
                    );
              if (
                metric.recording_id !== next.recording_id ||
                metric.frame !== (next.frame ?? 0)
              )
                throw new Error("Signal response does not match current file");
              if (
                metric.normalization?.baseline_id &&
                next.normalization?.baseline_id &&
                metric.normalization.baseline_id !==
                  next.normalization.baseline_id
              )
                throw new Error(
                  "Calm reference changed; waiting for the next capture",
                );
              cached = { key, metric };
            } catch (e) {
              metric = null;
              metricError = (e as Error).message;
            }
          }
        }
        if (!abort.signal.aborted) {
          setCurrent({ snapshot: next, metric, metricError });
          setError("");
        }
      } catch (e) {
        if (!abort.signal.aborted) {
          setError((e as Error).message);
          setCurrent(null);
        }
      } finally {
        if (!abort.signal.aborted) {
          setLoading(false);
          timer = setTimeout(poll, 5000);
        }
      }
    }
    poll();
    return () => {
      abort.abort();
      clearTimeout(timer);
    };
  }, [overview?.mapping_lids.join(",")]);
  const snapshot = current?.snapshot;
  const age = snapshot?.acquisition_epoch
    ? Math.max(0, clock / 1000 - snapshot.acquisition_epoch)
    : null;
  const publicationFresh =
    snapshot?.published_at == null ||
    clock / 1000 - snapshot.published_at <= 30;
  const demo = snapshot?.demo === true;
  const publicationAge =
    snapshot?.published_at == null
      ? null
      : Math.max(0, clock / 1000 - snapshot.published_at);
  const fresh =
    !error &&
    publicationFresh &&
    (demo
      ? snapshot?.status === "demo" &&
        publicationAge != null &&
        publicationAge <= 30
      : snapshot?.status === "live" && age != null && age <= 30);
  const live = fresh ? snapshot! : null;
  const calmEnabled = useCalm(calmPreference, live?.normalization);
  const displayed = useMemo(
    () => calmMetric(fresh ? (current?.metric ?? null) : null, calmEnabled),
    [fresh, current?.metric, calmEnabled],
  );
  const scaleKey = live
    ? `${live.lid ?? displayed?.lid ?? live.points[0]?.lid}:${live.unit}:${live.metric_processing}`
    : "";
  const suggestedMax = Math.max(
    current?.metric?.scale.max ??
      live?.profile?.values?.reduce<number>(
        (max, v) => Math.max(max, v ?? 0),
        0,
      ) ??
      1,
    1e-12,
  );
  useEffect(() => {
    if (scaleKey)
      setLockedScale((prev) =>
        prev?.key === scaleKey ? prev : { key: scaleKey, max: suggestedMax },
      );
  }, [scaleKey, suggestedMax]);
  const maximum = calmEnabled
    ? 10
    : lockedScale?.key === scaleKey
      ? lockedScale.max
      : suggestedMax;
  const selectChannel = useCallback((channel: number) => {
    if (Number.isFinite(channel)) setSelectedChannel(channel);
  }, []);
  const selected = useMemo(
    () =>
      displayed?.data.features.find(
        (f) => f.properties.recording_channel === selectedChannel,
      ) ?? null,
    [displayed, selectedChannel],
  );
  const status = error
    ? "Connection unavailable"
    : demo
      ? fresh
        ? "Demo replay · looping archive"
        : snapshot?.status === "demo_loading" && publicationFresh
          ? "Preparing demo replay"
          : "Demo replay is stale"
      : fresh
        ? "Live capture"
        : snapshot?.status === "replay"
          ? "Replay source · not live"
          : snapshot?.status === "unverified"
            ? "Acquisition time unverified"
            : snapshot?.status === "stale" || snapshot?.status === "live"
              ? "Capture is stale"
              : "Waiting for live capture";
  const detection = live?.detection;
  const detectionStatus = detection?.status ?? "unavailable";
  return (
    <main className="live-workspace">
      <section className="live-status" aria-label="Live capture status">
        <div className="live-status-heading">
          <span
            className={`live-dot ${demo ? "is-demo" : fresh ? "is-live" : ""}`}
          />
          <div>
            <span className="eyebrow">
              {demo ? "DEMONSTRATION · NOT LIVE ACQUISITION" : "LIVE MONITOR"}
            </span>
            <h2>{status}</h2>
          </div>
        </div>
        <dl>
          <div>
            <dt>{fresh ? "Current file" : "Last published file"}</dt>
            <dd>
              {snapshot?.filename ??
                (snapshot?.recording_id != null
                  ? `Recording ${snapshot.recording_id}`
                  : "—")}
            </dd>
          </div>
          <div>
            <dt>{demo ? "Original acquisition" : "Acquisition"}</dt>
            <dd>
              {snapshot?.acquisition_epoch
                ? utcTime(snapshot.acquisition_epoch)
                : "—"}
            </dd>
          </div>
          <div>
            <dt>{demo ? "Demo update age" : "Age"}</dt>
            <dd>
              {(demo ? publicationAge : age) == null
                ? "—"
                : `${number(Math.floor((demo ? publicationAge : age)!))} s`}
            </dd>
          </div>
          <div>
            <dt>Channels</dt>
            <dd>{number(snapshot?.channel_count)}</dd>
          </div>
        </dl>
        {demo && (
          <p className="demo-source">
            {snapshot?.demo_source} · File {number(snapshot?.demo_position)} /{" "}
            {number(snapshot?.demo_count)} · Loop {number(snapshot?.demo_cycle)}
            {snapshot?.demo_preparing ? " · Preparing next file…" : ""}
            {snapshot?.status === "demo_loading"
              ? ` · ${snapshot.note ?? "Preparing…"}`
              : ""}
          </p>
        )}
        {error && <p role="alert">{error}</p>}
      </section>
      <CalmControls
        preference={calmPreference}
        onChange={setCalmPreference}
        data={live?.normalization}
      />
      <div className="live-grid">
        <section className="live-map-panel" aria-label="Live network map">
          <Map
            weatherMode={demo ? "investigate" : "live"}
            geo={geo}
            events={empty}
            route=""
            selected={selected}
            onSelect={() => {}}
            onEvent={() => {}}
            fibre={empty}
            metricData={displayed}
            scale={{ min: 0, max: maximum, log: false }}
            onChannel={(f) =>
              selectChannel(Number(f.properties.recording_channel))
            }
          />
          <div className="live-map-toolbar">
            <span>
              {loading
                ? "Loading current file…"
                : displayed
                  ? calmEnabled
                    ? "Departure from calm reference · colours 0–10"
                    : demo
                      ? "Demo AC RMS · illustrative mapping · scale locked"
                      : "AC RMS · amplitude colours · scale locked"
                  : "Network assets · awaiting current signal"}
            </span>
            <button
              disabled={!live || calmEnabled}
              onClick={() =>
                setLockedScale({ key: scaleKey, max: suggestedMax })
              }
            >
              Rescale
            </button>
          </div>
          <div className="live-selection">
            <label>
              Channel{" "}
              <input
                aria-label="Highlight live channel"
                type="number"
                step="1"
                value={selectedChannel ?? ""}
                onChange={(e) =>
                  e.target.value === ""
                    ? setSelectedChannel(null)
                    : selectChannel(Number(e.target.value))
                }
              />
            </label>
            <span>
              {live && selectedChannel != null
                ? selected
                  ? "Highlighted on map and charts"
                  : "No mapped position in current frame"
                : "Select a signal point, chart peak or candidate"}
            </span>
          </div>
          {fresh && current?.metricError && (
            <p className="live-map-error" role="alert">
              {current.metricError}
            </p>
          )}
        </section>
        <aside className="live-insights" aria-label="Current file insights">
          <Suspense
            fallback={
              <>
                <section className="live-card live-empty">
                  Loading activity chart…
                </section>
                <section className="live-card live-empty">
                  Loading heatmap…
                </section>
              </>
            }
          >
            <LiveCharts
              normalized={calmEnabled}
              snapshot={live}
              maximum={maximum}
              selected={live ? selectedChannel : null}
              onChannel={selectChannel}
            />
          </Suspense>
          <section
            className="live-card live-detection"
            aria-label="Current file detection"
          >
            <header>
              <h2>Current file · Detection</h2>
              <span
                className={`detection-badge detection-${detectionStatus}`}
                role="status"
              >
                {detectionLabels[detectionStatus] ?? "Unavailable"}
              </span>
            </header>
            {!live ? (
              <div className="live-empty">Waiting for current live signal</div>
            ) : (
              <div className="live-detection-content">
                <p className="live-chart-caption">
                  {live.filename ?? `Recording ${live.recording_id}`} · whole
                  file · {number(live.duration)} s
                </p>
                {detectionStatus === "complete" ? (
                  <>
                    <p className="live-candidate-count">
                      <strong>{number(detection?.candidate_count)}</strong>{" "}
                      candidate{" "}
                      {detection?.candidate_count === 1
                        ? "channel"
                        : "channels"}{" "}
                      <span>Requires review</span>
                    </p>
                    <p className="live-chart-caption">
                      Evaluated {number(detection?.evaluated_channels)} /{" "}
                      {number(detection?.total_channels)} recorded channels ·{" "}
                      {number(detection?.requested_channels)} configured
                    </p>
                    {detection?.candidate_count === 0 && (
                      <p>No threshold exceedances in evaluated channels.</p>
                    )}
                    <ol className="live-candidates">
                      {detection?.candidates?.map((candidate) => (
                        <li key={candidate.channel}>
                          <button
                            onClick={() => selectChannel(candidate.channel)}
                          >
                            <span>
                              Ch {number(candidate.channel)}{" "}
                              <b>{number(candidate.ratio)}× threshold</b>
                            </span>
                            <small>
                              {number(candidate.value)} /{" "}
                              {number(candidate.threshold)} {detection.unit} ·{" "}
                              {candidate.rule}
                            </small>
                          </button>
                        </li>
                      ))}
                    </ol>
                    <p className="live-chart-caption">
                      {detection?.metric} · strongest five shown
                    </p>
                  </>
                ) : (
                  <p>
                    {detection?.note ??
                      (detectionStatus === "not_configured"
                        ? "No calibrated detection rules are configured."
                        : detectionStatus === "processing"
                          ? "Evaluating configured thresholds for this file…"
                          : "No assessment is available for this capture.")}
                  </p>
                )}
              </div>
            )}
          </section>
        </aside>
      </div>
      <p className="map-footnote">
        {demo
          ? "Demo replay of archived files. Original timestamps are retained; current-map positions and weather alignment are provisional. No events are created. Display clears if the demo publisher stops for 30 seconds."
          : fresh
            ? "Charts and detection refer to this file. Map and profile show the published frame; heatmap and detection cover the whole file. Candidates require review."
            : "Current visuals clear after 30 seconds without fresh acquisition. Network assets remain visible for orientation."}
      </p>
    </main>
  );
}
