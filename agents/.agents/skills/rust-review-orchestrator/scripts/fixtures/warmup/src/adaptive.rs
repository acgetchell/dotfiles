//! Explicit bounded warmup; returned draws are discarded.
use crate::{Chain, Outcome, Proposal};

/// Bounded positive warmup length.
pub struct WarmupSteps(usize);

impl WarmupSteps {
    /// Parse an allowed warmup length.
    ///
    /// # Errors
    /// Returns [`InvalidSteps`] for zero or more than 1000 transitions.
    pub fn new(value: usize) -> Result<Self, InvalidSteps> {
        if (1..=1000).contains(&value) { Ok(Self(value)) } else { Err(InvalidSteps(value)) }
    }
}

/// Rejected warmup length, retaining the caller's input.
#[derive(Debug, PartialEq)]
pub struct InvalidSteps(pub usize);

impl<P: Proposal> Chain<P> {
    /// Count accepted in-place warmup transitions without retaining a trace.
    pub fn warmup_mut(&mut self, steps: &WarmupSteps) -> usize {
        (0..steps.0).filter(|_| self.step_mut().outcome == Outcome::Accepted).count()
    }
    /// Count accepted delayed warmup transitions without retaining a trace.
    pub fn warmup_delayed(&mut self, steps: &WarmupSteps) -> usize {
        (0..steps.0).filter(|_| self.step_delayed().outcome == Outcome::Accepted).count()
    }
}
