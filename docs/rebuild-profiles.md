# Machine rebuild profiles

Use these profiles to set up a host, install skills independently, or provision
and restore locked environments on a cloud machine.

## Platform setup

`just setup` selects macOS or the Linux-cloud profile. Explicit selections are
`just setup macos` and `just setup linux-cloud`. Unsupported operating systems,
architectures, and Linux releases fail before installation. The Linux-cloud
profile accepts Ubuntu 24.04 and Debian 13 on x86_64. The separate
[site-managed Linux/HPC route](linux-review-environment.md) retains its broader
tooling-only scope and does not require root.

On a clean supported Linux host, an administrator first provides base packages:

```sh
bash bin/linux-host.sh plan
sudo bash bin/linux-host.sh install
```

Then run user-space setup as the ordinary user, from any checkout location:

```sh
bash bin/setup-profile.sh linux-cloud setup
```

The Bash entry point bootstraps Just. Open a fresh Bash or Zsh session so the
installed shell startup files add the profile tools to `PATH`. From the checkout,
run `just profile-doctor linux-cloud` to recheck the setup. With Just already
available, `just setup linux-cloud` is the setup entry point. Setup
checks Stow collisions before downloads, prepares pinned user-owned review
tools and an isolated review helper, links whole skill directories, and installs
Bash/Zsh/Git links. It preserves existing unrelated files and local overrides;
resolve collisions explicitly rather than replacing user files. Oh My Zsh is
optional. Cargo and GitHub CLI lookup work without Homebrew. No credential or
global agent instruction file is created.

`just update linux-cloud` reconciles the checked-in pins using the same setup
path; it does not upgrade dependency versions. `just update macos` retains the
existing Homebrew/Python/Cargo update workflow, which can change dependency
files. `just setup macos` retains desktop bootstrap behavior. This guide does
not authorize running the macOS updater while source changes are prohibited.

The Linux installation accepts absolute `DOTFILES_REVIEW_PREFIX`,
`DOTFILES_REVIEW_CACHE`, and `DOTFILES_REVIEW_SKILLS_DIR` overrides. Keep them
consistent across setup and later commands. Defaults are beneath
`~/.local/share/dotfiles-review`, `~/.cache/dotfiles-review`, and `~/.agents/skills`.
Setup and doctor select `$DOTFILES_REVIEW_PREFIX/helper-<rrt-version>-markdown-it-<parser-version>`
using the locked tooling versions. An upgrade creates the newly selected helper alongside
earlier environments. The old `helper` directory stays available to frozen
reviews that already reference it.

## Skills without desktop setup

Prepare the versioned helper and choose a discovery directory:

```sh
just skills-helper-setup
just skills-install "$HOME/.agents/skills"
just skills-check "$HOME/.agents/skills"
```

For isolation, replace the destination with an empty directory intended for
that agent's discovery configuration. An arbitrary directory is not discovered
automatically. Whole-directory links retain scripts, references, assets, and
relative paths. Missing helpers, wrong helper origins, existing files,
conflicting directory links, and stale managed links fail with diagnostics.
You can pass an explicit helper directory as the last argument to each recipe.
Setup verifies an existing directory against the current pin before reuse.
Unrelated skills are preserved.

These checks establish installation and helper provenance. Start a new agent
session and confirm its loaded skill catalog separately; filesystem checks do
not establish discovery. These commands do not change agent settings or AGENTS.md.

## Connected provisioning and offline restoration

The versioned `profiles/cloud.toml` selects only this checkout. To include other
repositories, copy it to `target/cloud-inventory.toml` and append an entry for
each checkout. Paths resolve relative to the inventory file. For example, a
checkout beside dotfiles uses `../../my-project` from the `target/` directory.

```toml
[[repository]]
name = "my-project"
path = "../../my-project"
groups = ["dev"]
# Optional owning-repository recipes: [connected provisioning, read-only check].
tools = [["tools-sync", "tools-check"]]
```

