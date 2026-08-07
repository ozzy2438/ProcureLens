targetScope = 'resourceGroup'

@description('Azure region for the Container Apps environment.')
param location string = 'australiaeast'

@description('Short environment suffix such as dev, staging or prod.')
@allowed(['dev', 'staging', 'prod'])
param environmentName string

@description('Immutable release tag. Never use latest in production.')
param imageTag string = 'v1.0.0'

@description('Full API image repository without a tag.')
param apiImageRepository string

@description('Full UI image repository without a tag.')
param uiImageRepository string

@description('Optional private registry server, for example name.azurecr.io.')
param registryServer string = ''

@description('PostgreSQL SQLAlchemy URL for application access.')
@secure()
param databaseUrl string

@description('Read-only PostgreSQL SQLAlchemy URL for the SQL agent.')
@secure()
param agentDatabaseUrl string

@description('Reachable MLflow tracking server containing the champion alias.')
@secure()
param mlflowTrackingUri string

@description('Optional OpenAI API key. Deterministic agent operation does not require it.')
@secure()
param openAiApiKey string = ''

@description('Optional Langfuse public key.')
@secure()
param langfusePublicKey string = ''

@description('Optional Langfuse secret key.')
@secure()
param langfuseSecretKey string = ''

@description('Langfuse ingestion host.')
param langfuseHost string = 'https://cloud.langfuse.com'

var prefix = 'procurelens-${environmentName}'
var workspaceName = '${prefix}-logs'
var containerEnvironmentName = '${prefix}-env'
var apiName = '${prefix}-api'
var uiName = '${prefix}-ui'
var registryCredentials = empty(registryServer) ? [] : [
  {
    server: registryServer
    identity: 'system'
  }
]
var requiredApiSecrets = [
  {
    name: 'database-url'
    value: databaseUrl
  }
  {
    name: 'agent-database-url'
    value: agentDatabaseUrl
  }
  {
    name: 'mlflow-tracking-uri'
    value: mlflowTrackingUri
  }
]
var optionalOpenAiSecrets = empty(openAiApiKey) ? [] : [
  {
    name: 'openai-api-key'
    value: openAiApiKey
  }
]
var optionalLangfuseSecrets = empty(langfusePublicKey) || empty(langfuseSecretKey) ? [] : [
  {
    name: 'langfuse-public-key'
    value: langfusePublicKey
  }
  {
    name: 'langfuse-secret-key'
    value: langfuseSecretKey
  }
]
var apiSecrets = concat(requiredApiSecrets, optionalOpenAiSecrets, optionalLangfuseSecrets)
var optionalOpenAiEnvironment = empty(openAiApiKey) ? [] : [
  {
    name: 'OPENAI_API_KEY'
    secretRef: 'openai-api-key'
  }
]
var optionalLangfuseEnvironment = empty(langfusePublicKey) || empty(langfuseSecretKey) ? [] : [
  {
    name: 'LANGFUSE_PUBLIC_KEY'
    secretRef: 'langfuse-public-key'
  }
  {
    name: 'LANGFUSE_SECRET_KEY'
    secretRef: 'langfuse-secret-key'
  }
]

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: workspaceName
  location: location
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

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: containerEnvironmentName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
    zoneRedundant: false
  }
}

