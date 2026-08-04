targetScope = 'resourceGroup'

param location string
param tags object
param principalId string
param appServicePlanName string
param webAppName string
param keyVaultName string
param appInsightsName string
param logAnalyticsWorkspaceName string
param foundryAccountName string
param gatewayName string
param virtualNetworkName string
param keyVaultPublicNetworkAccess string
param enableKeyVaultPrivateEndpoint bool
param disableFoundryLocalAuth bool
param foundryModelVersion string
param gatewayTokenLimitPerMinute int
param publisherEmail string
param publisherName string
@secure()
param toolServerConfigs object

var stableGatewayModelName = 'appservice-chat'
var gatewayRuntimeKeyName = 'default'
var gatewayRuntimeKeySecretName = 'gateway-runtime-key'
var mcpBackendSecretName = 'mcp-backend-secret'
var foundryUserRoleDefinitionId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '53ca6127-db72-4b80-b1b0-d745d6d5456d')
var keyVaultSecretsUserRoleDefinitionId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', '4633458b-17de-408a-b874-0445c86b69e6')
var keyVaultSecretsOfficerRoleDefinitionId = subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'b86a8fe4-44ce-4948-aee5-eccb2c155cd7')
var webHostingTags = union(tags, {
  'azd-service-name': 'web'
})
var appStartupCommand = 'gunicorn --chdir src --bind=0.0.0.0:8000 --timeout 120 --worker-class uvicorn.workers.UvicornWorker app.main:app'

resource virtualNetwork 'Microsoft.Network/virtualNetworks@2024-05-01' = {
  name: virtualNetworkName
  location: location
  tags: tags
  properties: {
    addressSpace: {
      addressPrefixes: [
        '10.42.0.0/16'
      ]
    }
  }
}

resource integrationSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' = {
  parent: virtualNetwork
  name: 'appservice-integration'
  properties: {
    addressPrefix: '10.42.1.0/24'
    delegations: [
      {
        name: 'appservice'
        properties: {
          serviceName: 'Microsoft.Web/serverFarms'
        }
      }
    ]
  }
}

resource privateEndpointSubnet 'Microsoft.Network/virtualNetworks/subnets@2024-05-01' = {
  parent: virtualNetwork
  name: 'private-endpoints'
  properties: {
    addressPrefix: '10.42.2.0/24'
    privateEndpointNetworkPolicies: 'Disabled'
  }
}

resource logAnalyticsWorkspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: logAnalyticsWorkspaceName
  location: location
  tags: tags
  properties: {
    retentionInDays: 30
    features: {
      enableLogAccessUsingOnlyResourcePermissions: true
    }
    sku: {
      name: 'PerGB2018'
    }
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: appInsightsName
  location: location
  kind: 'web'
  tags: tags
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalyticsWorkspace.id
    DisableIpMasking: true
  }
}

resource keyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: keyVaultName
  location: location
  tags: tags
  properties: {
    tenantId: tenant().tenantId
    sku: {
      family: 'A'
      name: 'standard'
    }
    enableRbacAuthorization: true
    enablePurgeProtection: true
    enableSoftDelete: true
    softDeleteRetentionInDays: 7
    publicNetworkAccess: keyVaultPublicNetworkAccess
    networkAcls: {
      bypass: 'AzureServices'
      defaultAction: keyVaultPublicNetworkAccess == 'Enabled' ? 'Allow' : 'Deny'
    }
  }

}

resource deploymentKeyVaultSecretsOfficer 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, principalId, keyVaultSecretsOfficerRoleDefinitionId)
  scope: keyVault
  properties: {
    roleDefinitionId: keyVaultSecretsOfficerRoleDefinitionId
    principalId: principalId
  }
}

resource keyVaultPrivateDnsZone 'Microsoft.Network/privateDnsZones@2020-06-01' = if (enableKeyVaultPrivateEndpoint) {
  name: 'privatelink.vaultcore.azure.net'
  location: 'global'
  tags: tags
}

resource keyVaultPrivateDnsLink 'Microsoft.Network/privateDnsZones/virtualNetworkLinks@2020-06-01' = if (enableKeyVaultPrivateEndpoint) {
  parent: keyVaultPrivateDnsZone
  name: '${virtualNetworkName}-link'
  location: 'global'
  properties: {
    registrationEnabled: false
    virtualNetwork: {
      id: virtualNetwork.id
    }
  }
}

resource keyVaultPrivateEndpoint 'Microsoft.Network/privateEndpoints@2024-05-01' = if (enableKeyVaultPrivateEndpoint) {
  name: 'pep-${keyVaultName}'
  location: location
  tags: tags
  properties: {
    subnet: {
      id: privateEndpointSubnet.id
    }
    privateLinkServiceConnections: [
      {
        name: 'keyvault'
        properties: {
          privateLinkServiceId: keyVault.id
          groupIds: [
            'vault'
          ]
        }
      }
    ]
  }
}

