//! This Rust program is a transcriber that processes navigation files and generates SEGY or SEGD files based on the provided arguments.
//!
//! # Modules
//! - `segy`: Contains functions to create SEGY files.
//! - `args`: Handles command-line argument parsing.
//! - `rabbit`: Module for RabbitMQ integration (not used in this snippet).
//! - `segd`: Contains functions to create SEGD files.
//!
//! # External Crates
//! - `ebcdic`: External crate for EBCDIC encoding.
//! - `venator`: External crate for navigation processing.
//!
//! # Functions
//! - `touch`: Creates a file if it does not exist.
//! - `main`: Entry point of the program. Parses arguments, processes navigation files, and generates SEGY or SEGD files.
//!
//! # Tests
//! - `test_samples_moved`: Unit test to verify the calculation of samples moved based on drift and time interval.
//!
//! # Usage
//! The program expects command-line arguments to specify the navigation format, SEGY/SEGD file format, and other parameters.
//! It reads navigation files matching the specified pattern, processes them, and generates the corresponding SEGY or SEGD files.
//!
//! # Example
//! ```sh
//! cargo run -- --nav_format Sbs --segy_file_format SEGY --ssd /path/to/ssd --nodeid node123
//! ```
//!
//! This command will process all `.sbs` files in the specified SSD path and generate SEGY files.
//!
extern crate ebcdic;
extern crate seismic_utils;

use args::{Args, NavFormat, SegyFileFormat};
use clap::Parser;
use glob::glob;
pub use seismic_utils::su;
use seismic_utils::venator::navigation::{self, Navigation};
use std::path::{Path, PathBuf};
use std::{fs::OpenOptions, io};

pub mod args;
pub mod postgres;
pub mod rabbit;
pub mod rotation;
pub mod segd;
pub mod segy;

fn read_shot_samples(
    reader: &mut seismic_utils::venator::riff::RiffReader,
    time: chrono::DateTime<chrono::Utc>,
    num_samples: u32,
) -> Result<Option<seismic_utils::venator::riff::Riff>, seismic_utils::venator::riff::RiffReadError>
{
    let samples = reader.read_samples(time, num_samples)?;
    let breadcrumb = &samples.breadcrumb;
    if breadcrumb.prms == 0.0
        && breadcrumb.xrms == 0.0
        && breadcrumb.yrms == 0.0
        && breadcrumb.zrms == 0.0
    {
        Ok(None)
    } else {
        Ok(Some(samples))
    }
}

fn touch(path: &Path) -> io::Result<()> {
    match OpenOptions::new()
        .create(true)
        .truncate(false)
        .write(true)
        .open(path)
    {
        Ok(_) => Ok(()),
        Err(e) => Err(e),
    }
}

