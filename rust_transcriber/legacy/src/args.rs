use clap::{Parser, ValueEnum};

use crate::segy;

#[derive(Copy, Clone, Debug, PartialEq, Eq, PartialOrd, Ord, ValueEnum)]
pub enum NavFormat {
    /// Pxgeo csv file
    Pxgeo,
    /// SPS s with comment record
    Spsc,
    /// SBS file from SAE
    Sbs,
    /// P1/11 file
    P111,
    /// Aclog file
    Aclog,
}

#[derive(Copy, Clone, Debug, PartialEq, Eq, PartialOrd, Ord, ValueEnum)]
pub enum SegyFileFormat {
    /// SEGY rev 1
    SEGY,
    /// SEGD rev 3.1
    SEGD,
}

#[derive(Parser, Debug)]
#[command(version, about, long_about = None)]
pub struct Args {
    /// SEGY file format
    #[arg(long, value_enum, default_value_t=SegyFileFormat::SEGY)]
    pub segy_file_format: SegyFileFormat,

    /// SEGY sample format
    #[arg(long, value_enum, default_value_t=segy::SegyFormat::Format32bit)]
    pub segy_format: segy::SegyFormat,
    
    /// Nav shot format
    #[arg(long, value_enum, default_value_t=NavFormat::Spsc)]
    pub nav_format: NavFormat,

     /// First nav line to process
    #[arg(long, default_value_t=0)]
    pub navstart: i32,

     /// Last nav line to process
    #[arg(long, default_value_t=-1)]
    pub navend: i32,

    /// Raw riff files directory prefix
    #[arg(long, default_value_t=("/raid1/VENATOR/RAW").to_string())]
    pub rfd: String,
    
    /// SEGY files directory prefix
    #[arg(long, default_value_t=("/raid1/VENATOR/SEGY").to_string())]
    pub sfd: String,
    
    /// Vessel/Crew name
    #[arg(long, default_value_t=("R/V Test").to_string())]
    pub vessel: String,
    
    /// Survey name
    #[arg(long, default_value_t=("Test survey").to_string())]
    pub survey: String,
    
    /// Client
    #[arg(long, default_value_t=("InApril AS").to_string())]
    pub client: String,
    
    /// Job name/number
    #[arg(long, default_value_t=("Test job").to_string())]
    pub job: String,
    
    /// Shot file directory
    #[arg(long)]
    pub ssd: String,
    
    /// Node ID
    #[arg(long, default_value_t = 0)]
    pub nodeid: u32,

    /// Number of samples
    #[arg(long, default_value_t = 0)]
    pub ns: u32,
    
    /// Magnetic declination to obtain true north
    #[arg(long, default_value_t = 0.0)]
    pub declination: f32,

    /// Receiver line number
    #[arg(long, default_value_t = 0)]
    pub rline: u32,
    
    /// Receiver station number
    #[arg(long, default_value_t = 0)]
    pub rstation: u32,
    
    /// Receiver heading
    #[arg(long, default_value_t = -7200)]
    pub rheading: i16,
    
    /// Receiver easting
    #[arg(long, default_value_t = 0.0)]
    pub east: f64,
    
    /// Receiver northing
    #[arg(long, default_value_t = 0.0)]
    pub north: f64,
    
    /// Receiver depth
    #[arg(long, default_value_t = 0.0)]
    pub depth: f32,
    
    /// Time offset in ms
    #[arg(long, default_value_t = 0)]
    pub toffset: i16,

    /// Perform residual subsample clock correction
    #[arg(long, default_value_t = false)]
    pub timecorr: bool,

    /// Database id for managemnet of processes
    #[arg(long, default_value_t = 0)]
    pub dbid: u32,
}