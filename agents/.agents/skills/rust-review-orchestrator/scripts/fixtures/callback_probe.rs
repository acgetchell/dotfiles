use std::cell::Cell;
use warmup_fixture::{adaptive::WarmupSteps, prelude::*};
struct Counted<'a> { accepted: bool, calls: &'a Cell<usize> }
impl Proposal for Counted<'_> {
    type Metadata = ();
    fn transition(&mut self, state: &mut i64) -> Outcome {
        if self.accepted { *state += 1; Outcome::Accepted } else { Outcome::Rejected }
    }
    fn metadata(&mut self, _: Outcome) { self.calls.set(self.calls.get() + 1); }
}
fn main() {
    let steps = WarmupSteps::new(100).unwrap();
    for accepted in [true, false] {
        for delayed in [false, true] {
            for warmup in [true, false] {
                let calls = Cell::new(0);
                let mut chain = Chain::new(Counted { accepted, calls: &calls });
                match (warmup, delayed) {
                    (true, false) => { chain.warmup_mut(&steps); }
                    (true, true) => { chain.warmup_delayed(&steps); }
                    (false, false) => chain.run_mut(100),
                    (false, true) => chain.run_delayed(100),
                }
                println!("accepted={accepted} delayed={delayed} warmup={warmup} callbacks={}", calls.get());
            }
        }
    }
}