fn main() -> io::Result<()> {
    let args = Args::parse();

    let mut pattern = "*.csv";
    if args.nav_format == NavFormat::Sbs {
        pattern = "*.sbs"
    } else if args.nav_format == NavFormat::Spsc {
        pattern = "*.S01"
    } else if args.nav_format == NavFormat::P111 {
        pattern = "*.p111"
    } else if args.nav_format == NavFormat::Aclog {
        pattern = "*.csv"
    }

    let shotfiles =
        glob(&format!("{}/{}", args.ssd, pattern)).expect("Failed to read nav file pattern");

    // dbg!(&shotfiles, count);
    touch(Path::new(&format!(
        "/venatorproc/VENATOR/LOGS/TRANSCRIBER/{}.log",
        args.nodeid
    )))
    .unwrap_or_else(|why| eprintln!("! {:?}", why.kind()));

    for shotfile in shotfiles {
        let start_time = std::time::Instant::now();
        let mut seg_result: (PathBuf, i32, u64, u16) = (PathBuf::new(), 0, 0, 0);

        match shotfile {
            Ok(shotfile) => {
                let shot_file_name = shotfile.as_path().to_str().unwrap();
                let format = match args.nav_format {
                    NavFormat::Pxgeo => navigation::NavFormat::PxGeo,
                    NavFormat::Spsc => navigation::NavFormat::Sps,
                    NavFormat::Sbs => navigation::NavFormat::SbsSae,
                    NavFormat::P111 => navigation::NavFormat::P1_11,
                    NavFormat::Aclog => navigation::NavFormat::Aclog,
                };
                let nav = Navigation::new(Path::new(&shot_file_name), format, args.navstart, args.navend);
                // dbg!(&nav);
                if args.segy_file_format == SegyFileFormat::SEGY {
                    seg_result = segy::make_segy_file(&args, &nav, shot_file_name);
                } else if args.segy_file_format == SegyFileFormat::SEGD {
                    seg_result = segd::make_segd_file(&args, &nav, shot_file_name);
                }

                let insert_query = format!(
                    "INSERT INTO transcribe_qc \
                        (node_id, filename, reciverpoint, reasting, rnorthing, rwdepth, \
                        firstsp, lastsp, shots, \
                        filesize, traces, dt, ns, toffset, speed, processtime, processhost) VALUES \
                        ({}, '{}', {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, '{}');",
                    args.nodeid,
                    seg_result.0.display(),
                    args.rstation,
                    args.east,
                    args.north,
                    args.depth,
                    &nav.shots().first().unwrap().ep,
                    &nav.shots().last().unwrap().ep,
                    seg_result.1,
                    seg_result.2,
                    seg_result.1 * 4,
                    seg_result.3,
                    args.ns,
                    args.toffset,
                    (seg_result.1 * 4) as f64 / start_time.elapsed().as_secs_f64(),
                    start_time.elapsed().as_secs_f64(),
                    hostname::get()
                        .unwrap_or_default()
                        .to_string_lossy()

                );
                
                let job_query = format!(
                    "UPDATE transcribe_jobs SET status = 0 WHERE id = {};",
                    args.dbid
                );
                dbg!(&job_query);
                let _ = postgres::connect_and_query(
                    "host=localhost user=venatordms password=obs dbname=venatordb",
                    &job_query,
                );
                let _ = postgres::connect_and_query(
                    "host=localhost user=venatordms password=obs dbname=venatordb",
                    &insert_query,
                );
            }
            Err(e) => eprint!("{:?}", e),
        }
    }
    Ok(())
}

#[test]
fn test_samples_moved() {
    let mut drift = 2102;
    let dt = 1.0 / 500 as f64;
    let mut samples_moved = (drift as f64 / dt / 1e6).round() as i16;

    dbg!(drift, dt, samples_moved, drift as f64 / dt / 1e6);
    assert_eq!(samples_moved, 1_i16);

    drift = -2102;
    samples_moved = (drift as f64 / dt / 1e6).round() as i16;
    assert_eq!(samples_moved, -1_i16);
}

#[cfg(test)]
mod riff_tests {
    use super::read_shot_samples;
    use chrono::{DateTime, Datelike, TimeDelta, TimeZone, Timelike, Utc};
    use seismic_utils::venator::riff::{self, Riff};
    use std::{
        fs,
        io::{BufWriter, Write},
        sync::atomic::{AtomicUsize, Ordering},
    };

    struct TestDirectory(std::path::PathBuf);

    impl TestDirectory {
        fn new() -> Self {
            static SEQUENCE: AtomicUsize = AtomicUsize::new(0);
            let path = std::env::temp_dir().join(format!(
                "transcriber-riff-{}-{}",
                std::process::id(),
                SEQUENCE.fetch_add(1, Ordering::Relaxed)
            ));
            fs::create_dir(&path).unwrap();
            Self(path)
        }

        fn save(&self, time: DateTime<Utc>, bytes: &[u8]) {
            let path = self.0.join(riff::get_riff_fn(time, 11115));
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            fs::write(path, bytes).unwrap();
        }
    }

