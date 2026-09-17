import { useEffect, useState } from "react";
import Map from "./Map";
import { api, number, utcTime, type Geography, type Overview, type Live, type MetricFrame, type Collection } from "./types";
const empty: Collection = { type: "FeatureCollection", features: [] };
export default function LiveMonitor({ geo, overview }: { geo: Geography | null; overview: Overview | null }) {
  const [snapshot, setSnapshot] = useState<Live | null>(null);
  const [metric, setMetric] = useState<MetricFrame | null>(null);
  const [metricEpoch, setMetricEpoch] = useState(0);
  const [error, setError] = useState("");
  const [clock, setClock] = useState(Date.now());
  useEffect(() => {
    const timer = setInterval(() => setClock(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    const abort = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const next = await api<Live>("/live", { signal: abort.signal });
        if (abort.signal.aborted) return;
        setSnapshot(next);
        setError("");
        if (next.status !== "live" || !next.recording_id) {
          setMetric(null);
        } else {
          // The live snapshot's mapped points carry the instrument ID when verified.
          const lid = next.points[0]?.lid ?? (overview?.mapping_lids.length === 1 ? overview.mapping_lids[0] : null);
          if (lid == null) { setMetric(null); setError("Live instrument mapping is unavailable."); }
          else {
            const data = await api<MetricFrame>(`/recordings/${next.recording_id}/metrics?lid=${lid}&frame=${next.frame ?? 0}&metric=ac_rms&low=1&high=10`, { signal: abort.signal });
            if (!abort.signal.aborted) { setMetric(data); setMetricEpoch(next.acquisition_epoch ?? 0); }
          }
        }
      } catch (e) {
        if (!abort.signal.aborted) { setError((e as Error).message); setMetric(null); }
      } finally {
        if (!abort.signal.aborted) timer = setTimeout(poll, 5000);
      }
    }
    poll();
    return () => { abort.abort(); clearTimeout(timer); };
  }, [overview?.mapping_lids.join(",")]);
  const age = snapshot?.acquisition_epoch ? Math.max(0, clock / 1000 - snapshot.acquisition_epoch) : null;
  const fresh = !error && snapshot?.status === "live" && age != null && age <= 30;
  const displayed = fresh && clock / 1000 - metricEpoch <= 30 ? metric : null;
  const status = error ? "Connection unavailable" : fresh ? "Live capture" : snapshot?.status === "replay" ? "Replay source · not displayed as live" : snapshot?.status === "unverified" ? "Acquisition time unverified" : snapshot?.status === "stale" || snapshot?.status === "live" ? "Capture is stale" : "Waiting for live capture";
  return <main className="live-workspace">
    <section className="live-status" aria-label="Live capture status">
      <div><span className="eyebrow">LIVE MONITOR</span><h2>{status}</h2><p>{fresh ? "Latest acquisition · automatic updates" : "No current live signal is displayed. Archive browsing and replay are available in Investigate."}</p></div>
      <dl><div><dt>Last acquisition</dt><dd>{snapshot?.acquisition_epoch ? utcTime(snapshot.acquisition_epoch) : "—"}</dd></div>
      <div><dt>Acquisition age</dt><dd>{age == null ? "—" : `${number(Math.floor(age))} s`}</dd></div>
      <div><dt>Channels</dt><dd>{number(snapshot?.channel_count)}</dd></div>
      <div><dt>Signal layer</dt><dd>{displayed ? "AC RMS · latest capture" : "Awaiting current data"}</dd></div></dl>
      {error && <p role="alert">{error}</p>}
    </section>
    <Map weatherMode="live" geo={geo} events={empty} route="" selected={null} onSelect={() => {}} onEvent={() => {}} fibre={empty}
      metricData={displayed} scale={{min:0,max:Math.max(displayed?.scale.max ?? 1,1e-12),log:false}} onChannel={() => {}} />
    <p className="map-footnote">{displayed ? "Live AC RMS; previous live frame stays visible while the next frame loads. Stale data is removed after 30 seconds." : "Network assets remain visible for orientation. Historical events and recording signals are hidden."}</p>
  </main>;
}
