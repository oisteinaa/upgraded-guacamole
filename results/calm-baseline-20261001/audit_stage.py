"""Audit the first staged reference before it is deployed. No database writes."""
import hashlib
import json
import time
from pathlib import Path

from src.Mapui.calm import artifact_root, reference, normalize_frame
from src.Mapui.db import rows
from src.Mapui.metrics import metric_frame, map_metrics
from src.Mapui.signals import safe_path
from src.Mapui.stitched_signals import read_stitched_signal
from src.Mapui.train_calm import finalize_manifest, atomic_json

root = artifact_root()
m = json.loads((root / "active.json").read_text())
finalize_manifest(m)
sources = [s for c in m["configurations"].values() for s in c["sources"]]
catalog = rows("""SELECT id,relative_path,size_bytes,mtime_ns FROM das_recordings
    WHERE acquisition_epoch BETWEEN %s AND %s""", (min(s["epoch"] for s in sources)-600, max(s["epoch"] for s in sources)+1))
by_path = {r["relative_path"]: r for r in catalog}
for source in sources:
    r = by_path[source["path"]]
    stat = safe_path(source["path"]).stat()
    assert (stat.st_size, stat.st_mtime_ns) == (r["size_bytes"], r["mtime_ns"])
    source.update(recording_id=r["id"], size_bytes=r["size_bytes"], mtime_ns=r["mtime_ns"], identity_audited_after_training=True)
for c in m["configurations"].values():
    c["sha256"] = hashlib.sha256((root / c["file"]).read_bytes()).hexdigest()
atomic_json(root / (m["id"] + ".json"), m)
atomic_json(root / "active.json", m)

rec = rows("SELECT * FROM das_recordings WHERE time_verified AND mapping_verified ORDER BY acquisition_epoch DESC LIMIT 1")[0]
t = time.monotonic()
frame = metric_frame(rec, 0)
info, values = normalize_frame(rec, frame)
assert info["available_channels"] == 25234
mapped = map_metrics(rec, rec["lid"])
map_seconds = time.monotonic()-t
assert mapped["normalization"]["baseline_id"] == m["id"]
channel = next(f["properties"]["recording_channel"] for f in mapped["data"]["features"] if f["properties"]["calm_score"] is not None)
t = time.monotonic()
signal = read_stitched_signal(rec, channel, 0, 10, channel_count=500)
signal_seconds = time.monotonic()-t
column = signal["normalization"]["channels"].index(channel)
expected = next(f["properties"]["calm_score"] for f in mapped["data"]["features"] if f["properties"]["recording_channel"] == channel)
assert abs(signal["normalization"]["scores"]["ac_rms"][0][column] - expected) < 1e-10
summary = {k: m[k] for k in ("id", "training_start", "training_end", "rules")}
summary.update(sampled_frames=len(sources), exclusions=len(m["exclusions"]),
    qualified_channels=info["available_channels"], total_channels=info["total_channels"],
    map_seconds=map_seconds, signal_seconds=signal_seconds, verified_recording=rec["id"],
    configurations={key: {k: c[k] for k in ("channels", "qualified_channels", "mapping_counts", "station_reports", "sha256")} for key,c in m["configurations"].items()})
atomic_json(root / "validation-summary.json", summary)
print(json.dumps({k:v for k,v in summary.items() if k != "configurations"}, indent=2))
