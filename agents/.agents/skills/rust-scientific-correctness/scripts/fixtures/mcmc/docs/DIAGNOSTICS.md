# Diagnostic Contracts

The input is a flattened pool of finite observations. Return one-based pooled
ranks in original observation order. Equal values share the arithmetic mean of
their occupied rank positions. Empty input returns an empty vector. NaN and
infinity are outside this fixture's input domain. Rank computation is
deterministic and does not use an RNG or depend on how observations were sampled.
