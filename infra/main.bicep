targetScope = 'subscription'

@minLength(1)
@maxLength(48)
param environmentName string

@allowed([
  'eastus2'
  'swedencentral'
])
@description('Preview location. The dedicated tier is currently limited to East US 2 and Sweden Central.')
param location string = 'eastus2'

@description('Optional deterministic resource group override for an existing azd environment.')
param resourceGroupName string = ''

@description('Object ID of the user or service principal running post-provision Key Vault data-plane operations.')
param principalId string

@description('Key Vault public network access. Use SecuredByPerimeter only when a pre-existing perimeter is managed outside this sample.')
@allowed([
  'Enabled'
  'Disabled'
  'SecuredByPerimeter'
])
param keyVaultPublicNetworkAccess string = 'Enabled'

@description('Optional private endpoint for Key Vault. Leave false for the portable default configuration.')
param enableKeyVaultPrivateEndpoint bool = false

@description('Disable Azure AI Services local authentication when managed identity is supported by the gateway.')
param disableFoundryLocalAuth bool = true

@description('Version of gpt-5-mini available in the selected preview region.')
param foundryModelVersion string = '2025-08-07'

@minValue(1)
@maxValue(100000)
param gatewayTokenLimitPerMinute int = 1000

param publisherEmail string = 'noreply@example.com'
param publisherName string = 'App Service AI Gateway tier sample'

@secure()
@description('Optional secure ToolServer resource configurations. The default is empty because postprovision injects the backend credential.')
param toolServerConfigs object = {}

var resourceToken = take(toLower(uniqueString(subscription().id, environmentName, location)), 10)
var environmentLabel = toLower(environmentName)
var effectiveResourceGroupName = !empty(resourceGroupName) ? resourceGroupName : 'rg-${environmentLabel}-${resourceToken}'
var tags = {
  'azd-env-name': environmentName
  sample: 'app-service-ai-gateway-tier-python'
  'managed-by': 'azd'
  'preview-only': 'true'
}
var names = {
  appServicePlan: 'asp-${resourceToken}'
  webApp: 'appsvc-aigw-${resourceToken}'
  keyVault: 'kvaigw${resourceToken}'
  appInsights: 'appi-aigw-${resourceToken}'
  logAnalytics: 'log-aigw-${resourceToken}'
  foundry: 'aifoundry${resourceToken}'
  gateway: 'aigw-${resourceToken}'
  vnet: 'vnet-aigw-${resourceToken}'
}

resource resourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: effectiveResourceGroupName
  location: location
  tags: tags
}

module workload './modules/workload.bicep' = {
  name: 'workload-${resourceToken}'
  scope: resourceGroup
  params: {
    location: location
    tags: tags
    principalId: principalId
    appServicePlanName: names.appServicePlan
    webAppName: names.webApp
    keyVaultName: names.keyVault
    appInsightsName: names.appInsights
    logAnalyticsWorkspaceName: names.logAnalytics
    foundryAccountName: names.foundry
    gatewayName: names.gateway
    virtualNetworkName: names.vnet
    keyVaultPublicNetworkAccess: keyVaultPublicNetworkAccess
    enableKeyVaultPrivateEndpoint: enableKeyVaultPrivateEndpoint
    disableFoundryLocalAuth: disableFoundryLocalAuth
    foundryModelVersion: foundryModelVersion
    gatewayTokenLimitPerMinute: gatewayTokenLimitPerMinute
    publisherEmail: publisherEmail
    publisherName: publisherName
    toolServerConfigs: toolServerConfigs
  }
}

output AZURE_LOCATION string = location
output AZURE_RESOURCE_GROUP string = resourceGroup.name
output RESOURCE_GROUP string = resourceGroup.name
output WEB_NAME string = workload.outputs.webAppName
output WEB_URL string = workload.outputs.webAppUrl
output WEB_STAGING_URL string = workload.outputs.stagingSlotUrl
output AI_GATEWAY_NAME string = workload.outputs.gatewayName
output AI_GATEWAY_URL string = workload.outputs.gatewayUrl
output KEY_VAULT_NAME string = workload.outputs.keyVaultName
output APPLICATIONINSIGHTS_NAME string = workload.outputs.appInsightsName
output LOG_ANALYTICS_WORKSPACE_ID string = workload.outputs.logAnalyticsWorkspaceId
output AZURE_AI_GATEWAY_MODEL string = workload.outputs.stableGatewayModelName
output AI_GATEWAY_RUNTIME_KEY_NAME string = workload.outputs.runtimeKeyResourceName
output AI_GATEWAY_RESOURCE_ID string = workload.outputs.gatewayResourceId
output GATEWAY_RUNTIME_KEY_SECRET_NAME string = workload.outputs.gatewayRuntimeKeySecretName
output MCP_BACKEND_SECRET_NAME string = workload.outputs.mcpBackendSecretName
