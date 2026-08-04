from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_bicep_has_canonical_dedicated_gateway_shapes() -> None:
    main = (ROOT / "infra/main.bicep").read_text()
    bicep = (ROOT / "infra/modules/workload.bicep").read_text()
    assert "Microsoft.ApiManagement/service@2025-09-01-preview" in bicep
    assert "Microsoft.Web/connectorGateways@2026-05-01-preview" in bicep
    assert "name: 'AIGateway'" in bicep
    assert "type: 'SystemAssigned'" in bicep
    assert "Microsoft.ApiManagement/service/workspaces/telemetryExporters@2025-09-01-preview" in bicep
    assert "payloadCapture: false" in bicep
    assert "Microsoft.ApiManagement/service/workspaces/modelProviders@2025-09-01-preview" in bicep
    assert "kind: 'Foundry'" in bicep
    assert "type: 'tokenLimit'" in bicep
    assert "counterKey: 'Identity'" in bicep
    assert "displayName: 'gpt-5-mini'" in bicep
    assert "resource foundryModelDeployment" in bicep
    assert "name: stableGatewayModelName" in bicep
    assert "<policies>" not in bicep
    assert "param gatewayTokenLimitPerMinute int = 1000" in main
    assert "var gatewayRuntimeKeyName = 'default'" in bicep


def test_runtime_dependencies_do_not_install_every_agent_framework_provider() -> None:
    requirements = (ROOT / "requirements.txt").read_text().splitlines()
    assert "agent-framework==1.13.0" not in requirements
    assert "agent-framework-core==1.13.0" in requirements
    assert "agent-framework-openai==1.12.0" in requirements
    assert "mcp>=1.24.0,<2" in requirements


def test_bicep_grants_least_privilege_deployment_secret_access_and_service_tags() -> None:
    main = (ROOT / "infra/main.bicep").read_text()
    bicep = (ROOT / "infra/modules/workload.bicep").read_text()
    parameters = json.loads((ROOT / "infra/main.parameters.json").read_text())

    assert "param principalId string" in main
    assert main.count("principalId: principalId") == 1
    assert parameters["parameters"]["principalId"]["value"] == "${AZURE_PRINCIPAL_ID}"
    assert (
        parameters["parameters"]["keyVaultPublicNetworkAccess"]["value"]
        == "${KEY_VAULT_PUBLIC_NETWORK_ACCESS}"
    )
    assert parameters["parameters"]["gatewayTokenLimitPerMinute"]["value"] == (
        "${GATEWAY_TOKEN_LIMIT_PER_MINUTE}"
    )
    assert "b86a8fe4-44ce-4948-aee5-eccb2c155cd7" in bicep
    assert "resource deploymentKeyVaultSecretsOfficer" in bicep
    assert "scope: keyVault" in bicep
    assert "principalType:" not in bicep.split("resource deploymentKeyVaultSecretsOfficer", 1)[1].split(
        "resource keyVaultPrivateDnsZone", 1
    )[0]
    assert "'azd-service-name': 'web'" in bicep
    staging_resource = bicep.split("resource stagingSlot", 1)[1].split(
        "resource slotConfigNames", 1
    )[0]
    assert "tags: union(tags" in staging_resource
    assert "tags: union(webHostingTags" not in staging_resource
    assert "name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'" in bicep
    assert "name: 'ENABLE_ORYX_BUILD'" in bicep
    assert (
        "var appStartupCommand = 'gunicorn --chdir src "
        "--bind=0.0.0.0:8000 --timeout 120 "
        "--worker-class uvicorn.workers.UvicornWorker app.main:app'"
    ) in bicep
    assert bicep.count("appCommandLine: appStartupCommand") == 2
    assert "/home/site/wwwroot/src" not in bicep


