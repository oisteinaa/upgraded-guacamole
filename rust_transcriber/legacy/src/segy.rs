//! This module provides functionality for handling SEGY files in the context of seismic data processing.
//!
//! The module includes:
//!
//! - Error types for handling various write operations (`WriteTraceError`, `WriteBinHdrError`, `WriteEbcdicError`).
//! - An enumeration `SegyFormat` to specify different SEGY data formats.
//! - Functions for interpolating samples, converting floating-point numbers to IBM format, and writing EBCDIC headers.
//! - Functions for writing binary headers and trace data to SEGY files.
//! - A function to populate SEGY trace headers with relevant metadata.
//! - A function to create and write a SEGY file based on provided arguments and navigation data.
//!
//! The module relies on various external crates such as `ebcdic`, `su`, `venator`, `chrono`, `clap`, and `bincode` for its functionality.
use chrono::prelude::{Datelike, Timelike};
use chrono::TimeDelta;
use clap::ValueEnum;
use ebcdic::ebcdic::Ebcdic;
pub use seismic_utils::su;
use seismic_utils::su::SegyBinHdr;
use seismic_utils::su::SegyHdr;
use seismic_utils::venator::navigation::Shot;
use seismic_utils::venator::riff::{Breadcrumb, Format};
use std::{f64::consts, fs::File, io, io::Write};

use seismic_utils::venator::navigation::Navigation;
use seismic_utils::venator::{get_acq_settings, get_drift, riff};
use std::fs;
use std::path::Path;
use std::time::SystemTime;
use std::{fs::OpenOptions, io::BufWriter, net::UdpSocket, process};

use crate::args::Args;
use crate::rabbit::send_to_rabbitmq;
use crate::rotation;

#[derive(Debug, Clone)]
pub struct WriteTraceError;

#[derive(Debug, Clone)]
pub struct WriteBinHdrError;

#[derive(Debug, Clone)]
pub struct WriteEbcdicError;

#[derive(Copy, Clone, Debug, PartialEq, Eq, PartialOrd, Ord, ValueEnum)]
pub enum SegyFormat {
    /// 32-bit integer
    Format32bit = 2,
    /// IBM Floating point 32-bit
    FormatIBM = 1,
    /// IEEE Floating point 32-bit
    FormatIEEE = 5,
}

fn interpolate(frac: f64, sample1: i32, sample2: i32) -> i32 {
    ((sample2 - sample1) as f64 * frac + sample1 as f64) as i32
}

pub fn f32_to_ibm_float(input: f32) -> u32 {
    if input == 0.0 {
        return input.to_bits();
    }
    let mut float_as_int = input.to_bits();

    let mut mantisse = (0x007fffff & float_as_int) | 0x00800000;
    let mut t: i32 = ((0x7f800000 & float_as_int) >> 23) as i32 - 126;

    while t & 0x3 != 0 {
        t += 1;
        mantisse >>= 1;
    }

    float_as_int = (0x80000000 & float_as_int) | (((t as u32 >> 2) + 64) << 24) | mantisse;

    // let exponent = (t as u32 >>2) + 64;
    // let sign = (0x80000000 & float_as_int) >> 31;
    // eprintln!("{} {:032b}: {:#b} {:#b} {:#b}", input, input.to_bits(), sign, exponent, mantisse);
    float_as_int
}

