import { useEffect, useRef, useState, type ReactNode } from "react";

export default function MapLegend({ children, storageKey }: { children: ReactNode; storageKey: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; y: number; left: number; top: number } | null>(null);
  const [position, setPosition] = useState<{ left: number; top: number } | null>(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(storageKey) ?? "null");
      return saved && Number.isFinite(saved.left) && Number.isFinite(saved.top) ? saved : null;
    } catch { return null; }
  });
  const clamp = (left: number, top: number) => {
    const panel = ref.current!, parent = panel.parentElement!;
    return { left: Math.max(8, Math.min(left, parent.clientWidth - panel.offsetWidth - 8)),
      top: Math.max(8, Math.min(top, parent.clientHeight - panel.offsetHeight - 8)) };
  };
  useEffect(() => {
    if (position) {
      try { localStorage.setItem(storageKey, JSON.stringify(position)); } catch { /* optional persistence */ }
    }
  }, [position, storageKey]);
  useEffect(() => {
    const resize = new ResizeObserver(() => setPosition(p => p ? clamp(p.left, p.top) : p));
    resize.observe(ref.current!);
    resize.observe(ref.current!.parentElement!);
    return () => resize.disconnect();
  }, []);
  return <div ref={ref} className="map-legend" style={position ? { ...position, bottom: "auto" } : undefined}>
    <button className="legend-handle" aria-label="Move map legend" title="Drag to move; arrow keys to position; Home to reset"
      onPointerDown={e => {
        if (e.button !== 0) return;
        const panel = ref.current!;
        drag.current = { x: e.clientX, y: e.clientY, left: panel.offsetLeft, top: panel.offsetTop };
        e.currentTarget.setPointerCapture(e.pointerId);
      }}
      onPointerMove={e => {
        const start = drag.current;
        if (start) setPosition(clamp(start.left + e.clientX - start.x, start.top + e.clientY - start.y));
      }}
      onPointerUp={() => { drag.current = null; }}
      onPointerCancel={() => { drag.current = null; }}
      onLostPointerCapture={() => { drag.current = null; }}
      onKeyDown={e => {
        if (e.key === "Home") { e.preventDefault(); setPosition(null); try { localStorage.removeItem(storageKey); } catch {} return; }
        const delta: Record<string, [number, number]> = { ArrowLeft: [-10,0], ArrowRight: [10,0], ArrowUp: [0,-10], ArrowDown: [0,10] };
        if (!delta[e.key]) return;
        e.preventDefault();
        const panel = ref.current!, [x,y] = delta[e.key];
        setPosition(clamp(panel.offsetLeft + x, panel.offsetTop + y));
      }}>⠿ <span>Map legend</span></button>
    {children}
  </div>;
}
