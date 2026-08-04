# Differences from existing samples

This repository uses two public references as guidance but deliberately takes
a different path.

## Existing App Service MCP/APIM Python sample

`seligj95/app-service-ai-gateway-mcp-apim-python` at commit
`1a8cfeecf9efe24aea01d38b6e25ca429a9465c9` provides useful FastAPI, Jinja,
App Service, and Azure Monitor conventions. This sample does **not** copy:

- regular APIM XML policy resources;
- a regular APIM service SKU or subscription-key design;
- direct provider endpoint configuration;
- a direct/local MCP tool fallback.

Instead, it uses only dedicated AI Gateway OpenAI v1 and ToolServer routes,
the gateway's runtime key, Key Vault references, a generated gateway-injected
backend MCP secret, SSE behavior, and focused tests.

## Microsoft Foundry-hosted agent AI Gateway sample

`Azure-Samples/simple-foundry-hosted-agent-python-aigateway` at baseline
commit `c572db847e4bff5278bc5f8630c2acb4b6991119` is the authoritative source
for the preview resource lineage used here:

- `Microsoft.ApiManagement/service@2025-09-01-preview` with `AIGateway`;
- `Microsoft.Web/connectorGateways@2026-05-01-preview`;
- the existing default workspace;
- Foundry model provider and catalog model resources;
- structured `policies` array with `tokenLimit`;
- Application Insights telemetry exporter;
- ToolServer resource and runtime API key resource;
- lifecycle and post-provision concepts.

This sample adapts those patterns for App Service rather than Foundry-hosted
agents. It changes the ToolServer backend to the App Service `/mcp` endpoint,
injects an app-specific backend secret, stores both secret values in Key Vault,
and omits Toolbox/GitHub-specific setup. Its Python agent uses
`MCPStreamableHTTPTool` directly against the gateway ToolServer endpoint.

For the ToolServer itself, this repository now mirrors the baseline's secure
empty `toolServerConfigs` Bicep pattern. It does not deploy a credential-less
placeholder. Post-provision creates the ToolServer through the same documented
streamable HTTP endpoint and header-credentials JSON shape after the backend
secret is generated.

The sample does not imply that every feature or behavior in the baseline is
available in every subscription, preview region, or portal experience.
