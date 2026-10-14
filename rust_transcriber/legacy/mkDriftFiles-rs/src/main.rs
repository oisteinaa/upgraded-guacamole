use clap::{Parser, ValueEnum};
use postgres::{Client, NoTls};
use std::env;
use std::error::Error;
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone)]
struct SyncSession {
    phase: f64,
    measure_time: f64,
    duration: f64,
    csc_drift: f64,
    t0: f64,
}

#[derive(Debug, Clone)]
struct ClogSession {
    time: f64,
    online_drift: f64,
    diff: f64,
}

#[derive(Copy, Clone, Debug, PartialEq, Eq, PartialOrd, Ord, ValueEnum)]
enum Mode {
    Phase,
    Freq,
    Combined,
    Clog,
}

#[derive(Parser, Debug)]
#[command(version, about, long_about = None)]
struct Args {
    /// Node ID
    #[arg(long)]
    nodeid: i32,

    /// Start time as epoch seconds. Defaults to one hour before --to.
    #[arg(long = "from")]
    fromtime: Option<i64>,

    /// End time as epoch seconds
    #[arg(long = "to")]
    totime: i64,

    /// Base VENATOR directory
    #[arg(long, default_value = "/raid1/VENATOR")]
    basedir: PathBuf,

    /// Drift calculation mode
    #[arg(long, value_enum, default_value_t = Mode::Phase)]
    mode: Mode,
}

impl Args {
    fn fromtime(&self) -> i64 {
        self.fromtime.unwrap_or(self.totime - 3600)
    }
}

fn setting_from_productroot(key: &str) -> Option<String> {
    let productroot = env::var("PRODUCTROOT").ok()?;
    let settings = fs::read_to_string(Path::new(&productroot).join("config/settings.ini")).ok()?;

    for line in settings.lines() {
        let mut parts = line.splitn(2, '=');
        if parts.next()?.trim() == key {
            return parts.next().map(|value| value.trim().to_string());
        }
    }

    None
}

fn connect_db() -> Result<Client, Box<dyn Error>> {
    let host = env::var("VENATOR_DB_HOST")
        .ok()
        .or_else(|| setting_from_productroot("db_host"))
        .ok_or("Missing DB host: set VENATOR_DB_HOST or PRODUCTROOT/config/settings.ini db_host")?;
    let dbname = env::var("VENATOR_DB_NAME").unwrap_or_else(|_| "venatordb".to_string());
    let user = env::var("VENATOR_DB_USER").unwrap_or_else(|_| "venatordms".to_string());
    let password = env::var("VENATOR_DB_PASSWORD").unwrap_or_else(|_| "obs".to_string());

    let conn = format!("host={host} dbname={dbname} user={user} password={password}");

    dbg!(&conn);
    Ok(Client::connect(&conn, NoTls)?)
}

fn get_from_db(
    client: &mut Client,
    nodeid: i32,
    fromtime: i64,
    totime: i64,
) -> Result<Vec<SyncSession>, Box<dyn Error>> {
    let qry = r#"
        SELECT
            "0x0702"::double precision,
            EXTRACT(epoch FROM "0x0703")::double precision AS measure_time,
            EXTRACT(epoch FROM "0x0703" - "0x0715")::double precision AS duration,
            "0x0713"::double precision AS c,
            EXTRACT(epoch FROM "0x0715")::double precision AS t0
        FROM csac_qc
        WHERE "0x0703" > timestamp 'epoch' + $1 * interval '1 seconds'
          AND "0x0715" < timestamp 'epoch' + $2 * interval '1 seconds'
          AND type LIKE 'dwn%'
          AND node_id = $3
        ORDER BY "0x0703";
    "#;

    // println!("Not test {}", qry);
    let fromtime: f64 = fromtime as f64;
    let totime: f64 = totime as f64;
    
    let rows = client.query(qry, &[&fromtime, &totime, &nodeid])?;
    if rows.is_empty() {
        println!("No sync sessions found for node {nodeid} between {fromtime} and {totime}.");
        return Ok(Vec::new());
    }

    Ok(rows
        .into_iter()
        .map(|row| SyncSession {
            phase: row.get(0),
            measure_time: row.get(1),
            duration: row.get(2),
            csc_drift: row.get(3),
            t0: row.get(4),
        })
        .collect())
}

