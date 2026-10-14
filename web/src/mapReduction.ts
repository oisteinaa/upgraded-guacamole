import type { Feature } from "./types";

// Merge only consecutive channel positions in the same fibre run and screen cell.
// Extrema remain actual samples at actual coordinates; this never joins gaps.
export function reduceFibre(
  features: Feature[],
  project: (xy: any) => { x: number; y: number },
  width: number,
  height: number,
  cell: number,
): Feature[] {
  const out: Feature[] = [];
  let bucket: Feature[] = [];
  let key = "";
  let previous: number | null = null;
  function flush() {
    if (!bucket.length) return;
    let min = bucket[0],
      max = bucket[0];
    for (const f of bucket) {
      if ((f.properties.value ?? 0) < (min.properties.value ?? 0)) min = f;
      if ((f.properties.value ?? 0) > (max.properties.value ?? 0)) max = f;
    }
    for (const f of new Set([min, max]))
      out.push({
        ...f,
        properties: { ...f.properties, bucket_count: bucket.length },
      });
    bucket = [];
  }
  for (const f of features) {
    const p = project(f.geometry.coordinates),
      ch = Number(f.properties.channel);
    if (p.x < -16 || p.y < -16 || p.x > width + 16 || p.y > height + 16) {
      flush();
      previous = null;
      continue;
    }
    if (cell <= 1) {
      flush();
      out.push({ ...f, properties: { ...f.properties, bucket_count: 1 } });
      previous = ch;
      continue;
    }
    const next = `${f.properties.run}:${Math.floor(p.x / cell)}:${Math.floor(p.y / cell)}`;
    // Older API/cache payloads used the original four-channel acquisition grid.
    const step = f.properties.channel_step ?? 4;
    if (next !== key || previous === null || Math.abs(ch - previous) !== step) flush();
    key = next;
    bucket.push(f);
    previous = ch;
  }
  flush();
  return out;
}
export function colorPosition(
  value: number,
  min: number,
  max: number,
  log: boolean,
) {
  if (log) {
    if (value <= 0) return 0;
    return Math.max(
      0,
      Math.min(
        1,
        (Math.log(value) - Math.log(min)) / (Math.log(max) - Math.log(min)),
      ),
    );
  }
  return Math.max(0, Math.min(1, (value - min) / (max - min)));
}
