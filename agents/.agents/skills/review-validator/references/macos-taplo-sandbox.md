# macOS Taplo Sandbox Failure

Use this diagnostic only when a canonical repository command invokes Taplo on
native macOS inside the Codex `workspace-write` sandbox and the log contains a
panic in `system-configuration-*/src/dynamic_store.rs` immediately followed by
`Attempted to create a NULL object.` A successful managed-toolchain preflight
does not establish that macOS system-configuration services are usable inside
that sandbox. This signature is execution infrastructure evidence; it does not
establish malformed TOML or justify changing rules, exclusions, or tool versions.

Preserve the original command, working directory, toolchain/preflight result,
stdout/stderr, elapsed time, and exit code. Taplo may return `101` while the Just
wrapper returns `1`; retain both when observed. The validation remains failed.
Classify a retained log without executing anything:

```sh
uv run --locked python "$SKILLS_ROOT/review-validator/scripts/classify_failure.py" \
  --log "$REVIEW_STORE/toml-fix.sandbox.log" \
  --tool taplo --platform darwin --sandbox workspace-write --exit-code 1
```

The JSON receipt binds the existing log bytes and reports `infrastructure` for
this signature, otherwise `inconclusive`. It grants no execution permission and
does not edit the log, retry the command, or turn the failed result into a pass.

The coordinator may request one narrowly scoped approved escalation for the
identical canonical command, directory, inputs, and toolchain. Keep the original
failure and the retry's separate timing/output and permission identity. Stop if
approval is denied or the retry fails; inspect that new evidence before any
further action. Do not upgrade Taplo, rewrite project TOML, bypass the repository
recipe, or change configuration to make this diagnostic disappear.

For an executed non-mutating graph validator, publish the failed infrastructure
result and use `recover-validation-execution` with the retained failure evidence
and explicit permission change, as described in
[execution recovery](../../review-graph/references/state-transitions.md).
The failed unit must already bind a macOS/Darwin `platform`, a `toolchain` naming
Taplo, a `workspace-write` `environment`, and `use_default` executor permissions.
Use `failure_kind: executor-permission` in the recovery request; the failed
validation payload remains `infrastructure`. In `failure_evidence.diagnostic`
and the execution's `evidence`, retain the full panic excerpt from `panicked at`
through `Attempted to create a NULL object.` on one line, replacing the log's
line break with a space. Recovery recognizes this signature without denial text,
compares the excerpt with the recorded log using whitespace normalization, and
still verifies the raw log digest, source captures, and workspace audit.
Do not reuse the failed attempt's receipt for the replacement. A formatter such
as `just toml-fix` mutates source and belongs to the authorized serialized repair
step, followed by recapture; it is not a non-mutating validation command.

## Native macOS Reproduction

[Issue #239](https://github.com/acgetchell/dotfiles/issues/239) records the observed
case on native `aarch64-apple-darwin`, Rust `1.99.1`, Taplo `0.10.0`. Managed
preflight passed; the sandboxed canonical `just toml-fix` panicked in
`system-configuration-0.5.1/src/dynamic_store.rs:154`. The identical approved
escalated command succeeded. This is a reported native observation, not a claim
that every macOS host or future Taplo release reproduces it.

To reproduce in an authorized disposable checkout of a project providing that
recipe:

1. Record the native OS/architecture, tool versions, repository source identity,
   exact recipe, and managed preflight output. Use one external review cache.
2. Run `env UV_CACHE_DIR="$REVIEW_STORE/helper-cache" just toml-fix` with the
   execution tool's default `workspace-write` permissions. Retain the complete
   output and timing in a new approved log. If it does not produce the signature,
   record that result; do not manufacture a failure or alter the inputs.
3. Classify that retained log using the helper above. Request escalation for
   that same command only if the signature matches and a retry is needed.
4. After approval, repeat the exact command through `require_escalated`, keeping
   directory, cache, versions, and configuration identical. Record any partial
   formatter effects from the failed attempt and recapture after the retry.
   Preserve both attempts even if the retry succeeds.

The regression tests exercise diagnostic classification and evidence retention
with representative log bytes. They do not emulate macOS services or prove that
escalation succeeds on the current host.
