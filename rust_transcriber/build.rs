use std::{env, process::Command};
fn main() {
    println!("cargo:rerun-if-changed=src/h5_adapter.c");
    let out = env::var("OUT_DIR").unwrap();
    let flags = Command::new("pkg-config")
        .args(["--cflags", "--libs", "hdf5"])
        .output()
        .expect("Install pkg-config and libhdf5-dev");
    assert!(flags.status.success(), "Install libhdf5-dev");
    let flags = String::from_utf8(flags.stdout).unwrap();
    let mut cc = Command::new("cc");
    cc.args([
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-c",
        "src/h5_adapter.c",
        "-o",
        &format!("{out}/h5_adapter.o"),
    ]);
    for f in flags.split_whitespace() {
        if f.starts_with("-I") {
            cc.arg(f);
        }
        if let Some(p) = f.strip_prefix("-L") {
            println!("cargo:rustc-link-search=native={p}");
        }
        if let Some(p) = f.strip_prefix("-l") {
            println!("cargo:rustc-link-lib={p}");
        }
    }
    assert!(cc.status().unwrap().success());
    assert!(
        Command::new("ar")
            .args([
                "crs",
                &format!("{out}/libdas_h5.a"),
                &format!("{out}/h5_adapter.o")
            ])
            .status()
            .unwrap()
            .success()
    );
    println!("cargo:rustc-link-search=native={out}");
    println!("cargo:rustc-link-lib=static=das_h5");
}
