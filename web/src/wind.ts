export interface WindStation {
  lid: number;
  name: string;
  latitude: number;
  longitude: number;
  speed: number | null;
  direction: number | null;
  source_time: string | null;
  time: string | null;
  stale: boolean;
}

export function windArrow(speed: number | null, direction: number | null) {
  if (speed === null || direction === null || !Number.isFinite(speed) ||
      !Number.isFinite(direction) || speed <= 0 || direction < 0 || direction > 360)
    return null;
  return {
    // Keep light winds legible; calm still has no arrow.
    length: 18 + 54 * Math.min(speed, 30) / 30,
    color: speed <= 8 ? "#8ee06b" : speed <= 18 ? "#ffd15c" : "#ff6b72",
    // Meteorological direction is where wind comes FROM.
    rotation: (direction + 180) % 360,
  };
}
