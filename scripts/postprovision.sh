#!/usr/bin/env bash
set -euo pipefail
umask 077

readonly API_VERSION="2025-09-01-preview"
readonly REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly MAX_POLLS="${POSTPROVISION_MAX_POLLS:-30}"
readonly POLL_SECONDS="${POSTPROVISION_POLL_SECONDS:-4}"

fail() {
  echo "Post-provision gateway setup failed during ${current_stage:-initialization}. No secret values were emitted." >&2
  exit 1
}

usage() {
  echo "Usage: $0 configure|verify" >&2
}

azd_value() {
  local value
  if value="$(azd env get-value "$1" 2>/dev/null)"; then
    printf '%s' "${value}"
  fi
}

first_value() {
  local value
  for value in "$@"; do
    if [[ -n "${value}" && "${value}" != "null" ]]; then
      printf '%s' "${value}"
      return 0
    fi
  done
}

required_value() {
  local value
  value="$(first_value "$2")"
  [[ -n "${value}" ]] || fail
  printf '%s' "${value}"
}

validate_nonnegative_integer() {
  [[ "$2" =~ ^[0-9]+$ ]] || fail
}

wait_for() {
  local attempt
  for ((attempt = 1; attempt <= MAX_POLLS; attempt++)); do
    if "$@"; then
      return 0
    fi
    sleep "${POLL_SECONDS}"
  done
  return 1
}

set_secret_from_file() {
  local secret_name="$1"
  local value="$2"
  printf '%s' "${value}" |
    python3 -c \
      'import json, pathlib, sys; pathlib.Path(sys.argv[1]).write_text(json.dumps({"properties": {"value": sys.stdin.read()}}), encoding="utf-8")' \
      "${secret_file}"
  chmod 600 "${secret_file}"
  az rest \
    --method put \
    --uri "https://management.azure.com${key_vault_resource_id}/secrets/${secret_name}?api-version=2023-07-01" \
    --body @"${secret_file}" \
    --only-show-errors \
    -o none >/dev/null 2>&1 || return 1
  : >"${secret_file}"
}

model_registered() {
  [[ "$(az rest --method get \
    --uri "https://management.azure.com${gateway_resource_id}/workspaces/default/modelProviders/foundry/models/appservice-chat?api-version=${API_VERSION}" \
    --query name --only-show-errors -o tsv 2>/dev/null || true)" == "appservice-chat" ]]
}

gateway_owned_and_ready() {
  local record owner='' sku='' state=''
  record="$(az rest --method get \
    --uri "https://management.azure.com${gateway_resource_id}?api-version=${API_VERSION}" \
    --query 'join(`|`, [tags."azd-env-name", sku.name, properties.provisioningState])' \
    --only-show-errors -o tsv 2>/dev/null || true)"
  IFS='|' read -r owner sku state <<<"${record}"
  [[ "${owner}" == "${environment_name}" && "${sku}" == "AIGateway" && "${state}" == "Succeeded" ]]
}

inject_tool_server() {
  az rest \
    --method put \
    --uri "https://management.azure.com${gateway_resource_id}/workspaces/default/toolServers/appservice-ops?api-version=${API_VERSION}" \
    --body @"${tool_server_body}" \
    --only-show-errors \
    -o none >/dev/null 2>&1
}

