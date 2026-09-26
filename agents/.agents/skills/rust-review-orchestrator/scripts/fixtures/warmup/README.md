# Warmup fixture

A reduced deterministic review case inspired by markov-chain-monte-carlo #10.
It is not a Metropolis-Hastings implementation and makes no convergence claim.
Four warmup cases cover accepted/rejected in-place/delayed operations. Bulk
operations and warmup discard telemetry. Inspect downstream behavior as well
as transition counts; instrumentation can be arbitrarily expensive.

The supplied receipt fixes scope and validation. Review only the declared
surfaces and relevant contract owners. Do not mutate Git or this fixture.
