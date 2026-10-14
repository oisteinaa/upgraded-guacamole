//! This module provides comprehensive functionality for generating SEGD (SEG-D) files from navigation and shot data.
//! It includes functions to write general headers, scan type headers, trace headers, and trace data.
//! The module leverages various external crates for handling binary-coded decimal (BCD) numbers, date and time operations,
//! packed structures, and SEGD headers. Additionally, it interacts with a RabbitMQ server to send progress updates.
//!
//! The primary function `make_segd_file` orchestrates the entire process of reading navigation data, adjusting shot times,
//! reading RIFF files, and writing the SEGD file. The module also includes auxiliary functions for writing specific
//! headers and trace data, ensuring a structured and efficient workflow.
//!
use crate::{args::Args, rabbit, rotation};
use bcd_numbers::BCD;
use chrono::{Datelike, TimeDelta, Timelike};
use packed_struct::{
    prelude::*,
    types::{bits::Bits, Integer},
};
use std::{fmt, io::Seek};
use rust_segd_lib::{
    headers::{
        extension::{TimeDrift, TimestampHeader}, general::{
            FormatCode, General, ManufacturerCode, PackedBcdRecordType, PackedU4Bcd, Polarity, RecordType
        }, scan_type::{
            ChannelGain, ChannelSetDesc1, ChannelSetDesc2, ChannelSetDesc3, ChannelType,
            PhysicalUnit, ScanType,
        }, trace::{IAOrientation, InAprilMultiSourceDesc, InAprilReceiverPositions, InAprilSourcePositions, SensorInfo, SensorType, Trace}, HeaderBlock
    },
    Extended,
};
use seismic_utils::venator::{
    get_drift,
    navigation::{Navigation, Shot},
    riff::{self, Breadcrumb, Data, Format},
};
use std::{
    f32::consts::{PI},
    fs::{self, File, OpenOptions},
    io::{BufWriter, Write},
    path::Path,
    process,
    time::SystemTime,
};

