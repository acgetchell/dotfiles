# shellcheck disable=SC2148
# Justfile for dotfiles validation.

set shell := ["bash", "-euo", "pipefail", "-c"]

export UV_CACHE_DIR := env_var_or_default("UV_CACHE_DIR", ".uv-cache")

python_paths := "agents/.agents/skills scripts"
dprint_version := "0.57.0"
just_version := "1.58.0"
rumdl_version := "0.2.62"
uv_version := "0.12.8"
zizmor_version := "1.30.0"

_ensure-actionlint:
    #!/usr/bin/env bash
    set -euo pipefail
    command -v uv >/dev/null || { echo "'uv' not found. See https://github.com/astral-sh/uv"; exit 1; }
    uv run --locked actionlint -version >/dev/null

_ensure-brew:
    #!/usr/bin/env bash
    set -euo pipefail
    command -v brew >/dev/null || { echo "'brew' not found. See https://brew.sh"; exit 1; }

_ensure-dprint:
    #!/usr/bin/env bash
    set -euo pipefail
    installed_version=""
    if command -v dprint >/dev/null; then
        installed_version="$(dprint --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true)"
    fi
    if [[ "$installed_version" != "{{ dprint_version }}" ]]; then
        echo "'dprint' {{ dprint_version }} not found. Run bin/bootstrap.sh or install:"
        echo "   cargo install --locked dprint --version {{ dprint_version }}"
        exit 1
    fi

_ensure-just:
    #!/usr/bin/env bash
    set -euo pipefail
    resolved="$(command -v just 2>/dev/null || true)"
    actual="$(just --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true)"
    if [[ "$actual" != "{{ just_version }}" ]]; then
        echo "'just' resolves to '${resolved:-missing}' at version '${actual:-missing}', expected '{{ just_version }}'." >&2
        echo "   Install with: cargo install --locked just --version {{ just_version }}" >&2
        exit 1
    fi

_ensure-rumdl:
    #!/usr/bin/env bash
    set -euo pipefail
    resolved="$(command -v rumdl 2>/dev/null || true)"
    actual="$(rumdl --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true)"
    if [[ "$actual" != "{{ rumdl_version }}" ]]; then
        echo "'rumdl' resolves to '${resolved:-missing}' at version '${actual:-missing}', expected '{{ rumdl_version }}'." >&2
        echo "   Install with: cargo install --locked rumdl --version {{ rumdl_version }}" >&2
        exit 1
    fi

_ensure-uv:
    #!/usr/bin/env bash
    set -euo pipefail
    resolved="$(command -v uv 2>/dev/null || true)"
    actual="$(uv --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true)"
    if [[ "$actual" != "{{ uv_version }}" ]]; then
        echo "'uv' resolves to '${resolved:-missing}' at version '${actual:-missing}', expected '{{ uv_version }}'." >&2
        echo "   Install or upgrade Homebrew uv to {{ uv_version }}." >&2
        exit 1
    fi

_ensure-zizmor:
    #!/usr/bin/env bash
    set -euo pipefail
    installed_version=""
    if command -v zizmor >/dev/null; then
        installed_version="$(zizmor --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true)"
    fi
    if [[ "$installed_version" != "{{ zizmor_version }}" ]]; then
        echo "'zizmor' {{ zizmor_version }} not found. Run bin/bootstrap.sh or install:"
        echo "   cargo install --locked zizmor --version {{ zizmor_version }}"
        exit 1
    fi

action-lint: _ensure-actionlint
    #!/usr/bin/env bash
    set -euo pipefail
    files=()
    while IFS= read -r -d '' file; do
        files+=("$file")
    done < <(git ls-files -co --exclude-standard -z -- '.github/workflows/*.yml' '.github/workflows/*.yaml')
    if [ "${#files[@]}" -gt 0 ]; then
        printf '%s\0' "${files[@]}" | xargs -0 uv run --locked actionlint
    else
        echo "No workflow files found to lint."
    fi

brew-check: _ensure-brew
    HOMEBREW_NO_AUTO_UPDATE=1 brew bundle check --file="$PWD/Brewfile"

