use nalgebra;

pub fn get_pitch_rotation_matrix(pitch: f64) -> [[f64; 3]; 3] {
    let c = pitch.cos();
    let s = pitch.sin();
    [
        [c, 0.0, -s],
        [0.0, 1.0, 0.0],
        [s, 0.0, c],
    ]
}

pub fn get_roll_rotaion_matrix(roll: f64) -> [[f64; 3]; 3] {
    let c = roll.cos();
    let s = roll.sin();
    [
        [1.0, 0.0, 0.0],
        [0.0, c, -s],
        [0.0, s, c],
    ]
}

pub fn get_yaw_rotation_matrix(yaw: f64) -> [[f64; 3]; 3] {
    let c = yaw.cos();
    let s = yaw.sin();
    [
        [c, s, 0.0],
        [-s, c, 0.0],
        [0.0, 0.0, 1.0],
    ]
}

pub fn get_vic_rotation_matrix(pitch: f64, roll: f64) -> [[f64; 3]; 3] {
    let pitch_matrix = get_pitch_rotation_matrix(pitch);
    let roll_matrix = get_roll_rotaion_matrix(roll);

    (nalgebra::Matrix3::from(pitch_matrix) * nalgebra::Matrix3::from(roll_matrix)).into()
}

pub fn get_vne_rotation_matrix(pitch: f64, roll: f64, yaw: f64) -> [[f64; 3]; 3] {
    let vic_matrix = get_vic_rotation_matrix(pitch, roll);
    let yaw_matrix = get_yaw_rotation_matrix(yaw);

    (nalgebra::Matrix3::from(yaw_matrix) * nalgebra::Matrix3::from(vic_matrix)).into()
}

pub fn get_pitch_roll(gx: f64, gy: f64, gz: f64) -> (f64, f64) {
    let pitch: f64 =
        (gx as f64).atan2(((gy as f64).powf(2.0) + (gz as f64).powf(2.0)).sqrt());
    let roll: f64 =
        (-gy as f64).atan2(gz as f64);

    (pitch, roll)
}

#[test]
fn test_pitch_roll() {
    let gx = 0.04331;
    let gy = 0.049776;
    let gz = 0.98576;

    let (pitch, roll) = get_pitch_roll(gx, gy, gz);

    dbg!(pitch/std::f64::consts::PI*180.0, roll/std::f64::consts::PI*180.0);

    assert_eq!((pitch/std::f64::consts::PI*180.0 * 100.0).round() / 100.00, -2.51);
    assert_eq!((roll/std::f64::consts::PI*180.0 * 100.0).round() / 100.00, -2.89);
}

#[test]
fn test_vic_rotation_pitch() {
    let pitch = -2.8 * std::f64::consts::PI / 180.0; // 2.5 degrees
    let roll = -3.1 * std::f64::consts::PI / 180.0; // 2.5 degrees
    // let roll = 0.0;  // 0 degrees

    let data = nalgebra::Vector3::new(1.0, 0.0, 0.0);

    let vic_matrix = get_vic_rotation_matrix(-pitch, -roll);

    let compensated_data = nalgebra::Matrix3::from(vic_matrix) * data;

    dbg!(vic_matrix, compensated_data);

    // Test the properties of the rotation matrices
    assert_eq!((compensated_data[0] * 10.0).round() / 10.0, 0.0);
    assert_eq!((compensated_data[1] * 10.0).round() / 10.0, 0.0);
    assert_eq!((compensated_data[2] * 10.0).round() / 10.0, 1.0);
}

#[test]
fn test_vic_rotation_roll() {
    let pitch = 0.0;  // 0 degrees
    let roll = std::f64::consts::PI / 2.0; // 90 degrees

    let data = nalgebra::Vector3::new(0.0, 1.0, 0.0);

    let vic_matrix = get_vic_rotation_matrix(-pitch, -roll);

    let compensated_data = nalgebra::Matrix3::from(vic_matrix) * data;

    // dbg!(compensated_data);

    // Test the properties of the rotation matrices
    assert_eq!((compensated_data[0] * 10.0).round() / 10.0, 0.0);
    assert_eq!((compensated_data[1] * 10.0).round() / 10.0, 0.0);
    assert_eq!((compensated_data[2] * 10.0).round() / 10.0, 1.0);
}

#[test]
fn test_vne_rotation_yaw() {
    // let pitch = -2.7 * std::f64::consts::PI / 180.0;
    // let roll = -3.0 * std::f64::consts::PI / 180.0;
    // let yaw = 201.2 * std::f64::consts::PI / 180.0;
    let pitch = 0.0 * std::f64::consts::PI / 180.0;
    let roll = 0.0 * std::f64::consts::PI / 180.0;
    let yaw = 90.0 * std::f64::consts::PI / 180.0;

    let data = nalgebra::Vector3::new(1.0, 0.0, 0.0);

    let vne_matrix = get_vne_rotation_matrix(-pitch, -roll, -yaw);

    // dbg!(vne_matrix);

    let compensated_data = nalgebra::Matrix3::from(vne_matrix) * data;

    // dbg!(compensated_data);

    // Test the properties of the rotation matrices
    assert_eq!((compensated_data[0] * 10.0).round() / 10.0, 0.0);
    assert_eq!((compensated_data[1] * 10.0).round() / 10.0, -1.0);
    assert_eq!((compensated_data[2] * 10.0).round() / 10.0, 0.0);
}