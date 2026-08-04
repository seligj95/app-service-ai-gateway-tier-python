# Deployment Plan

## Status

Deployed and Verified

## Scope

Create a new public, runnable, preview-only Python sample that hosts a FastAPI
agent and read-only MCP server on Linux Azure App Service. The agent must call
the dedicated Azure API Management AI Gateway tier for both model inference and
MCP tool access, with no direct provider fallback.

## Azure context

- Subscription: Demo Three Subscription
  (`7e574780-0f87-42e8-af8c-5e8cb7d3540a`)
- Location: East US 2
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
- Demo Three override for `publicNetworkAccess: SecuredByPerimeter`
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
- Portable Key Vault network parameter with the Demo Three
  `SecuredByPerimeter` override documented and validated
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
6. Write the README, architecture, preview limitations, sample differences,
   Tech Community HTML body fragment, and claims/screenshot checklist.
7. Run local tests, static checks, and Bicep builds.
8. Set this plan status to `Ready for Validation` and invoke `azure-validate`.
9. Invoke `azure-deploy`, run a resource-group what-if, deploy to Demo Three,
   and verify health, model streaming, MCP routing/security, expected failure
   paths, and Application Insights telemetry.
10. Commit and push all deliverables, then report results and any verified
    preview limitations to the creator session.

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

## Azure validation steps

- [x] Azure Developer CLI installation and authentication
- [x] `azure.yaml` schema validation
- [x] Demo Three environment, subscription, principal, and East US 2 context
- [x] Provider registration and preview API inspection
- [x] `gpt-5-mini` GlobalStandard quota inspection
- [x] Python tests and application package validation
- [x] Bicep compilation and lint
- [x] Static least-privilege RBAC verification
- [x] Azure Policy review
- [x] No-change azd provisioning preview

## Section 7: Validation Proof

Validated on 2026-08-03 against Demo Three Subscription in East US 2.

- `azure-azd validate_azure_yaml`: passed against the stable schema.
- `azd auth login --check-status`: authenticated.
- Demo Three context: subscription
  `7e574780-0f87-42e8-af8c-5e8cb7d3540a`, environment
  `ai-gateway-tier-demo3`, location `eastus2`.
- Provider inspection: `Microsoft.ApiManagement`, `Microsoft.Web`,
  `Microsoft.CognitiveServices`, `Microsoft.KeyVault`, `Microsoft.Network`,
  `Microsoft.Insights`, and `Microsoft.OperationalInsights` are registered.
  APIM advertises `2025-09-01-preview`; no provider registration was changed.
- `az cognitiveservices usage list --location eastus2`: `gpt-5-mini`
  GlobalStandard limit 1000 TPM, current usage 0.
- `./.venv/bin/python -m pytest`: 26 passed.
- `bash scripts/build-bicep.sh`: all Bicep files built. `BCP081` warnings are
  limited to the requested preview types missing from the local Bicep type
  registry.
- `az bicep lint` on both templates: passed with the same preview type warnings.
- `azd package --no-prompt`: App Service package created successfully.
- `azd provision --preview --no-prompt`: succeeded in 24 seconds with only
  create operations under deterministic resource group
  `rg-ai-gateway-tier-demo3-k6adxbp64d`.
- Static RBAC review:
  - gateway system identity -> Foundry User at the Azure AI Services account;
  - web and staging identities -> Key Vault Secrets User at the vault;
  - deployment principal -> Key Vault Secrets Officer at the vault.
- Policy review: Cognitive Services local authentication is disabled by the
  template; Key Vault uses the required `SecuredByPerimeter` Demo Three value;
  the applicable App Service public-network built-in is Audit, not Deny; VNet
  outbound routing and TLS settings are configured.

## Deployment Verification

- Infrastructure provisioned successfully in deterministic resource group
  `rg-ai-gateway-tier-demo3-k6adxbp64d`.
- App Service endpoint:
  `https://appsvc-aigw-k6adxbp64d.azurewebsites.net/`.
- Health and status return 200; status reports gateway configured, telemetry
  enabled, and stable model `appservice-chat`.
- Direct model streaming through the gateway passed.
- Gateway ToolServer initialization, tool discovery, and `tools/call` passed;
  the App Service backend returned `status: healthy`.
- Direct `/mcp` without the backend secret returned 401.
- Invalid runtime key returned 401; unknown model returned 404.
- Disposable 1-TPM policy returned 429. The preview response did not emit
  `Retry-After`; the policy was restored to 1000 TPM. Client tests cover both
  header-present and header-absent bounded retry behavior.
- Live role verification passed for gateway Foundry User and production/staging
  Key Vault Secrets User assignments.
- Application Insights contains 105 request records from deployment and live
  checks. Gateway telemetry contains six `gen_ai.client.token.usage` samples
  totaling 1336 tokens. The documented preview limitation remains: gateway OTLP
  exports model token usage, not MCP traffic.
- Both production and staging `/health` endpoints return 200 after the
  staging-first deployment and swap flow.