fn get_clog_session(
    client: &mut Client,
    nodeid: i32,
    totime: i64,
) -> Result<Option<ClogSession>, Box<dyn Error>> {
    let qry = r#"
        SELECT
            EXTRACT(epoch FROM time)::double precision,
            "0x0712"::double precision,
            diff::double precision
        FROM clog2020_1
        WHERE node_id = $1
          AND time < timestamp 'epoch' + $2 * interval '1 seconds'
        ORDER BY time DESC
        LIMIT 1;
    "#;

    println!("{qry}");
    let totime: f64 = totime as f64;

    let rows = client.query(qry, &[&nodeid, &totime])?;
    Ok(rows.into_iter().next().map(|row| ClogSession {
        time: row.get(0),
        online_drift: row.get(1),
        diff: row.get(2),
    }))
}

fn drift_paths(nodeid: i32, t0: f64, basedir: &Path) -> Result<(PathBuf, PathBuf), Box<dyn Error>> {
    let node_dir = basedir
        .join("RAW")
        .join(format!("NODE_{nodeid:010}"))
        .join("driftfiles");
    let common_dir = basedir.join("driftfiles");

    fs::create_dir_all(&node_dir)?;
    fs::create_dir_all(&common_dir)?;

    let filename = format!("{}_{nodeid:010}.drift", t0 as i64);
    Ok((node_dir.join(&filename), common_dir.join(filename)))
}

fn write_drift_file(
    nodeid: i32,
    t0: f64,
    a: f64,
    b: f64,
    c: f64,
    dt: f64,
    basedir: &Path,
    drift_type: &str,
) -> Result<(), Box<dyn Error>> {
    let (node_path, common_path) = drift_paths(nodeid, t0, basedir)?;
    let mut out =
        format!("[{drift_type}]\ndt={dt:.6}\nt0={t0:.6}\na={a:.16}\nb={b:.16}\nc={c:.16}\n");

    if drift_type == "LINEAR" {
        out.push_str(&format!("drift={}\n", (a * dt + b) as i64));
    } else if drift_type == "PARABOLIC" {
        out.push_str(&format!(
            "drift={} {} {}\n",
            (a * dt * dt + b * dt + c) as i64,
            (a * dt * dt) as i64,
            (b * dt) as i64
        ));
    }

    fs::write(&node_path, &out)?;
    fs::write(&common_path, out)?;
    println!("Writing drift files to {} and {} for node {}", &node_path.display(), &common_path.display(), nodeid);
    Ok(())
}

fn linear_fit_fixed_intercept(t: &[f64], y: &[f64], intercept: f64) -> f64 {
    let denominator: f64 = t.iter().map(|x| x * x).sum();
    if denominator == 0.0 {
        return 0.0;
    }

    let numerator: f64 = t
        .iter()
        .zip(y.iter())
        .map(|(x, yy)| x * (yy - intercept))
        .sum();
    numerator / denominator
}

fn parabola_fit_fixed_c(t: &[f64], y: &[f64], c: f64) -> (f64, f64) {
    let s2: f64 = t.iter().map(|x| x * x).sum();
    let s3: f64 = t.iter().map(|x| x * x * x).sum();
    let s4: f64 = t.iter().map(|x| x * x * x * x).sum();
    let y_adj: Vec<f64> = y.iter().map(|yy| yy - c).collect();
    let r1: f64 = t.iter().zip(y_adj.iter()).map(|(x, yy)| x * x * yy).sum();
    let r2: f64 = t.iter().zip(y_adj.iter()).map(|(x, yy)| x * yy).sum();
    let det = s4 * s2 - s3 * s3;

    if det == 0.0 {
        return (0.0, 0.0);
    }

    ((r1 * s2 - r2 * s3) / det, (s4 * r2 - s3 * r1) / det)
}

