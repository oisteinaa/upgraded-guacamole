use crate::{Result, fail};
use std::{
    ffi::{CStr, CString, c_char, c_void},
    path::Path,
};
unsafe extern "C" {
    fn das_open(p: *const c_char) -> i64;
    fn das_close(f: i64);
    fn das_info(f: i64, n: *const c_char, d: *mut u64, k: *mut i32) -> i32;
    fn das_read(f: i64, n: *const c_char, o: *mut c_void, i: i32) -> i32;
    fn das_string(f: i64, n: *const c_char, o: *mut c_char, c: usize) -> i32;
    fn das_slice(f: i64, r: u64, c: u64, n: u64, m: u64, o: *mut f64) -> i32;
}
pub struct H5(i64);
impl Drop for H5 {
    fn drop(&mut self) {
        unsafe { das_close(self.0) }
    }
}
impl H5 {
    pub fn open(p: &Path) -> Result<Self> {
        use std::os::unix::ffi::OsStrExt;
        let s = CString::new(p.as_os_str().as_bytes())?;
        let id = unsafe { das_open(s.as_ptr()) };
        if id < 0 {
            return fail(format!("Cannot open HDF5 {}", p.display()));
        }
        Ok(Self(id))
    }
    pub fn info(&self, n: &str) -> Result<(Vec<usize>, i32)> {
        let n = CString::new(n)?;
        let mut dims = [1u64; 2];
        let mut kind = 0;
        let rank = unsafe { das_info(self.0, n.as_ptr(), dims.as_mut_ptr(), &mut kind) };
        if !(0..=2).contains(&rank) {
            return fail(format!(
                "Missing or unsupported H5 dataset {}",
                n.to_string_lossy()
            ));
        }
        Ok((
            dims[..rank as usize].iter().map(|x| *x as usize).collect(),
            kind,
        ))
    }
    pub fn scalar(&self, n: &str) -> Result<f64> {
        let (dims, kind) = self.info(n)?;
        if dims.iter().product::<usize>() != 1 || !(kind == 0 || kind == 1) {
            return fail(format!("Expected numeric scalar {n}"));
        }
        let name = CString::new(n)?;
        let mut v = 0.;
        if unsafe { das_read(self.0, name.as_ptr(), (&mut v as *mut f64).cast(), 0) } < 0 {
            return fail(format!("Cannot read {n}"));
        }
        Ok(v)
    }
    pub fn integers(&self, n: &str) -> Result<Vec<i64>> {
        let (dims, kind) = self.info(n)?;
        if dims.len() != 1 || kind != 0 || dims[0] > 10_000_000 {
            return fail(format!("Expected bounded integer vector {n}"));
        }
        let mut v = vec![0i64; dims[0]];
        let name = CString::new(n)?;
        if !v.is_empty() && unsafe { das_read(self.0, name.as_ptr(), v.as_mut_ptr().cast(), 1) } < 0
        {
            return fail(format!("Cannot read {n}"));
        }
        Ok(v)
    }
    pub fn string(&self, n: &str) -> Result<String> {
        let name = CString::new(n)?;
        let mut v = vec![0u8; 4096];
        if unsafe { das_string(self.0, name.as_ptr(), v.as_mut_ptr().cast(), v.len()) } < 0 {
            return fail(format!("Cannot read string {n}"));
        }
        Ok(unsafe { CStr::from_ptr(v.as_ptr().cast()) }
            .to_str()?
            .trim()
            .to_owned())
    }
    pub fn slice(&self, row: usize, col: usize, rows: usize, cols: usize) -> Result<Vec<f64>> {
        let n = rows.checked_mul(cols).ok_or("H5 slice too large")?;
        if n > 4_194_304 {
            return fail("H5 slice exceeds 32 MiB buffer");
        }
        let mut v = vec![0.; n];
        if n > 0
            && unsafe {
                das_slice(
                    self.0,
                    row as u64,
                    col as u64,
                    rows as u64,
                    cols as u64,
                    v.as_mut_ptr(),
                )
            } < 0
        {
            return fail("H5 slice read failed");
        }
        Ok(v)
    }
}
