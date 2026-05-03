# Brewfile - foundational dev environment
#
# Maintain with:
#   brew bundle install --file=Brewfile     # install everything declared here
#   brew bundle check   --file=Brewfile     # verify nothing is missing
#   brew bundle dump    --file=Brewfile.local --force --describe   # snapshot current machine
#
# Keep this file foundational. Per-machine extras belong in Brewfile.local
# (which should NOT be committed).


# ---- CLI tools (formulae) ----
brew "ansible"            # config management
brew "azure-cli"          # `az`
brew "dotnet"             # `dotnet`
brew "gh"                 # GitHub CLI
brew "git"                # newer than Apple's
brew "git-lfs"
brew "helm"               # `helm`
brew "kubernetes-cli"     # provides `kubectl`
brew "node"               # JS/TS toolchain
brew "python@3.13"        # `python3`
brew "powershell"         # `pwsh`
brew "rustup"             # rustc/cargo via rustup; alt: `brew "rust"`
brew "stow"               # GNU Stow (manages this repo)
brew "ripgrep"            # `rg`, used by verify.sh and dev tooling

# ---- GUI apps + tooling (casks) ----
cask "1password"
cask "1password-cli"      # `op`
cask "codex-app"
cask "docker-desktop"     # Docker Desktop (provides docker, buildx, compose)
cask "gitkraken"
cask "mactex"
cask "notion"
cask "obsidian"
cask "slack"
cask "tailscale-app"      # `tailscale`
cask "visual-studio-code" # `code`
cask "warp"
cask "zed"
cask "zotero"

# ---- Conditional: ChatGPT desktop (Apple Silicon, macOS 14+) ----
cask "chatgpt"            # safe to comment out on Intel / older macOS