    impl Drop for TestDirectory {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    fn fixture(bits: u16, minutes: &[(DateTime<Utc>, i32, bool)]) -> Vec<u8> {
        let frame_bytes = bits / 8 * 4;
        let mut bytes = vec![0; 92];
        bytes[..4].copy_from_slice(b"RIFF");
        bytes[8..12].copy_from_slice(b"WAVE");
        bytes[28..32].copy_from_slice(b"fmt ");
        bytes[32..36].copy_from_slice(&56_u32.to_le_bytes());
        bytes[36..38].copy_from_slice(&1_u16.to_le_bytes());
        bytes[38..40].copy_from_slice(&4_u16.to_le_bytes());
        bytes[40..42].copy_from_slice(&1_u16.to_le_bytes());
        bytes[42..44].copy_from_slice(&frame_bytes.to_le_bytes());
        bytes[44..46].copy_from_slice(&bits.to_le_bytes());
        bytes[48..52].copy_from_slice(&60_u32.to_le_bytes());
        bytes[52..54].copy_from_slice(&(minutes.len() as u16).to_le_bytes());
        for &(time, base, valid) in minutes {
            let mut breadcrumb = [0; 56];
            breadcrumb[..4].copy_from_slice(b"bcrm");
            breadcrumb[4..8].copy_from_slice(&48_u32.to_le_bytes());
            breadcrumb[8] = (time.year() - 2000) as u8;
            breadcrumb[9] = time.month() as u8;
            breadcrumb[10] = time.day() as u8;
            breadcrumb[11] = time.hour() as u8;
            breadcrumb[12] = time.minute() as u8;
            breadcrumb[36..40].copy_from_slice(&(if valid { 1_f32 } else { 0_f32 }).to_le_bytes());
            bytes.extend_from_slice(&breadcrumb);
            bytes.extend_from_slice(b"data");
            bytes.extend_from_slice(&(60_u32 * u32::from(frame_bytes)).to_le_bytes());
            for sample in 0..60 {
                for channel in 0..4 {
                    let value = base + sample * 4 + channel;
                    bytes.extend_from_slice(&value.to_be_bytes()[4 - bits as usize / 8..]);
                }
            }
        }
        let size = bytes.len() as u32 - 8;
        bytes[4..8].copy_from_slice(&size.to_le_bytes());
        bytes
    }

    pub(crate) fn assert_skip_and_retry(
        header_bytes: usize,
        fixed_sample_bytes: Option<usize>,
        mut write: impl FnMut(&Riff, &mut BufWriter<fs::File>),
    ) {
        let start = Utc.with_ymd_and_hms(2024, 3, 15, 10, 58, 0).unwrap();
        let next = start + TimeDelta::minutes(2);
        for bits in [24, 32] {
            let directory = TestDirectory::new();
            directory.save(
                start,
                &fixture(
                    bits,
                    &[
                        (start, 1_000_000, true),
                        (start + TimeDelta::minutes(1), 2_000_000, false),
                    ],
                ),
            );
            directory.save(next, &fixture(bits, &[(next, 3_000_000, true)]));
            let output = directory.0.join("trace-output");
            let mut writer = BufWriter::new(fs::File::create(&output).unwrap());
            let mut reader = riff::RiffReader::new(directory.0.to_str().unwrap(), 11115);
            let sample_bytes = fixed_sample_bytes.unwrap_or(bits as usize / 8);
            let mut accepted = 0;
            let mut skipped = 0;
            for (time, expected) in [
                (next - TimeDelta::seconds(1), None),
                (start, Some(1_000_000)),
                (next, Some(3_000_000)),
                (next + TimeDelta::hours(1), None),
                (next, Some(3_000_000)),
            ] {
                match read_shot_samples(&mut reader, time, 2) {
                    Ok(Some(samples)) => {
                        let base = expected.expect("invalid shot was accepted");
                        for channel in 0..4 {
                            assert_eq!(
                                samples.data.component[channel],
                                vec![base + channel as i32, base + 4 + channel as i32]
                            );
                        }
                        write(&samples, &mut writer);
                        accepted += 1;
                    }
                    Ok(None) => {
                        assert!(expected.is_none());
                        assert_eq!(time, next - TimeDelta::seconds(1));
                        skipped += 1;
                    }
                    Err(_) => {
                        assert!(expected.is_none());
                        assert_eq!(time, next + TimeDelta::hours(1));
                        skipped += 1;
                    }
                }
                writer.flush().unwrap();
                assert_eq!(
                    fs::metadata(&output).unwrap().len() as usize,
                    accepted * 4 * (header_bytes + 2 * sample_bytes)
                );
            }
            assert_eq!((accepted, skipped), (3, 2));
            let actual = fs::read(output).unwrap();
            let mut position = 0;
            for base in [1_000_000_i32, 3_000_000, 3_000_000] {
                for channel in 0..4 {
                    position += header_bytes;
                    for sample in 0..2 {
                        let expected = (base + sample * 4 + channel).to_be_bytes();
                        assert_eq!(
                            &actual[position..position + sample_bytes],
                            &expected[4 - sample_bytes..]
                        );
                        position += sample_bytes;
                    }
                }
            }
        }
    }
}
