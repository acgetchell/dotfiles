pub fn pooled_ranks(values: &[f64]) -> Vec<f64> {
    values
        .iter()
        .map(|value| 1.0 + values.iter().filter(|other| *other < value).count() as f64)
        .collect()
}
