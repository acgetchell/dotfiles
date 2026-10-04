pub struct Snapshot {
    pub original_seed: u64,
    pub current_state: u64,
}

pub fn resume(snapshot: &Snapshot) -> u64 {
    snapshot.original_seed
}

pub fn next_draw(state: &mut u64) -> u64 {
    *state = state.wrapping_mul(3).wrapping_add(1);
    *state
}