def test_toolserver_contract_and_no_secret_env_persistence() -> None:
    script = (ROOT / "scripts/postprovision.sh").read_text()
    bicep = (ROOT / "infra/modules/workload.bicep").read_text()
    assert "listSecrets?api-version=${API_VERSION}" in script
    assert '"x-appservice-mcp-secret"' in script
    assert '"type": "mcp"' in script
    assert '"failureMode": "failClosed"' in script
    assert "streamableHttp" in script
    assert "contains(keys(properties.endpoints[0].credentials.headers)" in script
    assert "azd env set AZURE_AI_GATEWAY_API_KEY" not in script
    assert 'echo "${gateway_api_key}"' not in script
    assert 'echo "${mcp_backend_secret}"' not in script
    assert "wait_for set_secret_from_file" in script
    assert "/secrets/${secret_name}?api-version=2023-07-01" in script
    assert "az keyvault secret set" not in script
    assert "@secure()" in bicep
    assert "param toolServerConfigs object" in bicep
    assert "for config in items(toolServerConfigs)" in bicep
    assert "resource appServiceToolServer" not in bicep


def test_postdeploy_verifies_production_without_swapping_staging() -> None:
    script = (ROOT / "scripts/postprovision.sh").read_text()
    azure_yaml = (ROOT / "azure.yaml").read_text()
    verify_branch = script.split('else\n  current_stage="runtime key retrieval"', 1)[1]
    assert 'current_stage="production web readiness"' in verify_branch
    assert 'web_url="${web_url:-https://${web_name}.azurewebsites.net}"' in script
    assert "AZD_DEPLOY_WEB_SLOT_NAME production" in azure_yaml
    assert "WEB_STAGING_URL" not in script
    assert "az webapp deployment slot swap" not in script
    assert "target-slot production" not in script


def test_lifecycle_is_bounded_and_guarded_to_current_environment() -> None:
    script = (ROOT / "scripts/manage-ai-gateway-lifecycle.sh").read_text()
    assert 'tags."azd-env-name"' in script
    assert 'sku.name' in script
    assert 'state}" != "Failed"' in script
    assert "MAX_POLLS" in script
    assert "predown)" in script
    assert "write_marker" in script
    assert "wait_for_deleted_gateway" in script
    assert "join(`|`" in script
    assert "IFS='|'" in script
    assert "az group delete" not in script
    assert "az resource delete" not in script
    assert "deletedservices" in script
    azure_yaml = (ROOT / "azure.yaml").read_text()
    assert "predown:" in azure_yaml
    assert "manage-ai-gateway-lifecycle.sh predown" in azure_yaml


def test_shell_scripts_pass_syntax_checks() -> None:
    for script in (
        ROOT / "scripts/manage-ai-gateway-lifecycle.sh",
        ROOT / "scripts/ensure-azd-parameters.sh",
        ROOT / "scripts/postprovision.sh",
        ROOT / "scripts/build-bicep.sh",
        ROOT / "scripts/run-tests.sh",
    ):
        subprocess.run(["bash", "-n", str(script)], check=True)


def test_preprovision_initializes_optional_azd_parameters() -> None:
    azure_yaml = (ROOT / "azure.yaml").read_text()
    defaults = (ROOT / "scripts/ensure-azd-parameters.sh").read_text()
    assert "scripts/ensure-azd-parameters.sh" in azure_yaml
    assert "KEY_VAULT_PUBLIC_NETWORK_ACCESS Enabled" in defaults
    assert "ENABLE_KEY_VAULT_PRIVATE_ENDPOINT false" in defaults
    assert "FOUNDRY_MODEL_VERSION 2025-08-07" in defaults
    assert "GATEWAY_TOKEN_LIMIT_PER_MINUTE 1000" in defaults
    assert "AZD_DEPLOY_WEB_SLOT_NAME production" in defaults
    assert "--output" not in defaults
    assert "resourceGroup: ${AZURE_RESOURCE_GROUP}" in azure_yaml
    assert "resourceName: ${WEB_NAME}" in azure_yaml
    assert 'if value="$(azd env get-value "$1" 2>/dev/null)"; then' in defaults


def test_missing_azd_outputs_are_not_treated_as_values() -> None:
    for script_name in (
        "ensure-azd-parameters.sh",
        "manage-ai-gateway-lifecycle.sh",
        "postprovision.sh",
    ):
        script = (ROOT / "scripts" / script_name).read_text()
        assert 'if value="$(azd env get-value "$1" 2>/dev/null)"; then' in script