[confirm("Uninstall Homebrew formulae and casks not declared in this repository's Brewfile, then run brew cleanup?")]
brew-cleanup: _ensure-brew
    HOMEBREW_NO_AUTO_UPDATE=1 brew bundle cleanup --force --file="$PWD/Brewfile"
    HOMEBREW_NO_AUTO_UPDATE=1 brew cleanup

brew-cleanup-preview: _ensure-brew
    #!/usr/bin/env bash
    set -euo pipefail
    status=0
    output="$(HOMEBREW_NO_AUTO_UPDATE=1 brew bundle cleanup --file="$PWD/Brewfile" 2>&1)" || status=$?
    printf '%s\n' "$output"
    if (( status == 0 )); then
        exit 0
    fi
    if (( status == 1 )) && [[ "$output" == *'Run `brew bundle cleanup --force` to make these changes.'* ]]; then
        exit 0
    fi
    exit "$status"

brew-install: _ensure-brew
    brew bundle install --file="$PWD/Brewfile"

check: shell-check git-config-check justfile-fmt-check toml-check yaml-check markdown-check github-actions-check check-skills semgrep semgrep-test python-ci
    @echo "Checks complete!"

check-skills: _ensure-uv
    #!/usr/bin/env bash
    set -euo pipefail
    failed=0
    while IFS= read -r skill_file; do
        skill_dir="${skill_file%/SKILL.md}"
        if ! just skill-check "$skill_dir"; then
            failed=1
        fi
    done < <(find agents/.agents/skills -mindepth 2 -maxdepth 2 -name SKILL.md -print | sort)
    if (( failed )); then
        echo "One or more skill checks failed." >&2
        exit 1
    fi
    echo "Skill checks complete!"

ci: check
    @echo "CI checks complete!"

fix: justfile-fmt python-fix yaml-fix markdown-fix
    @echo "Fixes complete!"

git-config-check:
    git config --file git/.gitconfig --list >/dev/null

github-actions-check: action-lint zizmor
    @echo "GitHub Actions checks complete!"

justfile-fmt: _ensure-just
    just --fmt

justfile-fmt-check: _ensure-just
    just --fmt --check

markdown-check: _ensure-rumdl
    #!/usr/bin/env bash
    set -euo pipefail
    files=()
    while IFS= read -r -d '' file; do
        if [ -f "$file" ]; then
            files+=("$file")
        fi
    done < <(git ls-files -co --exclude-standard -z -- '*.md')
    if [ "${#files[@]}" -gt 0 ]; then
        printf '%s\0' "${files[@]}" | xargs -0 -n100 rumdl check --deny-config-warnings --
    else
        echo "No Markdown files found to check."
    fi

markdown-fix: _ensure-rumdl
    #!/usr/bin/env bash
    set -euo pipefail
    files=()
    while IFS= read -r -d '' file; do
        if [ -f "$file" ]; then
            files+=("$file")
        fi
    done < <(git ls-files -co --exclude-standard -z -- '*.md')
    if [ "${#files[@]}" -gt 0 ]; then
        printf '%s\0' "${files[@]}" | xargs -0 -n100 rumdl check --fix --deny-config-warnings --
    else
        echo "No Markdown files found to fix."
    fi

markdown-lint: markdown-check

[confirm("Apply captured macOS defaults (Dock, Finder, keyboard, trackpad) while leaving native window tiling unchanged, then restart Dock/Finder?")]
macos-defaults:
    bin/macos-defaults.sh

[confirm("Apply captured macOS defaults and let an installed Rectangle Pro take over edge tiling by disabling native macOS edge-drag gestures?")]
macos-defaults-rectangle-pro:
    bin/macos-defaults.sh --rectangle-pro-takeover

python-check: _ensure-uv
    uv run --locked ruff format --check {{ python_paths }}
    uv run --locked ruff check {{ python_paths }}
    just python-typecheck

python-ci: python-check test-python
    @echo "Python checks complete!"

python-fix: _ensure-uv
    uv run --locked ruff check {{ python_paths }} --fix
    uv run --locked ruff format {{ python_paths }}

python-lint: python-check

python-sync: _ensure-uv
    uv sync --group dev

