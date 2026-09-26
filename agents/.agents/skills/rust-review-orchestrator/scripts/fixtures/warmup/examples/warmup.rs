use warmup_fixture::{adaptive::WarmupSteps, prelude::*};
struct Increment;
impl Proposal for Increment {
    type Metadata = ();
    fn transition(&mut self, state: &mut i64) -> Outcome { *state += 1; Outcome::Accepted }
    fn metadata(&mut self, _: Outcome) {}
}
fn main() {
    let count = Chain::new(Increment).warmup_mut(&WarmupSteps::new(10).unwrap());
    println!("accepted={count}");
}
