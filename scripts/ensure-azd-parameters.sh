#!/usr/bin/env bash
set -euo pipefail

fail() {
  echo "Unable to initialize required azd deployment parameters." >&2
  exit 1
}

azd_value() {
  local value
  if value="$(azd env get-value "$1" 2>/dev/null)"; then
    printf '%s' "${value}"
  fi
}

set_default() {
  local name="$1"
  local value="$2"
  if [[ -z "$(azd_value "${name}")" ]]; then
    azd env set "${name}" "${value}" --no-prompt >/dev/null 2>&1 || fail
  fi
}

resolve_principal_id() {
  local account_type account_name
  account_type="$(az account show --query user.type --only-show-errors -o tsv 2>/dev/null || true)"
  if [[ "${account_type}" == "user" ]]; then
    az ad signed-in-user show --query id --only-show-errors -o tsv 2>/dev/null
    return
  fi

  account_name="$(az account show --query user.name --only-show-errors -o tsv 2>/dev/null || true)"
  [[ -n "${account_name}" ]] || return 1
  az ad sp show --id "${account_name}" --query id --only-show-errors -o tsv 2>/dev/null
}

set_default KEY_VAULT_PUBLIC_NETWORK_ACCESS Enabled
set_default ENABLE_KEY_VAULT_PRIVATE_ENDPOINT false
set_default FOUNDRY_MODEL_VERSION 2025-08-07
set_default GATEWAY_TOKEN_LIMIT_PER_MINUTE 1000
set_default AZD_DEPLOY_WEB_SLOT_NAME production

if [[ -z "$(azd_value AZURE_PRINCIPAL_ID)" ]]; then
  principal_id="$(resolve_principal_id || true)"
  [[ -n "${principal_id}" ]] || fail
  azd env set AZURE_PRINCIPAL_ID "${principal_id}" --no-prompt >/dev/null 2>&1 || fail
fi
