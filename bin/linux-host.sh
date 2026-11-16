#!/usr/bin/env bash
# Explicit privileged base provisioning; user-space setup never invokes sudo.
set -euo pipefail
repository="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
source "$repository/bin/platform-profile.sh"
select_profile linux-cloud >/dev/null
packages=(bash build-essential ca-certificates curl gh git jq pkg-config stow tar unzip xz-utils zsh)
case "${1:-plan}" in
  plan) printf 'apt-get install --no-install-recommends'; printf ' %s' "${packages[@]}"; printf '\n' ;;
  install)
    [[ "$EUID" -eq 0 ]] || { echo "Run the explicit host step as root: sudo bash bin/linux-host.sh install" >&2; exit 2; }
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y --no-install-recommends "${packages[@]}"
    ;;
  *) echo "Usage: bin/linux-host.sh {plan|install}" >&2; exit 2 ;;
esac