pub fn write_ebcdic(fd: &mut io::BufWriter<File>, nodeid: u32) -> Result<(), WriteEbcdicError> {
    for i in 0..40 {
        let mut line = format!("C{:02}", i);

        // IA INFO
        if i == 0 {
            line = format!("C{:02} InApril AS VENATOR A3000", i + 1);
        } else if i == 2 {
            line = format!("C{:02} CLIENT: {}", i + 1, get_acq_settings("client"));
        } else if i == 3 {
            line = format!("C{:02} SURVEY: {}", i + 1, get_acq_settings("survey"));
        } else if i == 4 {
            line = format!("C{:02} CREW:{}", i + 1, get_acq_settings("crew"));
        } else if i == 5 {
            line = format!(
                "C{:02} VESSEL: {}",
                i + 1,
                get_acq_settings("seismicVessel1")
            );
        } else if i == 6 {
            line = format!(
                "C{:02} SOURCE VESSEL: {}",
                i + 1,
                get_acq_settings("sourceVessel1")
            );
        } else if i == 7 {
            line = format!("C{:02} COMMENT: {}", i + 1, get_acq_settings("comment"));
        } else if i == 8 {
            line = format!("C{:02} NODE ID: {}", i + 1, nodeid);
        } else if i == 9 {
            line = format!("C{:02}", i + 1);
        } else if i == 10 {
            line = format!("C{:02} {}", i + 1, get_acq_settings("other"));

        // SEGY TRACE HEADERS
        } else if i == 14 {
            line = format!("C{:02} SEGY TRACE HEADER MAPPING", i + 1);
        } else if i == 15 {
            line = format!("C{:02} CORRECTION MASK         125-126", i + 1);
        } else if i == 16 {
            line = format!("C{:02} RAW ACCEL X             127-128", i + 1);
        } else if i == 17 {
            line = format!("C{:02} RAW ACCEL Y             129-130", i + 1);
        } else if i == 18 {
            line = format!("C{:02} RAW ACCEL Z             131-132", i + 1);
        } else if i == 19 {
            line = format!("C{:02} WHOLE SAMPLES CORRECTED 133-134", i + 1);
        } else if i == 20 {
            line = format!("C{:02} NODE PITCH              173-174", i + 1);
        } else if i == 21 {
            line = format!("C{:02} NODE ROLL               175-176", i + 1);
        } else if i == 22 {
            line = format!("C{:02} RECEIVER LINE           197-200", i + 1);
        } else if i == 23 {
            line = format!("C{:02} RECEIVER STATION        201-202", i + 1);
        } else if i == 24 {
            line = format!("C{:02} RECEIVER HEADING        203-204", i + 1);
        } else if i == 25 {
            line = format!("C{:02} NUMBER OF TRACES        205-208", i + 1);
        } else if i == 26 {
            line = format!("C{:02} SOURCE LINE NO          209-212", i + 1);
        } else if i == 27 {
            line = format!("C{:02} NODE SERIAL NO          213-216", i + 1);
        } else if i == 28 {
            line = format!("C{:02} RESIDUAL TIME ERR [ns]  217-220", i + 1);
        } else if i == 29 {
            line = format!("C{:02} ROTX                    221-224", i + 1);
        } else if i == 30 {
            line = format!("C{:02} ROTY                    225-228", i + 1);
        } else if i == 31 {
            line = format!("C{:02} ROTZ                    229-232", i + 1);
        } else if i == 32 {
            line = format!("C{:02} SHOT TIME EPOCH [us]    233-240", i + 1);

        // ENDING
        } else if i == 37 {
            line = format!(
                "C{:02} SENSITIVITY GEOPHONE 39.75 V/m/s  HYDROPHONE 1.011 V/Bar",
                i + 1
            );
        } else if i == 38 {
            line = format!(
                "C{:02} CREATED:  time.strftime('%a %b %d %H:%M:%S %Y')",
                i + 1
            );
        } else if i == 39 {
            line = format!("C{:02} END OF TEXTUAL HEADER", i + 1);
        }
        let len = line.len();
        line.push_str(&" ".repeat(80 - len));

        let mut ebcdic_bytes: [u8; 80] = [0u8; 80];
        Ebcdic::ascii_to_ebcdic(line.as_bytes(), &mut ebcdic_bytes, 80, true);

        let _ = fd.write(&ebcdic_bytes);
    }
    Ok(())
}

pub fn write_binary(
    fd: &mut io::BufWriter<File>,
    hdr: &SegyBinHdr,
) -> Result<(), WriteBinHdrError> {
    let config = bincode::config::legacy();
    match bincode::serde::encode_into_std_write(hdr, fd, config) {
        Ok(_) => 1,
        Err(_) => return Err(WriteBinHdrError),
    };

    Ok(())
}

