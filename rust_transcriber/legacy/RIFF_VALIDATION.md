# RIFF Boundary and Cache Validation

Both `rust_transcriber` and its sibling `RustSU` checkout use the local branch
`fix/riff-boundary-cache`. Full-scale validation is required before merging
either branch. Both checkouts must be used together: the transcriber has a
local path dependency on `../RustSU`.

The transcriber was validated against RustSU commit `ae5d6b2`.

## Implemented Behavior

- Minute lookup uses breadcrumb dates and minutes, with year `2000 + year`.
- Partial hours containing complete minute blocks are supported. Indexing
  uses the smaller of the declared count and the complete blocks present.
  A cut-short final minute or bytes beyond declared blocks produce a warning;
  earlier complete minutes remain readable through both reader APIs. Partial
  payloads are not decoded, and requests into them fail. Invalid dates,
  duplicate/reversed timestamps and gaps still produce errors.
- Nearest-sample rounding can select the next minute or hour without reading
  block headers as samples. Residual remains requested minus selected time.
- Four-channel frame bounds use 12 bytes for 24-bit and 16 bytes for 32-bit.
- The reader owns file identity, buffer and minute index together. Both output
  paths keep this state independent of whether a shot is accepted or skipped.
- A failed extraction produces no partial four-channel trace. The existing
  zero-RMS skip policy, rotations and output encodings remain unchanged.
- Requests just before a late-start file's first block are rounded before
  timestamp lookup, so a nearest sample in that first block can be selected.
- Filename generation no longer emits per-call `dbg!` output.

Known limitation: unset-clock files named with a 1970 date may have breadcrumb
year `0x46` (70), which is interpreted as 2070. A request for 1970 therefore
returns `MissingMinute`; the filename does not override the breadcrumb century.
This accepted limitation is separate from truncated-tail handling.

## Automated Checks

Run from the transcriber directory:

```sh
cargo test --manifest-path ../RustSU/Cargo.toml --lib venator::riff::tests
cargo test --manifest-path ../RustSU/Cargo.toml --doc
cargo test seg
cargo check
```

The reader's 16 tests, documentation example and six caller-focused tests pass.
The two new caller regressions use temporary RIFF files and the real SEG-D
and SEG-Y data writers; they require no RabbitMQ or database services.

RustSU binaries require build metadata. For full tests or checks in fish:

```fish
env VERGEN_GIT_SHA_SHORT=(git -C ../RustSU rev-parse --short HEAD) \
    VERGEN_BUILD_DATE=(date -u +%Y-%m-%d) \
    cargo test --manifest-path ../RustSU/Cargo.toml
env VERGEN_GIT_SHA_SHORT=(git -C ../RustSU rev-parse --short HEAD) \
    VERGEN_BUILD_DATE=(date -u +%Y-%m-%d) \
    cargo check --manifest-path ../RustSU/Cargo.toml
cargo test
```

Both compile checks pass. Full tests are not green:

- Transcriber: existing `rotation::test_pitch_roll` and
  `rotation::test_vic_rotation_pitch` assertions fail, as at baseline.
- RustSU: navigation tests `test_get_samples` and `test_read_aclog` require
  absent `../asset/test.S0` and `../asset/aclog.csv`; `test_parse` fails with
  `ParseIntError`. The navigation code was not changed.
- Repository-wide `cargo fmt --check` reports existing formatting drift.
  Newly added declarations, tests and caller matches were formatted without
  reformatting unrelated code.

## Full-Scale Gate Before Merging

The candidate release executable was built successfully during implementation.

Use identical inputs and options with separately built baseline and candidate
binaries, writing to separate output directories. Preserve the baseline build
and record both repositories' revisions and local diffs. Build the candidate
with `cargo build --release --bin rust_transcriber`; an existing release binary
is not automatically updated by unit tests or `cargo check`.

Compare both SEG-D and SEG-Y outputs for representative nodes and shot sets:

- Ordinary shots, including the approximately 24-ms-before-minute case.
- Rounding thresholds at 250 Hz and 500 Hz, minute/hour transitions and
  midnight/date/year rollovers, for both 24-bit and 32-bit input.
- Late-start and early-end hours, missing minutes, unavailable next files
  and zero-RMS shots that cross an hour before being skipped.
- Stale declared block counts and cut-short final minutes: complete earlier
  blocks must remain readable; requests into the ignored tail must fail.
- Exact channel sample values, channel order, trace/header counts, output
  numbering, breadcrumb metadata, residual/skew and processing throughput.

Confirm the complete-minute binary layout against recorder-produced files.
Chunk sizes are not used to infer shortened blocks; partial-minute decoding
and arbitrary filename discovery remain outside this change.

No real-data comparison, full-scale run or throughput benchmark has been
performed. Resolve or explicitly disposition the existing test/format gates,
then obtain approval after full-scale validation before coordinating a merge
of the two repositories. Do not merge either repository independently.