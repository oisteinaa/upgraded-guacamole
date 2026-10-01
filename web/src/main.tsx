import CalmControls, { calmMetric, useCalm, type CalmPreference } from "./CalmControls";
import React, { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowRight,
  Check,
  ChevronLeft,
  ChevronRight,
  Clock,
  Database,
  FileText,
  MapPin,
  Radio,
  Search,
  SlidersHorizontal,
  X,
} from "lucide-react";
import "@fontsource/ibm-plex-sans/latin-400.css";
import "@fontsource/ibm-plex-sans/latin-500.css";
import "@fontsource/ibm-plex-sans/latin-600.css";
import "@fontsource/ibm-plex-sans-condensed/latin-700.css";
import "@fontsource/ibm-plex-mono/latin-400.css";
import Map from "./Map";
import LiveMonitor from "./LiveMonitor";
import SignalPanel from "./SignalPanel";
import MetricControls from "./MetricControls";
import EventLayerControls, { defaultEventLayer } from "./EventLayerControls";
import {
  api,
  classColors,
  number,
  storedTime,
  utcTime,
  type Overview,
  type EventRow,
  type EventDetail,
  type Recording,
  type Geography,
  type Feature,
  type Collection,
  type Inspection,
  type MetricName,
  type MetricFrame,
  type ColorScale,
} from "./types";
import "./style.css";
const empty: Collection = { type: "FeatureCollection", features: [] };
function Badge({ id, name }: { id: number | null; name?: string | null }) {
  return (
    <span className="badge" style={{ color: classColors[id ?? 0] }}>
      <i style={{ background: classColors[id ?? 0] }} />
      {name ?? "Unclassified"}
    </span>
  );
}
function App() {
  const [eventLayer, setEventLayer] = useState(defaultEventLayer);
  const [mapBusy, setMapBusy] = useState(false);
  const [mapError, setMapError] = useState("");
  const [mapRange, setMapRange] = useState("");
  const [mapTick, setMapTick] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setMapTick(n => n + 1), 60000);
    return () => clearInterval(timer);
  }, []);
  const [mode, setMode] = useState("investigate");
  const [sidebarTab, setSidebarTab] = useState("selection");
  const [signalVisible, setSignalVisible] = useState(true);
  const detailRequest = useRef(0);
  const [inspection, setInspection] = useState<Inspection>({
    rid: 0,
    channel: 0,
    frame: 0,
  });
  const [metric, setMetric] = useState<MetricName>("ac_rms");
  const [band, setBand] = useState<[number, number]>([1, 10]);
  const [scale, setScale] = useState<ColorScale>({
    min: 0,
    max: 1,
    log: false,
  });
  const [calmPreference, setCalmPreference] = useState<CalmPreference>("auto");
  const [metricData, setMetricData] = useState<MetricFrame | null>(null);
  const calmEnabled = useCalm(calmPreference, metricData?.normalization);
  const displayMetric = useMemo(() => calmMetric(metricData, calmEnabled), [metricData, calmEnabled]);
  const [metricBusy, setMetricBusy] = useState(false),
    [metricError, setMetricError] = useState("");
  const [lid, setLid] = useState(0),
    [fibre, setFibre] = useState<Collection>(empty);
  const scaleKey = useRef("");
  useEffect(() => {
    if (!lid) return;
    const abort = new AbortController();
    api<Collection>(`/fibre?lid=${lid}`, { signal: abort.signal })
      .then(setFibre)
      .catch((e) => {
        if (e.name !== "AbortError") setMetricError(e.message);
      });
    return () => abort.abort();
  }, [lid]);
  useEffect(() => {
    if (mode !== "investigate" || !inspection.rid || !lid) return;
    const abort = new AbortController();
    setMetricBusy(true);
    setMetricError("");
    api<MetricFrame>(
      `/recordings/${inspection.rid}/metrics?lid=${lid}&frame=${inspection.frame}&metric=${metric}&low=${band[0]}&high=${band[1]}`,
      { signal: abort.signal },
    )
      .then((d) => {
        setMetricData(d);
        const key = `${lid}:${metric}:${band.join(":")}`;
        if (scaleKey.current !== key) {
          scaleKey.current = key;
          setScale({ min: 0, max: Math.max(d.scale.max, 1e-12), log: false });
        }
      })
      .catch((e) => {
        if (e.name !== "AbortError") setMetricError(e.message);
      })
      .finally(() => {
        if (!abort.signal.aborted) setMetricBusy(false);
      });
    return () => abort.abort();
  }, [inspection.rid, inspection.frame, metric, band, lid, mode]);
  const [overview, setOverview] = useState<Overview | null>(null),
    [geo, setGeo] = useState<Geography | null>(null),
    [recordings, setRecordings] = useState<Recording[]>([]),
    [events, setEvents] = useState<EventRow[]>([]),
    [total, setTotal] = useState(0),
    [locations, setLocations] = useState<Collection>(empty);
  const [event, setEvent] = useState<EventDetail | null>(null),
    [selected, setSelected] = useState<Feature | null>(null);
  const [route, setRoute] = useState(""),
    [classid, setClassid] = useState(""),
    [review, setReview] = useState("all"),
    [search, setSearch] = useState(""),
    [query, setQuery] = useState(""),
    [start, setStart] = useState(""),
    [end, setEnd] = useState(""),
    [offset, setOffset] = useState(0),
    [refresh, setRefresh] = useState(0);
  const [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [detailBusy, setDetailBusy] = useState(false),
    [requestedRecording, setRequestedRecording] = useState<number | null>(null),
    [assetSearch, setAssetSearch] = useState("");
  const [classification, setClassification] = useState(""),
    [reviewer, setReviewer] = useState(
      localStorage.getItem("sensnet-reviewer") ?? "",
    ),
    [note, setNote] = useState(""),
    [saving, setSaving] = useState(false),
    [saved, setSaved] = useState(false),
    [reviewError, setReviewError] = useState("");
  useEffect(() => {
    const abort = new AbortController();
    Promise.all([
      api<Overview>("/overview", { signal: abort.signal }),
      api<Geography>("/map", { signal: abort.signal }),
      api<Recording[]>("/recordings", { signal: abort.signal }),
    ])
      .then(([o, g, r]) => {
        setOverview(o);
        setGeo(g);
        setRecordings(r);
        setLid(o.mapping_lids[0] ?? 0);
        const first = [...r].sort(
          (a, b) => a.acquisition_epoch - b.acquisition_epoch,
        )[0];
        if (first)
          setInspection({
            rid: first.id,
            channel: first.first_channel,
            frame: 0,
          });
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => abort.abort();
  }, []);
  useEffect(() => {
    const timer = setTimeout(() => {
      setQuery(search);
      setOffset(0);
    }, 250);
    return () => clearTimeout(timer);
  }, [search]);
  const params = new URLSearchParams({ review, search: query });
  if (route) params.set("route", route);
  if (classid !== "") params.set("classid", classid);
  if (start) params.set("start", start + "T00:00:00");
  if (end) {
    const d = new Date(end + "T00:00:00Z");
    d.setUTCDate(d.getUTCDate() + 1);
    params.set("end", d.toISOString().slice(0, 19));
  }
  const filters = params.toString();
  useEffect(() => {
    const abort = new AbortController();
    if (mode !== "investigate") return;
    setBusy(true);
    setError("");
    setEvents([]);
    api<{ items: EventRow[]; total: number }>(`/events?${filters}&offset=${offset}`, { signal: abort.signal })
      .then(e => {
        setEvents(e.items);
        setTotal(e.total);
      })
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      })
      .finally(() => {
        if (!abort.signal.aborted) setBusy(false);
      });
    return () => abort.abort();
  }, [filters, offset, refresh, mode]);
  useEffect(() => {
    const abort = new AbortController();
    setLocations(empty);
    setMapError("");
    setMapRange("");
    setMapBusy(false);
    if (mode !== "investigate" || !eventLayer.visible) return;
    if (eventLayer.window === "custom" && (!eventLayer.start || !eventLayer.end || eventLayer.end <= eventLayer.start)) {
      setMapError("Choose a start and a later end for the custom range.");
      return;
    }
    const params = new URLSearchParams({ window: eventLayer.window, review: eventLayer.review, classes: eventLayer.classes.join(",") });
    if (route) params.set("route", route);
    if (eventLayer.window === "custom") {
      params.set("start", eventLayer.start);
      params.set("end", eventLayer.end);
    }
    setMapBusy(true);
    api<{ data: Collection; window_start: string | null; window_end: string | null }>(`/map/events?${params}`, { signal: abort.signal })
      .then(result => {
        setLocations(result.data);
        setMapRange(result.window_start && result.window_end ? `${storedTime(result.window_start)} – ${storedTime(result.window_end)}` : "");
      })
      .catch(e => { if (e.name !== "AbortError") setMapError(e.message); })
      .finally(() => { if (!abort.signal.aborted) setMapBusy(false); });
    return () => abort.abort();
  }, [eventLayer, route, refresh, mapTick, mode]);
  const selectEvent = useCallback(
    async (id: number) => {
      setSidebarTab("selection");
      setMode("investigate");
      const request = ++detailRequest.current;
      setDetailBusy(true);
      setReviewError("");
      setSaved(false);
      setEvent(null);
      setSelected(null);
      try {
        const d = await api<EventDetail>(`/events/${id}`);
        if (request !== detailRequest.current) return;
        setEvent(d);
        setClassification(d.classid?.toString() ?? "");
        setNote("");
        let f = locations.features.find((f) => f.id === id);
        if (!f && d.location) f = { type: "Feature", id, geometry: { type: "Point", coordinates: [d.location.longitude, d.location.latitude] }, properties: { ...d } };
        if (!f) {
          const located = await api<{ data: Collection }>(`/map/events?window=all&search=${id}`);
          if (request !== detailRequest.current) return;
          f = located.data.features.find(feature => feature.id === id);
        }
        if (f) setSelected(f);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        if (request === detailRequest.current) setDetailBusy(false);
      }
    },
    [locations],
  );
  function filter(setter: (s: string) => void, value: string) {
    setter(value);
    setOffset(0);
  }
  function selectAsset(f: Feature) {
    setSidebarTab("selection");
    detailRequest.current++;
    setDetailBusy(false);
    setSelected(f);
    setEvent(null);
    setAssetSearch("");
  }
  async function save() {
    if (!event) return;
    const savingRequest = detailRequest.current;
    setSaving(true);
    setSaved(false);
    setReviewError("");
    try {
      const d = await api<EventDetail>(`/events/${event.id}/reviews`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          classid: classification ? +classification : null,
          expected_revision: event.revision,
          expected_classid: event.classid,
          reviewer,
          note,
        }),
      });
      if (savingRequest === detailRequest.current) {
        setEvent(d);
        setNote("");
        setSaved(true);
      }
      localStorage.setItem("sensnet-reviewer", reviewer);
      setRefresh((n) => n + 1);
      setOverview(await api<Overview>("/overview"));
    } catch (e) {
      if (savingRequest === detailRequest.current)
        setReviewError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }
  const assets =
    assetSearch.length > 1
      ? geo?.masts.features
          .filter((f) =>
            `${f.properties.route} ${f.properties.mast}`
              .toLowerCase()
              .includes(assetSearch.toLowerCase()),
          )
          .slice(0, 8)
      : [];
  const selectedChannel = selected?.properties.recording_channel;
  const currentChannel =
    selectedChannel === undefined
      ? null
      : displayMetric?.data.features.find(
          (f) => f.properties.recording_channel === selectedChannel,
        );
  const p =
    selectedChannel === undefined
      ? selected?.properties
      : {
          ...selected?.properties,
          value: currentChannel?.properties.value ?? null,
          raw_value: currentChannel?.properties.raw_value,
          calm_median: currentChannel?.properties.calm_median,
        };
  return (
    <>
      <header className="app-header">
        <div className="brand-icon">
          <Activity size={25} />
        </div>
        <div className="brand">
          <span className="eyebrow">SENSNET / DAS MONITORING</span>
          <h1>Cable Observatory</h1>
        </div>
        <nav className="main-nav" aria-label="Workspace mode">
          <button
            className={mode === "investigate" ? "active" : ""}
            onClick={() => setMode("investigate")}
          >
            <Search size={15} />
            Investigate
          </button>
          <button
            className={mode === "live" ? "active" : ""}
            onClick={() => setMode("live")}
          >
            <Radio size={15} />
            Live monitor
          </button>
        </nav>
        <div className="environment">
          <i />
          {overview?.environment ?? "Connecting…"}
          <small>{mode === "live" ? "Acquisition / demo monitor" : "Recording investigation"}</small>
        </div>
      </header>
      {mode === "investigate" && <div className="summary-bar">
        <div>
          <span className="eyebrow">EVENT ARCHIVE</span>
          <strong>{number(overview?.counts.events)}</strong>
        </div>
        <div>
          <span className="eyebrow">AWAITING CLASSIFICATION</span>
          <strong>{number(overview?.counts.unclassified)}</strong>
        </div>
        <div>
          <span className="eyebrow">MASTS / SPANS</span>
          <strong>
            {number(overview?.counts.masts)}{" "}
            <span className="muted">/ {number(overview?.counts.spans)}</span>
          </strong>
        </div>
        <div>
          <span className="eyebrow">LOCAL RECORDINGS</span>
          <strong>{number(overview?.counts.recordings)}</strong>
        </div>
        <div className="archive-coverage">
          <Clock size={15} />
          <span>
            {overview?.counts.first_event?.slice(0, 10)}{" "}
            <ArrowRight size={12} /> {overview?.counts.last_event?.slice(0, 10)}
            <small>Stored event coverage · timestamps as recorded</small>
          </span>
        </div>
      </div>
      }
      {mode === "investigate" && error && (
        <div role="alert" className="error-banner">
          {error}
          <button onClick={() => window.location.reload()}>Retry</button>
        </div>
      )}
      {mode === "live" ? <LiveMonitor geo={geo} overview={overview} /> : <>
      <main className={`workspace ${signalVisible ? "" : "signal-hidden"}`}>
        <aside className="event-sidebar">
          <div className="panel-title">
            <div>
              <span className="eyebrow">INVESTIGATION</span>
              <h2>Event queue</h2>
            </div>
            <SlidersHorizontal size={17} />
          </div>
          <label className="search-box">
            <Search size={15} />
            <input
              placeholder="Search comment or event ID"
              aria-label="Search events"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </label>
          <div className="filters">
            <div className="date-row">
              <label>
                From
                <input
                  type="date"
                  aria-label="Events from"
                  value={start}
                  onChange={(e) => filter(setStart, e.target.value)}
                />
              </label>
              <label>
                Through
                <input
                  type="date"
                  aria-label="Events through"
                  value={end}
                  onChange={(e) => filter(setEnd, e.target.value)}
                />
              </label>
            </div>
            <label>
              Classification
              <select
                aria-label="Classification filter"
                value={classid}
                onChange={(e) => filter(setClassid, e.target.value)}
              >
                <option value="">All classifications</option>
                <option value="0">Unclassified</option>
                {overview?.classes.map((c) => (
                  <option key={c.classid} value={c.classid}>
                    {c.name}
                  </option>
                ))}
              </select>
            </label>
            <div className="filter-row">
              <label>
                Route
                <select
                  aria-label="Route filter"
                  value={route}
                  onChange={(e) => filter(setRoute, e.target.value)}
                >
                  <option value="">All routes</option>
                  {overview?.routes.map((r) => (
                    <option key={r.route} value={r.route}>
                      {r.route}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Review
                <select
                  aria-label="Review filter"
                  value={review}
                  onChange={(e) => filter(setReview, e.target.value)}
                >
                  <option value="all">All events</option>
                  <option value="unreviewed">Not reviewed</option>
                  <option value="reviewed">Reviewed</option>
                </select>
              </label>
            </div>
          </div>
          <div className="queue-count">
            <span>{busy ? "Loading…" : `${number(total)} events`}</span>
            <button
              className="plain"
              onClick={() => {
                setSearch("");
                setRoute("");
                setClassid("");
                setReview("all");
                setStart("");
                setEnd("");
                setOffset(0);
              }}
            >
              Reset filters
            </button>
          </div>
          <div className="event-list" aria-busy={busy}>
            {events.map((e) => (
              <button
                className={`event-item ${event?.id === e.id ? "selected" : ""}`}
                key={e.id}
                onClick={() => selectEvent(e.id)}
              >
                <div>
                  <span className="mono">#{e.id}</span>
                  <span className="metric">
                    {number(e.value)} <small>{e.metric?.toUpperCase()}</small>
                  </span>
                </div>
                <strong>{e.comment || "Unnamed event"}</strong>
                <time>{storedTime(e.time)}</time>
                <div>
                  <Badge id={e.classid} name={e.class_name} />
                  {e.revision > 0 ? (
                    <Check size={14} />
                  ) : (
                    <span className="location-status">
                      {e.location ? (e.location.routes.join(", ") || "Channel mapped") : e.alignment_verified
                        ? (e.route ?? "Located")
                        : "Unlocated"}
                    </span>
                  )}
                </div>
              </button>
            ))}
            {!busy && !events.length && (
              <div className="empty compact">
                <Search size={22} />
                <strong>No matching events</strong>
                <span>
                  {route
                    ? "Legacy events without verified routes remain under All routes."
                    : "Try a wider time range or different filters."}
                </span>
              </div>
            )}
          </div>
          <div className="pagination">
            <button
              aria-label="Previous event page"
              disabled={!offset || busy}
              onClick={() => setOffset((n) => Math.max(0, n - 50))}
            >
              <ChevronLeft size={16} />
            </button>
            <span>
              {total ? `${offset + 1}–${Math.min(offset + 50, total)}` : "0"} of{" "}
              {number(total)}
            </span>
            <button
              aria-label="Next event page"
              disabled={offset + 50 >= total || busy}
              onClick={() => setOffset((n) => n + 50)}
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </aside>
        <div className="map-column">
          <div className="map-search">
            <button
              className="secondary signal-visibility"
              aria-controls="signal-investigation"
              aria-expanded={signalVisible}
              onClick={() => setSignalVisible((visible) => !visible)}
            >
              <Activity size={14} />
              {signalVisible ? "Hide signal" : "Show signal"}
            </button>
            <Search size={15} />
            <input
              aria-label="Find mast"
              placeholder="Find a mast · try R06 M12"
              value={assetSearch}
              onChange={(e) => setAssetSearch(e.target.value)}
            />
            <span>
              {locations.features.length} located events
              {locations.features.length >= 5000 ? " · latest 5,000 shown" : ""}
            </span>
            {!!assets?.length && (
              <div className="asset-results">
                {assets.map((f) => (
                  <button key={f.id} onClick={() => selectAsset(f)}>
                    <MapPin size={14} />
                    {f.properties.route} · {f.properties.mast}
                    <span>CH {f.properties.channel}</span>
                  </button>
                ))}
              </div>
            )}
          </div>
          <Map
            geo={geo}
            events={locations}
            route={route}
            selected={selected}
            onSelect={selectAsset}
            onEvent={selectEvent}
            fibre={fibre}
            metricData={displayMetric}
            scale={calmEnabled ? { min: 0, max: 10, log: false } : scale}
            onChannel={(f) => {
              setSidebarTab("selection");
              detailRequest.current++;
              setEvent(null);
              setSelected(f);
              setInspection((i) => ({
                ...i,
                channel: Number(f.properties.recording_channel),
              }));
            }}
          />
          <div className="map-footnote">
            <MapPin size={13} />
            {metricBusy && metricData && <span>Updating signal layer · previous frame remains visible. </span>}
            {event && selected && !locations.features.some(f => f.id === event.id)
              ? "Selected event highlighted outside map filters. Close selection to hide it."
              : "Event markers follow Signal layer filters; the queue retains older events."}
          </div>
        </div>
        <aside className="detail-sidebar">
          <div className="tabs sidebar-tabs" role="tablist" aria-label="Map sidebar">
            {[["selection", "Selection"], ["signal", "Signal layer"]].map(([id, label]) => (
              <button key={id} id={`sidebar-tab-${id}`} role="tab"
                aria-selected={sidebarTab === id} aria-controls={`sidebar-panel-${id}`}
                tabIndex={sidebarTab === id ? 0 : -1}
                className={sidebarTab === id ? "active" : ""}
                onClick={() => setSidebarTab(id)}
                onKeyDown={(e) => {
                  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
                  e.preventDefault();
                  const next = e.key === "Home" ? "selection" : e.key === "End" ? "signal" : id === "selection" ? "signal" : "selection";
                  setSidebarTab(next);
                  document.getElementById(`sidebar-tab-${next}`)?.focus();
                }}>
                {label}
              </button>
            ))}
          </div>
          <div id="sidebar-panel-signal" role="tabpanel" aria-labelledby="sidebar-tab-signal"
            className="sidebar-pane signal-settings" hidden={sidebarTab !== "signal"}>
          <EventLayerControls value={eventLayer} onChange={setEventLayer}
            classes={overview?.classes ?? []} count={locations.features.length}
            busy={mapBusy} error={mapError} range={mapRange}
            selectedOutside={!!event && !!selected && !locations.features.some(f => f.id === event.id)} />
          <CalmControls preference={calmPreference} onChange={setCalmPreference} data={metricData?.normalization} />
          <MetricControls
            metric={metric}
            setMetric={setMetric}
            band={band}
            setBand={setBand}
            scale={calmEnabled ? { min: 0, max: 10, log: false } : scale}
            setScale={setScale}
            data={displayMetric}
            busy={metricBusy}
            error={metricError}
            inspection={inspection}
            setInspection={(i) => {
              setEvent(null);
              setInspection(i);
            }}
            recordings={recordings}
            lid={lid}
            setLid={setLid}
            lids={overview?.mapping_lids ?? []}
          />
          </div>
          <div id="sidebar-panel-selection" role="tabpanel" aria-labelledby="sidebar-tab-selection"
            className="sidebar-pane" hidden={sidebarTab !== "selection"}>
          <div className="panel-title">
            <div>
              <span className="eyebrow">INSPECT & REVIEW</span>
              <h2>
                {event
                  ? "Event details"
                  : selected
                    ? "Asset details"
                    : "Selection"}
              </h2>
            </div>
            {(event || selected) && (
              <button
                className="plain"
                aria-label="Close selection"
                onClick={() => {
                  detailRequest.current++;
                  setDetailBusy(false);
                  setEvent(null);
                  setSelected(null);
                }}
              >
                <X size={17} />
              </button>
            )}
          </div>
          {detailBusy ? (
            <div className="empty">Loading event…</div>
          ) : event ? (
            <div className="detail-content">
              <div className="event-heading">
                <span className="mono">EVENT #{event.id}</span>
                <Badge id={event.classid} name={event.class_name} />
                <h3>{event.comment || "Unnamed event"}</h3>
                <time>{storedTime(event.time)}</time>
              </div>
              <dl className="facts">
                <div>
                  <dt>Metric</dt>
                  <dd>
                    {event.metric?.toUpperCase()} · {number(event.value)}
                  </dd>
                </div>
                <div>
                  <dt>Location</dt>
                  <dd>
                    {event.location
                      ? `${event.location.latitude.toFixed(5)}, ${event.location.longitude.toFixed(5)}`
                      : event.alignment_verified ? (event.route ?? `CH ${event.channel}`) : "Unavailable"}
                  </dd>
                </div>
                <div>
                  <dt>Recording</dt>
                  <dd>
                    {event.context?.alignment_verified
                      ? "Verified reference"
                      : event.context?.source_linked ? "Source samples linked; alignment unverified" : "No verified link"}
                  </dd>
                </div>
              </dl>
              {event.location && (
                <dl className="facts">
                  <div><dt>Channels · DAS line {event.location.lid}</dt><dd>{event.location.channel_start}–{event.location.channel_end}</dd></div>
                  <div><dt>Coordinate mapping</dt><dd>{event.location.mapping === "interpolated" ? `Interpolated between CH ${event.location.lower_channel} and ${event.location.upper_channel}` : "Exact channel coordinates"}</dd></div>
                  <div><dt>Spans in sampled block</dt><dd>{event.location.spans.length ? event.location.spans.map(s => `${s.route} ${s.from_mast}–${s.to_mast}`).join(", ") : "Outside imported span coverage"}</dd></div>
                  <div><dt>Nearest masts to marker</dt><dd>{event.location.nearest_masts.map(m => `${m.route} ${m.mast} (${Math.round(m.distance_m)} m)`).join(", ")}</dd></div>
                </dl>
              )}
              {!event.alignment_verified && (
                <div className="notice">
                  <MapPin size={16} />
                  <span>
                    {event.location ? event.location.note : "Time and geographic alignment are unverified. Linked source samples can still be inspected."}
                  </span>
                </div>
              )}
              <div className="review-form">
                <span className="eyebrow">HUMAN REVIEW</span>
                <label>
                  Classification
                  <select
                    aria-label="Review classification"
                    value={classification}
                    onChange={(e) => {
                      setClassification(e.target.value);
                      setSaved(false);
                    }}
                  >
                    <option value="">Unclassified</option>
                    {overview?.classes.map((c) => (
                      <option key={c.classid} value={c.classid}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  Reviewed by
                  <input
                    aria-label="Reviewer"
                    value={reviewer}
                    placeholder="Your name"
                    maxLength={100}
                    onChange={(e) => setReviewer(e.target.value)}
                  />
                </label>
                <label>
                  Evidence & notes
                  <textarea
                    aria-label="Review notes"
                    value={note}
                    placeholder="Record the evidence behind this classification…"
                    maxLength={4000}
                    onChange={(e) => setNote(e.target.value)}
                  />
                </label>
                <button
                  className="primary"
                  disabled={
                    saving ||
                    !reviewer.trim() ||
                    !note.trim() ||
                    !overview?.write_enabled
                  }
                  onClick={save}
                >
                  {saving ? "Saving…" : saved ? "Review saved" : "Save review"}
                  {saved ? <Check size={15} /> : <ArrowRight size={15} />}
                </button>
                <small className="muted">
                  Classification changes are recorded with reviewer, notes, and
                  time.
                </small>
                {saved && (
                  <div role="status" className="success">
                    Saved to the local database.
                  </div>
                )}
                {reviewError && (
                  <div role="alert" className="inline-error">
                    {reviewError}
                    <button onClick={() => selectEvent(event.id)}>
                      Reload event
                    </button>
                  </div>
                )}
              </div>
              <div className="review-history">
                <span className="eyebrow">
                  REVIEW HISTORY · {event.reviews.length}
                </span>
                {event.reviews.length ? (
                  event.reviews.map((r) => (
                    <div key={r.id} className="review-entry">
                      <strong>{r.class_name ?? "Unclassified"}</strong>
                      <p>{r.note}</p>
                      <small>
                        {r.reviewer} ·{" "}
                        {new Date(r.reviewed_at).toLocaleString()}
                      </small>
                    </div>
                  ))
                ) : (
                  <p className="muted small">No reviews yet.</p>
                )}
              </div>
            </div>
          ) : selected && p && p.recording_channel !== undefined ? (
            <div className="detail-content">
              <span className="eyebrow">RECORDED SIGNAL</span>
              <h3>Channel {p.recording_channel}</h3>
              <dl className="facts">
                <div>
                  <dt>Mapped channel</dt>
                  <dd>
                    {p.mapped_channel ??
                      `${p.lower_channel}–${p.upper_channel}`}
                  </dd>
                </div>
                <div>
                  <dt>Instrument</dt>
                  <dd>{p.lid}</dd>
                </div>
                <div>
                  <dt>Position source</dt>
                  <dd>
                    {p.mapping === "exact"
                      ? "masteliste · exact ID"
                      : `masteliste · interpolated ${p.lower_channel}–${p.upper_channel}`}
                  </dd>
                </div>
                <div>
                  <dt>Selected metric</dt>
                  <dd>
                    {number(p.value)} {displayMetric?.unit}
                    {calmEnabled && <small>Raw {number(p.raw_value)} {metricData?.unit} · calm median {number(p.calm_median)}</small>}
                  </dd>
                </div>
              </dl>
              <p className="muted small">
                This channel is open in the signal panel below. The map
                summarizes a fixed ten-second frame.
              </p>
            </div>
          ) : selected && p ? (
            <div className="detail-content">
              <span className="mono">{p.route}</span>
              <h3>{p.mast ?? `${p.from_mast} → ${p.to_mast}`}</h3>
              <dl className="facts">
                {p.mast ? (
                  <>
                    <div>
                      <dt>Channel / lid</dt>
                      <dd>
                        {p.channel} / {p.lid}
                      </dd>
                    </div>
                    <div>
                      <dt>Channel match</dt>
                      <dd>{number(p.channel_distance_m)} m</dd>
                    </div>
                    <div>
                      <dt>Coordinates</dt>
                      <dd>
                        {Number(p.latitude).toFixed(5)},{" "}
                        {Number(p.longitude).toFixed(5)}
                      </dd>
                    </div>
                  </>
                ) : (
                  <>
                    <div>
                      <dt>Endpoint length</dt>
                      <dd>{number(p.straight_length_m)} m</dd>
                    </div>
                    <div>
                      <dt>Connection</dt>
                      <dd>{p.connection_status}</dd>
                    </div>
                    <div>
                      <dt>Water status</dt>
                      <dd>{p.water_status}</dd>
                    </div>
                    <div>
                      <dt>Installation</dt>
                      <dd>{p.installation}</dd>
                    </div>
                  </>
                )}
              </dl>
              <div className="notice">
                <FileText size={16} />
                <span>
                  {p.mast
                    ? "Current channel mapping does not establish historical event alignment."
                    : `Illustrative straight-line connection, not measured cable length. ${p.review_reason ?? ""}`}
                </span>
              </div>
              <button
                className="secondary"
                onClick={() => filter(setRoute, p.route)}
              >
                Filter verified events on {p.route}
              </button>
            </div>
          ) : (
            <div className="selection-empty">
              <div className="selection-icon">
                <MapPin size={30} />
              </div>
              <h3>
                Start with an event
                <br />
                or a place
              </h3>
              <p>
                Select an event to review its classification and evidence. Click
                a mast or span to inspect the network.
              </p>
              <div className="hint">
                <Search size={16} />
                <span>Search the archive by event ID or comment</span>
              </div>
              <div className="hint">
                <Activity size={16} />
                <span>Explore real DAS recordings in the panel below</span>
              </div>
              <div className="hint">
                <Database size={16} />
                <span>All review changes stay in the local database copy</span>
              </div>
            </div>
          )}
          </div>
        </aside>
      </main>
      <SignalPanel
        mapLoading={metricBusy}
        open={signalVisible}
        setOpen={setSignalVisible}
        geography={geo}
        recordings={recordings}
        event={event}
        overview={overview}
        requestedRecording={requestedRecording}
        inspection={inspection}
        onInspection={setInspection}
      />
      </>}
      <footer>
        <span>
          SENSNET <span className="muted">/ Cable intelligence</span>
        </span>
        <span>
          Classifications describe reviewed evidence · threshold crossings
          remain unclassified
        </span>
        <span>Nord / IBM Plex</span>
      </footer>
    </>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
