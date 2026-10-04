#[path = "proposal_state.rs"]
pub mod proposal_state;

use self::proposal_state::ProposalState;

pub struct Snapshot {
    pub current_state: u64,
    pub proposal: ProposalState,
}

pub struct Chain {
    pub rng_state: u64,
    pub proposal: ProposalState,
}

pub fn resume(snapshot: &Snapshot) -> Chain {
    Chain {
        rng_state: snapshot.current_state,
        proposal: ProposalState::default(),
    }
}