resource keyVaultPrivateDnsZoneGroup 'Microsoft.Network/privateEndpoints/privateDnsZoneGroups@2024-05-01' = if (enableKeyVaultPrivateEndpoint) {
  parent: keyVaultPrivateEndpoint
  name: 'keyvault-dns'
  properties: {
    privateDnsZoneConfigs: [
      {
        name: 'vaultcore'
        properties: {
          privateDnsZoneId: keyVaultPrivateDnsZone.id
        }
      }
    ]
  }
}

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' = {
  name: foundryAccountName
  location: location
  kind: 'AIServices'
  sku: {
    name: 'S0'
  }
  tags: tags
  properties: {
    customSubDomainName: foundryAccountName
    publicNetworkAccess: 'Enabled'
    disableLocalAuth: disableFoundryLocalAuth
  }
}

resource foundryModelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2024-10-01' = {
  parent: foundryAccount
  name: stableGatewayModelName
  sku: {
    name: 'GlobalStandard'
    capacity: 1
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5-mini'
      version: foundryModelVersion
    }
  }
}

resource aiGateway 'Microsoft.ApiManagement/service@2025-09-01-preview' = {
  name: gatewayName
  location: location
  tags: tags
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'AIGateway'
    capacity: 1
  }
  properties: {
    publisherEmail: publisherEmail
    publisherName: publisherName
  }
}

resource connectorNamespace 'Microsoft.Web/connectorGateways@2026-05-01-preview' = {
  name: gatewayName
  location: location
  properties: {}
  dependsOn: [
    aiGateway
  ]
}

resource defaultWorkspace 'Microsoft.ApiManagement/service/workspaces@2025-09-01-preview' existing = {
  parent: aiGateway
  name: 'default'
}

resource gatewayFoundryUserRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(foundryAccount.id, aiGateway.id, foundryUserRoleDefinitionId)
  scope: foundryAccount
  properties: {
    roleDefinitionId: foundryUserRoleDefinitionId
    principalId: aiGateway.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource telemetryExporter 'Microsoft.ApiManagement/service/workspaces/telemetryExporters@2025-09-01-preview' = {
  parent: defaultWorkspace
  name: 'appinsights'
  properties: {
    kind: 'applicationInsights'
    payloadCapture: false
    applicationInsights: {
      connectionString: appInsights.properties.ConnectionString
      resourceId: appInsights.id
    }
  }
}

resource foundryProvider 'Microsoft.ApiManagement/service/workspaces/modelProviders@2025-09-01-preview' = {
  parent: defaultWorkspace
  name: 'foundry'
  dependsOn: [
    gatewayFoundryUserRoleAssignment
  ]
  properties: {
    kind: 'Foundry'
    displayName: 'Foundry'
    description: 'Managed-identity provider for the sample model deployment.'
    foundry: {
      endpoint: foundryAccount.properties.endpoint
      resourceIds: [
        foundryAccount.id
      ]
      authentication: {
        kind: 'ManagedIdentity'
        managedIdentity: {
          resource: 'https://cognitiveservices.azure.com/'
        }
      }
    }
  }
}

resource gatewayModel 'Microsoft.ApiManagement/service/workspaces/modelProviders/models@2025-09-01-preview' = {
  parent: foundryProvider
  name: stableGatewayModelName
  properties: {
    description: 'Stable model name for the App Service sample.'
    displayName: 'gpt-5-mini'
    apiFormat: 'OpenAIChatCompletions'
    supportedEndpoints: [
      '/openai/v1/chat/completions'
      '/openai/v1/responses'
    ]
    deployment: {
      resourceId: foundryModelDeployment.id
      modelName: last(split(foundryModelDeployment.id, '/'))
      modelVersion: foundryModelVersion
    }
    policies: [
      {
        type: 'tokenLimit'
        period: 'minute'
        count: gatewayTokenLimitPerMinute
        counterKey: 'Identity'
      }
    ]
  }
}

resource appServicePlan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: appServicePlanName
  location: location
  kind: 'linux'
  sku: {
    name: 'P0v3'
    tier: 'PremiumV3'
    capacity: 1
  }
  tags: webHostingTags
  properties: {
    reserved: true
  }
}

