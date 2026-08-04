# Claims and screenshots to confirm before publishing

Do not publish or stage the companion HTML fragment until every applicable
item is checked in the target preview subscription. The preview has no SLA,
and the checklist is evidence gathering rather than a promise of availability.

## API and automation claims

- [ ] Flag the documentation/automation API difference explicitly:
  `2026-05-01-preview` is used for connector gateway automation, while the
  published Microsoft baseline uses
  `Microsoft.ApiManagement/service@2025-09-01-preview` and
  `Microsoft.Web/connectorGateways@2026-05-01-preview`.
- [ ] Confirm the exact accepted service, workspace child, model provider,
  model, ToolServer, telemetry exporter, and API-key resource shapes.
- [ ] Confirm that `policies` is accepted as a JSON array containing a
  `tokenLimit` object, not an XML policy or a nested `tokenLimit` map.
- [ ] Confirm the ToolServer accepts `type: mcp`, `failureMode: failClosed`,
  streamable HTTP transport, and header credentials.
- [ ] Confirm the gateway system identity has Foundry User at the intended
  Azure AI Services account scope.

## Portal and experience claims

- [ ] Capture the dedicated AI Gateway card and default workspace only after
  confirming it is distinct from a regular APIM service experience.
- [ ] Check and flag the portal URL inconsistency:
  `ai.gateway.azure.com` versus `gateway.ai.azure.com`.
- [ ] Capture model/provider catalog, runtime key resource, ToolServer, and
  telemetry exporter views.
- [ ] Capture the card and JSON policy experience if exposed, while avoiding
  claims that it is a regular APIM XML policy experience.
- [ ] Confirm whether multi-provider and self-service catalog surfaces are
  present for this subscription; do not claim them otherwise.

## Runtime and security claims

- [ ] Capture a successful `appservice-chat` model stream through
  `/default/models/openai/v1/`.
- [ ] Capture a successful `appservice-ops` MCP call through
  `/default/toolservers/appservice-ops/mcp`.
- [ ] Capture direct `/mcp` denial without the backend header.
- [ ] Confirm the gateway-generated runtime key is retrieved through
  `listSecrets`, stored in Key Vault, and never shown in screenshots.
- [ ] Confirm Key Vault references resolve for production and staging slot
  identities after RBAC propagation.
- [ ] Run and document a stable backing-model swap drill. Do not claim stable
  swap support until this succeeds in the target preview environment.

## Failure and telemetry claims

- [ ] Capture an invalid key 401 and an unknown model 404.
- [x] Capture a token-policy 429 in a disposable environment. Demo Three on
  2026-08-03 did not emit `Retry-After`; retain that limitation until a future
  preview build proves otherwise.
- [ ] Capture local mocked 5xx and partial-stream test results rather than
  mutating a shared preview gateway.
- [ ] Confirm App Insights correlation ID, route, and status telemetry.
- [ ] Confirm the gateway OTLP preview export describes model token usage only
  and does not include MCP traffic.

## Availability cautions to retain

- [ ] State preview-only, no SLA, and not production-ready.
- [ ] State the documented regions are East US 2 and Sweden Central.
- [ ] State pricing/business model is unannounced and numeric limits are
  unpublished.
- [ ] State APIs and portal surfaces may change.
