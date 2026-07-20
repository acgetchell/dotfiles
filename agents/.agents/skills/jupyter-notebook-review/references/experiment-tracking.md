# Experiment Tracking

Load this reference only for notebooks that manage model training, learned proposals, hyperparameter sweeps, or comparable experiments requiring tracked lineage.

Do not add MLflow or another tracking service to simple quickstarts that only run a binary and plot artifacts.

## Contracts

Check:

- tracking URI, experiment name, artifact root, and credentials are configurable
- run identity is explicit and reruns are idempotent or intentionally distinct
- parameters, code revision, dataset/run identifiers, random seeds, environment details, and relevant metrics are recorded
- artifacts point to stable project or cluster storage rather than notebook-local blobs
- secrets and private metadata are never embedded in cells, outputs, logs, or committed configuration
- service unavailability fails clearly or follows a documented offline path

Keep tracking optional for ordinary headless notebook validation unless the notebook is specifically an integration test for the tracking system. Separate experiment execution from analysis so existing run artifacts can be inspected without starting a new run.

## Reproducibility

Record enough provenance to distinguish code, data, configuration, and stochastic state. Avoid treating a tracking record as a substitute for a locked environment or versioned dataset contract.

Validate the smallest safe path available. Do not create live remote runs merely to lint or structurally review a notebook.
