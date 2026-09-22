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

# 3. Oh My Zsh (clone only; preserve shell configuration and default shell).
OMZ_DIR="$HOME/.oh-my-zsh"
if [[ -f "$OMZ_DIR/oh-my-zsh.sh" ]]; then
  echo "==> Oh My Zsh already installed"
elif [[ -e "$OMZ_DIR" || -L "$OMZ_DIR" ]]; then
  echo "==> Incomplete Oh My Zsh installation at $OMZ_DIR; review it before retrying." >&2
  exit 1
else
  echo "==> Installing Oh My Zsh"
  git clone --depth=1 https://github.com/ohmyzsh/ohmyzsh.git "$OMZ_DIR"
fi

# 4. Stow packages
PACKAGES=(git zsh agents)
echo "==> Stowing packages: ${PACKAGES[*]}"
for pkg in "${PACKAGES[@]}"; do
  if [[ -d "$DOTFILES_DIR/$pkg" ]]; then
    stow_options=(-d "$DOTFILES_DIR" -t "$HOME")
    if [[ "$pkg" != agents ]]; then
      stow_options+=(--no-folding)
    fi
    if [[ "$pkg" == agents ]]; then
      bash "$DOTFILES_DIR/bin/restow-agents.sh" "$DOTFILES_DIR"
    else
      stow "${stow_options[@]}" -R "$pkg"
    fi
  else
    echo "    skipping missing package: $pkg" >&2
  fi
done

# 5. Cargo-installed tools
if command -v cargo >/dev/null 2>&1; then
  cargo_version_pattern='[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?(\+[0-9A-Za-z.-]+)?'
  install_cargo_tool() {
    local tool="$1"
    local version="$2"
    local executable="${3:-$tool}"
    local installed_version=""
    if command -v "$executable" >/dev/null 2>&1; then
      installed_version="$("$executable" --version 2>/dev/null | grep -oE "$cargo_version_pattern" | head -1 || true)"
    fi
    if [[ "$installed_version" != "$version" ]]; then
      echo "==> Installing $tool $version"
      cargo install --locked --force "$tool" --version "$version"
    else
      echo "==> $tool already installed: $installed_version"
    fi
  }

  install_cargo_tool just "$JUST_VERSION"
  for tool in cargo-update dprint rumdl zizmor; do
    pin_name="${tool//-/_}_version"
    version="$(just --justfile "$DOTFILES_DIR/justfile" --evaluate "$pin_name")"
    if [[ ! "$version" =~ ^${cargo_version_pattern}$ ]]; then
      echo "==> Invalid $pin_name in $DOTFILES_DIR/justfile: $version" >&2
      exit 1
    fi
    executable="$tool"
    if [[ "$tool" == cargo-update ]]; then
      executable=cargo-install-update
    fi
    install_cargo_tool "$tool" "$version" "$executable"
  done
else
  echo "==> Skipping cargo-installed tools: cargo not on PATH" >&2
fi

# 6. Verify
if [[ -x "$DOTFILES_DIR/bin/verify.sh" ]]; then
  echo "==> Running verify.sh"
  "$DOTFILES_DIR/bin/verify.sh"
fi

echo "==> Bootstrap complete."
