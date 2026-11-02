# Docker deployment

Requires Linux Docker Engine with Compose v2. PostgreSQL, remote capture and weather
collection remain on the host/outside Docker. Host networking preserves localhost
connections; there are no port mappings. The app listens on 8051 and its ZMQ PULL
receiver binds the configured endpoint (normally 12345). Restrict receiver access
with the existing host firewall. Do not run the old receiver concurrently.

## Configuration and build

Copy `deploy/docker/{compose,app,report-ai}.env.example` to corresponding `.env`
files. Use `id -u` and `id -g` for the application account in compose.env.
Set an absolute existing DAS_STATE_DIR containing the existing `.local` data;
it must be writable by that account. Grant archive read/traverse permissions to
that account. If access requires supplementary groups, add their numeric IDs
with Compose `group_add` to both services.

Transfer existing production app settings into app.env (Compose env-file syntax,
no shell commands or `export`). Keep credentials mode 600. Preserve verified live
lid/time/mapping flags and review-write policy. Replace host-checkout paths for
state with `/app/.local/...`. Preserve the actual archive subdirectory beneath
`/raid1`, rather than broadening it unnecessarily. ZMQ notifications and indexed
recordings must reference absolute paths available under `/raid1` unchanged.
Symlink targets outside that tree require an additional matching read-only mount.
For a localhost database use TCP (`host=127.0.0.1`) with existing credentials;
Unix sockets require an explicit socket-directory mount. No database changes or
migrations run at startup. Preserve schema migrations already installed.

The AI file can contain the existing key and model setting, or remain empty for
numerical reports. Only report jobs receive these environment variables.
The state mount contains existing configuration files as well: maintain normal
host permissions. Never bake state or credentials into the image.

```bash
docker compose --env-file deploy/docker/compose.env config --quiet
docker compose --env-file deploy/docker/compose.env build
```

## Cutover when the server returns

Back up source, service units, environment files and `.local` state first. Retain
the current image before rebuilding for subsequent upgrades. Stop only the user
`sensnet-observatory.service`, then start:

```bash
docker compose --env-file deploy/docker/compose.env up -d observatory
curl --fail http://127.0.0.1:8051/api/health
curl --fail http://127.0.0.1:8051/api/overview
docker compose --env-file deploy/docker/compose.env logs --tail=100 observatory
```

Verify the dashboard, a genuine completed-file notification, HDF5 window reads,
calm baseline selection and existing report downloads. Health means API process
liveness; overview checks database/schema availability. Check database access
before allowing the remote sender to deliver notifications. The existing receiver
writes recording metadata to PostgreSQL; the archive mount itself is read-only.
Container startup never creates events or verifies labels automatically.

Stop the report timer during transition and wait for any running report job.
Install `deploy/sensnet-reports-docker.service` as the user
`~/.config/systemd/user/sensnet-reports.service`, preserving the previous unit.
Retain the existing timer (Mondays 04:00 UTC), reload the user manager and restart
the timer. The application user needs Docker access. Reports share the existing
report directory and lock; never expire preserved report evidence with recordings.
Manual invocation and AI retry:

```bash
docker compose --env-file deploy/docker/compose.env run --rm --no-deps reports
docker compose --env-file deploy/docker/compose.env run --rm --no-deps reports python -m src.Mapui.report_worker --retry-ai 2
```

Confirm state survives container recreation and SIGTERM stops both children.
Test synthetic notifications and report generation against an isolated database,
not production. On rollback stop Compose, restore the report unit, reload the
user manager, and start the previous observatory and report timer. Keep all
persistent state. No database restore is needed for this packaging change.

Docker was unavailable in the implementation workspace and the server was
offline: image build, runtime networking and production cutover require validation
on a Docker-enabled host before declaring deployment complete.
