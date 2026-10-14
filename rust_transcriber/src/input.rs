use crate::{Result, check_cancel, fail, h5::H5};
use serde::{Deserialize, Serialize};
use std::{
    collections::{BTreeMap, BTreeSet},
    path::{Path, PathBuf},
};

#[derive(Clone, Debug, PartialEq, Serialize)]
pub struct Config {
    pub dt: i64,
    pub scale: f64,
    pub unit: String,
    pub channels: Vec<u32>,
    pub recorded_channels: Vec<u32>,
    pub columns: Vec<usize>,
    pub synchronized: Option<i32>,
    pub acquisition: BTreeMap<String, String>,
}
#[derive(Clone, Debug, Serialize)]
pub struct FileInfo {
    pub path: PathBuf,
    pub start: i64,
    pub samples: usize,
    pub config: usize,
    pub size: u64,
    pub modified_ns: u128,
    pub usable: bool,
}
#[derive(Debug, Serialize)]
pub struct Archive {
    pub files: Vec<FileInfo>,
    pub configs: Vec<Config>,
    pub warnings: Vec<String>,
}
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Receiver {
    pub lid: u32,
    pub channel: u32,
    pub latitude: f64,
    pub longitude: f64,
}
pub fn receivers(p: &Path, lid: u32) -> Result<BTreeMap<u32, Receiver>> {
    let mut map = BTreeMap::new();
    for row in csv::Reader::from_path(p)?.deserialize() {
        let r: Receiver = row?;
        if r.lid != lid {
            continue;
        }
        if !r.latitude.is_finite()
            || !r.longitude.is_finite()
            || r.latitude.abs() > 90.
            || r.longitude.abs() > 180.
        {
            return fail("Invalid receiver coordinates");
        }
        if map.insert(r.channel, r).is_some() {
            return fail("Duplicate (lid, channel) in receiver CSV");
        }
    }
    if map.is_empty() {
        return fail("Receiver CSV has no rows for requested lid");
    };
    Ok(map)
}
pub fn ranges(s: &str) -> Result<Vec<(u32, u32)>> {
    if s == "all" {
        return Ok(vec![(0, u32::MAX)]);
    }
    let mut out = Vec::new();
    for part in s.split(',') {
        let v: Vec<_> = part.trim().split('-').collect();
        let (a, b) = match v.as_slice() {
            [a] => {
                let a = a.parse()?;
                (a, a)
            }
            [a, b] => (a.parse()?, b.parse()?),
            _ => return fail("Invalid channel range"),
        };
        if a > b {
            return fail("Reversed channel range");
        };
        out.push((a, b));
    }
    out.sort_unstable();
    let mut merged: Vec<(u32, u32)> = Vec::new();
    for (a, b) in out {
        if let Some(last) = merged.last_mut()
            && a <= last.1.saturating_add(1)
        {
            last.1 = last.1.max(b);
            continue;
        }
        merged.push((a, b));
    }
    Ok(merged)
}
pub fn paths(inputs: &[String], h5: bool) -> Result<Vec<PathBuf>> {
    fn visit(p: &Path, h5: bool, out: &mut BTreeSet<PathBuf>) -> Result<()> {
        if p.is_dir() {
            for entry in std::fs::read_dir(p)? {
                let e = entry?;
                if e.file_type()?.is_symlink() {
                    continue;
                }
                visit(&e.path(), h5, out)?
            }
        } else if p.is_file()
            && (!h5
                || matches!(
                    p.extension()
                        .and_then(|x| x.to_str())
                        .map(str::to_lowercase)
                        .as_deref(),
                    Some("h5" | "hdf5")
                ))
        {
            out.insert(p.canonicalize()?);
        }
        Ok(())
    }
    let mut out = BTreeSet::new();
    for i in inputs {
        if Path::new(i).exists() {
            visit(Path::new(i), h5, &mut out)?
        } else {
            let mut found = false;
            for p in glob::glob(i)? {
                visit(&p?, h5, &mut out)?;
                found = true
            }
            if !found {
                return fail(format!("No matches: {i}"));
            }
        }
    }
    if out.is_empty() {
        return fail("No input files selected");
    };
    Ok(out.into_iter().collect())
}
pub fn stamp(p: &Path) -> Result<(u64, u128)> {
    let m = std::fs::metadata(p)?;
    Ok((
        m.len(),
        m.modified()?
            .duration_since(std::time::UNIX_EPOCH)?
            .as_nanos(),
    ))
}
pub fn index(inputs: &[String], selection: &str) -> Result<Archive> {
    let ranges = ranges(selection)?;
    let mut a = Archive {
        files: vec![],
        configs: vec![],
        warnings: vec![],
    };
    for path in paths(inputs, true)? {
        check_cancel()?;
        let before = stamp(&path)?;
        let f = H5::open(&path)?;
        let (shape, kind) = f.info("data")?;
        if shape.len() != 2 || shape.contains(&0) || !(kind == 0 || kind == 1) {
            return fail(format!(
                "{}: expected numeric samples × channels",
                path.display()
            ));
        }
        let raw = f.integers("header/channels")?;
        if raw.len() != shape[1] {
            return fail("Channel count differs from H5 columns");
        }
        let recorded_channels = raw
            .iter()
            .map(|id| u32::try_from(*id))
            .collect::<std::result::Result<Vec<_>, _>>()?;
        let mut seen = BTreeSet::new();
        let mut cols = BTreeMap::new();
        for (col, id) in raw.into_iter().enumerate() {
            let id = u32::try_from(id)?;
            if !seen.insert(id) {
                return fail("Duplicate H5 channel ID");
            };
            if ranges.iter().any(|(lo, hi)| id >= *lo && id <= *hi) {
                cols.insert(id, col);
            }
        }
        if cols.is_empty() {
            a.warnings
                .push(format!("{}: no selected channels", path.display()));
            continue;
        }
        let dt = f.scalar("header/dt")? * 1e6;
        let start = f.scalar("header/time")? * 1e6;
        let scale = f.scalar("header/dataScale")?;
        if !dt.is_finite()
            || dt < 1.
            || (dt - dt.round()).abs() > 1e-5
            || dt > 16_777_215.
            || !start.is_finite()
            || !(0.0..=4_102_444_800_000_000.).contains(&start)
            || !scale.is_finite()
            || scale == 0.
        {
            return fail(format!(
                "{}: invalid timing/scale or interval not representable in integer microseconds",
                path.display()
            ));
        }
        let sync = f.scalar("header/timeSynchronized").ok().map(|x| x as i32);
        let mut acquisition = BTreeMap::new();
        for name in [
            "name",
            "gaugeLength",
            "instrumentSerial",
            "wavelength",
            "spatialUnwrRange",
            "sensitivities",
            "dataType",
        ] {
            let key = format!("header/{name}");
            if f.info(&key).is_ok() {
                let value = if name == "name" {
                    f.string(&key)?
                } else {
                    let v = f.scalar(&key)?;
                    if !v.is_finite() {
                        return fail("Nonfinite acquisition metadata");
                    };
                    v.to_string()
                };
                acquisition.insert(name.to_owned(), value);
            }
        }
        for name in ["roiDec", "roiStart", "roiEnd"] {
            let key = format!("demodSpec/{name}");
            if f.info(&key).is_ok() {
                acquisition.insert(key.clone(), serde_json::to_string(&f.integers(&key)?)?);
            }
        }
        let cfg = Config {
            recorded_channels,
            acquisition,
            dt: dt.round() as i64,
            scale,
            unit: f.string("header/unit")?,
            channels: cols.keys().copied().collect(),
            columns: cols.values().copied().collect(),
            synchronized: sync,
        };
        let usable = f
            .integers("header/missingSamples")
            .is_ok_and(|v| v.is_empty());
        if !usable {
            a.warnings.push(format!(
                "{}: excluded entire file (missing/unknown sample-quality metadata)",
                path.display()
            ))
        }
        if sync.is_none() || sync == Some(0) {
            a.warnings.push(format!(
                "{}: acquisition clock unknown or unsynchronized",
                path.display()
            ))
        }
        let config = if let Some(i) = a.configs.iter().position(|c| c == &cfg) {
            i
        } else {
            a.configs.push(cfg);
            a.configs.len() - 1
        };
        if before != stamp(&path)? {
            return fail("Input changed during indexing");
        }
        a.files.push(FileInfo {
            path,
            start: start.round() as i64,
            samples: shape[0],
            config,
            size: before.0,
            modified_ns: before.1,
            usable,
        });
    }
    a.files.sort_by_key(|f| f.start);
    for pair in a.files.windows(2) {
        let end = pair[0].start + pair[0].samples as i64 * a.configs[pair[0].config].dt;
        if pair[1].start < end - 1 {
            return fail(format!(
                "Overlapping inputs: {} and {}",
                pair[0].path.display(),
                pair[1].path.display()
            ));
        }
        if pair[1].start > end + 1 {
            a.warnings.push(format!(
                "Time gap: {end}..{} (Unix microseconds)",
                pair[1].start
            ))
        }
    }
    if a.files.is_empty() {
        return fail("No selected recorded channels");
    };
    Ok(a)
}
