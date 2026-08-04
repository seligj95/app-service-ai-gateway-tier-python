#!/usr/bin/env bash
set -euo pipefail
umask 077

readonly API_VERSION="2025-09-01-preview"
readonly DELETED_SERVICE_API_VERSION="2024-05-01"
readonly REPOSITORY_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly MAX_POLLS="${AI_GATEWAY_LIFECYCLE_MAX_POLLS:-30}"
readonly POLL_SECONDS="${AI_GATEWAY_LIFECYCLE_POLL_SECONDS:-2}"

fail() {
  echo "AI Gateway lifecycle operation failed." >&2
  exit 1
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

validate_nonnegative_integer() {
  [[ "$2" =~ ^[0-9]+$ ]] || fail
}

validate_target() {
  [[ "${gateway_name}" =~ ^aigw-[a-z0-9]{6,}$ ]] || fail
  [[ "${resource_group}" =~ ^rg-[a-z0-9-]{6,}$ ]] || fail
  [[ -n "${environment_name}" && -n "${subscription_id}" ]] || fail
}

marker_path() {
  printf '%s/.azure/%s/gateway-lifecycle-owned' "${REPOSITORY_ROOT}" "${environment_name}"
}

write_marker() {
  local marker
  [[ -n "${location}" ]] || fail
  marker="$(marker_path)"
  mkdir -p "$(dirname "${marker}")"
  chmod 700 "$(dirname "${marker}")"
  {
    printf 'environment_name=%s\n' "${environment_name}"
    printf 'subscription_id=%s\n' "${subscription_id}"
    printf 'resource_group=%s\n' "${resource_group}"
    printf 'gateway_name=%s\n' "${gateway_name}"
    printf 'location=%s\n' "${location}"
  } >"${marker}"
  chmod 600 "${marker}"
}

load_marker() {
  local marker
  marker="$(marker_path)"
  [[ -f "${marker}" ]] || return 1
  environment_name="$(sed -n 's/^environment_name=//p' "${marker}" | tail -n 1)"
  subscription_id="$(sed -n 's/^subscription_id=//p' "${marker}" | tail -n 1)"
  resource_group="$(sed -n 's/^resource_group=//p' "${marker}" | tail -n 1)"
  gateway_name="$(sed -n 's/^gateway_name=//p' "${marker}" | tail -n 1)"
  location="$(sed -n 's/^location=//p' "${marker}" | tail -n 1)"
  validate_target
  [[ -n "${location}" ]] || fail
}

delete_marker() {
  rm -f "$(marker_path)"
}

gateway_uri() {
  printf 'https://management.azure.com/subscriptions/%s/resourceGroups/%s/providers/Microsoft.ApiManagement/service/%s?api-version=%s' \
    "${subscription_id}" "${resource_group}" "${gateway_name}" "${API_VERSION}"
}

deleted_gateway_uri() {
  local normalized_location
  normalized_location="$(printf '%s' "${location}" | tr -d ' ' | tr '[:upper:]' '[:lower:]')"
  printf 'https://management.azure.com/subscriptions/%s/providers/Microsoft.ApiManagement/locations/%s/deletedservices/%s?api-version=%s' \
    "${subscription_id}" "${normalized_location}" "${gateway_name}" "${DELETED_SERVICE_API_VERSION}"
}

load_current_target() {
  environment_name="$(first_value "${AZURE_ENV_NAME:-}" "$(azd_value AZURE_ENV_NAME)")"
  subscription_id="$(first_value "${AZURE_SUBSCRIPTION_ID:-}" "$(azd_value AZURE_SUBSCRIPTION_ID)")"
  resource_group="$(first_value "${AZURE_RESOURCE_GROUP:-}" "${RESOURCE_GROUP:-}" "$(azd_value AZURE_RESOURCE_GROUP)")"
  gateway_name="$(first_value "${AI_GATEWAY_NAME:-}" "$(azd_value AI_GATEWAY_NAME)")"
  location="$(first_value "${AI_GATEWAY_LOCATION:-}" "${AZURE_LOCATION:-}" "$(azd_value AZURE_LOCATION)")"
  [[ -n "${resource_group}" && -n "${gateway_name}" ]] || return 1
  validate_target
}

read_live_gateway() {
  local record owner='' sku='' state='' live_location=''
  record="$(az rest --method get --uri "$(gateway_uri)" \
    --query 'join(`|`, [tags."azd-env-name", sku.name, properties.provisioningState, location])' \
    --only-show-errors -o tsv 2>/dev/null || true)"
  [[ -n "${record}" ]] || return 1

  IFS='|' read -r owner sku state live_location <<<"${record}"
  [[ "${owner}" == "${environment_name}" && "${sku}" == "AIGateway" ]] || fail
  [[ -n "${live_location}" ]] || fail
  location="${live_location}"
  gateway_state="${state}"
}

wait_for_missing() {
  local attempt
  for ((attempt = 1; attempt <= MAX_POLLS; attempt++)); do
    if ! az rest --method get --uri "$(gateway_uri)" --only-show-errors -o none >/dev/null 2>&1; then
      return 0
    fi
    sleep "${POLL_SECONDS}"
  done
  return 1
}

wait_for_deleted_gateway() {
  local attempt
  for ((attempt = 1; attempt <= MAX_POLLS; attempt++)); do
    if az rest --method get --uri "$(deleted_gateway_uri)" --only-show-errors -o none >/dev/null 2>&1; then
      return 0
    fi
    sleep "${POLL_SECONDS}"
  done
  return 1
}

purge_marked_deleted_gateway() {
  [[ -f "$(marker_path)" ]] || return 1
  az rest --method delete --uri "$(deleted_gateway_uri)" --only-show-errors -o none >/dev/null 2>&1 || fail
  delete_marker
}

prepare() {
  if ! read_live_gateway; then
    if [[ -f "$(marker_path)" ]] && wait_for_deleted_gateway; then
      purge_marked_deleted_gateway
    fi
    return 0
  fi

  if [[ "${gateway_state}" != "Failed" ]]; then
    return 0
  fi

  write_marker
  az rest --method delete --uri "$(gateway_uri)" --headers 'If-Match=*' --only-show-errors -o none >/dev/null 2>&1 || fail
  wait_for_missing || fail
  wait_for_deleted_gateway || fail
  purge_marked_deleted_gateway
}

predown() {
  load_current_target || return 0
  read_live_gateway || return 0
  write_marker
}

postdown() {
  environment_name="${AZURE_ENV_NAME:-$(azd_value AZURE_ENV_NAME)}"
  [[ -n "${environment_name}" ]] || return 0
  load_marker || return 0
  if wait_for_deleted_gateway; then
    purge_marked_deleted_gateway
  fi
}

validate_nonnegative_integer AI_GATEWAY_LIFECYCLE_MAX_POLLS "${MAX_POLLS}"
validate_nonnegative_integer AI_GATEWAY_LIFECYCLE_POLL_SECONDS "${POLL_SECONDS}"

mode="${1:-}"
case "${mode}" in
  prepare)
    load_current_target || exit 0
    prepare
    ;;
  predown)
    predown
    ;;
  postdown)
    postdown
    ;;
  *)
    echo "Usage: $0 prepare|predown|postdown" >&2
    exit 2
    ;;
esac
