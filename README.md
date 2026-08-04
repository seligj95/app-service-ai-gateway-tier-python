# App Service AI Gateway tier Python sample

This is a **preview-only sample with no SLA**. It runs a Python 3.12 FastAPI
chat application and a small read-only MCP server on Linux Azure App Service.
The app reaches its model and MCP tools only through the dedicated Azure API
Management AI Gateway tier. It is a learning sample, not a production-ready
reference.

## What it demonstrates

- Linux App Service P0v3 with one instance and a `staging` deployment slot.
- Microsoft Agent Framework `OpenAIChatCompletionClient` configured with the
  gateway-only OpenAI v1 route and explicit lowercase `api-key` header.
- Microsoft Agent Framework `MCPStreamableHTTPTool` configured with
  `/default/toolservers/appservice-ops/mcp`, an explicit timeout, a fixed
  read-only tool allow-list, and the same gateway runtime key header.
- Narrow Agent Framework core, OpenAI, and MCP dependencies rather than the
  umbrella package that installs every optional provider.
- A stable gateway model name, `appservice-chat`, backed initially by one
  `gpt-5-mini` GlobalStandard deployment with capacity 1 and a 1000 TPM
  structured token policy.
- FastAPI health/status endpoints, a browser chat UI, and SSE chat streaming.
- A direct `/mcp` backend protected by a separate backend secret. Only the
  gateway ToolServer receives that secret; browser and direct callers do not.
- Key Vault references for the runtime key and MCP backend secret, managed
  identity, App Insights/OpenTelemetry, correlation IDs, and safe telemetry
  attributes.
- Subscription-scope azd+Bicep with a deterministic environment resource
  group, VNet integration subnet, optional Key Vault private endpoint, and
  canonical preview AI Gateway child resources.

## Architecture

```text
Browser ──SSE──> FastAPI on App Service (production or staging slot)
                         │ explicit api-key, stable model
                         ▼
      Dedicated APIM AI Gateway /default/models/openai/v1/
                         │ managed identity
                         ▼
                 Foundry / Azure AI Services gpt-5-mini

Agent Framework MCPStreamableHTTPTool
                         │ explicit api-key
                         ▼
      Dedicated APIM AI Gateway /default/toolservers/appservice-ops/mcp
                         │ injected x-appservice-mcp-secret
                         ▼
               FastAPI /mcp read-only tool server
```

See [docs/architecture.md](docs/architecture.md) for the request flow and
security boundaries.

## Repository layout

| Path | Purpose |
| --- | --- |
| `src/app/` | Typed FastAPI application, strict gateway config, retry adapter, MCP endpoint, UI, and telemetry safety layer. |
| `infra/` | Subscription-scope Bicep entry point and resource-group workload module. |
| `scripts/postprovision.sh` | Retrieves the generated gateway runtime key without emitting it, writes Key Vault secrets, injects ToolServer credentials, and verifies registrations. |
| `scripts/manage-ai-gateway-lifecycle.sh` | Bounded current-environment-only failed recovery and predown/postdown gateway cleanup. |
| `tests/` | Pytest coverage plus infrastructure and shell contract checks. |
| `docs/` | Architecture, preview limitations, and comparisons. |
| `blog/` | Unpublished Tech Community body fragment and claims/screenshot checklist. |

## Prerequisites

- Python 3.12.
- Azure Developer CLI 1.29.0 or later and Azure CLI with Bicep support. Azd
  1.29.0 adds explicit App Service slot targeting used by this sample.
- An Azure subscription authorized for the dedicated AI Gateway tier preview.
- A selected preview region: `eastus2` or `swedencentral`.
- Permission to create the resource group and role assignments. The
  Bicep principal receives Key Vault Secrets Officer at the vault scope so the
  post-provision hook can write only the required secrets. The deployment
  identity also needs permission to create that role assignment and update the
  ToolServer child resource.

The approved `.azure/deployment-plan.md` remains the execution plan. Do not
place a runtime key in an azd environment file or source control.

## Prepare an azd environment

