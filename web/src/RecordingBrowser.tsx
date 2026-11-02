import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";
import { api, number, type Inspection, type Recording } from "./types";

type File = Recording & { available: boolean };
type Scope = { day?: string; hour?: number; offset?: number };
type Catalog = {
  days: { day: string; count: number }[];
  hours: { hour: number; count: number }[];
  day: string | null; hour: number | null;
  items: File[]; latest: File | null; total: number; offset: number; limit: number;
};
const clock = (epoch: number) => new Date(epoch * 1000).toISOString().slice(11, 19);

export function useRecordingBrowser(inspection: Inspection, onInspection: (i: Inspection) => void) {
  const [request, setRequest] = useState<{ scope: Scope; select: boolean }>({ scope: {}, select: true });
  const [data, setData] = useState<Catalog | null>(null);
  const [selected, setSelected] = useState<File | null>(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [updated, setUpdated] = useState("");
  const current = useRef(inspection);
  current.current = inspection;
  useEffect(() => {
    const abort = new AbortController();
    let scope = request.scope, select = request.select, loading = false;
    async function load() {
      if (loading) return;
      loading = true;
      setBusy(true);
      try {
        const params = new URLSearchParams();
        if (scope.day) params.set("day", scope.day);
        if (scope.hour != null) params.set("hour", String(scope.hour));
        if (scope.offset) params.set("offset", String(scope.offset));
        const result = await api<Catalog>(`/recording-browser?${params}`, { signal: abort.signal });
        if (abort.signal.aborted) return;
        scope = { day: result.day ?? undefined, hour: result.hour ?? undefined, offset: result.offset };
        setData(result);
        setError("");
        setUpdated(new Date().toISOString().slice(11, 19));
        if (select) {
          const file = result.items.find(r => r.available);
          setSelected(file ?? null);
          onInspection({ ...current.current, rid: file?.id ?? 0, frame: 0 });
          select = false;
        }
      } catch (e: any) {
        if (!abort.signal.aborted) setError(e.message);
      } finally {
        loading = false;
        if (!abort.signal.aborted) setBusy(false);
      }
    }
    void load();
    const timer = setInterval(load, 15000);
    const focus = () => { void load(); };
    window.addEventListener("focus", focus);
    return () => { abort.abort(); clearInterval(timer); window.removeEventListener("focus", focus); };
  }, [request, onInspection]);
  useEffect(() => {
    const abort = new AbortController();
    if (!inspection.rid) { setSelected(null); return; }
    const item = data?.items.find(r => r.id === inspection.rid);
    if (item) { setSelected(item); return; }
    if (selected?.id === inspection.rid) return;
    api<File>(`/recordings/${inspection.rid}`, { signal: abort.signal })
      .then(r => { if (!abort.signal.aborted && current.current.rid === r.id) setSelected(r); })
      .catch(e => { if (!abort.signal.aborted) setError(e.message); });
    return () => abort.abort();
  }, [inspection.rid, data]);
  const recordings = useMemo(() => {
    const items = data?.items ?? [];
    return selected && selected.id === inspection.rid && !items.some(r => r.id === selected.id)
      ? [selected, ...items] : items;
  }, [data, selected, inspection.rid]);
  return {
    data, recordings, busy, error, updated,
    navigate: (scope: Scope, select = true) => setRequest({ scope, select }),
    refresh: () => setRequest({ scope: { day: data?.day ?? undefined, hour: data?.hour ?? undefined, offset: data?.offset }, select: false }),
  };
}

export type RecordingBrowserState = ReturnType<typeof useRecordingBrowser>;
export default function RecordingBrowser({ browser, rid, choose }: {
  browser: RecordingBrowserState; rid: number; choose: (id: number) => void;
}) {
  const { data, recordings, busy, error, updated, navigate, refresh } = browser;
  const unavailable = data?.items.filter(r => !r.available).length ?? 0;
  const outside = rid && !data?.items.some(r => r.id === rid);
  return <div className="recording-browser" aria-label="Archive file browser" aria-busy={busy}>
    <div className="recording-browser-fields">
      <label>Day · UTC
        <select aria-label="Recording day" value={data?.day ?? ""} onChange={e => navigate({ day: e.target.value })}>
          {!data?.days.length && <option value="">No indexed days</option>}
          {data?.days.map(d => <option key={d.day} value={d.day}>{d.day} · {number(d.count)} files</option>)}
        </select>
      </label>
      <label>Hour · UTC
        <select aria-label="Recording hour" value={data?.hour ?? ""} onChange={e => navigate({ day: data?.day ?? undefined, hour: +e.target.value })}>
          {!data?.hours.length && <option value="">No recordings</option>}
          {data?.hours.map(h => <option key={h.hour} value={h.hour}>{String(h.hour).padStart(2, "0")}:00–{String(h.hour).padStart(2, "0")}:59 · {number(h.count)} files</option>)}
        </select>
      </label>
      <label className="recording-file">Recording
        <select aria-label="Recording" value={rid || ""} onChange={e => choose(+e.target.value)}>
          {!rid && <option value="">Select a file</option>}
          {recordings.map(r => <option key={r.id} value={r.id} disabled={!r.available}>
            {outside && r.id === rid ? `Selected · ${new Date(r.acquisition_epoch * 1000).toISOString().slice(0, 10)} · ` : ""}
            {clock(r.acquisition_epoch)} · {r.relative_path.split("/").pop()} · {number(r.samples * r.dt)} s{!r.available ? " · unavailable" : ""}
          </option>)}
        </select>
      </label>
      <button type="button" onClick={() => navigate({})} disabled={busy || !data?.latest} title={data?.latest?.relative_path}>
        Latest file{data?.latest ? ` · ${clock(data.latest.acquisition_epoch)}` : ""}
      </button>
      <button type="button" aria-label="Refresh recording list" onClick={refresh} disabled={busy}><RefreshCw size={15} /> Refresh</button>
    </div>
    <div className="recording-browser-status">
      <span>{data?.total ? `${number(data.offset + 1)}–${number(data.offset + data.items.length)} of ${number(data.total)} files this hour` : "No files in this hour"}</span>
      <button aria-label="Newer recording page" disabled={busy || !data?.offset} onClick={() => navigate({ day: data!.day!, hour: data!.hour!, offset: Math.max(0, data!.offset-data!.limit) }, false)}><ChevronLeft size={14} /> Newer</button>
      <button aria-label="Older recording page" disabled={busy || !data || data.offset+data.items.length >= data.total} onClick={() => navigate({ day: data!.day!, hour: data!.hour!, offset: data!.offset+data!.limit }, false)}>Older <ChevronRight size={14} /></button>
      <span>{busy ? "Updating…" : `Updates every 15 s${updated ? ` · checked ${updated} UTC` : ""}`}</span>
      {!!unavailable && <span>{unavailable} indexed {unavailable === 1 ? "file is" : "files are"} no longer in storage.</span>}
    </div>
    {error && <p role="alert">Could not refresh recordings: {error}</p>}
  </div>;
}
