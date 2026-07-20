# HPC And Headless Notebooks

Load this reference for CI, remote servers, HPC clusters, Slurm, Open OnDemand, scratch storage, or notebook environment setup.

## Environment

Prefer a repository dependency group and named command over ad hoc installation cells. Let the lockfile capture resolved versions unless repository policy requires exact declarations.

Provide separate commands for environment setup, interactive launch, lint, and deliberate execution. Keep routine checks lint-only when runtime cost depends on user-controlled parameters.

## Headless Execution

- Use `nbconvert`, `nbclient`, or a repository executor without modifying source notebooks.
- Configure a noninteractive plotting backend when needed.
- Write executed notebooks and artifacts under `target/`, `$SCRATCH`, or another documented output root.
- Make cache and output roots configurable when home-directory storage is unavailable or slow.
- Document whether dependency synchronization must occur before an offline compute job.
- Avoid browser-only rendering in batch jobs; save stable files instead.

Do not create a permanent `slow/` notebook category or execute-all recipe unless the repository explicitly requires one. State time, memory, service, and data assumptions for costly notebooks.

## Slurm And Open OnDemand

- Treat the Jupyter session as running inside a compute allocation when appropriate.
- Let long-running cells submit explicit jobs and later load their artifacts instead of monopolizing the notebook kernel.
- Build `sbatch` or `srun` arguments safely, with explicit paths, walltime, memory, output, and error locations.
- Make job IDs, run directories, logs, trace paths, and summary paths visible.
- Keep cluster modules, binaries, and service endpoints configurable rather than tied to one login environment.

## Validation

Run structured lint first. Execute only the affected notebook with bounded resources when runtime behavior is in scope. Record skipped cluster/service validation as an environment limitation rather than implying portability.
