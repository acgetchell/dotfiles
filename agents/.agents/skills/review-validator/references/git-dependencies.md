# Validation Git Dependencies

Each `git_dependencies[].command` must match an exact `executions[].command`
and occur in at most one dependency declaration. Omit `command` to apply a
dependency to the entire unit. Both forms add constraints to repository-owned
contracts. For example, after executing this Cargo packaging command once,
declare its HEAD metadata dependency and the unit-wide index dependency:

```json
{
  "git_dependencies": [
    {
      "kind": "head",
      "command": "cargo publish --locked --dry-run --allow-dirty",
      "reason": "Package VCS metadata uses HEAD."
    },
    {
      "kind": "index",
      "reason": "Package selection and dirty metadata use tracked/index state."
    }
  ]
}
```

For multiple packaging commands, bind one HEAD declaration to each exact
command and retain the single command-less index declaration. Correcting an
unknown or duplicate binding changes payload metadata only; do not invent or
repeat an execution.

For a recipe that only uses tracked/nonignored worktree enumeration, first inspect
its implementation and pinned helper. Declare the exact executed command:

```json
{
  "kind": "input-selection",
  "command": "just ci",
  "selection_algorithm": "git-ls-files-cached-others-exclude-standard-v1",
  "reason": "The recipe selects tracked plus nonignored paths and checks worktree bytes."
}
```

This version binds the sorted unique union of `git ls-files -z` and
`git ls-files --others --exclude-standard -z` at the repository root. Runtime
captures bind actual selection membership, including absent tracked paths.
The equivalent plain `git ls-files --cached --others --exclude-standard -z`
command is supported directly. Other algorithms, Git environment overrides,
staged-blob reads, HEAD metadata, and history-dependent checks must use the
conservative dependency categories. Additional HEAD/index/history dependencies
apply to the whole unit without a `command`; this cannot weaken a repository
contract. Do not classify a command as enumeration merely because it invokes Git.

Unchanged membership and complete source identities can preserve a historical
passed early scheduling gate when no repository registry exists. That admission
remains `historical-source-pass`, with formal reuse unproven; it is not certified
current-metadata evidence. Failed, stale, incomplete or unproven selections never
release the gate. A repository-owned registry is still required for formal reuse.

Metadata resume archives existing regular raw logs and log directories before
returning a validator for replay. Its `validation_log_archives` receipt maps
original execution paths and identities to immutable copies and their verified
digests. Files retain raw bytes; directories use tar archives that preserve the
tree and symlink targets without following them. Preserve the archive manifest,
original captures and sealed evidence; never relabel their results.
