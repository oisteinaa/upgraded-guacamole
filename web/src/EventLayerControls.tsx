import type { Overview } from "./types";
export type EventLayerSettings = {
  visible: boolean;
  window: string;
  review: string;
  classes: number[];
  start: string;
  end: string;
};
export const defaultEventLayer: EventLayerSettings = {
  visible: true, window: "latest_day", review: "all",
  classes: [0, 1, 2, 3, 4], start: "", end: "",
};
export default function EventLayerControls({ value, onChange, classes, count, busy, error, range, selectedOutside }: {
  value: EventLayerSettings; onChange: (value: EventLayerSettings) => void;
  classes: Overview["classes"]; count: number; busy: boolean; error: string;
  range: string; selectedOutside: boolean;
}) {
  const update = (patch: Partial<EventLayerSettings>) => onChange({ ...value, ...patch });
  return <section className="event-layer-controls" aria-label="Event map settings">
    <h3>Events</h3>
    <label className="event-check"><input type="checkbox" checked={value.visible} onChange={e => update({ visible: e.target.checked })} />Show event markers</label>
    <label>Map time range<select aria-label="Map event time range" value={value.window} onChange={e => update({ window: e.target.value })}>
      <option value="latest_day">Latest recorded day · demonstration</option>
      <option value="hour">Last hour</option><option value="day">Last 24 hours</option><option value="week">Last 7 days</option>
      <option value="all">All dates</option><option value="custom">Custom range</option>
    </select></label>
    {value.window === "custom" && <>
      <label>From (Oslo)<input aria-label="Map events from" type="datetime-local" value={value.start} onChange={e => update({ start: e.target.value })} /></label>
      <label>Until (Oslo, exclusive)<input aria-label="Map events until" type="datetime-local" value={value.end} onChange={e => update({ end: e.target.value })} /></label>
    </>}
    <label>Review status<select aria-label="Map event review status" value={value.review} onChange={e => update({ review: e.target.value })}>
      <option value="all">All</option><option value="unreviewed">Unreviewed</option><option value="reviewed">Reviewed</option>
    </select></label>
    <fieldset><legend>Event classes</legend>{[{ classid: 0, name: "Unclassified" }, ...classes].map(c => <label className="event-check" key={c.classid}>
      <input type="checkbox" checked={value.classes.includes(c.classid)} onChange={e => update({ classes: e.target.checked ? [...value.classes, c.classid] : value.classes.filter(id => id !== c.classid) })} />{c.name}
    </label>)}</fieldset>
    {error && <p role="alert">{error}</p>}
    <p className="muted">{busy ? "Loading event markers…" : `${count} event markers${count >= 5000 ? " · latest 5,000 shown" : ""}`}{!value.visible && " · layer hidden"}</p>
    {value.visible && range && <p className="muted">{range} · Oslo stored time</p>}
    {selectedOutside && <p className="notice">Selected event temporarily highlighted outside these filters.</p>}
    <p className="muted">These controls affect the map. Older events remain searchable in the queue. Selecting an event reveals its location even when markers are hidden.</p>
  </section>;
}
