#!/usr/bin/env bash
# Bootstrap a fresh macOS machine from this dotfiles repo.
#
# Idempotent: safe to re-run.

set -euo pipefail

DOTFILES_DIR="${DOTFILES_DIR:-$HOME/projects/dotfiles}"

if [[ ! -d "$DOTFILES_DIR" ]]; then
  echo "==> Dotfiles directory not found at $DOTFILES_DIR" >&2
  echo "    Set DOTFILES_DIR or clone the repo first." >&2
  exit 1
fi

JUST_VERSION="$(bash "$DOTFILES_DIR/bin/resolve-just-version.sh" "$DOTFILES_DIR/justfile")"

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

# rustup is keg-only, so expose its Cargo proxy to this non-interactive shell.
RUSTUP_PREFIX="$(brew --prefix rustup)"
export PATH="$RUSTUP_PREFIX/bin:${CARGO_HOME:-$HOME/.cargo}/bin:$PATH"

# 3. Stow packages
PACKAGES=(git zsh agents)
echo "==> Stowing packages: ${PACKAGES[*]}"
for pkg in "${PACKAGES[@]}"; do
  if [[ -d "$DOTFILES_DIR/$pkg" ]]; then
    stow --no-folding -d "$DOTFILES_DIR" -t "$HOME" -R "$pkg"
  else
    echo "    skipping missing package: $pkg" >&2
  fi
done

# 4. Cargo-installed tools
if command -v cargo >/dev/null 2>&1; then
  install_cargo_tool() {
    local tool="$1"
    local version="$2"
    local installed_version=""
    if command -v "$tool" >/dev/null 2>&1; then
      installed_version="$("$tool" --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true)"
    fi
    if [[ "$installed_version" != "$version" ]]; then
      echo "==> Installing $tool $version"
      cargo install --locked --force "$tool" --version "$version"
    else
      echo "==> $tool already installed: $installed_version"
    fi
  }

  install_cargo_tool just "$JUST_VERSION"
  for tool in dprint rumdl zizmor; do
    pin_name="${tool}_version"
    version="$(just --justfile "$DOTFILES_DIR/justfile" --evaluate "$pin_name")"
    if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
      echo "==> Invalid $pin_name in $DOTFILES_DIR/justfile: $version" >&2
      exit 1
    fi
    install_cargo_tool "$tool" "$version"
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
