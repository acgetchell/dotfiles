#!/usr/bin/env bash
# Bootstrap a fresh macOS machine from this dotfiles repo.
#
# Idempotent: safe to re-run.

set -euo pipefail

DOTFILES_DIR="${DOTFILES_DIR:-$HOME/projects/dotfiles}"
JUST_VERSION="${JUST_VERSION:-1.56.0}"
ZIZMOR_VERSION="${ZIZMOR_VERSION:-1.26.1}"

if [[ ! -d "$DOTFILES_DIR" ]]; then
  echo "==> Dotfiles directory not found at $DOTFILES_DIR" >&2
  echo "    Set DOTFILES_DIR or clone the repo first." >&2
  exit 1
fi

# 1. Homebrew
if ! command -v brew >/dev/null 2>&1; then
  echo "==> Installing Homebrew"
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  # Apple Silicon: ensure brew is on PATH for the rest of this script
  if [[ -x /opt/homebrew/bin/brew ]]; then
    eval "$(/opt/homebrew/bin/brew shellenv)"
  fi
else
  echo "==> Homebrew already installed: $(brew --version | head -n1)"
fi

# 2. Brewfile
echo "==> Installing Brewfile bundle"
brew bundle install --file="$DOTFILES_DIR/Brewfile"

# 3. Stow packages
PACKAGES=(git zsh agents)
echo "==> Stowing packages: ${PACKAGES[*]}"
for pkg in "${PACKAGES[@]}"; do
  if [[ -d "$DOTFILES_DIR/$pkg" ]]; then
    stow -d "$DOTFILES_DIR" -t "$HOME" -R "$pkg"
  else
    echo "    skipping missing package: $pkg" >&2
  fi
done

# 4. Cargo-installed tools
if command -v cargo >/dev/null 2>&1; then
  for tool_spec in "just:$JUST_VERSION" "zizmor:$ZIZMOR_VERSION"; do
    tool="${tool_spec%%:*}"
    version="${tool_spec##*:}"
    installed_version=""
    if command -v "$tool" >/dev/null 2>&1; then
      installed_version="$("$tool" --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true)"
    fi
    if [[ "$installed_version" != "$version" ]]; then
      echo "==> Installing $tool $version"
      cargo install --locked --force "$tool" --version "$version"
    else
      echo "==> $tool already installed: $installed_version"
    fi
  done
else
  echo "==> Skipping cargo-installed tools: cargo not on PATH" >&2
fi

# 5. Verify
if [[ -x "$DOTFILES_DIR/bin/verify.sh" ]]; then
  echo "==> Running verify.sh"
  "$DOTFILES_DIR/bin/verify.sh"
fi

echo "==> Bootstrap complete."