var gatewayBaseUrl = aiGateway.properties.gatewayUrl
var appSettings = [
  {
    name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
    value: 'true'
  }
  {
    name: 'ENABLE_ORYX_BUILD'
    value: 'true'
  }
  {
    name: 'AZURE_AI_GATEWAY_BASE_URL'
    value: '${gatewayBaseUrl}/default/models/openai/v1/'
  }
  {
    name: 'AZURE_AI_GATEWAY_MCP_URL'
    value: '${gatewayBaseUrl}/default/toolservers/appservice-ops/mcp'
  }
  {
    name: 'AZURE_AI_GATEWAY_MODEL'
    value: stableGatewayModelName
  }
  {
    name: 'AZURE_AI_GATEWAY_API_KEY'
    value: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/${gatewayRuntimeKeySecretName}/)'
  }
  {
    name: 'MCP_BACKEND_SECRET'
    value: '@Microsoft.KeyVault(SecretUri=${keyVault.properties.vaultUri}secrets/${mcpBackendSecretName}/)'
  }
  {
    name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
    value: appInsights.properties.ConnectionString
  }
  {
    name: 'OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT'
    value: 'false'
  }
  {
    name: 'GATEWAY_REQUEST_TIMEOUT_SECONDS'
    value: '45'
  }
  {
    name: 'MCP_REQUEST_TIMEOUT_SECONDS'
    value: '30'
  }
  {
    name: 'GATEWAY_RETRY_MAX_ATTEMPTS'
    value: '3'
  }
]

resource webApp 'Microsoft.Web/sites@2024-04-01' = {
  name: webAppName
  location: location
  kind: 'app,linux'
  identity: {
    type: 'SystemAssigned'
  }
  tags: webHostingTags
  properties: {
    serverFarmId: appServicePlan.id
    httpsOnly: true
    publicNetworkAccess: 'Enabled'
    virtualNetworkSubnetId: integrationSubnet.id
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.12'
      appCommandLine: appStartupCommand
      alwaysOn: true
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      vnetRouteAllEnabled: true
      appSettings: appSettings
    }
  }
}

resource stagingSlot 'Microsoft.Web/sites/slots@2024-04-01' = {
  parent: webApp
  name: 'staging'
  location: location
  kind: 'app,linux'
  identity: {
    type: 'SystemAssigned'
  }
  tags: union(tags, {
    slot: 'staging'
  })
  properties: {
    serverFarmId: appServicePlan.id
    httpsOnly: true
    virtualNetworkSubnetId: integrationSubnet.id
    siteConfig: {
      linuxFxVersion: 'PYTHON|3.12'
      appCommandLine: appStartupCommand
      alwaysOn: true
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      vnetRouteAllEnabled: true
      appSettings: appSettings
    }
  }
}

resource slotConfigNames 'Microsoft.Web/sites/config@2024-04-01' = {
  parent: webApp
  name: 'slotConfigNames'
  properties: {
    appSettingNames: [
      'AZURE_AI_GATEWAY_BASE_URL'
      'AZURE_AI_GATEWAY_MCP_URL'
      'AZURE_AI_GATEWAY_MODEL'
      'AZURE_AI_GATEWAY_API_KEY'
      'MCP_BACKEND_SECRET'
      'APPLICATIONINSIGHTS_CONNECTION_STRING'
      'OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT'
    ]
  }
}

resource appKeyVaultSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, webApp.id, keyVaultSecretsUserRoleDefinitionId)
  scope: keyVault
  properties: {
    roleDefinitionId: keyVaultSecretsUserRoleDefinitionId
    principalId: webApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource slotKeyVaultSecretsUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(keyVault.id, stagingSlot.id, keyVaultSecretsUserRoleDefinitionId)
  scope: keyVault
  properties: {
    roleDefinitionId: keyVaultSecretsUserRoleDefinitionId
    principalId: stagingSlot.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource toolServers 'Microsoft.ApiManagement/service/workspaces/toolServers@2025-09-01-preview' = [for config in items(toolServerConfigs): {
  parent: defaultWorkspace
  name: config.key
  properties: config.value
}]

resource runtimeApiKey 'Microsoft.ApiManagement/service/apiKeys@2025-09-01-preview' = {
  parent: aiGateway
  name: gatewayRuntimeKeyName
  properties: {
    displayName: 'App Service runtime key'
  }
}

output webAppName string = webApp.name
output webAppUrl string = 'https://${webApp.properties.defaultHostName}'
output stagingSlotUrl string = 'https://${stagingSlot.properties.defaultHostName}'
output gatewayName string = aiGateway.name
output gatewayUrl string = gatewayBaseUrl
output gatewayResourceId string = aiGateway.id
output keyVaultName string = keyVault.name
output appInsightsName string = appInsights.name
output logAnalyticsWorkspaceId string = logAnalyticsWorkspace.id
output stableGatewayModelName string = stableGatewayModelName
output runtimeKeyResourceName string = runtimeApiKey.name
output gatewayRuntimeKeySecretName string = gatewayRuntimeKeySecretName
output mcpBackendSecretName string = mcpBackendSecretName
