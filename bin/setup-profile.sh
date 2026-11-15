#!/usr/bin/env bash
# Dispatch explicit machine profiles; keep host provisioning and updates separate.
set -euo pipefail
repository="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
source "$repository/bin/platform-profile.sh"
profile="$(select_profile "${1:-auto}")"
mode="${2:-setup}"
case "$mode" in setup|update|doctor) ;; *) profile_fail "Unknown operation $mode"; exit 2 ;; esac
cd "$repository"
if [[ "$profile" == macos ]]; then
  case "$mode" in
    setup) DOTFILES_DIR="$repository" bash bin/bootstrap.sh; just python-sync; just tools-sync ;;
    update) just update-macos ;;
    doctor) DOTFILES_DIR="$repository" bash bin/verify.sh ;;
  esac
  exit 0
fi
[[ "$EUID" -ne 0 ]] || { profile_fail "Run user-space setup as your ordinary user; only linux-host.sh install runs as root."; exit 2; }
for tool in bash git zsh stow curl tar unzip sha256sum gh cc; do
  command -v "$tool" >/dev/null || { profile_fail "Missing $tool; first run the documented bin/linux-host.sh provisioning step."; exit 2; }
done
export DOTFILES_REVIEW_PREFIX="${DOTFILES_REVIEW_PREFIX:-$HOME/.local/share/dotfiles-review}"
export DOTFILES_REVIEW_CACHE="${DOTFILES_REVIEW_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/dotfiles-review}"
export DOTFILES_REVIEW_SKILLS_DIR="${DOTFILES_REVIEW_SKILLS_DIR:-$HOME/.agents/skills}"
[[ "$DOTFILES_REVIEW_PREFIX" == /* && "$DOTFILES_REVIEW_SKILLS_DIR" == /* ]] || { profile_fail "Profile directories must be absolute."; exit 2; }
if [[ -d "$DOTFILES_REVIEW_PREFIX/cargo/bin" ]]; then
  export RUSTUP_HOME="$DOTFILES_REVIEW_PREFIX/rustup" CARGO_HOME="$DOTFILES_REVIEW_PREFIX/cargo"
  export PATH="$CARGO_HOME/bin:$PATH"
fi
if [[ "$mode" == doctor ]]; then
  exec bash bin/linux-review.sh exec uv run --locked --no-sync python scripts/profile_doctor.py
fi
# Refuse shell/Git collisions before downloading or changing links.
stow --simulate --no-folding -d "$repository" -t "$HOME" -S git zsh bash
bash bin/linux-rust.sh
if [[ -d "$DOTFILES_REVIEW_PREFIX/cargo/bin" ]]; then
  export RUSTUP_HOME="$DOTFILES_REVIEW_PREFIX/rustup" CARGO_HOME="$DOTFILES_REVIEW_PREFIX/cargo"
  export PATH="$CARGO_HOME/bin:$PATH"
fi
bash bin/linux-review.sh setup
export PATH="$DOTFILES_REVIEW_PREFIX/bin:$PATH"
export UV_CACHE_DIR="$DOTFILES_REVIEW_CACHE/uv"
export UV_PYTHON_INSTALL_DIR="$DOTFILES_REVIEW_PREFIX/python"
"$DOTFILES_REVIEW_PREFIX/venv/bin/python" scripts/skills_install.py helper-setup
"$DOTFILES_REVIEW_PREFIX/venv/bin/python" scripts/skills_install.py install --destination "$DOTFILES_REVIEW_SKILLS_DIR"
stow --no-folding -d "$repository" -t "$HOME" -S git zsh bash
bash bin/linux-review.sh exec uv run --locked --no-sync python scripts/profile_doctor.py
