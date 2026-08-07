# Azure Container Apps deployment

This directory is deployment-ready infrastructure as code; it does not deploy anything by itself.
The template provisions a Log Analytics workspace, Container Apps environment, API app and
Streamlit app. PostgreSQL and MLflow are treated as managed external dependencies.

## Prerequisites

- Azure CLI with the Container Apps extension and Bicep;
- an Azure Container Registry containing immutable `procurelens-api:v1.0.0` and
  `procurelens-ui:v1.0.0` images;
- managed PostgreSQL with snapshot v1.0.0 restored;
- a reachable MLflow registry containing `procurelens-amendment-risk@champion`;
- `AcrPull` granted to each Container App system identity when private ACR images are used.

Validate without deploying:

```bash
make azure-validate
```

Preview the exact Azure change set before approval:

```bash
az deployment group what-if \
  --resource-group "$AZURE_RESOURCE_GROUP" \
  --template-file deploy/azure/main.bicep \
  --parameters environmentName=prod imageTag=v1.0.0 \
  --parameters apiImageRepository="$API_IMAGE_REPOSITORY" \
  --parameters uiImageRepository="$UI_IMAGE_REPOSITORY" \
  --parameters registryServer="$REGISTRY_SERVER" \
  --parameters databaseUrl="$DATABASE_URL" \
  --parameters agentDatabaseUrl="$AGENT_DATABASE_URL" \
  --parameters mlflowTrackingUri="$MLFLOW_TRACKING_URI"
```

Deployment requires an explicit operator decision after `what-if`. Secret values are secure Bicep
parameters and become Container Apps secret references; they are never stored in this repository.
See `docs/runbooks/production_operations.md` for promotion and rollback.
