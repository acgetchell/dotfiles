# Scientific Basis

Targets use unnormalized natural-log weights. Transition correctness and
diagnostic interpretation are separate contracts. Diagnostics operate on
already collected, finite, equally weighted observations from multiple chains;
they do not certify convergence or ergodicity. Checkpoints promise exact seeded
continuation in the same build, including the generator's current state.
There is no adaptation. The coupled checkpoint also preserves fixed proposal
state, which determines its transition kernel.
