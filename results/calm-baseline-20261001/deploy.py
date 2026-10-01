"""Checksummed dashboard deployment; restart only the observatory, roll back on failure."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tarfile
import time
import urllib.request

root = Path("/home/inst/oistein/upgraded-guacamole")
work = root / ".local/calm-deploy-20261001"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def http(path, port=8051):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=20) as r:
        return r.status, r.read()


def write(name, data):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".calm-update-tmp")
    temporary.write_bytes(data)
    if path.exists():
        temporary.chmod(path.stat().st_mode & 0o777)
    os.replace(temporary, path)


with tarfile.open(work / "package.tgz") as archive:
    manifest = json.load(archive.extractfile("manifest.json"))
    payload = {}
    for name, expected in manifest["files"].items():
        path = Path(name)
        if path.is_absolute() or ".." in path.parts:
            raise RuntimeError("Unsafe package path")
        data = archive.extractfile(name).read()
        if digest(data) != expected:
            raise RuntimeError("Checksum mismatch: " + name)
        if name.endswith(".py"):
            compile(data, name, "exec")
        payload[name] = data
for name, expected in manifest["expected"].items():
    path = root / name
    actual = digest(path.read_bytes()) if path.exists() else None
    if actual != expected:
        raise RuntimeError("Server file changed since inspection: " + name)

settings = root / ".local/map-server.env"
settings_before = settings.read_bytes()
legacy_status = http("/", 8050)[0]
before_live = json.loads(http("/api/live")[1])
baseline = json.loads(payload[".local/calm-baselines/active.json"])["id"]
original = {name: (root / name).read_bytes() if (root / name).exists() else None for name in payload}
backup = work / "rollback.tgz"
if backup.exists():
    raise RuntimeError("Rollback bundle already exists; refusing to overwrite")
with tarfile.open(backup, "w:gz") as archive:
    for name, data in original.items():
        if data is not None:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mode = (root / name).stat().st_mode & 0o777
            archive.addfile(info, io.BytesIO(data))
(work / "new-files.json").write_text(json.dumps([name for name, data in original.items() if data is None]))

try:
    for name in sorted(payload, key=lambda n: n in ("web/dist/index.html", ".local/calm-baselines/active.json")):
        write(name, payload[name])
    subprocess.run([str(root / ".venv-map/bin/python"), "-c", "import src.Mapui.api; import src.Mapui.calm; import src.Mapui.train_calm"], cwd=root, check=True)
    subprocess.run(["systemctl", "--user", "restart", "sensnet-observatory.service"], check=True)
    for attempt in range(45):
        try:
            live = json.loads(http("/api/live")[1])
            if live.get("normalization", {}).get("baseline_id") == baseline and live["status"] in ("live", "demo"):
                break
        except OSError:
            pass
        time.sleep(1)
    else:
        raise RuntimeError("Updated live publisher did not become ready")
    assert live.get("demo", False) == before_live.get("demo", False)
    assert settings.read_bytes() == settings_before
    assert http("/")[1] == payload["web/dist/index.html"]
    assert http("/api/overview")[0] == 200
    assert http("/", 8050)[0] == legacy_status
    frame = json.loads(http(f"/api/recordings/{live['recording_id']}/metrics?lid={live['lid']}")[1])
    assert frame["normalization"]["baseline_id"] == baseline
    assert frame["normalization"]["available_channels"] == 25234
    feature = next(f for f in frame["data"]["features"] if f["properties"]["calm_score"] is not None)
    channel = feature["properties"]["recording_channel"]
    signal = json.loads(http(f"/api/recordings/{live['recording_id']}/signal?channel={channel}&duration=10&channel_count=500")[1])
    column = signal["normalization"]["channels"].index(channel)
    assert abs(signal["normalization"]["scores"]["ac_rms"][0][column] - feature["properties"]["calm_score"]) < 1e-10
    report = dict(baseline_id=baseline, status=live["status"], recording_id=live["recording_id"],
                  qualified_channels=frame["normalization"]["available_channels"], settings_preserved=True,
                  legacy_http=legacy_status, page_http=200, overview_http=200,
                  map_signal_scores_match=True, rollback=str(backup), verified_at=time.time(), files=len(payload))
    (work / "verification.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
except Exception:
    for name, data in original.items():
        if data is None:
            (root / name).unlink(missing_ok=True)
        else:
            write(name, data)
    subprocess.run(["systemctl", "--user", "restart", "sensnet-observatory.service"], check=True)
    print("Deployment failed; restored previous files and restarted the previous observatory")
    raise
