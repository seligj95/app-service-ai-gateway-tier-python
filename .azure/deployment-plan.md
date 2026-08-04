# Deployment Plan

## Status

Validated

## Scope

Create a new public, runnable, preview-only Python sample that hosts a FastAPI
agent and read-only MCP server on Linux Azure App Service. The agent must call
the dedicated Azure API Management AI Gateway tier for both model inference and
MCP tool access, with no direct provider fallback.

## Azure context

- Subscription: selected through `AZURE_SUBSCRIPTION_ID` and authorized for the
  dedicated AI Gateway tier preview
- Location: an entitled preview region, such as East US 2
- Deployment: Azure Developer CLI with Bicep
- Resource ownership: every resource is scoped to the current `azd` environment
  and tagged for deterministic cleanup
- Subscription-level changes: never register providers or change preview
  entitlements/policies without explicit approval

## Application

- Python 3.12, FastAPI, Microsoft Agent Framework
- Linux App Service P0v3, one instance, with a staging slot
- Health, status, browser chat UI, and SSE streaming chat endpoint
- Minimal read-only MCP server at `/mcp`
- Direct MCP endpoint protected by a dedicated backend secret
- Gateway model endpoint:
  `/default/models/openai/v1/`
- Gateway tool endpoint:
  `/default/toolservers/appservice-ops/mcp`
- Stable gateway model name: `appservice-chat`
- Explicit timeouts and sanitized correlation-aware logging
- Retry behavior:
  - never retry 401 or 404
  - bounded backoff and jitter for 429, honoring `Retry-After`
  - retry transient 5xx only before the first streamed chunk
  - never retry after partial output

## Infrastructure

- Deterministic resource group, tags, and resource names
- App Service plan, web app, and staging slot
- Managed identity suitable for Key Vault references
- Virtual network and App Service integration subnet
- Key Vault with RBAC authorization and portable network configuration
- Parameterized Key Vault public-network mode and optional private endpoint for
  target environments that require an existing network security perimeter
- Log Analytics workspace and workspace-based Application Insights
- Microsoft Foundry/Azure AI Services account
- `gpt-5-mini` GlobalStandard deployment, capacity 1, parameterized version
- Dedicated AI Gateway:
  - `Microsoft.ApiManagement/service@2025-09-01-preview`
  - SKU `AIGateway`, capacity 1
  - default workspace model provider and stable model registration
  - generated runtime key under `service/apiKeys@2025-09-01-preview`
  - read-only MCP ToolServer with gateway-injected backend credential
  - structured JSON `properties.policies` array containing `tokenLimit` at
    1000 TPM for the capacity-1 preflight
  - telemetry exporter to Application Insights
- Connector gateway:
  `Microsoft.Web/connectorGateways@2026-05-01-preview`
- Gateway system-assigned identity receives Foundry User role
  `53ca6127-db72-4b80-b1b0-d745d6d5456d`
- App identities receive only required Key Vault secret access; the supplied
  deployment principal receives Key Vault Secrets Officer for bounded
  post-provision data-plane writes

## Secrets and configuration

- Generate the gateway runtime API key in Azure; never place it in source,
  command output, logs, or deployment outputs
- Generate a distinct MCP backend secret
- Store both in Key Vault
- App Service reads gateway base URL, model, and secrets via configuration and
  Key Vault references
- Gateway calls use the `api-key` header
- Post-provision configuration retrieves the runtime key with
  `apiKeys/<name>/listSecrets`, writes secrets securely, and completes the
  ToolServer credential payload without printing secret values

## Observability

- Azure Monitor OpenTelemetry for the app
- AI Gateway telemetry exporter to the same workspace-based Application
  Insights resource
- Correlation IDs propagated without recording prompts, model responses, or
  secrets as telemetry attributes
- Documentation states that gateway OTLP preview exports model token usage only,
  not MCP traffic

## Security and portability

- Managed identity between gateway and Foundry
- Key Vault references for application secrets
- No direct provider credentials or fallback path in the application
- Direct MCP backend denies missing or invalid backend secret
- Portable Key Vault network parameter with an optional
  `SecuredByPerimeter` configuration documented for compatible environments
- Validate Cognitive Services local-auth governance and App Service public
  network policy before deployment

## Implementation steps

1. Research the two baseline repositories and authoritative Microsoft preview
   schemas.
2. Implement the FastAPI application, gateway model client, Agent Framework
   integration, MCP server, retries, SSE, telemetry, and UI.
