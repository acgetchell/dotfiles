use warmup_fixture::{adaptive::WarmupSteps, prelude::*};

struct Fixed(bool);
impl Proposal for Fixed {
    type Metadata = ();
    fn transition(&mut self, state: &mut i64) -> Outcome {
        if self.0 { *state += 1; Outcome::Accepted } else { Outcome::Rejected }
    }
    fn metadata(&mut self, _: Outcome) {}
}

#[test]
fn transition_and_boundary_contracts() {
    assert!(WarmupSteps::new(0).is_err());
    assert!(WarmupSteps::new(1001).is_err());
    let steps = WarmupSteps::new(100).unwrap();
    for accepted in [true, false] {
        for delayed in [true, false] {
            let mut chain = Chain::new(Fixed(accepted));
            let count = if delayed { chain.warmup_delayed(&steps) } else { chain.warmup_mut(&steps) };
            assert_eq!(count, if accepted { 100 } else { 0 });
            assert_eq!(chain.state, count as i64);
        }
    }
}