fn write_gh_headers(
    args: &Args,
    _nav: &Navigation,
    fmt: &Format,
    fd: &mut BufWriter<File>,
) -> Result<(), std::io::Error> {
    let now = chrono::Local::now();
    let dt = 1e6 / fmt.dt as f32;
    let bytes_per_sample = fmt.bit_per_sample/8;;

    let mut headers = General::default();
    headers.head_1.file_number = Extended::Extended;


    dbg!(fmt.bit_per_sample);
    if fmt.bit_per_sample == 24 {
        headers.head_1.format_code = FormatCode::TwosComplement24Bit;
    } else {
        headers.head_1.format_code = FormatCode::TwosComplement32Bit;
    }

    //headers.head_1.format_code = FormatCode::TwosComplement24Bit;
    // 32 bit 8058
    //headers.head_1.format_code = FormatCode::TwosComplement32Bit;
    
    headers.head_1.year = BCD::new((now.year() - 2000) as u128);
    headers.head_1.day_and_gen_hdr =
        PackedU4Bcd::new(0x2, BCD::<2>::new(now.ordinal() as u128).into());
    headers.head_1.hour = BCD::new(now.hour() as u128);
    headers.head_1.min = BCD::new(now.minute() as u128);
    headers.head_1.sec = BCD::new(now.second() as u128);
    headers.head_1.base_scan_interval = (dt / 1e3 * 16.0).round() as i8;
    headers.head_1.scan_types_per_record = BCD::new(1);
    headers.head_1.polarity = Polarity::Zero;
    headers.head_1.chan_sets = BCD::new(4);
    headers.head_1.manufacurer_code = ManufacturerCode::InAprilAs;
    headers.head_1.record_type_and_length = PackedBcdRecordType {
        four: RecordType::NormalRecord,
        twelve: Extended::Extended,
    };

    headers.head_2.exp_file_num = args.nodeid.into();
    headers.head_2.dom_sampl_interval = (dt as u32).into();
    headers.head_2.ext_rec_len = (args.ns as f32 * dt).round() as u32;
    headers.head_2.major_rev_num = 3;
    headers.head_2.minor_rev_num = 1;
    headers.head_2.header_block_type = HeaderBlock::GenHead2 as u8;

    headers.timestamp_size.time_zero = 0x00;
    headers.timestamp_size.header_size = 32 * 6 + 4 * 96;
    headers.timestamp_size.data_size = (
        headers.timestamp_size.header_size + (4 * (bytes_per_sample as u32 * args.ns + (20 + 32 * 10)))
        // NOTE: needs update when num trace header extensions changes
    ) as u64;
    headers.timestamp_size.record_size = headers.timestamp_size.data_size;
    headers.timestamp_size.header_block_type = HeaderBlock::Timestamp as u8;

    let buf = headers.pack().unwrap().to_vec();

    // let vessel_header = VesselCrewId {
    //     name: {
    //         let mut name = [0u8; 28];
    //         let bytes = args.vessel.as_bytes();
    //         let len = bytes.len().min(28);
    //         name[..len].copy_from_slice(&bytes[..len]);
    //         name
    //     },
    //     header_block_type: HeaderBlock::VesselCrewId,
    //     ..Default::default()
    // };

    // let survey_header = SurveyAreaName {
    //     survey_area_name: {
    //         let mut name = [0u8; 31];
    //         let bytes = args.survey.as_bytes();
    //         let len = bytes.len().min(28);
    //         name[..len].copy_from_slice(&bytes[..len]);
    //         name
    //     },
    //     header_block_type: HeaderBlock::SurveyAreaName,
    //     ..Default::default()
    // };

    // let client_header = ClientId {
    //     client_id: {
    //         let mut name = [0u8; 31];
    //         let bytes = args.client.as_bytes();
    //         let len = bytes.len().min(28);
    //         name[..len].copy_from_slice(&bytes[..len]);
    //         name
    //     },
    //     header_block_type: HeaderBlock::ClientId,
    //     ..Default::default()
    // };

    // let job_header = JobId {
    //     job_id: {
    //         let mut name = [0u8; 26];
    //         let bytes = args.job.as_bytes();
    //         let len = bytes.len().min(28);
    //         name[..len].copy_from_slice(&bytes[..len]);
    //         name
    //     },
    //     header_block_type: HeaderBlock::JobId,
    //     ..Default::default()
    // };

    // buf.extend_from_slice(&vessel_header.pack().unwrap());
    // buf.extend_from_slice(&survey_header.pack().unwrap());
    // buf.extend_from_slice(&client_header.pack().unwrap());
    // buf.extend_from_slice(&job_header.pack().unwrap());

    fd.write_all(&buf)
}

