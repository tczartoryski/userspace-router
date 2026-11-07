#[cfg(any(target_os = "linux", feature = "linux-abi-check"))]
#[path = "../linux.rs"]
mod linux;
fn main() {
    #[cfg(target_os = "linux")]
    if let Err(error) = linux::run() {
        eprintln!("udp-router: {error}");
        std::process::exit(1);
    }
    #[cfg(not(target_os = "linux"))]
    {
        eprintln!("udp-router requires Linux and two explicitly precreated TUN interfaces; no network changes made");
        std::process::exit(1);
    }
}