3. Implement azd/Bicep infrastructure and bounded lifecycle scripts.
4. Implement secure post-provision key handling and ToolServer credential
   injection.
5. Add unit, integration-contract, lifecycle, redaction, and Bicep tests.
6. Write the README, architecture, preview limitations, and sample differences.
7. Run local tests, static checks, and Bicep builds.
8. Scan tracked files for secrets and environment-specific Azure identifiers.
9. In an authorized disposable environment, run a resource-group what-if,
   deploy, and verify health, model streaming, MCP routing/security, expected
   failure paths, and Application Insights telemetry.
10. Keep subscription-specific names, IDs, endpoints, timestamps, and deployment
    evidence outside the tracked repository.

## Validation criteria

- Pytest covers configuration/no-fallback, secret-safe headers/logging,
  401/404/429/Retry-After/5xx behavior, retry bounds, partial-stream behavior,
  SSE, MCP authentication/tools, correlation, and telemetry attributes.
- Script tests cover key redaction, registration payloads, and lifecycle guards.
- Every Bicep entry point and module builds.
- Resource-group what-if succeeds before deployment.
- Live checks prove:
  - health endpoint succeeds
  - model response streams through AI Gateway
  - MCP call succeeds through AI Gateway
  - direct MCP call without its backend secret is denied
  - invalid gateway key returns 401
  - unknown model returns 404
  - token policy returns 429 and records whether `Retry-After` is present
  - transient 5xx behavior is tested without unsafe production mutation
  - app and model-token telemetry arrives in Application Insights
- A backing model swap is exercised if safe, otherwise a precise procedure is
  documented.

## Cleanup

- Lifecycle cleanup is bounded: `predown` records a verified current-environment
  gateway marker and `postdown` targets only that marked soft-deleted gateway.
- No broad subscription or resource-group deletion is performed by scripts.

## Preview caveat

This sample demonstrates public-preview APIs and has no SLA. It must never be
described as production-ready. Preview APIs, regions, limits, pricing, portal
surfaces, and contracts can change.

## Portable validation procedure

Run local validation before using an Azure subscription:

```bash
./scripts/run-tests.sh
./scripts/build-bicep.sh
```

The tests cover retry behavior, SSE, MCP authentication and tools, telemetry
redaction, least-privilege contracts, lifecycle guards, and shell syntax. The
Bicep build compiles each entry point and module; preview resources may produce
`BCP081` warnings when their types are not yet present in the local Bicep type
registry.

## Validation proof

Validated on 2026-08-04 without recording subscription-specific identifiers:

- `PATH="$PWD/.venv/bin:$PATH" ./scripts/run-tests.sh`: 32 tests passed,
  including the project-relative Oryx startup-path contract.
- `./scripts/build-bicep.sh`: every Bicep entry point and module compiled; only
  expected `BCP081` warnings remained for preview types absent from the local
  Bicep registry.
- `azd provision --preview --no-prompt`: generated the infrastructure preview
  successfully without applying changes.
- `azd package web --no-prompt`: packaged the App Service application
  successfully.
- Azure Developer CLI 1.29.0 authentication, subscription/location selection,
  and the explicit `production` App Service deployment target were confirmed.

Before provisioning an authorized disposable environment:

- Confirm Azure Developer CLI authentication and validate `azure.yaml`.
- Confirm the selected subscription, deployment principal, region entitlement,
  provider availability, model version, and quota.
- Review Azure Policy effects and least-privilege role-assignment permissions.
- Run a no-change provisioning preview or resource-group what-if.

## Expected deployment verification

After an authorized deployment, verify the following without committing
resource names, IDs, URLs, timestamps, telemetry counts, or command output:

- `/health` and `/status` return 200 and report the expected generic
  configuration state.
- Model responses stream only through the AI Gateway route.
- Gateway ToolServer initialization, discovery, and a read-only `tools/call`
  succeed.
- Direct `/mcp` access without the backend secret returns 401.
- An invalid runtime key returns 401 and an unknown model returns 404.
- A disposable low token limit returns 429; record separately whether the
  response includes `Retry-After`.
- Client tests cover both header-present and header-absent bounded retry
  behavior, plus transient 5xx and partial-stream handling.
- Gateway Foundry User and App Service Key Vault Secrets User assignments are
  scoped only to the intended resources.
- Application Insights receives safe request/dependency telemetry, and the
  gateway exporter emits model token usage without MCP payloads.
- Production health succeeds after `azd deploy`; the default flow does not
  deploy or swap the optional staging slot.
