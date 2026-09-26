//! Reduced review fixture: deterministic transitions, not a statistical sampler.
pub mod adaptive;

/// Result of a transition attempt.
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Outcome { Accepted, Rejected }

/// Proposal with optional per-step telemetry.
pub trait Proposal {
    type Metadata;
    fn transition(&mut self, state: &mut i64) -> Outcome;
    fn metadata(&mut self, outcome: Outcome) -> Self::Metadata;
}

/// A completed transition and its telemetry.
pub struct Step<M> { pub outcome: Outcome, pub metadata: M }

/// Mutable owner of proposal and chain state.
pub struct Chain<P> { pub state: i64, pub proposal: P }

impl<P: Proposal> Chain<P> {
    /// Construct a chain from a proposal.
    pub fn new(proposal: P) -> Self { Self { state: 0, proposal } }
    /// Take an instrumented in-place step.
    pub fn step_mut(&mut self) -> Step<P::Metadata> {
        let outcome = self.proposal.transition(&mut self.state);
        Step { outcome, metadata: self.proposal.metadata(outcome) }
    }
    /// Take an instrumented delayed step (same deterministic fixture kernel).
    pub fn step_delayed(&mut self) -> Step<P::Metadata> { self.step_mut() }
    /// Take bulk in-place steps without retaining telemetry.
    pub fn run_mut(&mut self, steps: usize) {
        for _ in 0..steps { self.proposal.transition(&mut self.state); }
    }
    /// Take bulk delayed steps without retaining telemetry.
    pub fn run_delayed(&mut self, steps: usize) { self.run_mut(steps); }
}

/// Ordinary downstream imports.
pub mod prelude { pub use crate::{Chain, Outcome, Proposal}; }
