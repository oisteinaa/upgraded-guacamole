// A display coordinate only: native channel IDs stay in hover/click data.
// Sections are independent; the display spacer never asserts a cable connection.
export type FibreSection = { start: number; end: number; label: string };
export function fibreAxis(sections: FibreSection[], spacer = 1500) {
  let offset = 0;
  const spans = sections.map((s) => {
    const span = { ...s, offset, direction: s.end >= s.start ? 1 : -1 };
    offset += Math.abs(s.end - s.start) + spacer;
    return span;
  });
  const section = (channel: number) =>
    spans.findIndex(
      (s) =>
        channel >= Math.min(s.start, s.end) &&
        channel <= Math.max(s.start, s.end),
    );
  const position = (channel: number | null | undefined): number | null => {
    if (channel == null || !Number.isFinite(channel)) return null;
    const s = spans[section(channel)];
    return s ? s.offset + (channel - s.start) * s.direction : null;
  };
  return { spans, section, position, extent: offset - spacer };
}

export type Axis = ReturnType<typeof fibreAxis>;

// Reverse whole profile pieces, retaining null separators for gaps/missing scores.
// Return source indices so values, raw metrics and native IDs move together.
export function profileOrder(channels: (number | null)[], axis: Axis) {
  return axis.spans.flatMap((span, section) => {
    const indices = channels
      .map((ch, i) => ({ ch, i }))
      .filter(({ ch }) => ch !== null && axis.section(ch) === section)
      .map(({ i }) => i);
    if (!indices.length) return [];
    const first = Math.min(...indices),
      last = Math.max(...indices);
    const ordered: (number | null)[] = [];
    for (let i = first; i <= last; i++) {
      if (channels[i] === null) ordered.push(null);
      else if (axis.section(channels[i]!) === section) ordered.push(i);
    }
    if (span.direction < 0) ordered.reverse();
    return [null, ...ordered, null];
  });
}

// Keep original bin membership and width, including edge half-samples.
// Gap bins and bins spanning section boundaries are not reassigned to a location.
export function heatOrder(edges: number[], axis: Axis) {
  const bins = edges
    .slice(0, -1)
    .map((left, index) => {
      const right = edges[index + 1],
        midpoint = (left + right) / 2;
      const section = axis.section(midpoint),
        span = axis.spans[section];
      if (!span) return null;
      const transform = (ch: number) =>
        span.offset + (ch - span.start) * span.direction;
      return {
        index,
        section,
        left: Math.min(transform(left), transform(right)),
        right: Math.max(transform(left), transform(right)),
      };
    })
    .filter((bin) => bin !== null)
    .sort((a, b) => a.left - b.left);
  const indices: (number | null)[] = [],
    x: number[] = [];
  for (const bin of bins) {
    if (!x.length) x.push(bin.left);
    else if (bin.left > x[x.length - 1]) {
      indices.push(null);
      x.push(bin.left);
    }
    indices.push(bin.index);
    x.push(bin.right);
  }
  return { indices, edges: x };
}

// Orient each validated acquisition region by its mapped endpoints, then place
// the southern region first. Keep native ordering inside bends; never latitude-sort
// individual samples. Unknown geometry retains the original channel-axis view.
export function geographicSections(
  regions: { start: number; end: number }[],
  features: {
    properties: Record<string, any>;
    geometry: { coordinates: any };
  }[],
): FibreSection[] {
  const sections = regions.map((region) => {
    const points = features
      .filter((f) => {
        const ch = f.properties.recording_channel;
        return (
          ch >= region.start &&
          ch <= region.end &&
          Number.isFinite(f.geometry.coordinates[1])
        );
      })
      .sort(
        (a, b) =>
          a.properties.recording_channel - b.properties.recording_channel,
      );
    if (points.length < 2) return null;
    const first = points[0].geometry.coordinates[1],
      last = points[points.length - 1].geometry.coordinates[1];
    if (first === last) return null;
    return {
      start: first < last ? region.start : region.end,
      end: first < last ? region.end : region.start,
      south: Math.min(first, last),
      label: "",
    };
  });
  if (!sections.length || sections.some((s) => s === null)) return [];
  return sections
    .filter((s) => s !== null)
    .sort((a, b) => a.south - b.south)
    .map((s, i) => ({ start: s.start, end: s.end, label: `Section ${i + 1}` }));
}
