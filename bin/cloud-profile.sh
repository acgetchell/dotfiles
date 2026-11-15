#!/usr/bin/env bash
# Launch from an installed interpreter, even when project editable metadata is stale.
set -euo pipefail
repository="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
source "$repository/bin/platform-profile.sh"
profile="$(select_profile auto)"
cd "$repository"
if [[ "$profile" == linux-cloud ]]; then
  export DOTFILES_REVIEW_PREFIX="${DOTFILES_REVIEW_PREFIX:-$HOME/.local/share/dotfiles-review}"
  export DOTFILES_REVIEW_CACHE="${DOTFILES_REVIEW_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/dotfiles-review}"
  export UV_PYTHON_INSTALL_DIR="$DOTFILES_REVIEW_PREFIX/python"
  export UV_CACHE_DIR="${UV_CACHE_DIR:-$DOTFILES_REVIEW_CACHE/uv}"
  export PATH="$DOTFILES_REVIEW_PREFIX/bin:$PATH"
fi
unset VIRTUAL_ENV CONDA_PREFIX UV_PROJECT_ENVIRONMENT UV_PYTHON UV_PROJECT UV_WORKING_DIR UV_CONFIG_FILE UV_SYSTEM_PYTHON UV_TARGET UV_PREFIX
command -v uv >/dev/null || { echo "Cloud lifecycle requires the pinned uv from connected setup." >&2; exit 2; }
python="$(uv python find --no-project --no-config --system --offline --no-python-downloads "$(cat .python-version)")"
exec "$python" -E -s "$repository/scripts/cloud_profile.py" "$@"
