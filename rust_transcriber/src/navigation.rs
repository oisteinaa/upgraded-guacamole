use crate::{Result, args::Crs, fail};
use chrono::{DateTime, NaiveDate};
use serde::Serialize;
use std::{
    collections::BTreeSet,
    io::Write,
    path::Path,
    process::{Command, Stdio},
};
#[derive(Clone, Debug, Serialize)]
pub struct Shot {
    pub line: i32,
    pub point: i32,
    pub index: u8,
    pub source_id: u8,
    pub time: i64,
    pub longitude: f64,
    pub latitude: f64,
    pub source_depth: f64,
    pub water_depth: f64,
}
pub fn utc(s: &str) -> Result<i64> {
    Ok(DateTime::parse_from_rfc3339(s)?.timestamp_micros())
}
pub fn ptime(s: &str) -> Result<i64> {
    let c: Vec<_> = s.split(':').collect();
    let (date, h) = match c.len() {
        6 => (
            NaiveDate::from_ymd_opt(c[0].parse()?, c[1].parse()?, c[2].parse()?),
            3,
        ),
        5 => (NaiveDate::from_yo_opt(c[0].parse()?, c[1].parse()?), 2),
        _ => {
            return fail(
                "Unsupported P1/11 timestamp; expected year:month:day:hour:minute:second.fraction or year:day-of-year:hour:minute:second.fraction",
            );
        }
    };
    let (sec, frac) = c[h + 2].split_once('.').unwrap_or((c[h + 2], ""));
    if frac.len() > 6 || !frac.bytes().all(|b| b.is_ascii_digit()) {
        return fail("P1/11 fractional time must have at most six decimal digits");
    }
    let us = if frac.is_empty() {
        0
    } else {
        frac.parse::<u32>()? * 10u32.pow(6 - frac.len() as u32)
    };
    Ok(date
        .ok_or("Invalid P1/11 date")?
        .and_hms_micro_opt(c[h].parse()?, c[h + 1].parse()?, sec.parse()?, us)
        .ok_or("Invalid P1/11 time (leap-second samples are not supported)")?
        .and_utc()
        .timestamp_micros())
}
pub fn read(p: &Path, crs: Crs) -> Result<Vec<Shot>> {
    let mut shots = vec![];
    let mut seen = BTreeSet::new();
    let mut header = false;
    let mut reader = csv::ReaderBuilder::new()
        .has_headers(false)
        .flexible(true)
        .trim(csv::Trim::All)
        .from_path(p)?;
    for (row, record) in reader.records().enumerate() {
        let r = record?;
        let first = r.get(0).unwrap_or("");
        if first.starts_with('H') || first.starts_with("OGP") {
            header = true;
            continue;
        }
        if first.is_empty() || first.starts_with('#') {
            continue;
        }
        if !first.starts_with('S') {
            return fail(format!(
                "{}:{}: unsupported P1/11 record {}",
                p.display(),
                row + 1,
                first
            ));
        }
        if !header || r.len() < 27 {
            return fail(format!(
                "{}:{}: expected header and legacy 27-column S record",
                p.display(),
                row + 1
            ));
        }
        let num = |i: usize| -> Result<f64> {
            let x = r[i].parse::<f64>()?;
            if !x.is_finite() {
                return fail("Nonfinite source coordinate/depth");
            };
            Ok(x)
        };
        let shot = Shot {
            line: r[3].parse()?,
            point: r[5].parse()?,
            index: r[6].parse()?,
            source_id: r[9]
                .chars()
                .last()
                .ok_or("Missing source ID")?
                .to_digit(10)
                .ok_or("Unsupported source ID")? as u8,
            time: ptime(&r[7])?,
            longitude: num(12)?,
            latitude: num(13)?,
            source_depth: num(14)?,
            water_depth: num(26)?,
        };
        if !seen.insert((shot.line, shot.point, shot.index, shot.source_id, shot.time)) {
            return fail("Duplicate P1/11 shot");
        };
        shots.push(shot);
    }
    if shots.is_empty() {
        return fail(format!("{}: no supported shots", p.display()));
    }
    if crs == Crs::Utm33n {
        let mut child = Command::new("cs2cs")
            .args(["-f", "%.10f", "EPSG:32633", "EPSG:4326"])
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| {
                format!("UTM source coordinates require PROJ cs2cs (install proj-bin): {e}")
            })?;
        let mut stdin = child.stdin.take().unwrap();
        let text = shots
            .iter()
            .map(|s| format!("{} {}\n", s.longitude, s.latitude))
            .collect::<String>();
        let writer = std::thread::spawn(move || stdin.write_all(text.as_bytes()));
        let output = child.wait_with_output()?;
        writer
            .join()
            .map_err(|_| "Coordinate input worker failed")??;
        if !output.status.success() {
            return fail(format!(
                "PROJ conversion failed: {}",
                String::from_utf8_lossy(&output.stderr)
            ));
        }
        let text = String::from_utf8(output.stdout)?;
        let rows: Vec<_> = text.lines().collect();
        if rows.len() != shots.len() {
            return fail("PROJ returned wrong coordinate count");
        }
        for (s, row) in shots.iter_mut().zip(rows) {
            let v: Vec<_> = row.split_whitespace().collect();
            if v.len() < 2 {
                return fail("Invalid PROJ output");
            };
            s.latitude = v[0].parse()?;
            s.longitude = v[1].parse()?;
        }
    }
    for s in &shots {
        if !s.latitude.is_finite()
            || !s.longitude.is_finite()
            || s.latitude.abs() > 90.
            || s.longitude.abs() > 180.
        {
            return fail("Source coordinate outside WGS84 bounds; check --p111-crs");
        }
    }
    shots.sort_by_key(|s| s.time);
    Ok(shots)
}