Set the context and deployment parameters before any provisioning command.
`AZURE_PRINCIPAL_ID` is the Microsoft Entra object ID of the user or service
principal that runs the post-provision hook; it is not an application ID.
The pre-provision hook initializes omitted portable defaults and resolves the
signed-in deployment principal. Explicit values set with `azd env set` always
win, so CI should set `AZURE_PRINCIPAL_ID` directly.

```bash
azd auth login
azd env new <environment-name>
azd env set AZURE_SUBSCRIPTION_ID "$(az account show --query id -o tsv)"
azd env set AZURE_LOCATION eastus2
azd env set AZURE_PRINCIPAL_ID "$(az ad signed-in-user show --query id -o tsv)"
azd env set KEY_VAULT_PUBLIC_NETWORK_ACCESS Enabled
azd env set ENABLE_KEY_VAULT_PRIVATE_ENDPOINT false
azd env set FOUNDRY_MODEL_VERSION 2025-08-07
azd env set GATEWAY_TOKEN_LIMIT_PER_MINUTE 1000
azd env set AZD_DEPLOY_WEB_SLOT_NAME production
```

If the optional values are omitted, the pre-provision hook supplies `Enabled`,
`false`, `2025-08-07`, `1000`, and the explicit `production` App Service target,
and resolves the current Azure CLI principal. This prevents empty azd
substitutions from overriding Bicep defaults or ambiguous slot selection.

For an automation identity, obtain and set its Entra **object ID** instead of
using the interactive `az ad signed-in-user` command. If the target environment
requires Key Vault to use an existing network security perimeter, replace the
portable network settings with:

```bash
azd env set KEY_VAULT_PUBLIC_NETWORK_ACCESS SecuredByPerimeter
azd env set ENABLE_KEY_VAULT_PRIVATE_ENDPOINT true
```

Use `Enabled`, `Disabled`, or another approved parameter value when appropriate
for the target network design. `SecuredByPerimeter` requires an existing
perimeter managed outside this sample. After review and authorization, the
normal deployment command is `azd up`; this repository does not place any
runtime key into the azd environment.

## Local development and tests

