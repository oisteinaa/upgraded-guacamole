use clap::{Parser, ValueEnum};
use serde::Serialize;
use std::path::PathBuf;

#[derive(Clone, Copy, Debug, PartialEq, Eq, ValueEnum, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Mode {
    Continuous,
    Shot,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, ValueEnum, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Format {
    Segy,
    Segd,
    Both,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq, ValueEnum, Serialize)]
pub enum Crs {
    Wgs84,
    Utm33n,
}
#[derive(Parser, Debug, Serialize)]
#[command(
    version,
    about = "Transcribe DAS HDF5 recordings to SEG-Y rev 1 / SEG-D rev 3.1"
)]
pub struct Args {
    /// Repeat for files, directories (recursive), or quoted glob patterns.
    #[arg(long, required = true)]
    pub input: Vec<String>,
    /// Inclusive native channel IDs, e.g. 1-130,50000-78000; 'all' selects all recorded channels.
    #[arg(long, default_value = "all")]
    pub channels: String,
    #[arg(long)]
    pub receivers_csv: PathBuf,
    #[arg(long)]
    pub lid: u32,
    #[arg(long, value_enum, default_value = "continuous")]
    pub mode: Mode,
    #[arg(long, value_enum, default_value = "segy")]
    pub format: Format,
    #[arg(long)]
    pub output: PathBuf,
    /// Continuous trace duration in seconds, rounded to the nearest whole sample.
    #[arg(long, default_value_t = 60.0)]
    pub trace_length: f64,
    /// One output per P1/11 file (repeatable, supports globs).
    #[arg(long)]
    pub p111: Vec<String>,
    /// Interpretation of source X,Y columns (13,14) in the supported legacy P1/11 layout.
    #[arg(long, value_enum)]
    pub p111_crs: Option<Crs>,
    /// Shot duration in seconds (required in shot mode).
    #[arg(long)]
    pub duration: Option<f64>,
    /// Start offset relative to shot time in seconds; may be negative.
    #[arg(long, default_value_t = 0.0, allow_hyphen_values = true)]
    pub offset: f64,
    /// Inclusive UTC RFC3339 start; an explicit timezone is required.
    #[arg(long)]
    pub start: Option<String>,
    /// Exclusive UTC RFC3339 end.
    #[arg(long)]
    pub end: Option<String>,
    /// Validate and print a JSON plan without creating outputs.
    #[arg(long)]
    pub dry_run: bool,
}