Each repository must own a current `uv.lock` and an exact
`[tool.uv] required-version`. Repositories sharing the dotfiles pin use the
profile's installed uv. Connected provisioning installs each additional exact
version from a binary wheel (PyPI by default) and retains the standalone
executable at `$DOTFILES_REVIEW_PREFIX/uv/<version>/uv`. The prefix defaults to
`~/.local/share/dotfiles-review`. The same version is reused across checkouts,
and each checkout's tool recipes see its selected uv first on `PATH`.
Environments use the owning checkout's `.venv`; only this dotfiles checkout may
select its existing private review environment with `review-environment = true`.
Optional tool recipes must already exist in the owning repository and honor the
chosen lifecycle: provisioning may install tools, checks must only inspect them.

```sh
just cloud-provision target/cloud-inventory.toml
just cloud-startup target/cloud-inventory.toml
just cloud-doctor target/cloud-inventory.toml
```

Provisioning is connected and uses locked dependencies. Startup disables uv
network access and Python downloads, reinstalls editable metadata from retained
build inputs, and performs one ordinary locked reconciliation before the health
check. This second pass handles source timestamps changed by restored
setuptools metadata. Doctor uses `uv sync --check` and selected check recipes,
without synchronizing dependencies. For dotfiles it also checks fresh shells,
links, pinned tools, and helper provenance. Health probes may write ordinary
tool/shell caches, locks, and receipts; they are not a zero-write filesystem audit.

Keep the installed interpreter, profile uv, retained version-specific executables,
uv cache, build dependencies, selected tools, and checkouts together in the
provider snapshot. Keep the same `UV_CACHE_DIR` from setup through restore. Use
an absolute path when the inventory shares one cache across checkouts.
Startup and doctor check the exact executable version without
installing tools. Rerun platform setup if the profile's uv is missing or has
the wrong version. For a missing or invalid retained version, restore its
executable from the snapshot or rerun connected provisioning after removing any
invalid executable.

Missing cache inputs or stale locks fail without an online fallback. Correct
locks in their owning repository and rerun connected provisioning. Startup
neither regenerates locks nor changes Git state. Source and HEAD identities are
checked before and after commands; unexpected changes are reported and preserved
for inspection, never reset.

Cooperating lifecycle commands hold an exclusive lock per environment, including
through child-process cleanup on failure. Do not run other environment managers
against that environment concurrently. Each attempt writes a private receipt
beneath `target/cloud`, including platform, inventory/lock/source identities,
each repository's required uv version and selected executable, commands, exit
statuses, and output hashes. Raw child output is not copied into receipts.
Failed attempts remain available and do not imply successful readiness.

## Disposable Linux rebuild

```sh
just docker-rebuild
```

Docker is only needed for this test. The harness copies current tracked
working files into a temporary build context without Git metadata or untracked
files. Stage intended new public source files explicitly before running it;
untracked files such as a private `.env` stay outside the context. It uses a digest-pinned Ubuntu 24.04
image, an ordinary user with an empty home, and a checkout path containing
spaces. It seeds the old helper directory with
[research-repo-tools 0.2.9](https://pypi.org/project/research-repo-tools/0.2.9/),
runs profile update twice, then starts a separate container with networking
disabled. The container uses a disposable checkout and home directory. Git
fixture metadata inside the image lets it check source preservation.

The disconnected phase checks shells, skills, both helper origins, repeated startup,
deleted editable metadata, changed locked source, stale locks, missing build
cache, recovery after failure, and preserved skills conflicts. Logs and the
source/image receipt remain in `target/rebuild`. The image tag is retained for
diagnosis; remove that specific image manually when finished. Update the pinned
base digest deliberately and rerun both phases when refreshing OS packages.
The Linux CI job runs this same harness and uploads its logs.

## Evidence boundaries

Container checks establish the disposable Ubuntu path. They do not establish a
fresh provider snapshot restore, actual new-session skill discovery, a new
native macOS rebuild, or Debian profile acceptance. Record those native results
against the exact source identity before calling the implementation fully
validated. The older #123 cloud closeout is historical evidence, not a test of
this lifecycle. No cloud settings or saved provider image is changed here.
