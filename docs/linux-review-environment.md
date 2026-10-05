# Linux, cloud, and HPC review environment

This command surface provisions development and review tools independently of
the macOS desktop configuration. A configured CI job is not native host evidence.
Cloud and cluster verification remain separate, even when their OS versions match.

## Supported candidates and base tools

The installer accepts Linux x86_64 or aarch64 with glibc >= 2.28. Ubuntu 24.04
x86_64 is the CI target. Other distributions and aarch64 remain unverified until
their native checks pass. musl, older glibc, other architectures, and Windows
full setup fail with actionable diagnostics. macOS continues to use `just setup`.
The [README support matrix](../README.md#platform-scope) records current scope.

The host must provide Bash, Git, Zsh, and GNU Stow. Zsh is required by the native
timing suite; Stow is required by isolated link integration tests. Missing tools
fail checks rather than suppressing portable tests. Connected provisioning also
needs curl, tar, unzip, sha256sum, getconf, standard Unix utilities, and HTTPS CA
certificates. Load approved modules or ask the environment owner to supply base
tools. The installer does not run sudo, install system packages, or install a
global Python package. Linux CI supplies base tools before testing this installer.

uv's pin comes from `pyproject.toml`; Just's bootstrap pin uses the existing
`bin/resolve-just-version.sh`; dprint and rumdl use `just --evaluate`. Matching
tools on PATH are reused, including site/module tools. Otherwise the installer
downloads the pinned upstream release binary and verifies its published SHA-256
checksum before installation. Locked `uv sync --locked --group dev` selects the
repository Python from `.python-version`; a matching site Python can be selected
with `UV_PYTHON`. No Rust compiler or Homebrew is required for these binaries.

## Connected provisioning

Clone a checkout through the site's approved connected path, then run:

```sh
cd ~/projects/dotfiles
bash bin/linux-review.sh setup
bash bin/linux-review.sh check
bash bin/linux-review.sh smoke
```

Setup is idempotent and fails on a conflicting skill installation. Checks run
the same full `just ci` inventory used by macOS, including Python/skill/runtime,
Markdown, YAML, workflow, and Semgrep checks. The bootstrap regression uses
isolated macOS tool stand-ins; it does not provision desktop files on Linux.
macOS operational commands (`just setup`, Brewfile/health checks, Stow of desktop
files, and macOS defaults) remain separate from Linux installation.

Network destinations for provisioning include GitHub release assets, Python
distributions selected by uv, the configured package index, and the pinned
dprint plugin in `dprint.json`. Use a site-approved proxy or mirror and certificate
configuration. Setup warms dprint's plugin cache. A failed download, checksum,
dependency sync, or plugin check is a failed setup; rerun after correcting access.
Do not relax TLS or checksum validation to bypass a site restriction.

| Directory setting | Default | Purpose |
| --- | --- | --- |
| `DOTFILES_REVIEW_PREFIX` | `~/.local/share/dotfiles-review` | Binaries, private uv environment, managed Python |
| `DOTFILES_REVIEW_CACHE` | `$XDG_CACHE_HOME/dotfiles-review` or `~/.cache/dotfiles-review` | uv and formatter caches |
| `DOTFILES_REVIEW_TMP` | `$TMPDIR/dotfiles-review-$UID` or `/tmp/dotfiles-review-$UID` | Temporary work |
| `DOTFILES_REVIEW_ARTIFACTS` | Checkout `target/linux-review` | Unique private evidence directories |
| `DOTFILES_REVIEW_SKILLS_DIR` | Prefix `skills` | Directory links to checkout skill folders |

All settings require absolute paths. Keep the prefix on storage that permits
execution; downloaded binaries and Just's temporary recipe scripts are validated
and run there, so download scratch may be mounted with `noexec`. Full `check`
runs also need an executable `DOTFILES_REVIEW_TMP` because regression fixtures
create and launch scripts in that directory. Choose a
persistent artifact destination or copy evidence through the approved mechanism
before temporary/scratch storage expires. Provision on the same architecture,
libc, and filesystem path used for execution; uv environments and generated
dispatches are not relocatable bundles.

```sh
export DOTFILES_REVIEW_PREFIX="$HOME/.local/share/review-tools"
export DOTFILES_REVIEW_CACHE="${SCRATCH:?}/review-cache"
export DOTFILES_REVIEW_TMP="${SCRATCH:?}/review-tmp"
export DOTFILES_REVIEW_ARTIFACTS="$HOME/review-evidence"
export DOTFILES_REVIEW_SKILLS_DIR="$HOME/.agents/skills"
bash bin/linux-review.sh setup
```

The default isolated skill directory is available for agents with an explicit
skill-root setting. To enable Codex's home-directory discovery, select
`$HOME/.agents/skills` as above. Setup links entire skill directories and refuses
to overwrite other installations. Keep the checkout available; these are links,
not copied skills. Existing shell files and machine-local Codex configuration
are not edited. Use `bash bin/linux-review.sh exec just --list` to access the
provisioned command layer without changing shell startup files.

## Disconnected validation and optional capabilities

After connected provisioning, use the same directories and modules:

```sh
bash bin/linux-review.sh check
bash bin/linux-review.sh smoke
```

These commands set `UV_OFFLINE=1`, `UV_NO_SYNC=1`, and
`UV_PYTHON_DOWNLOADS=never`. They fail when installed tools, locked dependencies,
skills, or cached plugins are unavailable. The credential-free portable suite
first verifies the installed Python environment with `uv sync --locked --check`
without modifying it. The suite
uses only local Semgrep rules and offline workflow audits. Site network controls
provide the external boundary; setting uv offline does not sandbox arbitrary
programs. Live routing, vulnerability advisory refreshes, online workflow audits,
and authentication require separate connected authorization and access. Their
absence is not evidence that those capabilities passed.

Inject `TYPESAFE_API_KEY` using the environment's approved secret provider, then
explicitly run:

```sh
bash bin/linux-review.sh probe
```

The probe calls the existing model-list authentication check, with a 30-second
process bound. It sends no code and makes no inference request. Keys, raw
responses, proxy details, and exception bodies are neither printed nor persisted.
Missing/unresolved credentials, blocked networks, malformed responses, and
authentication failures return nonzero and record an unavailable capability.
Default CI never injects a TypeSafe credential or calls this probe. See the
[existing TypeSafe secret-provider instructions](../README.md#optional-typesafe-evaluation)
for local/cloud injection; provisioning credentials and compute-node credentials
are separate. Never put keys in shell arguments, public site configuration, or
artifact files.

## Cloud and HPC execution placement

Before execution, record the actual distribution, architecture/libc, approved
modules, storage policy, and network/secret boundaries in local site configuration.
For HPC, discover the scheduler (if any), account/allocation, wall-time policy,
and authorized command placement from the site documentation or administrator.
Do not assume Slurm or submit guessed allocation commands. Heavy full checks
belong in the site's approved allocation/execution path, not on a login node.
Connected provisioning may use a dedicated transfer/build node where allowed.
Compute nodes need no API connectivity for offline checks or the scripted smoke.

Prepare a site-owned job wrapper that loads approved modules, sets the five
directory variables, enters the checkout, and runs the two offline commands
above. Follow the discovered scheduler's submission procedure. Keep hostnames,
allocation identifiers, module selections, secret references, and scheduler
scripts in local/site configuration. This public repository has no scheduler
assumption, privileged service, container requirement, or cluster-specific paths.

For each actual target, retain the job/allocation receipt and exit status along
with the generated evidence. Run the bounded probe on an authorized connected
path if required; report API access as unavailable on disconnected compute nodes.
A passing connected probe does not prove the compute environment has API access.

## Evidence and verification status

Each command creates a new private directory and prints its `environment.json`.
It records source commit and checkout content digest, distribution, architecture,
libc, Python, shell/tool identities, command outcome, and artifact references.
Check/smoke launches use #89's execution-side timing helper, retaining exact argv,
working directory, exit status, and elapsed seconds in `timing.jsonl`.
The Linux/macOS smoke gives fixture validation a 30-second deadline. On timeout
it interrupts the owned process group, allows up to six seconds for the timing
helper to record interruption, then kills remaining processes and records
`validation-timeout.json`. A timeout never publishes a successful proof.
The smoke also retains its own validation timing, payload publication receipts,
compiled artifacts, journal, and `final-proof.json`. It reloads published evidence
to verify graph completeness and native fixture validation. It is explicitly
scripted protocol evidence, not an AI review of the repository. A real review
graph still requires its authorized coordinator and review workers.

The Linux CI job runs fresh setup twice, full offline checks, and smoke, then
uploads `linux-review-<commit>` artifacts for 14 days. Failed runs retain any
available evidence. The repository Actions allowlist must include the tracked
`actions/upload-artifact@*` entry; applying GitHub settings is a separate maintainer
operation described in [the settings guide](../.github/DEPENDABOT.md).

| Target | Status for this implementation | Remaining evidence |
| --- | --- | --- |
| Native Ubuntu 24.04 CI | Configured; result pending publication | Successful fresh/rerun setup, full suite, smoke, artifact link at the changed commit |
| Cara's cloud computer | Unverified; target access not provided | Host inventory, bounded probe, actual end-to-end review graph and final proof references |
| HPC system | Unverified; site execution path not provided | Discovered modules/scheduler/allocation policy, authorized native smoke/check job receipt and artifacts |

Record cloud and HPC results separately, including source identity, artifact URI,
job/workflow identifiers, command outcomes, and limitations. Update this table
and the README only when the matching native evidence exists. This work neither
changes the evidence schema for #87 nor adds a cloud/HPC prerequisite to local
routing experiments.

Upstream contracts: [uv environment settings](https://docs.astral.sh/uv/reference/environment/),
[Just releases](https://github.com/casey/just/releases),
[dprint releases](https://github.com/dprint/dprint/releases), and
[rumdl releases](https://github.com/rvben/rumdl/releases).