tool_server_registered() {
  [[ "$(az rest --method get \
    --uri "https://management.azure.com${gateway_resource_id}/workspaces/default/toolServers/appservice-ops?api-version=${API_VERSION}" \
    --query "properties.type == 'mcp' && properties.endpoints[0].mcp.transport == 'streamableHttp' && contains(keys(properties.endpoints[0].credentials.headers), 'x-appservice-mcp-secret')" \
    --only-show-errors -o tsv 2>/dev/null || true)" == "true" ]]
}

telemetry_registered() {
  [[ "$(az rest --method get \
    --uri "https://management.azure.com${gateway_resource_id}/workspaces/default/telemetryExporters/appinsights?api-version=${API_VERSION}" \
    --query properties.payloadCapture --only-show-errors -o tsv 2>/dev/null || true)" == "false" ]]
}

key_vault_references_registered() {
  local count
  count="$(az webapp config appsettings list \
    --name "${web_name}" \
    --resource-group "${resource_group}" \
    --query "[?name=='AZURE_AI_GATEWAY_API_KEY' || name=='MCP_BACKEND_SECRET'].value" \
    --only-show-errors -o tsv 2>/dev/null | grep -c '^@Microsoft.KeyVault' || true)"
  [[ "${count}" == "2" ]]
}

gateway_model_ready() {
  local status
  status="$(
    printf '%s\n' "header = \"api-key: ${gateway_api_key}\"" |
      curl --config - \
        --silent \
        --show-error \
        --output /dev/null \
        --write-out '%{http_code}' \
        --request POST \
        "${gateway_url%/}/default/models/openai/v1/chat/completions" \
        --header 'content-type: application/json' \
        --data '{"model":"appservice-chat","messages":[{"role":"user","content":"Reply with ok."}],"max_completion_tokens":16}' \
        2>/dev/null || true
  )"
  [[ "${status}" =~ ^2[0-9][0-9]$ ]]
}

gateway_mcp_ready() {
  local status
  status="$(
    printf '%s\n' "header = \"api-key: ${gateway_api_key}\"" |
      curl --config - \
        --silent \
        --show-error \
        --output /dev/null \
        --write-out '%{http_code}' \
        --request POST \
        "${gateway_url%/}/default/toolservers/appservice-ops/mcp" \
        --header 'content-type: application/json' \
        --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"postprovision","version":"1"}}}' \
        2>/dev/null || true
  )"
  [[ "${status}" =~ ^2[0-9][0-9]$ ]]
}

web_ready() {
  local status
  status="$(curl \
    --silent \
    --show-error \
    --output /dev/null \
    --write-out '%{http_code}' \
    "${web_url%/}/health" 2>/dev/null || true)"
  [[ "${status}" =~ ^2[0-9][0-9]$ ]]
}

retrieve_gateway_api_key() {
  gateway_api_key="$(
    az rest \
      --method post \
      --uri "https://management.azure.com${gateway_resource_id}/apiKeys/${runtime_key_name}/listSecrets?api-version=${API_VERSION}" \
      --body '{}' \
      --query 'primaryKey || properties.primaryKey || primaryValue || properties.primaryValue' \
      --only-show-errors \
      -o tsv 2>/dev/null || true
  )"
  [[ -n "${gateway_api_key}" ]]
}

validate_nonnegative_integer POSTPROVISION_MAX_POLLS "${MAX_POLLS}"
validate_nonnegative_integer POSTPROVISION_POLL_SECONDS "${POLL_SECONDS}"

mode="${1:-configure}"
case "${mode}" in
  configure|verify) ;;
  *) usage; exit 2 ;;
esac

environment_name="$(required_value AZURE_ENV_NAME "$(first_value "${AZURE_ENV_NAME:-}" "$(azd_value AZURE_ENV_NAME)")")"
resource_group="$(required_value AZURE_RESOURCE_GROUP "$(first_value "${AZURE_RESOURCE_GROUP:-}" "${RESOURCE_GROUP:-}" "$(azd_value AZURE_RESOURCE_GROUP)")")"
gateway_resource_id="$(required_value AI_GATEWAY_RESOURCE_ID "$(first_value "${AI_GATEWAY_RESOURCE_ID:-}" "$(azd_value AI_GATEWAY_RESOURCE_ID)")")"
gateway_url="$(required_value AI_GATEWAY_URL "$(first_value "${AI_GATEWAY_URL:-}" "$(azd_value AI_GATEWAY_URL)")")"
key_vault_name="$(required_value KEY_VAULT_NAME "$(first_value "${KEY_VAULT_NAME:-}" "$(azd_value KEY_VAULT_NAME)")")"
key_vault_resource_id="$(az keyvault show \
  --resource-group "${resource_group}" \
  --name "${key_vault_name}" \
  --query id --only-show-errors -o tsv 2>/dev/null || true)"
key_vault_resource_id="$(required_value KEY_VAULT_RESOURCE_ID "${key_vault_resource_id}")"
web_name="$(required_value WEB_NAME "$(first_value "${WEB_NAME:-}" "$(azd_value WEB_NAME)")")"
web_url="$(first_value "${WEB_URL:-}" "$(azd_value WEB_URL)")"
web_url="${web_url:-https://${web_name}.azurewebsites.net}"
web_staging_url="$(first_value "${WEB_STAGING_URL:-}" "$(azd_value WEB_STAGING_URL)")"
web_staging_url="${web_staging_url:-https://${web_name}-staging.azurewebsites.net}"
runtime_key_name="$(required_value AI_GATEWAY_RUNTIME_KEY_NAME "$(first_value "${AI_GATEWAY_RUNTIME_KEY_NAME:-}" "$(azd_value AI_GATEWAY_RUNTIME_KEY_NAME)")")"
runtime_key_secret_name="$(required_value GATEWAY_RUNTIME_KEY_SECRET_NAME "$(first_value "${GATEWAY_RUNTIME_KEY_SECRET_NAME:-}" "$(azd_value GATEWAY_RUNTIME_KEY_SECRET_NAME)")")"
mcp_secret_name="$(required_value MCP_BACKEND_SECRET_NAME "$(first_value "${MCP_BACKEND_SECRET_NAME:-}" "$(azd_value MCP_BACKEND_SECRET_NAME)")")"

