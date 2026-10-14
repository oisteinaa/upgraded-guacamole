# DAS transcriber

[Word user manual](docs/DAS_Transcriber_User_Manual.docx) — installation, GUI walkthroughs,
shot and continuous timing, CLI examples, receiver mapping, and troubleshooting.

Standalone Linux Rust CLI and PyQt6 desktop launcher for the project's HDF5 DAS
recordings. Writes SEG-Y revision 1 or SEG-D revision 3.1, or both. All seismic
encoding and the supported P1/11 parser are implemented here; no RustSU,
`rust_segd_lib`, database, or RabbitMQ is needed at runtime. The old copied RIFF
implementation is retained in `legacy/` for reference and is not compiled.

## Build and launch

Install Rust (1.88 or newer), a C compiler, `pkg-config`, and HDF5 development
headers. On Debian, the native packages are `build-essential pkg-config
libhdf5-dev`. PROJ's `proj-bin` is required only for UTM source coordinates.

```sh
cargo build --release --locked --manifest-path rust_transcriber/Cargo.toml
python3 -m venv rust_transcriber/.venv
rust_transcriber/.venv/bin/python -m pip install -r rust_transcriber/requirements-gui.txt
rust_transcriber/.venv/bin/python rust_transcriber/gui.py
```

The GUI runs the CLI locally using `QProcess`. Mount remote storage first when
using server data. Add files, directories or one glob per line, select receivers
and native channel ranges, then **Check inputs** to inspect channel counts,
estimated output sizes and warnings. **Start conversion** becomes available after
a successful check. Editing settings invalidates that check. Jobs can be saved as
JSON and reloaded. Cancel sends SIGTERM and waits for temporary-file cleanup.
CLI stdout consists of one JSON event per line; exit codes are 0 (success), 1
(conversion/validation error), 2 (argument error), and 130 (cancelled).

## Receiver positions

Export the complete channel mapping from the server using a read-only transaction:

```sh
bash rust_transcriber/scripts/export_receivers.sh > receivers.csv
```

The optional first script argument overrides `inst@10.147.20.10`. Required CSV
columns are `lid,channel,latitude,longitude`; additional columns are accepted.
Coordinates must be WGS84 decimal degrees (EPSG:4326). The export also retains
`distance,gid`, though conversion does not interpret these fields. The selected
`--lid` disambiguates channel identities. No database connection is made during
conversion. Mast IDs are not channel IDs, so a mast-only CSV is unsuitable.

Every selected **recorded** channel needs an exact CSV match. No coordinate
interpolation or signal reconstruction occurs. Some server coordinates and H5
channels have different sampling phases: a full database export does not guarantee
all recorded channels can be mapped. Preflight reports the first missing match;
narrow the channel selection or provide a verified matching CSV.

## Continuous mode

```sh
rust_transcriber/target/release/rust_transcriber \
  --input '/mounted/raid1/fsi/exps/Leknse_Solbjorn_Kvitfoss_Mux_Phase/20260924/dphi' \
  --receivers-csv receivers.csv --lid 1 \
  --channels '1-130,50000-78000' --format both \
  --mode continuous --trace-length 60 --output /exports/das --dry-run
```

Remove `--dry-run` to convert. `--input` is repeatable and accepts a file, directory
(recursive), or quoted glob. Files are deduplicated by canonical path and sorted by
H5 acquisition time, not filename. Directory symlinks encountered during recursive
scans are skipped. Use a new output directory outside the input archive.

`--channels all` is the default. Ranges are inclusive **native H5 channel IDs**,
not column indexes; absent IDs inside ranges are not invented. Overlapping ranges
are merged. Traces are ordered by time block and ascending channel ID.

Continuous output is one `YYYYMMDD_lidN.sgy` / `.segd` per UTC day containing all
selected channels. The default trace length is **60 seconds**; change it with
`--trace-length SECONDS`. Durations are rounded to the nearest sample, with the
actual duration reported. For the example 2.04 ms recordings, 60 seconds becomes
29,412 samples / 60.000480 seconds. No samples are interpolated or resampled.

Traces span consecutive compatible H5 files and are shortened at gaps, UTC
midnight, acquisition-configuration changes, and selection boundaries. Configuration checks
include the full native channel grid, ROI metadata, and gauge length, even when
only a channel subset is selected. Nominal 4 m and 8 m recordings can coexist;
channel IDs are never multiplied or inferred from row positions. A sample
belongs to the day containing its acquisition timestamp; its nominal sample
interval can extend past midnight. Optional `--start` and `--end` take RFC3339
with an explicit timezone and select sample timestamps in `[start,end)`.

Missing/unknown sample-quality metadata excludes the **entire affected H5 file**
and is reported. Gaps are retained as missing timed blocks, never zero-filled.
Conflicting overlapping input files fail preflight. Contiguous timestamps tolerate
one microsecond of floating-point timestamp quantization. Source size/mtime are
checked before and after reads to detect files changing during a job.

## Shot mode

```sh
rust_transcriber/target/release/rust_transcriber \
  --input /mounted/archive --receivers-csv receivers.csv --lid 1 \
  --channels '0-128' --mode shot --p111 '/navigation/*.p111' \
  --p111-crs utm33n --duration 10 --offset -1 \
  --format both --output /exports/shots --dry-run
```

One output file per P1/11 input basename and format contains all complete shots.
Basenames must be unique. `--duration` is required; `--offset` defaults to zero
and can be negative. The first sample at or after `shot time + offset` is selected;
its actual timestamp and original shot time are retained. Incomplete windows or
windows crossing configuration changes are skipped and reported. An explicitly
unsynchronized H5 clock (`timeSynchronized=0`) blocks complete shot extraction;
unknown clock status is warned and retained in the report. Confirm the
interrogator's clock-status convention before production shot alignment.

