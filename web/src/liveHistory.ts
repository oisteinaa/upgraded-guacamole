import type { ActivityHistory, Live } from "./types";

// Only advance the cursor once a response has been merged. A reconnect or
// configuration change requests/replaces the full history automatically.
export function liveHistoryQuery(previous?: ActivityHistory): string {
  const query = new URLSearchParams({ compact: "true" });
  if (previous?.rows.length) {
    query.set("history_key", previous.key);
    query.set("history_after", String(Math.max(...previous.rows.map(r => r.end))));
  }
  return `/live?${query}`;
}

export function mergeLiveHistory(previous: ActivityHistory | undefined, next: Live): ActivityHistory | undefined {
  const incoming = next.history;
  if (!incoming || !next.history_delta || previous?.key !== incoming.key ||
      JSON.stringify(previous.channel_edges) !== JSON.stringify(incoming.channel_edges)) return incoming;
  const indexed = new Map(previous.rows.map(r => [`${r.start}:${r.end}`, r]));
  for (const row of incoming.rows) indexed.set(`${row.start}:${row.end}`, row);
  const rows = [...indexed.values()].sort((a, b) => a.start - b.start);
  const end = next.history_latest_end ?? rows.at(-1)?.end ?? 0;
  return { ...incoming, rows: rows.filter(r => r.end > end - incoming.window_seconds).slice(-92) };
}