fn write_scantype_headers(
    args: &Args,
    fmt: &Format,
    comp: u8,
    ntr: u32,
    fd: &mut BufWriter<File>,
) -> Result<(), std::io::Error> {
    let dt = 1e6 / fmt.dt as f32;

    let scan_type = ScanType {
        chan_set_desc_blk_1: ChannelSetDesc1 {
            scan_type_no: BCD::new(1),
            ch_set_no: (comp + 1).into(),
            ch_type: if comp < 3 {
                ChannelType::Velocity
            } else {
                ChannelType::Pressure
            },
            ch_set_start_time: 0,
            ch_set_end_time: (dt as u32 * args.ns) as i32,
            num_samples: args.ns,
            ch_gain: ChannelGain::FixedGain,

            descale_mult: if comp < 3 {
                let mp = 2.5e3 / fmt.g_gain as f64 / ((2.0_f64.powi(23) - 1.0));
                ((mp.ln() / 2.0_f64.ln()) as f32).to_bits()
            } else {
                let mp = 2.5e3 / fmt.p_gain as f64 / ((2.0_f64.powi(23) - 1.0));
                ((mp.ln() / 2.0_f64.ln()) as f32).to_bits()
            },
            no_of_chan: ntr.into(),
            sampling_interval: (dt as u32).into(),
            array_forming: 0x01,
            trace_head_ext: 8,
            vertical_stack: 0x01,
            head_blk_type: 0x30,
            ..Default::default()
        }
        .pack()
        .unwrap(),
        chan_set_desc_blk_2: ChannelSetDesc2 {
            alias_filter_freq: fmt.anti_alias_freq.to_bits(),
            alias_filter_slope: (276_f32).to_bits(), //checked with Eskild and according to the spec 240 Hz at -60dB
            filter_phase: if fmt.anti_alias_response == 0x00 {
                0x02
            } else {
                0x01
            }, // riff file 0x00 - linear 0x01 - minimum phase
            low_cut_filter: if comp < 3 {
                // RIFF is a u16 in Hertz change in fw to 0 when not in use
                (fmt.g_lcfilt as f32 / 10.0).to_bits()
            } else {
                (fmt.p_lcfilt as f32 / 10.0).to_bits()
            },
            low_cut_filter_slope: (fmt.lcfilt_slope as f32).to_bits(),
            head_blk_type: 0x31,
            ..Default::default()
        }
        .pack()
        .unwrap(),
        chan_set_desc_blk_3: ChannelSetDesc3 {
            filter_delay: fmt.anti_alias_delay as u32 * dt as u32, // check riff file is in samples
            description: if comp == 0 {
                let mut desc = [0u8; 27];
                desc[..17].copy_from_slice(b"Inline geophone X");
                desc
            } else if comp == 1 {
                let mut desc = [0u8; 27];
                desc[..20].copy_from_slice(b"Crossline geophone Y");
                desc
            } else if comp == 2 {
                let mut desc = [0u8; 27];
                desc[..19].copy_from_slice(b"Vertical geophone Z");
                desc
            } else {
                let mut desc = [0u8; 27];
                desc[..12].copy_from_slice(b"Hydrophone P");
                desc
            },
            head_blk_type: 0x32,
        }
        .pack()
        .unwrap(),
    };

    let buf = scan_type.pack().unwrap();

    fd.write_all(&buf)
}

