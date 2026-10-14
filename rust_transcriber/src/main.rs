mod args;
mod h5;
mod input;
mod navigation;
mod plan;
mod segd;
mod segy;
use args::{Args, Format};
use clap::Parser;
use std::{
    collections::BTreeMap,
    fs::{File, OpenOptions},
    io::{BufWriter, Seek, SeekFrom, Write},
    path::{Path, PathBuf},
    sync::atomic::{AtomicBool, Ordering},
};
pub type Result<T> = std::result::Result<T, Box<dyn std::error::Error>>;
pub fn fail<T>(s: impl Into<String>) -> Result<T> {
    Err(s.into().into())
}
static CANCEL: AtomicBool = AtomicBool::new(false);
extern "C" fn stop(_: i32) {
    CANCEL.store(true, Ordering::Relaxed);
}
pub fn check_cancel() -> Result<()> {
    if CANCEL.load(Ordering::Relaxed) {
        fail("Cancelled")
    } else {
        Ok(())
    }
}
fn event(value: serde_json::Value) {
    println!("{value}");
}
struct Pending {
    path: PathBuf,
    writer: BufWriter<File>,
}
impl Pending {
    fn new(final_path: &Path) -> Result<Self> {
        if final_path.exists() {
            return fail(format!("Output exists: {}", final_path.display()));
        }
        let mut path = final_path.as_os_str().to_os_string();
        path.push(".partial");
        let path = PathBuf::from(path);
        let file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&path)?;
        Ok(Self {
            path,
            writer: BufWriter::with_capacity(1 << 20, file),
        })
    }
    fn sync(&mut self) -> Result<()> {
        self.writer.flush()?;
        self.writer.get_ref().sync_all()?;
        Ok(())
    }
    fn publish(&mut self, p: &Path) -> Result<()> {
        self.sync()?;
        std::fs::hard_link(&self.path, p)?;
        Ok(())
    }
}
impl Drop for Pending {
    fn drop(&mut self) {
        let _ = std::fs::remove_file(&self.path);
    }
}
fn fill(
    w: &mut BufWriter<File>,
    offsets: &[u64],
    b: &plan::Block,
    a: &input::Archive,
) -> Result<()> {
    let c = &a.configs[b.config];
    let end = w.stream_position()?;
    let mut cols: Vec<_> = c.columns.iter().copied().enumerate().collect();
    cols.sort_by_key(|(_, col)| *col);
    let mut sample_offset = 0;
    for piece in &b.pieces {
        check_cancel()?;
        let info = &a.files[piece.file];
        if input::stamp(&info.path)? != (info.size, info.modified_ns) {
            return fail("Input changed since preflight");
        }
        let f = h5::H5::open(&info.path)?;
        for row in (0..piece.count).step_by(4096) {
            let rows = (piece.count - row).min(4096);
            let mut begin = 0;
            while begin < cols.len() {
                check_cancel()?;
                let mut stop = begin + 1;
                while stop < cols.len() && stop - begin < 64 && cols[stop].1 == cols[stop - 1].1 + 1
                {
                    stop += 1
                }
                let width = stop - begin;
                let data = f.slice(piece.row + row, cols[begin].1, rows, width)?;
                for (column, (trace, _)) in cols[begin..stop].iter().enumerate() {
                    let mut bytes = Vec::with_capacity(rows * 4);
                    for r in 0..rows {
                        let x = (data[r * width + column] * c.scale) as f32;
                        if !x.is_finite() {
                            return fail(format!(
                                "Nonfinite or overflowing sample in {}",
                                info.path.display()
                            ));
                        };
                        bytes.extend_from_slice(&x.to_be_bytes());
                    }
                    w.seek(SeekFrom::Start(
                        offsets[*trace] + ((sample_offset + row) * 4) as u64,
                    ))?;
                    w.write_all(&bytes)?;
                }
                begin = stop;
            }
        }
        if input::stamp(&info.path)? != (info.size, info.modified_ns) {
            return fail("Input changed during conversion");
        };
        sample_offset += piece.count;
    }
    w.seek(SeekFrom::Start(end))?;
    Ok(())
}
fn run(args: Args) -> Result<()> {
    event(serde_json::json!({"event":"indexing"}));
    let archive = input::index(&args.input, &args.channels)?;
    let receivers = input::receivers(&args.receivers_csv, args.lid)?;
    let plan = plan::build(&archive, &args, &receivers)?;
    let formats: Vec<_> = match args.format {
        Format::Both => vec![Format::Segy, Format::Segd],
        f => vec![f],
    };
    let ext = |f: Format| if f == Format::Segy { "sgy" } else { "segd" };
    let mut files = vec![];
    for output in &plan.outputs {
        for &format in &formats {
            let path = args.output.join(format!("{}.{}", output.name, ext(format)));
            let report = path.with_extension(format!("{}.json", ext(format)));
            for p in [&path, &report] {
                if p.exists() || PathBuf::from(format!("{}.partial", p.display())).exists() {
                    return fail(format!("Output or partial file exists: {}", p.display()));
                }
            }
            files.push(serde_json::json!({"path":path,"bytes":if format==Format::Segy{output.segy_bytes}else{output.segd_bytes},"records":output.blocks.len()}));
        }
    }
    for warning in &plan.warnings {
        event(serde_json::json!({"event":"warning","message":warning}));
    }
    event(
        serde_json::json!({"event":"preflight","files":files,"selected_channels":plan.selected_channels,"skipped_shots":plan.skipped_shots,"trace_length_seconds":args.trace_length}),
    );
    if args.dry_run {
        return Ok(());
    }
    check_cancel()?;
    std::fs::create_dir_all(&args.output)?;
    let total: usize = plan
        .outputs
        .iter()
        .map(|o| o.blocks.len() * formats.len())
        .sum();
    let mut done = 0;
    for output in &plan.outputs {
        for &format in &formats {
            let path = args.output.join(format!("{}.{}", output.name, ext(format)));
            let report_path = path.with_extension(format!("{}.json", ext(format)));
            let mut pending = Pending::new(&path)?;
            let mut report = Pending::new(&report_path)?;
            if format == Format::Segy {
                segy::file_header(
                    &mut pending.writer,
                    "SEE JSON CONFIGURATION METADATA",
                    archive.configs[output.blocks[0].config].dt as u16,
                    output.blocks[0].samples as u16,
                )?;
            } else {
                segd::file_header(&mut pending.writer)?;
            }
            let mut sequence = 0;
            for (i, b) in output.blocks.iter().enumerate() {
                check_cancel()?;
                let c = &archive.configs[b.config];
                let record = i as u32 + 1;
                if format == Format::Segd {
                    segd::record_header(&mut pending.writer, b, c, record)?
                }
                let mut offsets = Vec::with_capacity(c.channels.len());
                for (within, ch) in c.channels.iter().enumerate() {
                    sequence += 1;
                    let r = &receivers[ch];
                    offsets.push(if format == Format::Segy {
                        segy::trace_header(
                            &mut pending.writer,
                            b,
                            c,
                            r,
                            record,
                            sequence,
                            within as u32 + 1,
                        )?
                    } else {
                        segd::trace_header(&mut pending.writer, b, r, record, within as u32 + 1)?
                    });
                }
                fill(&mut pending.writer, &offsets, b, &archive)?;
                done += 1;
                event(
                    serde_json::json!({"event":"progress","completed":done,"total":total,"output":path}),
                );
            }
            pending.sync()?;
            let expected = if format == Format::Segy {
                output.segy_bytes
            } else {
                output.segd_bytes
            };
            if pending.writer.get_ref().metadata()?.len() != expected {
                return fail("Internal output size verification failed");
            }
            let selected: BTreeMap<_, _> = plan
                .selected_channels
                .iter()
                .map(|id| (*id, &receivers[id]))
                .collect();
            serde_json::to_writer_pretty(
                &mut report.writer,
                &serde_json::json!({"version":2,"format":format,"settings":args,"archive":archive,"output":output,"receivers":selected,"warnings":plan.warnings,"skipped_shots":plan.skipped_shots,"conventions":{"sample_values":"H5 value * dataScale, IEEE float32","receiver_crs":"EPSG:4326","segy_coordinates":"arcseconds, scalar -1000","segy_native_channel":"bytes 229-232 u32 big endian","segy_acquisition_time":"bytes 233-240 i64 Unix microseconds","segd_timestamp":"GPS microseconds since 1980-01-06; leap table through 2017-01-01","missing_samples":"exclude entire flagged file, never zero fill"}}),
            )?;
            report.sync()?;
            check_cancel()?;
            report.publish(&report_path)?;
            if let Err(e) = pending.publish(&path) {
                let _ = std::fs::remove_file(&report_path);
                return Err(e);
            }
            event(serde_json::json!({"event":"output_complete","path":path,"bytes":expected}));
        }
    }
    event(serde_json::json!({"event":"complete","outputs":files.len()}));
    Ok(())
}
fn main() {
    unsafe {
        libc::signal(libc::SIGINT, stop as *const () as libc::sighandler_t);
        libc::signal(libc::SIGTERM, stop as *const () as libc::sighandler_t);
    }
    if let Err(error) = run(Args::parse()) {
        event(serde_json::json!({"event":"error","message":error.to_string()}));
        std::process::exit(if CANCEL.load(Ordering::Relaxed) {
            130
        } else {
            1
        });
    }
}
