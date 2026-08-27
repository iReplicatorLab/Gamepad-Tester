use std::sync::Arc;

use crate::session::SampleSource;

#[cfg(target_os = "linux")]
mod linux;
#[cfg(not(target_os = "linux"))]
mod gilrs_backend;

pub fn create_backend() -> Arc<dyn SampleSource> {
    #[cfg(target_os = "linux")]
    {
        Arc::new(linux::LinuxGamepadBackend::new())
    }
    #[cfg(not(target_os = "linux"))]
    {
        Arc::new(gilrs_backend::GilrsGamepadBackend::new())
    }
}
