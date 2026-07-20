# Dataframes And Plotting

Load this reference for notebooks that transform tabular data, use dataframe libraries, create plots, or save figures.

## Dataframe And I/O Choices

Prefer Polars when the repository has no conflicting standard and the workflow benefits from explicit expressions, lazy execution, or Arrow interoperability. Accept pandas when the repository standardizes on it, a dependency requires it, or the notebook intentionally studies pandas behavior.

Check:

- required columns and dtypes are validated before aggregation
- malformed rows are rejected or handled explicitly rather than silently coerced
- scans or lazy pipelines are used when data may exceed comfortable memory
- Parquet or Arrow is preferred for reusable typed intermediate tables when appropriate
- filtering and aggregation happen before conversion to Python lists or other eager copies
- ordering is explicit before presentation or artifact generation

Flag manual CSV parsing for dataframe-shaped work, unchecked dtype inference, silent dropping of bad rows, repeated list/array/dataframe conversions, and per-row Python operations where an expression is clearer.

## Scientific Data Contracts

When Rust or another producer supplies data, verify units, coordinate order, indexing base, dimension order, dtype, precision, missing-value behavior, and endianness. Treat NaN, infinity, overflow, underflow, and degenerate values deliberately. Route mathematical interpretation to `python-scientific-review`.

## Plotting

Use Matplotlib for stable static figures and headless validation. Use Plotly when interactive hover, zoom, faceting, or HTML artifacts provide real value.

Check:

- axes, units, legends, titles, scales, and uncertainty displays communicate the plotted quantity
- plotting code consumes dataframe columns or named arrays without duplicating transformation logic
- category and series ordering is deterministic
- color and marker choices remain interpretable in the target medium
- headless runs avoid browser-only side effects
- saved figures use deterministic paths and create parent directories
- tracked assets are refreshed only through their owning workflow

Build Plotly figures as objects and save HTML or JSON when batch interactivity matters. For headless execution, configure a noninteractive Matplotlib backend before importing `matplotlib.pyplot` when the repository does not already configure one; changing the backend after the `pyplot` import is too late to establish reliable headless behavior.
