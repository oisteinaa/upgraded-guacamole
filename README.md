# upgraded-guacamole

DAS cable monitoring and event detection.

Keep recordings, derived arrays, trained models, database copies, and generated
reports outside Git. Use `.local/` for local runtime data and `results/` for
analysis output; `presentations/` is also local-only. References to these folders
in the documentation describe local artifacts that are not included in a clone.
Reusable analysis tools belong in `scripts/`, with documentation in `docs/`.
Commit source code, migrations, dependency lockfiles, and configuration examples;
keep real environment settings and deployment archives local.

See [the four-class machine-learning pipeline](docs/event-ml.md) for labeling,
training, validation and quantified HDF5 window predictions.

For unlabeled archives, use [offline DAS pattern discovery](docs/event-discovery.md)
to sample recordings, inspect vibration patterns, and prepare verified labels.

The [Cable Observatory map app](docs/map-app.md) provides an interactive network
map, historical event review with classification history, and bounded HDF5 signal
inspection. Start the prepared local database/application with
`./scripts/run_map_local.sh`, then open <http://127.0.0.1:8051>.
