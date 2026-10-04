#[derive(Clone, Copy)]
pub struct ProposalState {
    pub probability_one: f64,
}

impl Default for ProposalState {
    fn default() -> Self {
        Self { probability_one: 0.5 }
    }
}

impl ProposalState {
    pub fn probability_of(&self, candidate: u8) -> f64 {
        match candidate {
            0 => 1.0 - self.probability_one,
            1 => self.probability_one,
            _ => unreachable!("the proposal domain is states 0 and 1"),
        }
    }
}