pub fn populate_trace_header(
    fmt: &Format,
    bcrm: &Breadcrumb,
    shot: &Shot,
    args: &Args,
    comp: &i32,
    pitch: f64,
    roll: f64,
    yaw: f64,
) -> SegyHdr {

    let vic_matrix = rotation::get_vic_rotation_matrix(pitch, roll);
    let _vne_matrix = rotation::get_vne_rotation_matrix(pitch, roll, yaw);

    let mut hdr = SegyHdr {
        dt: (1e6 / fmt.dt as f32).round() as u16,

        // Constant stuff
        corr: 1,
        gain: 1,
        timbas: 4,
        counit: 1,
        scalco: -100,
        scalel: -100,
        trid: 1,
        duse: 1,
        lcs: 6,

        // NAVIGATION STUFF
        sx: (shot.lat * 100.0) as i32,
        sy: (shot.lon * 100.0) as i32,
        swdep: (shot.wdepth * 100.0) as i32,
        ep: shot.ep,
        slineno: shot.line as u32,
        gx: (args.east * 100.0) as i32,
        gy: (args.north * 100.0) as i32,
        gwdep: (args.depth * 100.0) as i32,
        rstation: args.rstation as i16,
        rlineno: args.rline,

        // Timing stuff
        year: shot.shot_time.year() as i16,
        day: shot.shot_time.ordinal() as i16,
        hour: shot.shot_time.hour() as i16,
        minute: shot.shot_time.minute() as i16,
        sec: shot.shot_time.second() as i16,
        shot_time: shot.shot_time.timestamp_micros(),

        // Format stuff
        afilf: fmt.anti_alias_freq as i16,
        afils: fmt.anti_alias_slope as i16,

        // Breacrumb stuff
        pitch: (pitch / consts::PI * 1800.0) as i16,
        roll: (roll / consts::PI * 1800.0) as i16,
        rheading: bcrm.magnetometer as u16,
        sfe: bcrm.gx,
        sfs: bcrm.gy,
        slen: bcrm.gz,
        ..Default::default()
    };

    // Per component stuff
    if *comp == 0 {
        hdr.lcf = fmt.g_lcfilt as i16;
        hdr.igc = fmt.g_gain as i16;
        hdr.rotxc = vic_matrix[0][0] as f32;
        hdr.rotyc = vic_matrix[0][1] as f32;
        hdr.rotzc = vic_matrix[0][2] as f32;
        hdr.trid = 13;
    } else if *comp == 1 {
        hdr.lcf = fmt.g_lcfilt as i16;
        hdr.igc = fmt.g_gain as i16;
        hdr.rotxc = vic_matrix[1][0] as f32;
        hdr.rotyc = vic_matrix[1][1] as f32;
        hdr.rotzc = vic_matrix[1][2] as f32;
        hdr.trid = 14;
    } else if *comp == 2 {
        hdr.lcf = fmt.g_lcfilt as i16;
        hdr.igc = fmt.g_gain as i16;
        hdr.rotxc = vic_matrix[2][0] as f32;
        hdr.rotyc = vic_matrix[2][1] as f32;
        hdr.rotzc = vic_matrix[2][2] as f32;
        hdr.trid = 12;
    } else if *comp == 3 {
        hdr.lcf = fmt.p_lcfilt as i16;
        hdr.igc = fmt.p_gain as i16;
        hdr.rotxc = 0.0;
        hdr.rotyc = 0.0;
        hdr.rotzc = 0.0;
        hdr.trid = 11;
    }
    hdr.lcf = 0;
    if bcrm.gz < 0 {
        hdr.rotyc *= -1.0;
        hdr.rotzc *= -1.0;
    }

    hdr
}

pub fn write_trace(
    mut fd: &mut io::BufWriter<File>,
    hdr: &mut SegyHdr,
    data: &[i32],
    fmt: SegyFormat,
    mp: f32,
    timecorr: bool,
) -> Result<(), WriteTraceError> {
    let frac = (hdr.clock_drift as f64 / hdr.dt as f64) / 1.0e3;
    let gain = hdr.igc as f32;
    hdr.to_big_endian();

    let config = bincode::config::legacy();

    match bincode::serde::encode_into_std_write(&hdr, &mut fd, config) {
        Ok(_) => 1,
        Err(_) => return Err(WriteTraceError),
    };

    // let frac = hdr.clock_drift as f64 / hdr.dt as f64;

    dbg!(hdr.clock_drift, frac);

    for (i, sample) in data.iter().enumerate() {
        let mut adjusted_sample: i32 = *sample;

        if timecorr {
            if frac > 0.0 {
                if i < (data.len() - 1) {
                    adjusted_sample = interpolate(frac, data[i], data[i + 1]);
                }
            } else if i > 0 {
                adjusted_sample = interpolate(frac, data[i - 1], data[i]);
            }
        }

        if fmt == SegyFormat::FormatIBM {
            let test = adjusted_sample as f32 * mp / gain;
            let s = f32_to_ibm_float(test);
            let _ = fd.write(&s.to_be_bytes()).expect("Error writing data");
        } else if fmt == SegyFormat::FormatIEEE {
            // dbg!(adjusted_sample, mp);
            let _ = fd
                .write(&(adjusted_sample as f32 * mp / gain).to_bits().to_be_bytes())
                .expect("Error writing data");
        } else {
            let _ = fd
                .write(&adjusted_sample.to_be_bytes())
                .expect("Error writing data");
        }
    }

    Ok(())
}