fn phase_method(
    client: &mut Client,
    nodeid: i32,
    fromtime: i64,
    totime: i64,
    basedir: &Path,
) -> Result<(f64, f64, f64), Box<dyn Error>> {
    let syncsessions = get_from_db(client, nodeid, fromtime, totime)?;
    println!("{syncsessions:?}");

    if syncsessions.is_empty() {
        return Err("No sync sessions found".into());
    }

    let c = syncsessions[0].csc_drift;
    let t0 = syncsessions[0].t0;
    let dt = syncsessions[0].duration;

    let mut t = vec![0.0];
    let mut y = vec![c];
    for sync in syncsessions.iter().skip(1) {
        y.push(sync.phase);
        t.push(sync.duration);
    }

    let linear_a = linear_fit_fixed_intercept(&t, &y, c);
    write_drift_file(nodeid, t0, linear_a, 0.0, c, dt, basedir, "LINEAR")?;

    let mut a = linear_a;
    let mut b = 0.0;
    if y.len() > 2 {
        let diff = y[y.len() - 1] - y[1];
        if (diff > 0.0 && y[y.len() - 1] > 0.0) || (diff < 0.0 && y[y.len() - 1] < 0.0) {
            (a, b) = parabola_fit_fixed_c(&t, &y, c);
            write_drift_file(nodeid, t0, a, b, c, dt, basedir, "PARABOLIC")?;
        }
    }

    println!("Fitted parameters: a={a}, b={b} C={c}");
    Ok((a, b, c))
}

fn frequency_series(syncsessions: &[SyncSession], t0: f64) -> (Vec<f64>, Vec<f64>) {
    let mut t = Vec::new();
    let mut f = Vec::new();

    for i in 1..syncsessions.len() {
        let diff_col2 = syncsessions[i].phase - syncsessions[i - 1].phase;
        let diff_col3 = syncsessions[i].measure_time - syncsessions[i - 1].measure_time;
        let avg_time = (syncsessions[i].measure_time + syncsessions[i - 1].measure_time) / 2.0 - t0;
        if diff_col3 != 0.0 {
            t.push(avg_time);
            f.push(diff_col2 / diff_col3);
            println!("({i}) {avg_time} {}", diff_col2 / diff_col3);
        } else {
            println!("({i}) Division by zero");
        }
    }

    (t, f)
}

fn freq_method(
    client: &mut Client,
    nodeid: i32,
    fromtime: i64,
    totime: i64,
    basedir: &Path,
) -> Result<(f64, f64, f64), Box<dyn Error>> {
    let syncsessions = get_from_db(client, nodeid, fromtime, totime)?;
    println!("Freq method");

    if syncsessions.len() <= 1 {
        return Err("Not enough sync sessions found".into());
    }

    println!("Diffs of column 2 divided by diffs of column 3:");
    let t0 = syncsessions[0].t0;
    let (t, f) = frequency_series(&syncsessions, t0);
    if t.is_empty() {
        return Err("No usable frequency samples found".into());
    }

    let b = f[0] / 10.0;
    let c = 0.0;
    let mut a = linear_fit_fixed_intercept(&t, &f, b);
    a *= 0.5;

    let t_end = *t.last().unwrap();
    let t_last = syncsessions.last().unwrap().measure_time;
    let t_start = syncsessions.last().unwrap().t0;
    let dt = t_last - t_start;
    let integral = a * t_end * t_end + b * t_end;

    println!("Integral of fitted curve at t={t_end}: {integral}");
    println!("Fitted frequency drift rate: a={a}, C={c}");
    write_drift_file(nodeid, t0, a, b, c, dt, basedir, "PARABOLIC")?;
    Ok((a, b, c))
}