#[allow(clippy::too_many_arguments)]
fn write_trace_headers(
    args: &Args,
    shot: &Shot,
    fmt: &Format,
    bcrm: &Breadcrumb,
    drift: &TimeDelta,
    survey_start: &f64,
    survey_length: &f64,
    tot_drift: &i64,
    residual: &TimeDelta,
    fd: &mut BufWriter<File>,
    traceno: usize,
    comp: u8,
    pitch: f64,
    roll: f64,
    vic: [[f64; 3]; 3],
    vne: [[f64; 3]; 3],
) -> Result<(), std::io::Error> {
    let mut tracehead = Trace {
        demux: {
            let mut demux = Trace::default().demux;
            demux.file_num = Extended::Extended;
            demux.trace_num = Extended::Extended;
            demux.trace_head_ext = 8;
            demux.chan_set_num = BCD::new((comp + 1).into());
            demux.scan_type_num = BCD::new(1);
            demux.ext_file_num = args.nodeid.into();
            demux
        },
        extension: {
            let mut extension = Trace::default().extension;
            extension.rec_line_num = args.rline.into();
            extension.rec_point_num = args.rstation.into();
            extension.ext_rec_line_num_int = (args.rline as i32).into();
            extension.ext_rec_point_num_int = (args.rstation as i32).into();
            extension.ext_trace_num = (traceno as u32).into();
            extension.num_of_samples_per_trace = args.ns;
            extension.sensor_moving = 0;
            extension
        },
        ..Default::default()
    };

    if comp < 3 {
        tracehead.extension.physical_unit = PhysicalUnit::MillimeterPerSecond;
        if comp == 0 {
            tracehead.extension.sensor_type = SensorType::GeophoneHorizontalInline;
        } else if comp == 1 {
            tracehead.extension.sensor_type = SensorType::GeophoneHorizontalCrossline;
        } else {
            tracehead.extension.sensor_type = SensorType::GeophoneVertical;
        }
    } else {
        tracehead.extension.physical_unit = PhysicalUnit::Millibar;
        tracehead.extension.sensor_type = SensorType::Hydrophone;
    }

    // let airgun = Airgun {
    //     depth: (shot.sdepth * 100.0).round() as u16,
    //     src_point_num_int: shot.ep.into(),
    //     src_point_num_fraq: shot.epfrac as u16,
    //     src_line_num_int: shot.line.into(),
    //     src_line_num_fraq: 0,
    //     src_point_idx: shot.index as u8,
    //     src_set_num: shot.code as u8,
    //     src_id: shot.code as u8,
    //     header_type: HeaderBlock::Airgun,
    //     ..Default::default()
    // };

    let sensor_info_header = SensorInfo {
        sensor_sensitivity: if comp < 3 {
            (1.0 / fmt.g_sens).to_bits()
        } else {
            (1.0 / fmt.p_sens).to_bits()
        },
        serial_num: {
            let mut serial = [0x20u8; 18];
            let formatted = format!("{:010}", args.nodeid);
            serial[..formatted.len()].copy_from_slice(formatted.as_bytes());
            serial
        },
        head_blk_type: HeaderBlock::SensorInfoHeadExt,
        ..Default::default()
    };

    let timestamp_header = TimestampHeader {
        time_zero_of_data: shot.shot_time.timestamp_micros() as u64,
        ..Default::default()
    };

    let dt = 1e6 / fmt.dt as f64;
    let samples_moved = ((drift.num_microseconds().unwrap() as f64 + residual.num_microseconds().unwrap() as f64) / dt).round() as i16;

    let drift_header = TimeDrift {
        time_of_deployment: (survey_start * 1000.0) as u64,
        time_of_retrieval: (survey_start * 1000.0 + survey_length * 1000.0) as u64,
        time_offset_deployment: 0,
        time_offset_retrieval: (tot_drift.clone()/1000) as i32,
        // time_offset_retrieval: drift.num_microseconds().unwrap() as i32,
        timedrift_corrected: if args.timecorr { 2 } else { 1 },
        correction_method: 0xFF,
        whole_samples_moved: samples_moved as i16,
        subsamples_residual: Integer::<i32, Bits<24>>::from((-residual.num_microseconds().unwrap()) as i32),
        head_blk_type: HeaderBlock::TimeDrift,
    };

    // let orientation_header = Orientation {
    //     rot_x_axis: pitch.to_bits(),
    //     rot_y_axis: roll.to_bits(),
    //     rot_z_axis: (bcrm.magnetometer as f32 / 1800.0 * PI).to_bits(),
    //     rot_applied: 0,
    //     rot_north_applied: 0,
    //     ref_orient: args.declination.to_bits(),
    //     ref_orient_valid: if args.declination == 0.0 { 0 } else { 1 },
    //     orient_type: 0x05,
    //     timestamp: 0,
    //     head_blk_type: HeaderBlock::Orientation,
    // };

    // TODO: Implement the rest of the headers
    let ia_multi_source_desc = InAprilMultiSourceDesc {
        shotline_number: shot.line.into(),
        shot_point_no: shot.ep.into(),
        shot_point_frac: shot.epfrac as u16,
        shot_point_index: shot.index as u8,
        shot_skew:  -(((shot.shot_time.timestamp_micros() as f64 / dt).round() * dt - shot.shot_time.timestamp_micros() as f64) as i16),
        ..Default::default()
    };

    let ia_src_positions = InAprilSourcePositions {
        source_easting_x: shot.lat.to_bits(),
        source_northing_y: shot.lon.to_bits(),
        source_elevation_z: ((shot.wdepth - shot.sdepth) as f32).to_bits(),
        source_water_depth: (shot.wdepth as f32).to_bits(),
        source_depth: (shot.sdepth as f32).to_bits(),
        ..Default::default()
    };

    let ia_recv_position = InAprilReceiverPositions {
        receiver_easting_x: args.east.to_bits(),
        receiver_northing_y: args.north.to_bits(),
        receiver_elevation_z: args.depth.to_bits(),
        receiver_water_depth: args.depth.to_bits(),
        receiver_depth: args.depth.to_bits(),
        ..Default::default()
    };

    // VIC contributions
    let vertical;
    let inline;
    let crossline;
    
    // VNE contributions
    // let vertical_vne;
    let inline_vne;
    let crossline_vne;

    // Calculate the vertical, inline, and crossline components based on the component index
    match comp {
        0 => {
            inline = vic[0][0];
            crossline = vic[0][1];
            vertical = vic[0][2];

            inline_vne = vne[0][0];
            crossline_vne = vne[0][1];

        }
        1 => {
            inline = vic[1][0];
            crossline =  vic[1][1];
            vertical = vic[1][2];

            inline_vne = vne[1][0];
            crossline_vne = vne[1][1];
        }
        2 => {
            inline = vic[2][0];
            crossline = vic[2][1];
            vertical = vic[2][2];

            inline_vne = vne[2][0];
            crossline_vne = vne[2][1];
        }
        _ => {
            vertical = 0.0;
            inline = 0.0;
            crossline = 0.0;

            inline_vne = 0.0;
            crossline_vne = 0.0;
        },
    }

    let mut yaw = bcrm.magnetometer;

    if args.rheading != -7200 {
            yaw = args.rheading;
    }

    let ia_orientation = IAOrientation {
        gravity_x: bcrm.gx,
        gravity_y: bcrm.gy,
        gravity_z: bcrm.gz,
    
        sensor_vertical: ((vertical * 10000.0).round() as i16),
        sensor_inline: ((inline * 10000.0).round() as i16),
        sensor_crossline: ((crossline * 10000.0).round() as i16),

        sensor_mag_north: ((inline_vne * 10000.0).round() as i16),
        sensor_mag_east: ((crossline_vne * 10000.0).round() as i16),

       
        pitch: (pitch / PI as f64 * 1800.0).round() as i16,
        roll: (roll / PI as f64 * 1800.0).round() as i16,
        heading: yaw,
        rotation_applied: false,
        rotation_north_applied: false,
        ..Default::default()
    };

    let mut buf = tracehead.demux.pack().unwrap().to_vec();
    buf.extend_from_slice(&tracehead.extension.pack().unwrap());
    // buf.extend_from_slice(&airgun.pack().unwrap());
    buf.extend_from_slice(&sensor_info_header.pack().unwrap());
    buf.extend_from_slice(&timestamp_header.pack().unwrap());
    buf.extend_from_slice(&drift_header.pack().unwrap());
    // buf.extend_from_slice(&orientation_header.pack().unwrap());
    buf.extend_from_slice(&ia_multi_source_desc.pack().unwrap());
    buf.extend_from_slice(&ia_src_positions.pack().unwrap());
    buf.extend_from_slice(&ia_recv_position.pack().unwrap());
    buf.extend_from_slice(&ia_orientation.pack().unwrap());

    fd.write_all(&buf)
}

