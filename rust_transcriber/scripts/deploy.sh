#!/usr/bin/env bash
# Deploy only the standalone transcriber. Does not touch observatory services/settings.
set -euo pipefail
base_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
release_id=$(date -u +%Y%m%dT%H%M%SZ)
remote_root=/home/inst/oistein/upgraded-guacamole
cargo build --release --locked --manifest-path "$base_dir/Cargo.toml"
# Known-good releases and any prior installation remain available for rollback.
ssh inst@10.147.20.10 "mkdir -p '$remote_root/.local/transcriber-releases/$release_id/package'"
tar --exclude=__pycache__ -C "$base_dir" -czf - Cargo.toml Cargo.lock build.rs src gui.py README.md requirements-gui.txt requirements-test.txt scripts tests legacy target/release/rust_transcriber |
    ssh inst@10.147.20.10 "tar -xzf - -C '$remote_root/.local/transcriber-releases/$release_id/package'"
ssh inst@10.147.20.10 "set -eu
stage='$remote_root/.local/transcriber-releases/$release_id'
\"\$stage/package/target/release/rust_transcriber\" --version
cp -a \"\$stage/package\" \"\$stage/install\"
if test -e '$remote_root/rust_transcriber'; then
    mv '$remote_root/rust_transcriber' \"\$stage/previous\"
fi
if ! mv \"\$stage/install\" '$remote_root/rust_transcriber'; then
    if test -e \"\$stage/previous\"; then mv \"\$stage/previous\" '$remote_root/rust_transcriber'; fi
    exit 1
fi
\"$remote_root/rust_transcriber/target/release/rust_transcriber\" --version
printf '%s\\n' \"\$stage\"
"
printf 'Deployment release: %s/.local/transcriber-releases/%s\n' "$remote_root" "$release_id"