fn combined_method(
    client: &mut Client,
    nodeid: i32,
    fromtime: i64,
    totime: i64,
    basedir: &Path,
) -> Result<(f64, f64, f64), Box<dyn Error>> {
    let syncsessions = get_from_db(client, nodeid, fromtime, totime)?;
    println!("Frequency/Phase combined mode selected");

    if syncsessions.len() <= 1 {
        return Err("Not enough sync sessions found".into());
    }

    println!("Diffs of column 2 divided by diffs of column 3:");
    let t0 = syncsessions[0].t0;
    let (t, f) = frequency_series(&syncsessions, t0);
    if t.is_empty() {
        return Err("No usable frequency samples found".into());
    }

    let mut b = f[0] / 10.0;
    let c = 0.0;
    let mut a = linear_fit_fixed_intercept(&t, &f, b);
    a *= 0.5;

    let t_end = *t.last().unwrap();
    let t_last = syncsessions.last().unwrap().measure_time;
    let t_start = syncsessions.last().unwrap().t0;
    let last_phase = syncsessions.last().unwrap().phase;
    let b_new = (last_phase - (a * (t_last - t_start).powi(2) + c)) / (t_last - t_start);
    println!(
        "{a} {b} {b_new} {c} {t_last} {t_start} {} {t_end} {last_phase}",
        t_last - t_start
    );
    b = b_new;
    let integral = a * t_end * t_end + b * t_end;
    let dt = t_last - t_start;

    println!("Integral of fitted curve at t={t_end}: {integral}");
    println!("Fitted frequency drift rate: a={a}, C={c}");
    write_drift_file(nodeid, t0, a, b, c, dt, basedir, "PARABOLIC")?;
    Ok((a, b, c))
}

fn clog_start_method(
    client: &mut Client,
    nodeid: i32,
    fromtime: i64,
    totime: i64,
    basedir: &Path,
) -> Result<(f64, f64, f64), Box<dyn Error>> {
    let clog = get_clog_session(client, nodeid, totime)?.ok_or("No clog session found")?;
    let syncsessions = get_from_db(client, nodeid, fromtime, totime)?;

    println!("{clog:?} {syncsessions:?}");
    println!("Frequency/Phase combined with CLOG start mode selected");

    if syncsessions.len() <= 1 {
        return Err("Not enough sync sessions found".into());
    }

    println!("Diffs of column 2 divided by diffs of column 3:");
    let t0 = clog.time;
    let (mut t, mut f) = frequency_series(&syncsessions, t0);
    if t.is_empty() {
        return Err("No usable frequency samples found".into());
    }

    let mut b = clog.diff / 600.0;
    f[0] = b;
    t[0] = 0.0;
    let c = clog.online_drift;

    println!("{t:?} {f:?}");
    let mut a = linear_fit_fixed_intercept(&t, &f, b);
    a *= 0.5;

    let t_end = *t.last().unwrap();
    let t_last = syncsessions.last().unwrap().measure_time;
    let t_start = clog.time;
    let last_phase = syncsessions.last().unwrap().phase;
    let b_new = (last_phase - (a * (t_last - t_start).powi(2) + c)) / (t_last - t_start);
    println!(
        "{a} {b} {b_new} {c} {t_last} {t_start} {} {t_end} {last_phase}",
        t_last - t_start
    );
    b = b_new;
    let integral = a * t_end * t_end + b * t_end;
    let dt = t_last - t_start;

    println!("Integral of fitted curve at t={t_end}: {integral}");
    println!("Fitted frequency drift rate: a={a}, C={c}");
    write_drift_file(nodeid, t0, a, b, c, dt, basedir, "PARABOLIC")?;
    Ok((a, b, c))
}

fn run(args: &Args) -> Result<(), Box<dyn Error>> {
    let mut client = connect_db()?;

    let fromtime = args.fromtime();

    match args.mode {
        Mode::Phase => {
            phase_method(
                &mut client,
                args.nodeid,
                fromtime,
                args.totime,
                &args.basedir,
            )?;
        }
        Mode::Freq => {
            freq_method(
                &mut client,
                args.nodeid,
                fromtime,
                args.totime,
                &args.basedir,
            )?;
        }
        Mode::Combined => {
            combined_method(
                &mut client,
                args.nodeid,
                fromtime,
                args.totime,
                &args.basedir,
            )?;
        }
        Mode::Clog => {
            clog_start_method(
                &mut client,
                args.nodeid,
                fromtime,
                args.totime,
                &args.basedir,
            )?;
        }
    }

    Ok(())
}

fn main() {
    let args = Args::parse();

    if let Err(err) = run(&args) {
        eprintln!("{err}");
        std::process::exit(1);
    }
}
