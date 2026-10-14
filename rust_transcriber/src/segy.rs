//! SEG-Y rev 1, big endian IEEE float32, variable-length traces.
use crate::{
    Result,
    input::{Config, Receiver},
    plan::Block,
};
use chrono::{Datelike, Timelike};
use std::io::{Seek, SeekFrom, Write};
pub fn put<const N: usize>(b: &mut [u8], offset: usize, v: [u8; N]) {
    b[offset..offset + N].copy_from_slice(&v)
}
pub fn file_header(w: &mut impl Write, unit: &str, dt: u16, ns: u16) -> Result<()> {
    let mut text = [b' '; 3200];
    let lines = [
        "DAS TRANSCRIBER 2; SEG-Y REVISION 1; BIG ENDIAN IEEE FLOAT32".to_owned(),
        "COORDINATES: WGS84 EPSG:4326; X=LONGITUDE Y=LATITUDE".into(),
        "COORDINATE UNITS ARCSECONDS; SCALAR -1000; UTC ACQUISITION TIMES".into(),
        "VARIABLE TRACE LENGTHS/INTERVALS: READ EACH TRACE HEADER".into(),
        "CUSTOM BYTES 229-232: NATIVE CHANNEL ID, UNSIGNED BIG ENDIAN".into(),
        "CUSTOM BYTES 233-240: ACTUAL TRACE START UNIX MICROSECONDS, INT64".into(),
        "BYTES 189-192: DAS LINE ID; BYTES 193-196: SOURCE LINE ID".into(),
        "CONTINUOUS SOURCE COORDINATES/SHOT POINT ARE UNDEFINED (ZERO)".into(),
        format!("SCALED PHYSICAL SAMPLES; UNIT: {unit}"),
        "SEE ACCOMPANYING JSON FOR GAPS, SOURCE TIMES AND INPUT PROVENANCE".into(),
    ];
    for i in 0..40 {
        let line = format!(
            "C{:02} {}",
            i + 1,
            lines.get(i).map(String::as_str).unwrap_or("")
        );
        let bytes = line.as_bytes();
        let n = bytes.len().min(80);
        text[i * 80..i * 80 + n].copy_from_slice(&bytes[..n]);
    }
    w.write_all(&text)?;
    let mut b = [0u8; 400];
    put(&mut b, 16, dt.to_be_bytes());
    put(&mut b, 18, dt.to_be_bytes());
    put(&mut b, 20, ns.to_be_bytes());
    put(&mut b, 22, ns.to_be_bytes());
    put(&mut b, 24, 5u16.to_be_bytes());
    put(&mut b, 54, 1u16.to_be_bytes());
    put(&mut b, 300, 0x100u16.to_be_bytes());
    w.write_all(&b)?;
    Ok(())
}
pub fn trace_header(
    w: &mut (impl Write + Seek),
    b: &Block,
    c: &Config,
    r: &Receiver,
    record: u32,
    sequence: u32,
    within: u32,
) -> Result<u64> {
    let mut h = [0u8; 240];
    let t = chrono::DateTime::from_timestamp_micros(b.start).ok_or("Invalid timestamp")?;
    put(&mut h, 0, sequence.to_be_bytes());
    put(&mut h, 4, sequence.to_be_bytes());
    put(&mut h, 8, record.to_be_bytes());
    put(&mut h, 12, within.to_be_bytes());
    put(&mut h, 28, 1u16.to_be_bytes());
    put(&mut h, 34, 1u16.to_be_bytes());
    put(&mut h, 68, (-1000i16).to_be_bytes());
    put(&mut h, 70, (-1000i16).to_be_bytes());
    let coord = |x: f64| ((x * 3_600_000.).round() as i32).to_be_bytes();
    put(&mut h, 80, coord(r.longitude));
    put(&mut h, 84, coord(r.latitude));
    put(&mut h, 88, 2u16.to_be_bytes());
    if let Some(s) = &b.shot {
        put(&mut h, 16, s.point.to_be_bytes());
        put(&mut h, 72, coord(s.longitude));
        put(&mut h, 76, coord(s.latitude));
        put(
            &mut h,
            48,
            ((s.source_depth * 1000.).round() as i32).to_be_bytes(),
        );
        put(
            &mut h,
            60,
            ((s.water_depth * 1000.).round() as i32).to_be_bytes(),
        );
        put(&mut h, 192, s.line.to_be_bytes());
        let delay = ((b.start - s.time) as f64 / 1000.).round();
        if (-32768.0..=32767.0).contains(&delay) {
            put(&mut h, 108, (delay as i16).to_be_bytes());
        }
    }
    put(&mut h, 114, (b.samples as u16).to_be_bytes());
    put(&mut h, 116, (c.dt as u16).to_be_bytes());
    for (o, v) in [
        (156, t.year() as u16),
        (158, t.ordinal() as u16),
        (160, t.hour() as u16),
        (162, t.minute() as u16),
        (164, t.second() as u16),
        (166, 4),
    ] {
        put(&mut h, o, v.to_be_bytes());
    }
    put(&mut h, 188, r.lid.to_be_bytes());
    put(&mut h, 228, r.channel.to_be_bytes());
    put(&mut h, 232, b.start.to_be_bytes());
    w.write_all(&h)?;
    let data = w.stream_position()?;
    w.seek(SeekFrom::Current((b.samples * 4) as i64))?;
    Ok(data)
}
