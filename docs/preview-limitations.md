# Preview limitations

This sample uses preview-only APIs and has **no SLA**. It is not a
production-ready reference. APIs, resource schemas, portal surfaces, regional
availability, limits, and behavior may change without notice.

## Availability and business-model caveats

- The dedicated Azure API Management AI Gateway tier is currently limited to
  **East US 2 and Sweden Central** for this sample's documented preview scope.
- Pricing and the business model are unannounced.
- Numeric limits are unpublished.
- Preview APIs may change, including the `2025-09-01-preview` APIM service and
  workspace children and `2026-05-01-preview` connector gateway resources.
- Portal URLs and labels are not stable. The claims checklist tracks a current
  `ai.gateway.azure.com` versus `gateway.ai.azure.com` inconsistency.

## Validate before use

1. Confirm subscription entitlement, model availability/version, and quota in
   the selected region.
2. Confirm the `gpt-5-mini` GlobalStandard capacity-1 deployment succeeds
   before treating the Bicep parameter default as usable.
3. Confirm `disableLocalAuth: true` remains compatible with the gateway's
   managed identity provider in the selected preview API/region.
4. Confirm the ToolServer child accepts the documented streamable HTTP and
   header credential payload at deployment time.
5. Confirm whether a 429 from the model's structured `tokenLimit` policy emits
   `Retry-After`. The client uses bounded jittered backoff when the header is
   absent and honors it when present.
6. Confirm Key Vault reference resolution after RBAC propagation; role
   assignment convergence is asynchronous.
7. Confirm stable model swap behavior before claiming that a backing deployment
   can be changed without client impact.

## Telemetry limitation

The gateway OTLP telemetry exporter is preview behavior and exports **model
token usage only; it does not export MCP traffic**. Application-level
OpenTelemetry still captures safe request/dependency operational metadata, but
the sample intentionally excludes prompts, model responses, keys, and backend
secrets from custom telemetry attributes.

## Key Vault network mode

The portable Bicep default is `publicNetworkAccess: Enabled`. Environments that
require an existing network security perimeter can use
`SecuredByPerimeter` and enable the sample's Key Vault private endpoint so App
Service Key Vault references use VNet integration and private DNS. This
repository intentionally does not create or change a network security
perimeter. Choose settings that match the target subscription's network design.
