#!/usr/bin/env bash
# Resolve the just bootstrap pin before just itself is available.

set -euo pipefail
shopt -s extglob

justfile_path="${1:-justfile}"
declaration_re='^[[:space:]]*just_version[[:space:]]*:=[[:space:]]*(.*)$'
version=""

while IFS= read -r line; do
  if [[ "$line" =~ $declaration_re ]]; then
    value="${BASH_REMATCH[1]}"
    value="${value%%#*}"
    value="${value##+([[:space:]])}"
    value="${value%%+([[:space:]])}"

    if [[ ${#value} -ge 2 ]]; then
      first="${value:0:1}"
      last="${value: -1}"
      if [[ "$first" == "$last" && ( "$first" == '"' || "$first" == "'" ) ]]; then
        value="${value:1:${#value}-2}"
      fi
    fi

    version="$value"
    break
  fi
done < "$justfile_path"

if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "Invalid or missing just_version in $justfile_path: ${version:-missing}" >&2
  exit 1
fi

printf '%s\n' "$version"