Create an isolated environment and run the test suite:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e '.[dev]'
./scripts/run-tests.sh
```

To start only the local web surface, supply gateway-shaped placeholder values
through your shell or deployment configuration; never check values into a
file. The gateway model route must end exactly in
`/default/models/openai/v1/`, and the MCP route must end exactly in
`/default/toolservers/appservice-ops/mcp/`.

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

`/health` and `/status` remain usable without configuration. Streaming chat
returns a sanitized configuration-required response until App Service resolves
its Key Vault references.

## Provisioning model

The application deployment uses `azd` with `infra/main.bicep` at subscription
scope. Bicep creates a resource group tagged with `azd-env-name` and deploys:

1. VNet, delegated App Service integration subnet, and an optional Key Vault
   private endpoint.
2. Workspace-based Log Analytics and Application Insights.
3. RBAC-enabled Key Vault and App Service plan, web app, and `staging` slot.
   App Service enables Oryx remote dependency builds for both slots.
4. Azure AI Services with the parameterized `gpt-5-mini` model version,
   GlobalStandard SKU, capacity 1, and stable deployment name
   `appservice-chat`.
5. Dedicated `Microsoft.ApiManagement/service@2025-09-01-preview` AI Gateway,
   connector namespace, existing default workspace, Foundry provider, stable
   model registration, structured JSON token policy, ToolServer, runtime key,
   and Application Insights telemetry exporter.

The gateway's system-assigned identity receives the Foundry User role
`53ca6127-db72-4b80-b1b0-d745d6d5456d` at the Azure AI Services account.
The supplied deployment principal receives Key Vault Secrets Officer
(`b86a8fe4-44ce-4948-aee5-eccb2c155cd7`) at the vault scope so it can perform
the post-provision secret writes. App Service and its slot receive only Key
Vault Secrets User access.

### Key Vault networking portability

The Bicep default is `Enabled`; azd supplies
`KEY_VAULT_PUBLIC_NETWORK_ACCESS` through `infra/main.parameters.json`. When an
approved target environment requires an existing network security perimeter,
set the active environment values before deployment:

```bash
azd env set KEY_VAULT_PUBLIC_NETWORK_ACCESS SecuredByPerimeter
azd env set ENABLE_KEY_VAULT_PRIVATE_ENDPOINT true
```

That value assumes an appropriate existing network security perimeter managed
outside this sample. The sample deliberately does **not** create or guess a
network security perimeter. Use `Enabled` or another approved value when the
target subscription does not use that design. Enable the private endpoint only
when the target network design includes private DNS and App Service outbound
networking requirements.

`DISABLE_FOUNDRY_LOCAL_AUTH` defaults to `true`, so the gateway uses its
managed identity rather than a local Azure AI Services key. Confirm service
compatibility in the target preview region before changing this parameter.

### Secure post-provision work

`scripts/postprovision.sh configure` performs bounded, idempotent work after
Bicep:

1. Calls `POST .../apiKeys/default/listSecrets?api-version=2025-09-01-preview`.
2. Stores the returned runtime key and a separately generated MCP backend
   secret through the Key Vault ARM resource API without emitting either value.
   This remains usable when the Key Vault data plane is private or secured by a
   network security perimeter.
3. PUTs the ToolServer header credential payload so the gateway injects
   `x-appservice-mcp-secret` when it calls the App Service backend.
4. Waits for model, ToolServer, telemetry exporter, and Key Vault-reference
   registration; retries Key Vault data-plane writes while RBAC propagates,
   then performs a small gateway model readiness check.

The hook neither writes the runtime key into `azd env` nor prints it. Bicep
uses the Microsoft baseline's secure, empty `toolServerConfigs` pattern rather
than creating a credential-less placeholder. The post-provision PUT creates
the ToolServer with the baseline streamable HTTP and header-credentials shape
only after the backend secret exists in Key Vault.

The lifecycle hook acts only on an explicitly named, deterministic, current
environment AI Gateway after checking its `azd-env-name` tag and AIGateway SKU.
The `predown` hook writes that verified ownership marker before `azd down`,
allowing `postdown` to purge only the corresponding soft-deleted gateway. It
never deletes a resource group.

`postdeploy` runs `scripts/postprovision.sh verify` after application content
is present. That bounded verification checks the deployed web health endpoint,
model route, MCP ToolServer route, and telemetry exporter without emitting the
runtime key. Splitting it this way avoids testing an App Service `/mcp`
endpoint before azd deploys the application.

Only the production app carries `azd-service-name: web`. A predeploy hook sets
the azd-supported `AZD_DEPLOY_WEB_SLOT_NAME=production` target explicitly, and
postdeploy verifies the production URL directly. The sample does not
automatically deploy or swap the staging slot: swapping an empty or stale slot
is unsafe. The slot is an optional demonstration surface. To use it, deploy a
reviewed package explicitly with `az webapp deploy --slot staging`, verify its
health, and initiate a slot swap separately.

## Build Bicep

```bash
./scripts/build-bicep.sh
```

This invokes `az bicep build` for every Bicep file. It does not provision or
deploy resources.

## Live failure verification procedures

Run these only after an authorized preview deployment. Keep shell tracing off;
none of the following commands echoes a key. Replace resource names with azd
outputs as needed.

```bash
export RG="$(azd env get-value AZURE_RESOURCE_GROUP)"
export GATEWAY_ID="$(azd env get-value AI_GATEWAY_RESOURCE_ID)"
export GATEWAY_URL="$(azd env get-value AI_GATEWAY_URL)"
export KEY_NAME="$(azd env get-value AI_GATEWAY_RUNTIME_KEY_NAME)"
export RUNTIME_KEY="$(
  az rest --method post \
    --uri "https://management.azure.com${GATEWAY_ID}/apiKeys/${KEY_NAME}/listSecrets?api-version=2025-09-01-preview" \
    --body '{}' --query 'primaryKey || properties.primaryKey' -o tsv
)"
```

### Invalid key returns 401

Use a deliberately invalid literal, not the runtime key:

```bash
curl --silent --show-error --output /dev/null --write-out '%{http_code}\n' \
  --request POST "${GATEWAY_URL%/}/default/models/openai/v1/chat/completions" \
  --header 'api-key: invalid' --header 'content-type: application/json' \
  --data '{"model":"appservice-chat","messages":[{"role":"user","content":"hello"}]}'
