# shellcheck disable=SC2148
# Justfile for dotfiles validation.

set shell := ["bash", "-euo", "pipefail", "-c"]

export UV_CACHE_DIR := env_var_or_default("UV_CACHE_DIR", ".uv-cache")

python_paths := "agents/.agents/skills scripts"
zizmor_version := "1.26.1"

_ensure-actionlint:
    #!/usr/bin/env bash
    set -euo pipefail
    command -v uv >/dev/null || { echo "'uv' not found. See https://github.com/astral-sh/uv"; exit 1; }
    uv run actionlint -version >/dev/null

_ensure-uv:
    #!/usr/bin/env bash
    set -euo pipefail
    command -v uv >/dev/null || { echo "'uv' not found. See https://github.com/astral-sh/uv"; exit 1; }

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
    done < <(git ls-files -z '.github/workflows/*.yml' '.github/workflows/*.yaml')
    if [ "${#files[@]}" -gt 0 ]; then
        printf '%s\0' "${files[@]}" | xargs -0 uv run actionlint
    else
        echo "No workflow files found to lint."
    fi

check: shell-check git-config-check toml-check yaml-check github-actions-check check-skills semgrep semgrep-test python-ci
    @echo "Checks complete!"

ci: check
    @echo "CI checks complete!"

setup:
    DOTFILES_DIR="$PWD" bin/bootstrap.sh
    just python-sync

github-actions-check: action-lint zizmor
    @echo "GitHub Actions checks complete!"

git-config-check:
    git config --file git/.gitconfig --list >/dev/null

python-check: _ensure-uv
    uv run ruff format --check {{ python_paths }}
    uv run ruff check {{ python_paths }}
    just python-typecheck

python-ci: python-check test-python
    @echo "Python checks complete!"

python-fix: _ensure-uv
    uv run ruff check {{ python_paths }} --fix
    uv run ruff format {{ python_paths }}

python-lint: python-check

python-sync: _ensure-uv
    uv sync --group dev

python-typecheck: _ensure-uv
    uv run ty check {{ python_paths }} --error all

semgrep: _ensure-uv
    uv run semgrep --error --strict --timeout 120 --config semgrep.yaml .

semgrep-test: _ensure-uv
    #!/usr/bin/env bash
    set -euo pipefail
    config_dir="$(mktemp -d "${TMPDIR:-/tmp}/dotfiles-semgrep-config.XXXXXX")"
    state_root="$(mktemp -d "${TMPDIR:-/tmp}/dotfiles-semgrep-state.XXXXXX")"
    cleanup() {
        rm -rf "$config_dir" "$state_root"
    }
    trap cleanup EXIT

    while IFS= read -r -d '' fixture; do
        rel="${fixture#tests/semgrep/}"
        config_path="$config_dir/${rel%.*}.yaml"
        state_dir="$state_root/${rel%.*}"
        mkdir -p "$(dirname "$config_path")"
        mkdir -p "$state_dir"
        uv run python scripts/semgrep_fixture_config.py "$fixture" "$PWD/semgrep.yaml" "$config_path"

        SEMGREP_SEND_METRICS=off SEMGREP_SETTINGS_FILE="$state_dir/settings.yml" uv run semgrep scan --test --strict --config "$config_path" "$fixture"
    done < <(find tests/semgrep -type f ! -name '*.fixed' -print0)

shell-check:
    bash -n bin/bootstrap.sh bin/verify.sh

skill-check skill: _ensure-uv
    uv run python "$HOME/.codex/skills/.system/skill-creator/scripts/quick_validate.py" "{{skill}}"

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

stow-adopt package:
    #!/usr/bin/env bash
    set -euo pipefail
    package='{{package}}'
    case "$package" in git|zsh|agents) ;; *) echo "Unsupported stow package: $package" >&2; exit 2 ;; esac
    [ -d "$package" ] || { echo "Unknown stow package: $package" >&2; exit 2; }
    stow -d "$PWD" -t "$HOME" --adopt -v -R "$package"
    just stow-check "$package"

stow-all:
    just stow-apply-all

stow-apply-all:
    #!/usr/bin/env bash
    set -euo pipefail
    for package in git zsh agents; do
        just stow-apply "$package"
    done

stow-apply package:
    #!/usr/bin/env bash
    set -euo pipefail
    package='{{package}}'
    case "$package" in git|zsh|agents) ;; *) echo "Unsupported stow package: $package" >&2; exit 2 ;; esac
    [ -d "$package" ] || { echo "Unknown stow package: $package" >&2; exit 2; }
    stow -d "$PWD" -t "$HOME" -v -S "$package"

stow-check package:
    #!/usr/bin/env bash
    set -euo pipefail
    package='{{package}}'
    case "$package" in git|zsh|agents) ;; *) echo "Unsupported stow package: $package" >&2; exit 2 ;; esac
    [ -d "$package" ] || { echo "Unknown stow package: $package" >&2; exit 2; }
    stow -d "$PWD" -t "$HOME" -n -v -S "$package"

stow-restow package:
    #!/usr/bin/env bash
    set -euo pipefail
    package='{{package}}'
    case "$package" in git|zsh|agents) ;; *) echo "Unsupported stow package: $package" >&2; exit 2 ;; esac
    [ -d "$package" ] || { echo "Unknown stow package: $package" >&2; exit 2; }
    stow -d "$PWD" -t "$HOME" -v -R "$package"

stow-restow-all:
    #!/usr/bin/env bash
    set -euo pipefail
    for package in git zsh agents; do
        just stow-restow "$package"
    done

stow-delete package:
    #!/usr/bin/env bash
    set -euo pipefail
    package='{{package}}'
    case "$package" in git|zsh|agents) ;; *) echo "Unsupported stow package: $package" >&2; exit 2 ;; esac
    [ -d "$package" ] || { echo "Unknown stow package: $package" >&2; exit 2; }
    stow -d "$PWD" -t "$HOME" -v -D "$package"

test-python: _ensure-uv
    uv run pytest

toml-check: _ensure-uv
    uv run python -c 'import subprocess, tomllib; from pathlib import Path; [tomllib.load(Path(path).open("rb")) for path in subprocess.run(["git", "ls-files", "*.toml"], check=True, capture_output=True, text=True).stdout.splitlines()]'

yaml-check:
    ruby -e 'require "psych"; paths = Dir.glob([".coderabbit.yml", ".github/*.{yaml,yml}", ".github/workflows/*.{yaml,yml}", "agents/.agents/skills/**/agents/*.{yaml,yml}"]); paths.sort.each { |path| Psych.safe_load(File.read(path), permitted_classes: [], aliases: false) }'

zizmor: _ensure-zizmor
    zizmor .github