state_directory="${REPOSITORY_ROOT}/.azure/${environment_name}"
mkdir -p "${state_directory}"
chmod 700 "${state_directory}"
secret_file="${state_directory}/.postprovision-secret"
tool_server_body="${state_directory}/.toolserver-body.json"
cleanup() {
  rm -f "${secret_file}" "${tool_server_body}"
}
trap cleanup EXIT

current_stage="gateway readiness"
wait_for gateway_owned_and_ready || fail

if [[ "${mode}" == "configure" ]]; then
  current_stage="runtime key retrieval"
  retrieve_gateway_api_key || fail
  mcp_backend_secret="$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')"
  current_stage="runtime key storage"
  wait_for set_secret_from_file "${runtime_key_secret_name}" "${gateway_api_key}" || fail
  current_stage="MCP backend secret storage"
  wait_for set_secret_from_file "${mcp_secret_name}" "${mcp_backend_secret}" || fail

  MCP_BACKEND_SECRET_FOR_JSON="${mcp_backend_secret}" \
  WEB_URL_FOR_JSON="${web_url:-https://${web_name}.azurewebsites.net}" \
  python3 - "${tool_server_body}" <<'PY'
import json
import os
import pathlib
import sys

payload = {
    "properties": {
        "displayName": "App Service read-only operations",
        "description": "Read-only App Service operations MCP server.",
        "type": "mcp",
        "failureMode": "failClosed",
        "endpoints": [
            {
                "namespace": "appservice-ops",
                "kind": "mcp",
                "mcp": {
                    "url": os.environ["WEB_URL_FOR_JSON"].rstrip("/") + "/mcp",
                    "transport": "streamableHttp",
                },
                "credentials": {
                    "type": "header",
                    "headers": {
                        "x-appservice-mcp-secret": [os.environ["MCP_BACKEND_SECRET_FOR_JSON"]],
                    },
                },
            }
        ],
    }
}
pathlib.Path(sys.argv[1]).write_text(json.dumps(payload), encoding="utf-8")
PY
  chmod 600 "${tool_server_body}"

  current_stage="ToolServer credential injection"
  wait_for inject_tool_server || fail
  unset mcp_backend_secret

  current_stage="model registration"
  wait_for model_registered || fail
  current_stage="ToolServer registration"
  wait_for tool_server_registered || fail
  current_stage="telemetry exporter registration"
  wait_for telemetry_registered || fail
  sleep 20
  current_stage="Key Vault reference registration"
  wait_for key_vault_references_registered || fail
  current_stage="gateway model readiness"
  wait_for gateway_model_ready || fail

  unset gateway_api_key
  echo "Gateway model, ToolServer, telemetry exporter, and Key Vault references verified."
else
  current_stage="runtime key retrieval"
  retrieve_gateway_api_key || fail
  current_stage="model registration"
  wait_for model_registered || fail
  current_stage="ToolServer registration"
  wait_for tool_server_registered || fail
  current_stage="telemetry exporter registration"
  wait_for telemetry_registered || fail
  current_stage="staging web readiness"
  production_web_url="${web_url}"
  web_url="${web_staging_url}"
  wait_for web_ready || fail
  current_stage="staging slot swap"
  az webapp deployment slot swap \
    --resource-group "${resource_group}" \
    --name "${web_name}" \
    --slot staging \
    --target-slot production \
    --only-show-errors \
    -o none >/dev/null 2>&1 || fail
  web_url="${production_web_url}"
  current_stage="production web readiness"
  wait_for web_ready || fail
  current_stage="gateway model readiness"
  wait_for gateway_model_ready || fail
  current_stage="gateway MCP readiness"
  wait_for gateway_mcp_ready || fail
  unset gateway_api_key
  echo "Deployed web, gateway model, gateway MCP route, and telemetry exporter verified."
fi