fn write_trace_data(
    data: &Data,
    fd: &mut BufWriter<File>,
    _traceno: usize,
    comp: u8,
    resolution: u16,
) -> Result<(), std::io::Error> {
    dbg!(data.component[comp as usize].len(), comp);

    if resolution == 24 {
        let byte_slice: Vec<u8> = data.component[comp as usize]
            .iter()
            .flat_map(|&sample| sample.to_be_bytes()[1..].to_vec())
            .collect();

        fd.write_all(&byte_slice)
    } else if resolution == 32 {
        let byte_slice: Vec<u8> = data.component[comp as usize]
            .iter()
            .flat_map(|&sample| sample.to_be_bytes().to_vec())
            .collect();

        fd.write_all(&byte_slice)
    } else {
        Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "Unsupported sample resolution",
        ))
    }   
}

pub fn make_segd_file(args: &Args, nav: &Navigation, shot_filename_name: &str) -> (std::path::PathBuf, i32, u64, u16) {
    let runtime = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap();

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

    let path = args.sfd.to_string();
    match fs::create_dir_all(&path) {
        Ok(_) => (),
        Err(err) => eprintln!("Error creating directory: {}", err),
    }

    let filename_str = format!(
        "{}/{:08}_{:08}_{:010}_{}.SEGD",
        &path,
        args.rline,
        args.rstation,
        args.nodeid,
        Path::new(shot_filename_name)
                .file_stem()
                .and_then(|stem| stem.to_str())
                .unwrap_or(shot_filename_name),
    );
    let filename = Path::new(&filename_str).to_path_buf();

    let mut fd = BufWriter::new(
        OpenOptions::new()
            .write(true)
            .create(true)
            .truncate(true)
            .open(&filename)
            .unwrap(),
    );

    // Write general headers and scan type headers also the place for external header and extended header
    eprintln!("Writing to file: {}", filename.display());
    write_gh_headers(args, nav, &Format::default(), &mut fd).unwrap();
    for i in 0..4 {
        write_scantype_headers(args, &Format::default(), i, 0_u32, &mut fd).unwrap();
    }

    let mut counter = 0;
    let mut riff_reader = riff::RiffReader::new(&args.rfd, args.nodeid);
    let now = SystemTime::now();
    let count = nav.shots().len();

    let mut skipped_traces = 0;
    let mut riff_obj= riff::Riff::default();
    // Loop through all shots
    for (j, shot) in nav.shots().iter().enumerate() {
        // Send progress updates  to rabbitMQ
        if j % 900 == 0 {
            let dur = now.elapsed().unwrap().as_millis();
            let mut speed = 0.0;
            let mut eta = 0.0;

            if dur > 500 {
                speed = j as f64 / (dur as f64 / 1e3);
                eta = (count - j) as f64 / (j as f64 / dur as f64);
            }

            let percentage = j as f64 / count as f64 * 100.0;

            msg_json["value"] = serde_json::json!(&j);
            msg_json["percentage"] = serde_json::json!((&percentage * 10.0).round() / 10.0);
            msg_json["speed"] = serde_json::json!((speed * 10.0).round() / 10.0);
            msg_json["eta"] = serde_json::json!(&eta / 1e3);

            runtime.block_on(async {
                rabbit::send_to_rabbitmq(&msg_json).await;
            });
        }

        let (drift, survey_start, survey_length, tot_drift) = get_drift(args.nodeid, shot.shot_time, &args.rfd);
        let adjusted_shot_time =
            shot.shot_time - drift + TimeDelta::try_milliseconds(args.toffset as i64).unwrap();

        dbg!(shot.shot_time, adjusted_shot_time, drift, args.toffset);
        let tmp_riff_obj = match crate::read_shot_samples(&mut riff_reader, adjusted_shot_time, args.ns)
        {
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

        riff_obj = tmp_riff_obj;

        let (pitch, roll) = rotation::get_pitch_roll(
            riff_obj.breadcrumb.gx as f64, 
            riff_obj.breadcrumb.gy as f64, 
            riff_obj.breadcrumb.gz as f64
        );

        let mut yaw: f64 =
            -riff_obj.breadcrumb.magnetometer as f64 / 1800.0 * std::f64::consts::PI;

        if args.rheading != -7200 {
            yaw = args.rheading as f64 / 1800.0 * std::f64::consts::PI;
        }

        let vic_matrix = rotation::get_vic_rotation_matrix(-pitch, -roll);
        let vne_matrix = rotation::get_vne_rotation_matrix(-pitch, -roll, -yaw);

        // Write trace headers and data
        for i in 0..4 {
            let _ = write_trace_headers(
                args,
                shot,
                &riff_obj.format,
                &riff_obj.breadcrumb,
                &drift,
                &survey_start,
                &survey_length,
                &tot_drift,
                &riff_obj.residual,
                &mut fd,
                j-skipped_traces,
                i,
                pitch,
                roll,
                vic_matrix,
                vne_matrix
            );
            let _ = write_trace_data(&riff_obj.data, &mut fd, j-skipped_traces, i, riff_obj.format.bit_per_sample);

            // write_trace(&mut writer, &mut hdr, &data.component[i as usize], args.segy_format, mp, args.timecorr).unwrap();
            counter += 1;
        }
    }

    msg_json["value"] = serde_json::json!(100);
    msg_json["percentage"] = serde_json::json!(100);
    msg_json["eta"] = serde_json::json!(0.0);
    msg_json["state"] = serde_json::json!("done");

    runtime.block_on(async {
        rabbit::send_to_rabbitmq(&msg_json).await;
    });

   
    // Write general headers and scan type headers also the place for external header and extended header
    fd.seek(std::io::SeekFrom::Start(0)).unwrap();
    eprintln!("Writing to file: {}", filename.display());

    write_gh_headers(args, nav, &riff_obj.format, &mut fd).unwrap();
    for i in 0..4 {
        write_scantype_headers(args, &riff_obj.format, i, counter/4_u32, &mut fd).unwrap();
    } 

    let filesize = fd.get_ref().metadata().map(|m| m.len()).unwrap_or(0);
    (filename, (counter/4) as i32, filesize, riff_obj.format.dt)
}

#[test]
fn test_segd_trace_header_packed_sizes() {
    use packed_struct::PackedStruct;
    use rust_segd_lib::headers::{
        trace::{Demux, Extension, SensorInfo, InAprilMultiSourceDesc, InAprilSourcePositions, InAprilReceiverPositions, IAOrientation},
        extension::{TimestampHeader, TimeDrift},
    };

    assert_eq!(Demux::default().pack().unwrap().len(), 20, "Demux packed size should be 20 bytes");
    assert_eq!(Extension::default().pack().unwrap().len(), 32, "Extension packed size should be 32 bytes");
    assert_eq!(SensorInfo::default().pack().unwrap().len(), 32, "SensorInfo packed size should be 32 bytes");
    assert_eq!(TimeDrift::default().pack().unwrap().len(), 32, "TimeDrift packed size should be 32 bytes");
    assert_eq!(TimestampHeader::default().pack().unwrap().len(), 32, "TimestampHeader packed size should be 32 bytes");
    assert_eq!(InAprilMultiSourceDesc::default().pack().unwrap().len(), 32, "InAprilMultiSourceDesc packed size should be 32 bytes");
    assert_eq!(InAprilSourcePositions::default().pack().unwrap().len(), 32, "InAprilSourcePositions packed size should be 32 bytes");
    assert_eq!(InAprilReceiverPositions::default().pack().unwrap().len(), 32, "InAprilReceiverPositions packed size should be 32 bytes");
    assert_eq!(IAOrientation::default().pack().unwrap().len(), 32, "IAOrientation packed size should be 32 bytes");
}

#[test]
fn test_sample_skew() {
    use chrono::{NaiveDate};

    let shot_time = NaiveDate::from_ymd_opt(2024, 10, 5).unwrap()
        .and_hms_micro_opt(12, 0, 0, 123456).unwrap();
    let dt = 4000.0; // 4 ms sample interval
    
    let source_skew = -(((shot_time.and_utc().timestamp_micros() as f64 / dt).round() * dt - shot_time.and_utc().timestamp_micros() as f64) as i16);
    dbg!(source_skew);
    assert_eq!(source_skew, -(124000_i32-123456_i32) as i16);
}

#[test]
fn test_riff_skip_and_retry() {
    crate::riff_tests::assert_skip_and_retry(0, None, |samples, writer| {
        for component in 0..4 {
            write_trace_data(
                &samples.data,
                writer,
                0,
                component,
                samples.format.bit_per_sample,
            )
            .unwrap();
        }
    });
}

#[test]
fn test_segd_filename() {
    let args_rline = 1234;
    let args_rstation = 56;
    let args_nodeid = 789;
    let path = "/data/output";
    let shot_filename_name = "/raid1/test/7.7.9/20251809.csv";

    let filename_str = format!(
        "{}/{:08}_{:08}_{:010}_{}.SEGD",
            &path, 
            args_rline, 
            args_rstation, 
            args_nodeid,
            Path::new(shot_filename_name)
                .file_stem()
                .and_then(|stem| stem.to_str())
                .unwrap_or(shot_filename_name),
    );
    assert_eq!(filename_str, "/data/output/00001234_00000056_0000000789_20251809.SEGD");
}