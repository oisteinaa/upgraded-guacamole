use crate::{
    Result,
    args::{Args, Format, Mode},
    fail,
    input::{Archive, Receiver},
    navigation::{self, Shot},
};
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};
#[derive(Clone, Debug, Serialize)]
pub struct Piece {
    pub file: usize,
    pub row: usize,
    pub count: usize,
}
#[derive(Clone, Debug, Serialize)]
pub struct Block {
    pub start: i64,
    pub config: usize,
    pub samples: usize,
    pub pieces: Vec<Piece>,
    pub shot: Option<Shot>,
}
#[derive(Debug, Serialize)]
pub struct Output {
    pub name: String,
    pub blocks: Vec<Block>,
    pub segy_bytes: u64,
    pub segd_bytes: u64,
}
#[derive(Debug, Serialize)]
pub struct Plan {
    pub outputs: Vec<Output>,
    pub warnings: Vec<String>,
    pub skipped_shots: Vec<serde_json::Value>,
    pub selected_channels: Vec<u32>,
}
struct Run {
    start: i64,
    config: usize,
    samples: usize,
    pieces: Vec<Piece>,
}
fn ceildiv(a: i64, b: i64) -> i64 {
    a.div_euclid(b) + i64::from(a.rem_euclid(b) != 0)
}
pub fn count(seconds: f64, dt: i64) -> Result<usize> {
    let n = (seconds * 1e6 / dt as f64).round();
    if !seconds.is_finite() || seconds <= 0. || n < 1. || n > u32::MAX as f64 {
        return fail("Duration must be positive and representable as at least one sample");
    };
    Ok(n as usize)
}
fn extract(run: &Run, offset: usize, n: usize, dt: i64, shot: Option<Shot>) -> Block {
    let mut pieces = Vec::new();
    let mut skip = offset;
    let mut left = n;
    for p in &run.pieces {
        if skip >= p.count {
            skip -= p.count;
            continue;
        }
        let count = left.min(p.count - skip);
        pieces.push(Piece {
            file: p.file,
            row: p.row + skip,
            count,
        });
        left -= count;
        skip = 0;
        if left == 0 {
            break;
        }
    }
    Block {
        start: run.start + offset as i64 * dt,
        config: run.config,
        samples: n,
        pieces,
        shot,
    }
}
pub fn build(a: &Archive, args: &Args, receivers: &BTreeMap<u32, Receiver>) -> Result<Plan> {
    if args.lid == 0 || args.lid > 0x7fffff {
        return fail("lid must be in 1..8388607");
    }
    if args.output.as_os_str().is_empty() {
        return fail("Output directory must not be empty");
    }
    let duration = match args.mode {
        Mode::Continuous => {
            if !args.p111.is_empty() || args.duration.is_some() {
                return fail("--p111 and --duration require --mode shot");
            };
            args.trace_length
        }
        Mode::Shot => {
            if args.p111.is_empty() || args.p111_crs.is_none() {
                return fail("Shot mode requires --p111 and --p111-crs");
            };
            args.duration.ok_or("Shot mode requires --duration")?
        }
    };
    if !args.offset.is_finite() || args.offset.abs() > 2147. {
        return fail("Shot offset must be finite and within +/-2147 seconds");
    }
    let lo = args
        .start
        .as_deref()
        .map(navigation::utc)
        .transpose()?
        .unwrap_or(0);
    let hi = args
        .end
        .as_deref()
        .map(navigation::utc)
        .transpose()?
        .unwrap_or(i64::MAX);
    if lo >= hi {
        return fail("--start must precede --end");
    }
    let mut runs: Vec<Run> = vec![];
    let mut warnings = a.warnings.clone();
    let mut selected = BTreeSet::new();
    for (i, f) in a.files.iter().enumerate() {
        let c = &a.configs[f.config];
        if args.format != Format::Segy && f.start < 315_964_800_000_000 {
            return fail("SEG-D timestamp support starts at the GPS epoch, 1980-01-06");
        }
        if !f.usable {
            continue;
        }
        let first = ceildiv(lo.saturating_sub(f.start), c.dt)
            .max(0)
            .min(f.samples as i64) as usize;
        let end = ceildiv(hi.saturating_sub(f.start), c.dt)
            .max(0)
            .min(f.samples as i64) as usize;
        if first >= end {
            continue;
        }
        for ch in &c.channels {
            if !receivers.contains_key(ch) {
                return fail(format!(
                    "No exact receiver CSV match for lid {} channel {ch}; narrow --channels or supply matching coordinates",
                    args.lid
                ));
            };
            if *ch > 0x7fffff {
                return fail("Channel identity exceeds signed 24-bit SEG-D receiver-point range");
            };
            selected.insert(*ch);
        }
        let n = count(duration, c.dt)?;
        if args.format != Format::Segd && (n > 65535 || c.dt > 65535) {
            return fail(format!(
                "SEG-Y rev 1 limit exceeded: requested {n} samples, {} us interval; reduce duration (maximum {:.6} seconds at this interval) or select SEG-D",
                c.dt,
                65535.0 * c.dt as f64 / 1e6
            ));
        }
        if args.format != Format::Segy && n as u64 * c.dt as u64 > i32::MAX as u64 {
            return fail("SEG-D block duration exceeds supported 2147-second channel-set range");
        }
        let effective = n as f64 * c.dt as f64 / 1e6;
        if (effective - duration).abs() > 1e-9 {
            let msg = format!(
                "Requested {duration}s rounds to {n} samples ({effective:.6}s) at {}us",
                c.dt
            );
            if !warnings.contains(&msg) {
                warnings.push(msg);
            }
        }
        let start = f.start + first as i64 * c.dt;
        let piece = Piece {
            file: i,
            row: first,
            count: end - first,
        };
        if let Some(last) = runs.last_mut()
            && last.config == f.config
            && (last.start + last.samples as i64 * c.dt - start).abs() <= 1
        {
            last.samples += piece.count;
            last.pieces.push(piece);
            continue;
        }
        runs.push(Run {
            start,
            config: f.config,
            samples: piece.count,
            pieces: vec![piece],
        });
    }
    let mut outputs: BTreeMap<String, Vec<Block>> = BTreeMap::new();
    let mut skipped = vec![];
    if args.mode == Mode::Continuous {
        for run in &runs {
            let dt = a.configs[run.config].dt;
            let size = count(duration, dt)?;
            let mut offset = 0;
            while offset < run.samples {
                let start = run.start + offset as i64 * dt;
                let day = start.div_euclid(86_400_000_000);
                let until_midnight = ceildiv((day + 1) * 86_400_000_000 - start, dt) as usize;
                let n = size.min(run.samples - offset).min(until_midnight);
                let name = chrono::DateTime::from_timestamp_micros(start)
                    .ok_or("Invalid date")?
                    .format("%Y%m%d")
                    .to_string();
                outputs
                    .entry(format!("{name}_lid{}", args.lid))
                    .or_default()
                    .push(extract(run, offset, n, dt, None));
                offset += n;
            }
        }
    } else {
        for p in crate::input::paths(&args.p111, false)? {
            let name = p
                .file_stem()
                .ok_or("Invalid navigation filename")?
                .to_string_lossy()
                .to_string();
            if outputs.contains_key(&name) {
                return fail("P1/11 input basenames collide; rename navigation files");
            }
            let mut blocks = vec![];
            for shot in navigation::read(&p, args.p111_crs.unwrap())? {
                if !(-8388608..=8388607).contains(&shot.line)
                    || !(-8388608..=8388607).contains(&shot.point)
                    || shot.source_depth.abs() > 2147483.
                    || shot.water_depth.abs() > 2147483.
                {
                    return fail("Source identity/depth exceeds supported header range");
                }
                let start = shot.time + (args.offset * 1e6).round() as i64;
                let mut found = None;
                for run in &runs {
                    let c = &a.configs[run.config];
                    if start < run.start || start >= run.start + run.samples as i64 * c.dt {
                        continue;
                    }
                    let offset = ceildiv(start - run.start, c.dt) as usize;
                    let n = count(duration, c.dt)?;
                    if offset + n <= run.samples {
                        if c.synchronized == Some(0) {
                            return fail(
                                "Shot alignment blocked: H5 acquisition clock explicitly unsynchronized",
                            );
                        };
                        found = Some(extract(run, offset, n, c.dt, Some(shot.clone())));
                        break;
                    }
                }
                if let Some(b) = found {
                    blocks.push(b)
                } else {
                    skipped.push(serde_json::json!({"navigation":p,"shot":shot,"reason":"Incomplete coverage or configuration boundary"}));
                }
            }
            outputs.insert(name, blocks);
        }
    }
    let mut result = vec![];
    for (name, blocks) in outputs {
        if blocks.is_empty() {
            warnings.push(format!(
                "{name}: no complete blocks; no seismic file will be created"
            ));
            continue;
        }
        if blocks.len() > 0xffffff {
            return fail("Too many SEG-D records");
        }
        let traces: u64 = blocks
            .iter()
            .map(|b| a.configs[b.config].channels.len() as u64)
            .sum();
        if traces > i32::MAX as u64 {
            return fail("Too many SEG-Y traces");
        }
        let segy_bytes = 3600
            + blocks
                .iter()
                .map(|b| a.configs[b.config].channels.len() as u64 * (240 + 4 * b.samples as u64))
                .sum::<u64>();
        let segd_bytes = 128
            + blocks
                .iter()
                .map(|b| crate::segd::record_size(b, &a.configs[b.config]))
                .sum::<u64>();
        result.push(Output {
            name,
            blocks,
            segy_bytes,
            segd_bytes,
        });
    }
    if result.is_empty() {
        return fail(format!(
            "No complete output blocks; {} shots skipped; {}",
            skipped.len(),
            warnings.join("; ")
        ));
    }
    Ok(Plan {
        outputs: result,
        warnings,
        skipped_shots: skipped,
        selected_channels: selected.into_iter().collect(),
    })
}