The initial parser implements the copied program's comma-separated **legacy
P1/11 S-record layout**, not every P1/11 variant. A header record is required.
One-based column mapping:

| Column | Meaning |
| --- | --- |
| 4 | Integer source line |
| 6 | Integer shot point |
| 7 | Source point index |
| 8 | UTC shot timestamp |
| 10 | Source identifier, final decimal digit |
| 13, 14 | Source X,Y |
| 15, 27 | Source depth and water depth, metres |

Timestamps accept `YYYY:MM:DD:HH:MM:SS[.ffffff]` or
`YYYY:DDD:HH:MM:SS[.ffffff]`; fractional digits are decimal fractions, not literal
microsecond counts. Leap-second source records and unsupported layouts fail.
Source X,Y interpretation is explicitly required: `--p111-crs wgs84` means
longitude,latitude in degrees; `utm33n` means EPSG:32633 easting,northing and uses
PROJ `cs2cs` to transform to WGS84. This explicit option defines how the legacy
columns are read; the parser does not implement general P1/11 CRS record routing.
Validate a representative navigation file before production use.

## Formats and reports

Both writers use big-endian IEEE float32 values calculated as
`H5 data * header/dataScale`; the H5 physical unit is retained in the JSON report.
No filtering, rotation, strain conversion, or clock correction is applied.
Nonfinite or float32-overflowing values fail conversion.

SEG-Y has a 3200-byte ASCII textual header, 400-byte binary header, and 240-byte
trace headers. The fixed-length flag is zero; readers must respect each trace's
sample count and interval. Binary counts describe the first trace. Rev 1 limits
are enforced: up to 65,535 samples per trace and 65,535 microseconds per sample.
Requested durations exceeding those limits fail preflight even if coverage is
shorter. Shorten the duration or select SEG-D. Some readers, including segyio,
only handle fixed-length files; use a reader supporting variable-length rev 1
traces for files containing shorter boundary traces.

SEG-Y field conventions (one-based bytes):

| Field | Encoding |
| --- | --- |
| 73–88 | Source/receiver X,Y; arcseconds with coordinate scalar -1000 |
| 157–168 | Actual trace start UTC calendar fields; time basis code 4 |
| 189–192 | DAS line ID |
| 193–196 | Source line ID, zero for continuous mode |
| 229–232 | Custom native channel ID, unsigned big endian |
| 233–240 | Custom actual trace start, signed Unix microseconds |

Original shot identity/time and precise offset are retained in JSON; standard
millisecond delay is written when representable. Source coordinates/shot point
are zero/undefined in continuous mode. Depth fields use metre units and scalar
-1000; receiver elevations are not invented.

SEG-D includes its 128-byte storage-unit label and multiple records. Each record
has the three required general headers, CRS blocks, a 96-byte channel-set
descriptor, and one trace per selected channel. Each trace has extension 1,
a timestamp, and three position blocks. Shot records also include source identity,
source time and position. Receiver CRS is EPSG:4326, identified using the supported
SEG-D 3.0 EPSG reference stanza. Position uncertainties are unknown, not zero.
Sample format is 8058, descale factor 1. The physical-unit code is unknown because
DAS phase-rate-per-distance has no matching code in this subset; channel-set text
and JSON carry its actual unit. SEG-D timestamps use GPS microseconds from
1980-01-06 (earlier dates are rejected) with a leap-second table through 2017-01-01. Update that table for any
future announced leap second. Records crossing a leap-second insertion are not
supported by this POSIX-time input profile. SEG-D block length is limited to the
supported normal-record range (approximately 2147 seconds).

Each seismic file has an adjacent `.json` with job settings, file size/mtime
provenance, selected receiver coordinates, configurations, block-to-input sample
mapping, gaps and skipped shots. The CLI refuses existing outputs or `.partial`
files. It writes temporary files, syncs them, and publishes without replacing an
existing file. Cancellation/errors remove the active temporary files; completed
outputs from earlier in the job remain. Power loss/SIGKILL can leave `.partial`
files for manual inspection. Reports and seismic files are individually atomic,
not a filesystem-wide transaction.

## Validation

```sh
rust_transcriber/.venv/bin/python -m pip install -r rust_transcriber/requirements-test.txt
cargo build --locked --manifest-path rust_transcriber/Cargo.toml
QT_QPA_PLATFORM=offscreen rust_transcriber/.venv/bin/python -m unittest discover -s rust_transcriber/tests -v
cargo clippy --locked --manifest-path rust_transcriber/Cargo.toml -- -D warnings
```

The tests independently decode headers and samples, exercise both formats,
multifile stitching, midnight, gaps, source coordinates, format limits, cancellation,
and GUI process handling. SEG-Y also has a segyio interoperability check.
SEG-D is validated against the standard's byte layout with an independent decoder;
validation in the intended downstream SEG-D application is still required.

References: [SEG-Y revision 1](https://seg.org/wp-content/uploads/2025/11/seg_y_rev1.pdf),
[SEG-D revision 3.1](https://seg.org/wp-content/uploads/2025/11/seg_d_rev3_1-oct2015.pdf).

## Demonstration deployment

`bash rust_transcriber/scripts/deploy.sh` builds a locked release and installs the
standalone package at `/home/inst/oistein/upgraded-guacamole/rust_transcriber`.
It retains release packages and prior installations under
`.local/transcriber-releases/<UTC timestamp>/`. This tool is launched on demand;
it does not require a service restart. For rollback, move the current standalone
directory aside and restore the selected release's `previous` directory (or its
`package` copy). No observatory configuration or database state is changed.
