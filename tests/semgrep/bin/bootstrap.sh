#!/usr/bin/env bash

# ok: dotfiles.shell.no-unreviewed-curl-shell
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# ruleid: dotfiles.shell.no-unreviewed-curl-shell
curl -fsSL https://example.com/install.sh | bash

# ruleid: dotfiles.shell.no-unreviewed-curl-shell
sh -c "$(curl -fsSL https://example.com/install.sh)"

# ruleid: dotfiles.bootstrap.no-codex-stow-package
PACKAGES=(git zsh agents codex)

# ok: dotfiles.bootstrap.no-codex-stow-package
PACKAGES=(git zsh agents)
