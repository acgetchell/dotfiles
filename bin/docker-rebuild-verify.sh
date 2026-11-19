#!/usr/bin/env bash
# Runs only inside the disposable image; never mount a real home into this harness.
set -euo pipefail
repository="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$repository"
export DOTFILES_REVIEW_PREFIX="$HOME/.local/share/dotfiles-review"
export DOTFILES_REVIEW_CACHE="$HOME/.cache/dotfiles-review"
export UV_CACHE_DIR="$DOTFILES_REVIEW_CACHE/uv"
export UV_PYTHON_INSTALL_DIR="$DOTFILES_REVIEW_PREFIX/python"
export PATH="$DOTFILES_REVIEW_PREFIX/bin:$DOTFILES_REVIEW_PREFIX/cargo/bin:$PATH"
export RUSTUP_HOME="$DOTFILES_REVIEW_PREFIX/rustup" CARGO_HOME="$DOTFILES_REVIEW_PREFIX/cargo"
case "${1:-}" in
  provision)
    # Fixture-only Git metadata allows the real lifecycle to prove source preservation.
    git init -q
    git add .
    git -c user.name=Fixture -c user.email=fixture@example.invalid commit -qm 'Disposable rebuild source'
    printf 'preserve\n' > "$HOME/unrelated-file"
    printf 'export DOTFILES_LOCAL_MARKER=preserve\n' > "$HOME/.zshrc.local"
    mkdir -p "$HOME/.agents/skills/unrelated-skill"
    printf 'local skill\n' > "$HOME/.agents/skills/unrelated-skill/SKILL.md"
    bash bin/linux-rust.sh
    bash bin/linux-review.sh setup
    "$DOTFILES_REVIEW_PREFIX/venv/bin/python" scripts/docker_rebuild_fixture.py prepare
    just update linux-cloud
    just update linux-cloud
    just cloud-provision target/rebuild-inventory.toml
    ;;
  offline)
    export UV_OFFLINE=1 UV_PYTHON_DOWNLOADS=never
    bash bin/setup-profile.sh linux-cloud doctor
    just cloud-startup target/rebuild-inventory.toml
    just cloud-startup target/rebuild-inventory.toml
    just cloud-doctor target/rebuild-inventory.toml
    "$DOTFILES_REVIEW_PREFIX/venv/bin/python" scripts/docker_rebuild_fixture.py verify
    test "$(cat "$HOME/unrelated-file")" = preserve
    test "$(cat "$HOME/.agents/skills/unrelated-skill/SKILL.md")" = 'local skill'
    zsh -lic 'test "$DOTFILES_LOCAL_MARKER" = preserve'
    ;;
  *) echo 'Usage: docker-rebuild-verify.sh {provision|offline}' >&2; exit 2 ;;
esac
