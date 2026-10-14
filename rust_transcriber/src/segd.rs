//! SEG-D 3.1 byte-stream storage unit, demultiplexed IEEE 8058.
use crate::{
    Result,
    input::{Config, Receiver},
    plan::Block,
    segy::put,
};
use chrono::{Datelike, Timelike};
use std::io::{Seek, SeekFrom, Write};
const CRS: &str = "((SEG: Location Data EPSG Reference ver 3.0))\nLocation Data Stanza ID = 1\nCRS code = 4326\nCRS name = WGS 84\n";
fn crs_blocks() -> usize {
    CRS.len().div_ceil(31)
}
fn u24(b: &mut [u8], o: usize, v: u32) {
    b[o..o + 3].copy_from_slice(&v.to_be_bytes()[1..]);
}
fn bcd(v: u32) -> u8 {
    ((v / 10) << 4 | (v % 10)) as u8
}
/// GPS microseconds since 1980-01-06. Leap table through 2017-01-01.
pub fn gps(t: i64) -> i64 {
    const LEAPS: [i64; 18] = [
        362793600, 394329600, 425865600, 489024000, 567993600, 631152000, 662688000, 709948800,
        741484800, 773020800, 820454400, 867715200, 915148800, 1136073600, 1230768000, 1341100800,
        1435708800, 1483228800,
    ];
    t - 315_964_800_000_000
        + LEAPS.iter().filter(|s| t >= **s * 1_000_000).count() as i64 * 1_000_000
}
fn header_size(b: &Block) -> u64 {
    ((3 + crs_blocks() + if b.shot.is_some() { 5 } else { 0 }) * 32 + 96) as u64
}
pub fn record_size(b: &Block, c: &Config) -> u64 {
    header_size(b) + c.channels.len() as u64 * (20 + 5 * 32 + b.samples as u64 * 4)
}
pub fn file_header(w: &mut impl Write) -> Result<()> {
    let mut label = [b' '; 128];
    label[3] = b'1';
    label[4..9].copy_from_slice(b"SD3.1");
    label[9..15].copy_from_slice(b"RECORD");
    label[15..19].copy_from_slice(b"B2  ");
    label[28] = b'1';
    label[39..50].copy_from_slice(
        chrono::Utc::now()
            .format("%d-%b-%Y")
            .to_string()
            .to_uppercase()
            .as_bytes(),
    );
    let serial = format!(
        "{:012}",
        chrono::Utc::now().timestamp().rem_euclid(1_000_000_000_000)
    );
    label[50..62].copy_from_slice(serial.as_bytes());
    label[80..95].copy_from_slice(b"DAS TRANSCRIBER");
    label[127] = b'0';
    w.write_all(&label)?;
    Ok(())
}
fn position(w: &mut impl Write, t: i64, lat: f64, lon: f64) -> Result<()> {
    let mut h = [0u8; 96];
    put(&mut h, 0, gps(t).to_be_bytes());
    put(&mut h, 20, f32::INFINITY.to_be_bytes());
    put(&mut h, 24, f32::INFINITY.to_be_bytes());
    put(&mut h, 28, u16::MAX.to_be_bytes());
    h[30] = 15;
    h[31] = 0x50;
    put(&mut h, 32, lat.to_be_bytes());
    put(&mut h, 40, lon.to_be_bytes());
    put(&mut h, 48, f64::INFINITY.to_be_bytes());
    put(&mut h, 56, 1u16.to_be_bytes());
    h[58] = 1;
    h[59] = 2;
    h[63] = 0x51;
    for o in [64, 72, 80] {
        put(&mut h, o, f64::INFINITY.to_be_bytes());
    }
    h[95] = 0x52;
    w.write_all(&h)?;
    Ok(())
}
pub fn record_header(w: &mut impl Write, b: &Block, c: &Config, id: u32) -> Result<()> {
    let t = chrono::DateTime::from_timestamp_micros(b.start).ok_or("Invalid timestamp")?;
    let extra = 2 + crs_blocks() + if b.shot.is_some() { 5 } else { 0 };
    let mut h = [0u8; 96];
    h[0] = 255;
    h[1] = 255;
    h[2] = 0x80;
    h[3] = 0x58;
    h[10] = bcd((t.year() % 100) as u32);
    h[11] = ((extra.min(15) as u8) << 4) | (t.ordinal() / 100) as u8;
    h[12] = bcd(t.ordinal() % 100);
    h[13] = bcd(t.hour());
    h[14] = bcd(t.minute());
    h[15] = bcd(t.second());
    h[22] = 255;
    h[25] = 0x8f;
    h[26] = 255;
    h[27] = 1;
    h[28] = 1; // One channel set.
    u24(&mut h, 32, id);
    h[42] = 3;
    h[43] = 1;
    put(&mut h, 48, ((b.samples as i64 * c.dt) as u32).to_be_bytes());
    if extra >= 15 {
        put(&mut h, 54, (extra as u16).to_be_bytes());
    }
    u24(&mut h, 56, c.dt as u32);
    h[63] = 2;
    put(&mut h, 64, gps(b.start).to_be_bytes());
    put(&mut h, 72, record_size(b, c).to_be_bytes());
    put(&mut h, 80, record_size(b, c).to_be_bytes());
    put(&mut h, 88, (header_size(b) as u32).to_be_bytes());
    h[95] = 3;
    w.write_all(&h)?;
    for chunk in CRS.as_bytes().chunks(31) {
        let mut h = [b' '; 32];
        h[..chunk.len()].copy_from_slice(chunk);
        h[31] = 0x55;
        w.write_all(&h)?;
    }
    if let Some(s) = &b.shot {
        let mut h = [0u8; 32];
        u24(&mut h, 0, id);
        u24(&mut h, 3, s.line as u32);
        u24(&mut h, 8, s.point as u32);
        h[13] = s.index;
        h[18] = s.source_id;
        h[22] = 1;
        h[23] = 0x80;
        h[25] = 0x80;
        h[29] = 0x80;
        h[31] = 0x1f;
        w.write_all(&h)?;
        let mut h = [b' '; 32];
        put(&mut h, 0, gps(s.time).to_be_bytes());
        h[8] = 0;
        h[9] = s.source_id;
        h[10] = 0;
        h[31] = 0x20;
        w.write_all(&h)?;
        position(w, s.time, s.latitude, s.longitude)?;
    }
    let mut h = [0u8; 96];
    h[0] = 1;
    put(&mut h, 1, 1u16.to_be_bytes());
    h[3] = 0x10;
    // TF and TE must be zero when trace Timestamp Headers carry sample starts.
    put(&mut h, 12, (b.samples as u32).to_be_bytes());
    put(&mut h, 16, 1f32.to_be_bytes());
    u24(&mut h, 20, c.channels.len() as u32);
    u24(&mut h, 23, c.dt as u32);
    h[27] = 5;
    h[28] = 3; // Fixed gain; physical samples already have dataScale applied.
    h[29] = 1;
    h[31] = 0x30;
    h[63] = 0x31;
    h[68..95].fill(b' ');
    let description = format!("DAS {}", c.unit);
    let bytes = description.as_bytes();
    let len = bytes.len().min(27);
    h[68..68 + len].copy_from_slice(&bytes[..len]);
    h[95] = 0x32;
    w.write_all(&h)?;
    Ok(())
}
pub fn trace_header(
    w: &mut (impl Write + Seek),
    b: &Block,
    r: &Receiver,
    record: u32,
    within: u32,
) -> Result<u64> {
    let mut h = [0u8; 52];
    h[0] = 255;
    h[1] = 255;
    h[2] = 1;
    h[3] = 1;
    if within <= 9999 {
        h[4] = bcd(within / 100);
        h[5] = bcd(within % 100)
    } else {
        h[4] = 255;
        h[5] = 255;
    }
    h[9] = 5;
    u24(&mut h, 17, record);
    u24(&mut h, 20, r.lid);
    u24(&mut h, 23, r.channel);
    h[26] = 1;
    u24(&mut h, 41, within);
    put(&mut h, 44, (b.samples as u32).to_be_bytes());
    h[51] = 0x40;
    w.write_all(&h)?;
    let mut ts = [0u8; 32];
    put(&mut ts, 0, gps(b.start).to_be_bytes());
    ts[31] = 0x42;
    w.write_all(&ts)?;
    position(w, b.start, r.latitude, r.longitude)?;
    let data = w.stream_position()?;
    w.seek(SeekFrom::Current(b.samples as i64 * 4))?;
    Ok(data)
}