resource api 'Microsoft.App/containerApps@2024-03-01' = {
  name: apiName
  location: location
  tags: {
    'azd-env-name': environmentName
    'azd-service-name': 'api'
    release: imageTag
    dataClassification: 'public-pseudonymised'
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    environmentId: environment.id
    configuration: {
      activeRevisionsMode: 'Multiple'
      maxInactiveRevisions: 10
      ingress: {
        external: true
        allowInsecure: false
        targetPort: 8000
        transport: 'auto'
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
      registries: registryCredentials
      secrets: apiSecrets
    }
    template: {
      revisionSuffix: replace(imageTag, '.', '-')
      containers: [
        {
          name: 'api'
          image: '${apiImageRepository}:${imageTag}'
          env: concat([
            {
              name: 'ENV'
              value: environmentName
            }
            {
              name: 'RELEASE_VERSION'
              value: replace(imageTag, 'v', '')
            }
            {
              name: 'SNAPSHOT_VERSION'
              value: '1.0.0'
            }
            {
              name: 'DATABASE_URL'
              secretRef: 'database-url'
            }
            {
              name: 'AGENT_DATABASE_URL'
              secretRef: 'agent-database-url'
            }
            {
              name: 'MLFLOW_TRACKING_URI'
              secretRef: 'mlflow-tracking-uri'
            }
            {
              name: 'MODEL_SERVICE_URL'
              value: 'http://127.0.0.1:8000'
            }
            {
              name: 'LANGFUSE_TRACING_ENABLED'
              value: empty(langfusePublicKey) || empty(langfuseSecretKey) ? 'false' : 'true'
            }
            {
              name: 'LANGFUSE_HOST'
              value: langfuseHost
            }
          ], optionalOpenAiEnvironment, optionalLangfuseEnvironment)
          resources: {
            cpu: json('1.0')
            memory: '2Gi'
          }
          probes: [
            {
              type: 'Startup'
              httpGet: {
                path: '/health/live'
                port: 8000
              }
              initialDelaySeconds: 5
              periodSeconds: 5
              timeoutSeconds: 3
              failureThreshold: 30
            }
            {
              type: 'Liveness'
              httpGet: {
                path: '/health/live'
                port: 8000
              }
              periodSeconds: 15
              timeoutSeconds: 3
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/health/ready'
                port: 8000
              }
              initialDelaySeconds: 10
              periodSeconds: 10
              timeoutSeconds: 5
              failureThreshold: 6
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 3
        rules: [
          {
            name: 'api-http-scale'
            http: {
              metadata: {
                concurrentRequests: '20'
              }
            }
          }
        ]
      }
    }
  }
}

resource ui 'Microsoft.App/containerApps@2024-03-01' = {
  name: uiName
  location: location
  tags: {
    'azd-env-name': environmentName
    'azd-service-name': 'ui'
    release: imageTag
  }
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    environmentId: environment.id
    configuration: {
      activeRevisionsMode: 'Multiple'
      maxInactiveRevisions: 10
      ingress: {
        external: true
        allowInsecure: false
        targetPort: 8501
        transport: 'auto'
        traffic: [
          {
            latestRevision: true
            weight: 100
          }
        ]
      }
      registries: registryCredentials
    }
    template: {
      revisionSuffix: replace(imageTag, '.', '-')
      containers: [
        {
          name: 'ui'
          image: '${uiImageRepository}:${imageTag}'
          env: [
            {
              name: 'PROCURELENS_API_URL'
              value: 'https://${api.properties.configuration.ingress.fqdn}'
            }
            {
              name: 'DEMO_OPPORTUNITIES_PATH'
              value: 'config/demo_opportunities.json'
            }
          ]
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          probes: [
            {
              type: 'Startup'
              httpGet: {
                path: '/_stcore/health'
                port: 8501
              }
              initialDelaySeconds: 5
              periodSeconds: 5
              timeoutSeconds: 3
              failureThreshold: 20
            }
            {
              type: 'Liveness'
              httpGet: {
                path: '/_stcore/health'
                port: 8501
              }
              periodSeconds: 15
              timeoutSeconds: 3
              failureThreshold: 3
            }
            {
              type: 'Readiness'
              httpGet: {
                path: '/_stcore/health'
                port: 8501
              }
              initialDelaySeconds: 5
              periodSeconds: 10
              timeoutSeconds: 5
              failureThreshold: 6
            }
          ]
        }
      ]
      scale: {
        minReplicas: 1
        maxReplicas: 2
        rules: [
          {
            name: 'ui-http-scale'
            http: {
              metadata: {
                concurrentRequests: '30'
              }
            }
          }
        ]
      }
    }
  }
}

output apiUrl string = 'https://${api.properties.configuration.ingress.fqdn}'
output uiUrl string = 'https://${ui.properties.configuration.ingress.fqdn}'
output release string = imageTag
