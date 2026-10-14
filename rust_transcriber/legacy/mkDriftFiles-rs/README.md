# mk_drift_files

Rust port of `../mkDriftFiles.py`.

```sh
cargo run -- --nodeid=<id> --to=<totime> [--from=<fromtime>] [--basedir=<dir>] [--mode=phase|freq|combined|clog]
```

Defaults match the Python tool:

- `--basedir=/raid1/VENATOR`
- `--from` is one hour before `--to`
- `--mode=phase`

Database settings are read from `PRODUCTROOT/config/settings.ini` using `db_host`,
matching `venatorItems.connect()`. These environment variables can override the
connection details:

- `VENATOR_DB_HOST`
- `VENATOR_DB_NAME`
- `VENATOR_DB_USER`
- `VENATOR_DB_PASSWORD`
