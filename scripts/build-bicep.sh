#!/usr/bin/env bash
set -euo pipefail

command -v az >/dev/null 2>&1 || {
  echo "Azure CLI is required to build Bicep." >&2
  exit 127
}

while IFS= read -r file; do
  az bicep build --file "${file}" --stdout >/dev/null
done < <(find infra -type f -name '*.bicep' | sort)

echo "All Bicep files built successfully."