pub fn make_segy_file(args: &Args, nav: &Navigation, shot_filename_name: &str) -> (std::path::PathBuf, i32, u64, u16) {
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap();

    let mp = 2.9802e-04;
    let mut binary = su::SegyBinHdr {
        format: args.segy_format as i16,
        hdt: 0,
        hns: args.ns as u16,
        nart: 0,
        mfeet: 1,
        vscode: 1,
        tsort: 1,
        ntrpr: 4,
        segyrev: 0x0100,
        mp,
        nodeid: args.nodeid,
        rline: args.rline as i32,
        rstation: args.rstation as i32,
        sline: nav.shots()[0].line,
        from_ep: nav.shots().first().unwrap().ep,
        to_ep: nav.shots().last().unwrap().ep,
        time_first_shot: nav.shots().first().unwrap().shot_time.timestamp() as i32,
        time_last_shot: nav.shots().last().unwrap().shot_time.timestamp() as i32,
        ..Default::default()
    };

    // TODO: File and directory of segy file
    let path = args.sfd.to_string();
    match fs::create_dir_all(&path) {
        Ok(_) => (),
        Err(err) => eprintln!("Error creating directory: {}", err),
    }

    let filename_str = format!(
        "{}/{:08}_{:08}_{:010}_{:08}_{}.SEGY",
        &path,
        args.rline,
        args.rstation,
        args.nodeid,
        nav.shots()[0].line,
        Path::new(shot_filename_name)
                .file_stem()
                .and_then(|stem| stem.to_str())
                .unwrap_or(shot_filename_name),
    );

    
    let filename = Path::new(&filename_str);

    let fd = OpenOptions::new()
        .write(true)
        .create(true)
        .truncate(true)
        .open(filename)
        .unwrap();

    eprintln!("Writing to file: {}", filename.display());

    let mut writer = BufWriter::new(fd);

    write_ebcdic(&mut writer, args.nodeid).unwrap();
    let mut counter = 0;
    let mut riff_reader = riff::RiffReader::new(&args.rfd, args.nodeid);
    let now = SystemTime::now();
    let socket = UdpSocket::bind("0.0.0.0:0").expect("Can't bind udp socket");
    let count = nav.shots().len();

    let mut msg_json = serde_json::json!({
        "name": "transcribe",
        "state": "running",
        "node_id": args.nodeid,
        "pid": process::id(),
        "value": 0,
        "total": count,
        "percentage": 0,
        "speed": 0,
        "eta": 0,
    });

    let mut dt: u16 = 0;
    let mut skipped_traces = 0;

    for (j, shot) in nav.shots().iter().enumerate() {
        dbg!(&shot);
        let (drift, _survey_start, _survey_length, _tot_drift) = get_drift(args.nodeid, shot.shot_time, &args.rfd);
        let adjusted_shot_time =
            shot.shot_time - drift + TimeDelta::try_milliseconds(args.toffset as i64).unwrap();

        let riff_obj = match crate::read_shot_samples(&mut riff_reader, adjusted_shot_time, args.ns) {
            Ok(Some(samples)) => samples,
            Ok(None) => {
                eprintln!(
                    "No valid breadcrumb found in file: {}",
                    riff::get_riff_fn(adjusted_shot_time, args.nodeid)
                );
                skipped_traces += 1;
                continue;
            }
            Err(error) => {
                eprintln!(
                    "Skipping shot {} (corrected {}): {}",
                    shot.shot_time, adjusted_shot_time, error
                );
                skipped_traces += 1;
                continue;
            }
        };

        dbg!(&adjusted_shot_time);

        if j % 300 == 0 {
            let dur = now.elapsed().unwrap().as_millis();
            let mut speed = 0.0;
            let mut eta = 0.0;

            if dur > 500 {
                speed = j as f64 / (dur as f64 / 1e3);
                eta = (count - j) as f64 / (j as f64 / dur as f64);
            }

            let msg = format!(
                "{};{};{};{};{};{}",
                args.nodeid,
                process::id(),
                &j,
                count,
                speed,
                eta
            );
            let percentage = j as f64 / count as f64 * 100.0;

            msg_json["value"] = serde_json::json!(&j);
            msg_json["percentage"] = serde_json::json!(&percentage);
            msg_json["speed"] = serde_json::json!(&speed);
            msg_json["eta"] = serde_json::json!(&eta / 1e3);

            runtime.block_on(async {
                send_to_rabbitmq(&msg_json).await;
            });
            let _ = socket.send_to(msg.as_bytes(), "0.0.0.0:7757");
        }

        let (pitch, roll) = rotation::get_pitch_roll(
            riff_obj.breadcrumb.gx as f64, 
            riff_obj.breadcrumb.gy as f64, 
            riff_obj.breadcrumb.gz as f64
        );

        let yaw: f64 =
            -riff_obj.breadcrumb.magnetometer as f64 / 1800.0 * std::f64::consts::PI;
        
        // // dbg!(&data);

        if counter == 0 {
            dt = riff_obj.format.dt;
            binary.hdt = (1e6 / riff_obj.format.dt as f64) as u16;
            binary.to_big_endian();
            write_binary(&mut writer, &binary).unwrap();
        }

        let dt = 1.0 / riff_obj.format.dt as f64;
        let samples_moved = (drift.num_microseconds().unwrap() as f64 / dt / 1e6).round() as i16;

        for i in 0..4 {
            let mut hdr =
                populate_trace_header(&riff_obj.format, &riff_obj.breadcrumb, shot, args, &i, pitch, roll, yaw);
            hdr.fldr = 1000 + (counter / 4);
            hdr.dt = (dt * 1e6) as u16;
            hdr.ns = args.ns as u16;
            hdr.tracr = counter + 1;
            hdr.tracl = counter + 1;
            hdr.tracf = counter + 1;
            hdr.ntr = (nav.shots().len() * 4) as u32 - skipped_traces as u32;
            hdr.nodeid = args.nodeid;
            hdr.tatyp = shot.index;
            hdr.delrt = (0.0 - (riff_obj.format.anti_alias_delay as f64 * hdr.dt as f64 / 1e3)
                + args.toffset as f64)
                .round() as i16;
            hdr.styp = samples_moved;
            hdr.clock_drift = -riff_obj.residual.num_nanoseconds().unwrap() as i32;
            dbg!(hdr.clock_drift);
            write_trace(
                &mut writer,
                &mut hdr,
                &riff_obj.data.component[i as usize],
                args.segy_format,
                mp,
                args.timecorr,
            )
            .unwrap();
            counter += 1;
        }
    }
    msg_json["state"] = serde_json::json!("done");
    msg_json["value"] = serde_json::json!(&count);
    msg_json["percentage"] = serde_json::json!(100);
    msg_json["eta"] = serde_json::json!(0);

    runtime.block_on(async {
        send_to_rabbitmq(&msg_json).await;
    });

    let filesize = fs::metadata(filename)
        .map(|m| m.len())
        .unwrap_or(0);

    (filename.to_path_buf(), counter, filesize, dt)
}

#[test]
fn test_interpolate_sample() {
    let drift: i32 = 1_000_000;
    let dt: i32 = 2000;

    let sample1: i32 = 100;
    let sample2: i32 = 300;
    let frac = (drift as f64 / dt as f64) / 1.0e3;

    dbg!(
        drift,
        dt,
        sample1,
        sample2,
        frac,
        interpolate(frac, sample1, sample2)
    );
    assert!(interpolate(frac, sample1, sample2) == 200_i32);
}

#[test]
fn test_riff_skip_and_retry() {
    crate::riff_tests::assert_skip_and_retry(240, Some(4), |samples, writer| {
        for component in &samples.data.component {
            let mut header = SegyHdr {
                dt: 1000,
                ns: 2,
                ..Default::default()
            };
            write_trace(
                writer,
                &mut header,
                component,
                SegyFormat::Format32bit,
                1.0,
                false,
            )
            .unwrap();
        }
    });
}
