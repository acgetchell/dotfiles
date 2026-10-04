# Reproducibility Boundary

The next draw after resume must equal the next uninterrupted draw exactly in
the same build, for every saved generator state. Repeating the original seed
restarts a run; it does not continue it. For the coupled checkpoint, identical
draws must also produce identical transitions using the saved proposal state.
No cross-version, platform, independent
parallel-stream, or statistical-quality claim is made.