python-typecheck: _ensure-uv
    uv run --locked ty check {{ python_paths }} --error all

# Harden semgrep execution for CI/sandboxes:
# use explicit temporary cache/log paths, disable version checks and metrics,
# and prefer system CA certs so checks work when HOME/.cache paths are restricted.
semgrep: _ensure-brew _ensure-uv
    #!/usr/bin/env bash
    set -euo pipefail
    uv_executable="${UV_EXECUTABLE:-$(brew --prefix uv)/bin/uv}"
    if [[ ! -x "$uv_executable" ]]; then
        echo "Selected uv executable is unavailable at $uv_executable." >&2
        exit 1
    fi
    files=()
    while IFS= read -r -d '' file; do
        if [[ -f "$file" && "$file" != tests/semgrep/* ]]; then
            files+=("$file")
        fi
    done < <(git ls-files -co --exclude-standard -z)
    if ((${#files[@]})); then
        semgrep_tmp_dir="$(mktemp -d "${TMPDIR:-/tmp}/dotfiles-semgrep.XXXXXX")"
        cleanup() {
            rm -rf "$semgrep_tmp_dir"
        }
        trap cleanup EXIT
        semgrep_version_cache_path="$semgrep_tmp_dir/version-cache"
        semgrep_log_file="$semgrep_tmp_dir/semgrep.log"
        if [ -f /etc/ssl/cert.pem ]; then
            export SSL_CERT_FILE="/etc/ssl/cert.pem"
        elif [ -f /etc/ssl/certs/ca-certificates.crt ]; then
            export SSL_CERT_FILE="/etc/ssl/certs/ca-certificates.crt"
        else
            unset SSL_CERT_FILE
        fi
        SEMGREP_VERSION_CACHE_PATH="$semgrep_version_cache_path" \
            SEMGREP_LOG_FILE="$semgrep_log_file" \
            SEMGREP_SEND_METRICS=off \
            OTEL_SDK_DISABLED=true \
            "$uv_executable" run --locked semgrep --disable-version-check --metrics off --error --strict --timeout 120 --config semgrep.yaml "${files[@]}"
    else
        echo "No repository files found to scan."
    fi

# Keep fixture semgrep tests robust under the same CI/sandbox constraints.
semgrep-test: _ensure-brew _ensure-uv
    #!/usr/bin/env bash
    set -euo pipefail
    uv_executable="${UV_EXECUTABLE:-$(brew --prefix uv)/bin/uv}"
    if [[ ! -x "$uv_executable" ]]; then
        echo "Selected uv executable is unavailable at $uv_executable." >&2
        exit 1
    fi
    state_root="$(mktemp -d "${TMPDIR:-/tmp}/dotfiles-semgrep-state.XXXXXX")"
    cleanup() {
        rm -rf "$state_root"
    }
    trap cleanup EXIT

    if [ -f /etc/ssl/cert.pem ]; then
        export SSL_CERT_FILE="/etc/ssl/cert.pem"
    elif [ -f /etc/ssl/certs/ca-certificates.crt ]; then
        export SSL_CERT_FILE="/etc/ssl/certs/ca-certificates.crt"
    else
        unset SSL_CERT_FILE
    fi

    config_root="$state_root/configs"
    mkdir -p "$config_root"
    hidden_fixtures=()
    ordinary_fixture_count=0
    while IFS= read -r -d '' fixture; do
        rel="${fixture#tests/semgrep/}"
        if [[ "$rel" == .* ]]; then
            hidden_fixtures+=("$fixture")
            continue
        fi
        config_path="$config_root/${rel}.yaml"
        mkdir -p "$(dirname "$config_path")"
        "$uv_executable" run --locked python scripts/semgrep_fixture_config.py "$fixture" "$PWD/semgrep.yaml" "$config_path"
        ((ordinary_fixture_count += 1))
    done < <(find tests/semgrep -type f ! -name '*.fixed' -print0)

    run_fixture_suite() {
        local config_path="$1"
        local target="$2"
        local state_dir
        state_dir="$(mktemp -d "$state_root/suite.XXXXXX")"
        SEMGREP_VERSION_CACHE_PATH="$state_dir/version-cache" \
            SEMGREP_LOG_FILE="$state_dir/semgrep.log" \
            SEMGREP_SEND_METRICS=off \
            OTEL_SDK_DISABLED=true \
            SEMGREP_SETTINGS_FILE="$state_dir/settings.yml" \
            "$uv_executable" run --locked semgrep scan --disable-version-check --metrics off --test --strict --config "$config_path" "$target"
    }

    if ((ordinary_fixture_count)); then
        run_fixture_suite "$config_root" tests/semgrep
    fi

    for fixture in "${hidden_fixtures[@]}"; do
        hidden_state_dir="$(mktemp -d "$state_root/hidden.XXXXXX")"
        config_path="$hidden_state_dir/config.yaml"
        "$uv_executable" run --locked python scripts/semgrep_fixture_config.py "$fixture" "$PWD/semgrep.yaml" "$config_path"
        run_fixture_suite "$config_path" "$fixture"
    done

setup:
    DOTFILES_DIR="$PWD" bin/bootstrap.sh
    just python-sync

_preflight-stable-uv: _ensure-brew
    #!/usr/bin/env bash
    set -euo pipefail

    uv_executable="$(brew --prefix uv)/bin/uv"
    if [[ ! -x "$uv_executable" ]]; then
        echo "Homebrew-managed uv is unavailable at $uv_executable." >&2
        exit 1
    fi
    "$uv_executable" run --locked --no-sync python scripts/update_tool_pins.py --check-uv-version --uv-executable "$uv_executable"

# Update the Homebrew bundle, uv lock, and repository-owned Cargo tools.
update: _preflight-stable-uv update-dependencies update-cargo-tools
    @echo "Repository dependencies and tools updated."

# Update the Cargo CLI tools installed by bootstrap.sh and reconcile their pins.
update-cargo-tools: _ensure-brew
    #!/usr/bin/env bash
    set -euo pipefail

    if ! command -v cargo-install-update >/dev/null 2>&1; then
        echo "'cargo-install-update' not found. Install it with:"
        echo "   cargo install --locked cargo-update"
        exit 1
    fi

    uv_executable="$(brew --prefix uv)/bin/uv"
    if [[ ! -x "$uv_executable" ]]; then
        echo "Homebrew-managed uv is unavailable at $uv_executable." >&2
        exit 1
    fi
    "$uv_executable" run --locked --no-sync python scripts/update_tool_pins.py --check-uv-version --uv-executable "$uv_executable"

    packages=(dprint just rumdl zizmor)
    cargo install-update --locked "${packages[@]}"
    "$uv_executable" run --locked python scripts/update_tool_pins.py --justfile justfile --uv-executable "$uv_executable"

# Upgrade Brewfile dependencies and the complete uv development environment.
update-dependencies: _ensure-brew
    #!/usr/bin/env bash
    set -euo pipefail

    brew bundle upgrade --file="$PWD/Brewfile"
    uv_executable="$(brew --prefix uv)/bin/uv"
    if [[ ! -x "$uv_executable" ]]; then
        echo "Homebrew-managed uv is unavailable at $uv_executable." >&2
        exit 1
    fi
    "$uv_executable" run --locked --no-sync python scripts/update_tool_pins.py --check-uv-version --uv-executable "$uv_executable"
    "$uv_executable" lock --upgrade
    "$uv_executable" sync --locked --group dev

shell-check:
    bash -n bin/bootstrap.sh bin/macos-defaults.sh bin/resolve-just-version.sh bin/verify.sh

skill-check skill: _ensure-uv
    uv run --locked python scripts/skill_validate.py "{{ skill }}"

stow-adopt package:
    #!/usr/bin/env bash
    set -euo pipefail
    package='{{ package }}'
    case "$package" in git|zsh|agents) ;; *) echo "Unsupported stow package: $package" >&2; exit 2 ;; esac
    [ -d "$package" ] || { echo "Unknown stow package: $package" >&2; exit 2; }
    stow --no-folding -d "$PWD" -t "$HOME" --adopt -v -R "$package"
    just stow-check "$package"

stow-all:
    just stow-apply-all

stow-apply package:
    #!/usr/bin/env bash
    set -euo pipefail
    package='{{ package }}'
    case "$package" in git|zsh|agents) ;; *) echo "Unsupported stow package: $package" >&2; exit 2 ;; esac
    [ -d "$package" ] || { echo "Unknown stow package: $package" >&2; exit 2; }
    stow --no-folding -d "$PWD" -t "$HOME" -v -S "$package"

stow-apply-all:
    #!/usr/bin/env bash
    set -euo pipefail
    for package in git zsh agents; do
        just stow-apply "$package"
    done

stow-check package:
    #!/usr/bin/env bash
    set -euo pipefail
    package='{{ package }}'
    case "$package" in git|zsh|agents) ;; *) echo "Unsupported stow package: $package" >&2; exit 2 ;; esac
    [ -d "$package" ] || { echo "Unknown stow package: $package" >&2; exit 2; }
    stow --no-folding -d "$PWD" -t "$HOME" -n -v -S "$package"

stow-delete package:
    #!/usr/bin/env bash
    set -euo pipefail
    package='{{ package }}'
    case "$package" in git|zsh|agents) ;; *) echo "Unsupported stow package: $package" >&2; exit 2 ;; esac
    [ -d "$package" ] || { echo "Unknown stow package: $package" >&2; exit 2; }
    stow --no-folding -d "$PWD" -t "$HOME" -v -D "$package"

stow-restow package:
    #!/usr/bin/env bash
    set -euo pipefail
    package='{{ package }}'
    case "$package" in git|zsh|agents) ;; *) echo "Unsupported stow package: $package" >&2; exit 2 ;; esac
    [ -d "$package" ] || { echo "Unknown stow package: $package" >&2; exit 2; }
    stow --no-folding -d "$PWD" -t "$HOME" -v -R "$package"

stow-restow-all:
    #!/usr/bin/env bash
    set -euo pipefail
    for package in git zsh agents; do
        just stow-restow "$package"
    done

stow-verify: _ensure-uv
    DOTFILES_DIR="$PWD" uv run --locked python scripts/stow_verify.py

test-python: _ensure-uv
    uv run --locked pytest

toml-check: _ensure-uv
    uv run --locked python -c 'import subprocess, tomllib; from pathlib import Path; [tomllib.load(Path(path).open("rb")) for path in subprocess.run(["git", "ls-files", "*.toml"], check=True, capture_output=True, text=True).stdout.splitlines()]'

yaml-check: yaml-fmt-check yaml-lint

yaml-fix: _ensure-dprint
    #!/usr/bin/env bash
    set -euo pipefail
    files=()
    while IFS= read -r -d '' file; do
        if [ -f "$file" ]; then
            files+=("$file")
        fi
    done < <(git ls-files -co --exclude-standard -z -- '*.yml' '*.yaml' 'CITATION.cff')
    if [ "${#files[@]}" -gt 0 ]; then
        printf '%s\0' "${files[@]}" | xargs -0 dprint fmt --incremental=false
    else
        echo "No YAML files found to format."
    fi

yaml-fmt-check: _ensure-dprint
    #!/usr/bin/env bash
    set -euo pipefail
    files=()
    while IFS= read -r -d '' file; do
        if [ -f "$file" ]; then
            files+=("$file")
        fi
    done < <(git ls-files -co --exclude-standard -z -- '*.yml' '*.yaml' 'CITATION.cff')
    if [ "${#files[@]}" -gt 0 ]; then
        printf '%s\0' "${files[@]}" | xargs -0 dprint check --incremental=false
    else
        echo "No YAML files found to check."
    fi

yaml-lint: _ensure-uv
    #!/usr/bin/env bash
    set -euo pipefail
    files=()
    while IFS= read -r -d '' file; do
        if [ -f "$file" ]; then
            files+=("$file")
        fi
    done < <(git ls-files -co --exclude-standard -z -- '*.yml' '*.yaml' 'CITATION.cff')
    if [ "${#files[@]}" -gt 0 ]; then
        uv run --locked yamllint --strict -c .yamllint "${files[@]}"
    else
        echo "No YAML files found to lint."
    fi

zizmor: _ensure-zizmor
    zizmor .github