```

Expected result: `401`. Do not retry 401 responses in the app.

### Unknown model returns 404

```bash
printf '%s\n' "header = \"api-key: ${RUNTIME_KEY}\"" |
  curl --config - --silent --show-error --output /dev/null --write-out '%{http_code}\n' \
    --request POST "${GATEWAY_URL%/}/default/models/openai/v1/chat/completions" \
    --header 'content-type: application/json' \
    --data '{"model":"unknown-model","messages":[{"role":"user","content":"hello"}]}'
```

Expected result: `404`. Do not retry 404 responses in the app.

### Low token policy returns 429

The default is 1000 TPM, matching the capacity-1 preflight. In a disposable
environment, lower `GATEWAY_TOKEN_LIMIT_PER_MINUTE`, reprovision the model
registration, and send enough requests to exceed the limit. Inspect only the
status and optional `Retry-After` header:

```bash
printf '%s\n' "header = \"api-key: ${RUNTIME_KEY}\"" |
  curl --config - --silent --show-error --include --output /dev/null \
    --request POST "${GATEWAY_URL%/}/default/models/openai/v1/chat/completions" \
    --header 'content-type: application/json' \
    --data '{"model":"appservice-chat","messages":[{"role":"user","content":"short test"}]}'
```

Expected result: `429`. Preview responses may omit `Retry-After`, so the
application uses a bounded jittered delay when the header is absent and honors
the server-provided value when it is present.

### Mocked transient 5xx and partial streaming

No live gateway mutation is required. The local retry tests model transient
5xx before a first chunk, retry bounds, and a failure after a partial stream:

```bash
python -m pytest tests/test_retry.py
```

Expected behavior: a 5xx before output is retried up to the configured bound;
after any streamed text, no retry occurs.

### Direct MCP backend is denied

Call the app backend `/mcp` without `x-appservice-mcp-secret`:

```bash
curl --silent --show-error --output /dev/null --write-out '%{http_code}\n' \
  --request POST "https://$(azd env get-value WEB_NAME).azurewebsites.net/mcp" \
  --header 'content-type: application/json' \
  --data '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
```

Expected result: `401`. A successful MCP request must instead pass through
the gateway ToolServer, which injects the backend secret.

### App Insights verification

In Application Insights Logs, validate request/dependency telemetry by
correlation ID and safe route/status attributes. Do not query for prompt,
response, or key content because the app never sets them as telemetry
attributes. The gateway telemetry exporter preview is documented as exporting
**model token usage only; it does not export MCP traffic**.

### Backing model swap drill

1. In a disposable environment, deploy a compatible replacement model version.
2. Update only the Foundry provider model registration behind
   `appservice-chat`; retain the stable display/name expected by the app.
3. Verify a model stream, a gateway ToolServer MCP call, and the status route.
4. Restore the original deployment registration if verification fails.

Stable model swap support remains a preview claim to validate in the target
portal and API version; see the screenshot checklist before publishing claims.

### Cleanup

Use the azd environment's normal cleanup operation only after preserving
needed diagnostic data:

```bash
unset RUNTIME_KEY
azd down
```

The `postdown` lifecycle hook can purge only a deterministic, tagged,
current-environment AI Gateway that it previously verified as failed/deleted.
It does not perform broad subscription or resource-group deletion.

## Preview limits and documentation

Read [docs/preview-limitations.md](docs/preview-limitations.md) before using
the sample. The related-source comparison is in
[docs/differences-from-existing-samples.md](docs/differences-from-existing-samples.md).
The unpublished blog draft and its claims/screenshot checklist are under
`blog/`.
