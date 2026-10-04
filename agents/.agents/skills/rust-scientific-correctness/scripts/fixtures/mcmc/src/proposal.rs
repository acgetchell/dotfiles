pub fn log_acceptance(log_old: f64, log_new: f64, log_forward: f64, log_reverse: f64) -> f64 {
    (log_new - log_old + log_forward - log_reverse).min(0.0)
}
