# Refund Agent — A365 + 3IQs

A Python agent that wraps an **Azure AI Foundry agent** (with Fabric Data Agent + Work IQ tools) and publishes it to **Microsoft Teams / M365 Copilot** via the **Microsoft Agent 365 (A365)** SDK.

The Foundry agent handles all intelligence (instructions, model, tool connections). This project is the A365 hosting wrapper that adds: Teams messaging, notifications (email, Word comments), observability, and user identity passthrough (OBO).

---

## Setup Instructions

### Tested Versions

| Tool / SDK | Version |
|---|---|
| **A365 CLI** | `1.1.171` or later |
| **Python** | 3.11+ |
| `microsoft-agents-hosting-aiohttp` | latest (unpinned) |
| `microsoft-agents-hosting-core` | latest (unpinned) |
| `microsoft-agents-authentication-msal` | latest (unpinned) |
| `microsoft-agents-activity` | latest (unpinned) |
| **Azure CLI** | 2.60+ |

### Prerequisites

Follow these steps in order. The user must have:
- Azure CLI logged in (`az login`)
- An Azure AI Foundry project with an agent already created (with Fabric Data Agent and/or Foundry IQ tools connected)
- The A365 CLI installed (see https://learn.microsoft.com/en-us/microsoft-agent-365/developer/install-cli) — **version 1.1.171+**
- A tenant enrolled in the [Frontier Preview Program](https://adoption.microsoft.com/copilot/frontier-program/)
- **Global Admin** or **Application Administrator** role in the tenant (needed for blueprint setup + consent)
- At least one available **Microsoft 365 E5/E3/Business Basic license** with Teams (needed for Work IQ)

---

### Step 1: Clone and Install Dependencies

```bash
git clone https://github.com/microsoft/iq-samples.git
cd iq-samples/refund-agent-a365
python -m venv .venv
.venv/Scripts/activate  # Windows
pip install -r agent/requirements.txt
```

---

### Step 2: Create the Foundry Agent (if not already done)

In the Azure AI Foundry portal (https://ai.azure.com):

1. Open your project → **Agents** → **+ New agent**
2. Choose model: `gpt-4.1` (must match the model name in `agent.py`)
3. Set agent **Instructions** (system prompt) — keep it conversational, e.g.:
   > You are a refund support agent. Answer questions about package deliveries, refund policies, and help coordinate with team members. Be concise and direct. Do not use checklists unless asked.
4. Add **Tool connections** as needed:
   - **Fabric Data Agent**: Connect to your Fabric workspace data agent (for querying logistics/package data)
   - **Foundry IQ (Knowledge)**: Add knowledge files (e.g., refund policies PDF)
   - **Work IQ Teams**: For reading/sending Teams messages and emails
5. Note the agent's **display name** (e.g., `Refund-agent`) — you'll need this for `.env`

---

### Step 3: Configure the Foundry Agent Connection

Ask the user for these values and populate `.env` (copy from `.env.template`):

| Variable | Description |
|----------|-------------|
| `AZURE_AI_FOUNDRY_ENDPOINT` | Foundry project endpoint (e.g., `https://<account>.services.ai.azure.com/api/projects/<project>`) |
| `FOUNDRY_AGENT_NAME` | The agent's display name in Foundry (e.g., `Refund-agent`) |
| `AZURE_AI_SERVICES_KEY` | API key from the AI Services resource |

These are the only values set manually. Everything else is populated by the A365 CLI.

---

### Step 4: Run A365 Setup (AI Teammate Path)

This provisions the blueprint, configures inheritable permissions (Graph, Power Platform, Messaging Bot API, Observability, Agent 365 Tools), and registers the messaging endpoint.

#### 4.1 — Create `a365.config.json`

Copy `a365.config.example.json` → `a365.config.json` and ask the user for:

| Field | Description |
|-------|-------------|
| `tenantId` | Azure AD tenant ID (get from `az account show`) |
| `subscriptionId` | Azure subscription ID |
| `resourceGroup` | Resource group for the App Service |
| `webAppName` | Azure Web App name (globally unique) |
| `managerEmail` | User's email in the tenant |
| `messagingEndpoint` | `https://<webAppName>.azurewebsites.net/api/messages` |
| `clientAppId` | The A365 CLI client app ID in the tenant (auto-detected or ask user) |

Set `location` to a supported region (e.g., `canadacentral`, `westus`, `eastus`).

#### 4.2 — Ensure `customBlueprintPermissions` includes Cognitive Services + Azure ML

The `a365.config.json` **must** include these two extra resources (in addition to Agent 365 Tools) for OBO token exchange to work with Foundry:

```json
"customBlueprintPermissions": [
  {
    "resourceAppId": "ea9ffc3e-8a23-4a7d-836d-234d7c7565c1",
    "resourceName": null,
    "scopes": ["McpServers.Mail.All", "McpServers.Teams.All", "McpServersMetadata.Read.All"]
  },
  {
    "resourceAppId": "7d312290-28c8-473c-a0ed-8e53749b6d6d",
    "resourceName": "Microsoft Cognitive Services",
    "scopes": ["user_impersonation"]
  },
  {
    "resourceAppId": "18a66f5f-dbdf-4c17-9dd7-1634712a9cbe",
    "resourceName": "Azure Machine Learning Services",
    "scopes": ["user_impersonation"]
  }
]
```

**Why:** The Foundry API (`services.ai.azure.com`) requires a user token with audience `https://ai.azure.com`. The blueprint must have inheritable permissions for Azure ML Services (the resource behind `ai.azure.com`) and Cognitive Services (needed for internal OBO within Foundry).

#### 4.3 — Run setup

```bash
a365 setup all --aiteammate --agent-name <agent-name>
```

- The CLI will prompt for authentication (WAM dialog on Windows or device code flow). Warn the user to watch for the sign-in dialog.
- If the CLI asks for the client app ID, ask the user to provide it.
- If WAM fails, it falls back to device code — tell the user to open https://login.microsoft.com/device and enter the code shown.

**Expected output:**
- Blueprint created/reused
- Inheritable permissions configured (Microsoft Graph, Agent 365 Tools, Messaging Bot API, Observability, Power Platform, **Microsoft Cognitive Services**, **Azure Machine Learning Services**)
- OAuth2 grants configured
- Admin consent granted
- Messaging endpoint registered
- `.env` updated with SERVICE_CONNECTION credentials, AGENT_ID, observability settings

#### 4.4 — Identify the teammate account

After setup, find the teammate account (needed for Steps 5-7):

```bash
# The teammate is a user account created by a365 CLI
az ad user list --filter "startsWith(displayName,'Refund')" --query "[].{name:displayName,upn:userPrincipalName,id:id}" -o table
```

Note the **object ID** and **UPN** — you'll need these for RBAC assignment, license, and Fabric workspace access.

#### 4.5 — Register messaging endpoint (if skipped)

If setup reports "MessagingEndpoint not configured", ensure `messagingEndpoint` is in `a365.config.json`, then run:

```bash
a365 setup blueprint --endpoint-only --m365
```

---

### Step 5: Create Azure Web App (if not exists)

If the App Service doesn't exist yet, create it:

```bash
az group create --name <resourceGroup> --location <location>
az appservice plan create --name <planName> --resource-group <resourceGroup> --sku B1 --is-linux
az webapp create --name <webAppName> --resource-group <resourceGroup> --plan <planName> --runtime "PYTHON:3.11"
az webapp config set --name <webAppName> --resource-group <resourceGroup> --startup-file "python start_with_generic_host.py"
```

---

### Step 6: Assign RBAC Roles on the AI Services Resource

The delegated user identity needs **Azure AI Developer** role on both the AI Services account AND the project for OBO tokens to be accepted by Foundry:

```bash
# Get the AI Services resource ID
RESOURCE_ID=$(az cognitiveservices account show --name <ai-services-name> --resource-group <ai-services-rg> --query id -o tsv)

# Assign on account level
az role assignment create --role "Azure AI Developer" --assignee <user-object-id-or-email> --scope $RESOURCE_ID

# Assign on project level
az role assignment create --role "Azure AI Developer" --assignee <user-object-id-or-email> --scope "$RESOURCE_ID/projects/<project-name>"
```

**Required RBAC roles for the teammate account:**

| Role | Scope | Why |
|---|---|---|
| **Azure AI Developer** | AI Services account (`Microsoft.CognitiveServices/accounts/<name>`) | Allows Foundry agent API calls via OBO token |
| **Azure AI Developer** | Project (`Microsoft.CognitiveServices/accounts/<name>/projects/<project>`) | Allows project-level agent operations |
| **Cognitive Services User** | AI Services account | Needed for internal OBO within Foundry (added automatically by some setups) |

**Why:** The OBO token has audience `https://ai.azure.com` and the Foundry API checks RBAC on both the AI Services resource and the project. Without this role, Foundry returns 403 Forbidden even with a valid user token. "Cognitive Services User" alone is NOT sufficient — you need "Azure AI Developer" which includes agent operations.

**Tip:** You can also assign at resource group or subscription scope if all users should have access.

**Note:** The user identity used here is the **A365 teammate account** (e.g., `refundagentteammate@...`), NOT the end user. The A365 platform uses this service account to represent delegated access.

To verify roles are assigned correctly:
```bash
az role assignment list --assignee <teammate-object-id> --all --output table
```

---

### Step 7: Assign M365 License to Teammate Account

The A365 teammate account needs a **Microsoft 365 license WITH Teams** for Work IQ tools (Teams messages, chats, emails) to work. A license without Teams (e.g., "E5 no Teams") will only enable email but NOT Teams chat operations.

**Important:** The teammate account appears under **Admin Center → Agents** (not under Users).

```bash
# Find the teammate account's object ID (created by a365 setup)
TEAMMATE_ID=$(az ad user list --filter "startsWith(userPrincipalName,'refundagent')" --query "[0].id" -o tsv)

# Check current licenses
az rest --method GET --url "https://graph.microsoft.com/v1.0/users/$TEAMMATE_ID/licenseDetails" --query "value[].skuPartNumber" -o tsv

# Get available M365 SKU IDs in your tenant
az rest --method GET --url "https://graph.microsoft.com/v1.0/subscribedSkus" --query "value[].{sku:skuPartNumber,id:skuId,available:prepaidUnits.enabled,consumed:consumedUnits}" -o table

# Assign (replace SKU_ID with an M365 license that includes Teams)
az rest --method POST --url "https://graph.microsoft.com/v1.0/users/$TEAMMATE_ID/assignLicense" \
  --body '{"addLicenses":[{"skuId":"<SKU_ID>"}],"removeLicenses":[]}'
```

If no licenses are available, you may need to:
- Remove a license from an inactive user first (check `signInActivity` via Graph)
- Or start a free trial: Admin Center → Billing → Purchase services → "Microsoft 365 Business Basic" trial

**Or via Admin Center:** Admin Center → Agents → find the teammate → assign M365 license.

Exchange/Teams mailbox provisioning takes 5-10 minutes after assignment.

---

### Step 8: Grant Fabric Workspace Access (if using Fabric Data Agent)

Add the teammate account to the Fabric workspace:

1. Go to https://app.fabric.microsoft.com
2. Open the workspace containing your data agent's data sources
3. Click **Manage access** → **Add people or groups**
4. Search for the teammate account (e.g., `refundagentteammate@...`)
5. Assign **Viewer** or **Member** role → Save

---

### Step 9: Deploy to Azure

#### 9.1 — Sync App Settings

Push ALL settings from `.env` to Azure App Settings. Read every key=value pair from the `.env` file and push them:

```bash
# Read .env and push all settings to Azure (PowerShell)
$settings = Get-Content .env | Where-Object { $_ -match '^\w' -and $_ -notmatch '^#' } | ForEach-Object { $_.Trim() }
az webapp config appsettings set --name <webAppName> --resource-group <resourceGroup> --settings @($settings)
```

Or manually specify each setting:

```bash
az webapp config appsettings set --name <webAppName> --resource-group <resourceGroup> --settings \
  "AZURE_AI_FOUNDRY_ENDPOINT=..." \
  "FOUNDRY_AGENT_NAME=..." \
  "AZURE_AI_SERVICES_KEY=..." \
  "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTID=..." \
  "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__CLIENTSECRET=..." \
  "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__TENANTID=..." \
  "CONNECTIONS__SERVICE_CONNECTION__SETTINGS__SCOPES=..." \
  "AUTH_HANDLER_NAME=AGENTIC" \
  "AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__AGENTIC__SETTINGS__TYPE=AgenticUserAuthorization" \
  "AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__AGENTIC__SETTINGS__SCOPES=https://graph.microsoft.com/.default" \
  "AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__AGENTIC__SETTINGS__ALT_BLUEPRINT_NAME=SERVICE_CONNECTION" \
  "AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__AGENTIC__SETTINGS__ALTERNATEBLUEPRINTCONNECTIONNAME=https://graph.microsoft.com/.default" \
  "CONNECTIONSMAP__0__SERVICEURL=*" \
  "CONNECTIONSMAP__0__CONNECTION=SERVICE_CONNECTION" \
  "USE_AGENTIC_AUTH=true" \
  "AGENT_ID=..." \
  "AGENT365OBSERVABILITY__AGENTID=..." \
  "AGENT365OBSERVABILITY__AGENTBLUEPRINTID=..." \
  "AGENT365OBSERVABILITY__CLIENTID=..." \
  "AGENT365OBSERVABILITY__CLIENTSECRET=..." \
  "AGENT365OBSERVABILITY__TENANTID=..." \
  "AGENT365OBSERVABILITY__AGENTNAME=..." \
  "AGENT365OBSERVABILITY__AGENTDESCRIPTION=..." \
  "ENABLE_OBSERVABILITY=true" \
  "ENABLE_A365_OBSERVABILITY_EXPORTER=false" \
  "PORT=3978" \
  "LOG_LEVEL=INFO"
```

#### 9.2 — Zip deploy

Create a zip EXCLUDING `.venv`, `.git`, `__pycache__`, `logs`, `*.zip`, `node_modules`:

```bash
# PowerShell
Get-ChildItem -Exclude .venv,.git,__pycache__,logs,*.zip,node_modules | Compress-Archive -DestinationPath app.zip -Force
az webapp deploy --name <webAppName> --resource-group <resourceGroup> --src-path app.zip --type zip --timeout 300
```

The deploy may take 3-5 minutes (pip install on first cold start). If it times out with 504, retry — the build likely succeeded.

#### 9.3 — Verify

```bash
curl -s -o /dev/null -w "%{http_code}" https://<webAppName>.azurewebsites.net/api/messages
# Expected: 200
```

---

### Step 10: Publish Manifest to Teams

```bash
a365 publish
```

- When asked to open manifest editor, respond `n` (or let the user customize if they want)
- Press Enter to continue packaging
- Output: `manifest/manifest.zip`

Then tell the user:
1. Go to https://admin.microsoft.com > Agents > All agents > Upload custom agent
2. Upload `manifest/manifest.zip`
3. Create an agent instance following: https://learn.microsoft.com/en-us/microsoft-agent-365/developer/create-instance

---

## Architecture

```
Teams User → A365 Platform → This app (host_agent_server.py) → Foundry Agent (OpenAI Responses API)
                                    ↕
                        AgenticUserAuthorization
                        (platform provides user token)
                                    ↓
                        Foundry passes user identity to:
                        - Fabric Data Agent (queries data as user)
                        - Work IQ tools (accesses M365 as user)
```

### Key Files

| File | Purpose |
|------|---------|
| `agent.py` | Core agent logic — forwards messages to Foundry, handles OBO token exchange |
| `host_agent_server.py` | A365 host server — message routing, auth, notifications, typing indicators |
| `agent_interface.py` | Abstract base class for agents |
| `start_with_generic_host.py` | Entry point — imports RefundAgent and starts the host |
| `token_cache.py` | Caches observability tokens |
| `.env.template` | Template for environment variables |
| `a365.config.example.json` | Template for A365 CLI config |

### Authentication Flow (OBO via AgenticUserAuthorization)

The agent uses `AgenticUserAuthorization` handler type. This is the A365-native way to get user-delegated tokens:

1. User sends message in Teams
2. A365 platform delivers message to `/api/messages` with agentic context
3. `agent.py` calls `auth.exchange_token(context, scopes=["https://ai.azure.com/.default"])` 
4. The SDK's `AgenticUserAuthorization.get_agentic_user_token()` asks the A365 platform for a token
5. Platform returns a user-delegated token (because blueprint has inheritable permissions configured)
6. Agent passes the token as `Authorization: Bearer <token>` header to the Foundry Responses API
7. Foundry returns `mcp_approval_request` items — the agent **auto-approves** and re-sends
8. Foundry forwards user identity to Fabric Data Agent / Work IQ and returns the final response

**Critical:** The blueprint's inheritable permissions (configured by `a365 setup all --aiteammate`) define which scopes the platform can issue on behalf of the user. Without these, `get_agentic_user_token()` returns nothing.

### Environment Variables (all set by a365 CLI except Foundry ones)

| Variable | Source | Purpose |
|----------|--------|---------|
| `AZURE_AI_FOUNDRY_ENDPOINT` | Manual | Foundry project URL |
| `FOUNDRY_AGENT_NAME` | Manual | Agent name in Foundry |
| `AZURE_AI_SERVICES_KEY` | Manual | API key for fallback auth |
| `CONNECTIONS__SERVICE_CONNECTION__SETTINGS__*` | a365 CLI | Blueprint credentials (client ID = blueprint app ID) |
| `AUTH_HANDLER_NAME` | Fixed | Always `AGENTIC` |
| `AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__AGENTIC__SETTINGS__TYPE` | Fixed | Always `AgenticUserAuthorization` |
| `AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__AGENTIC__SETTINGS__SCOPES` | Fixed | `https://graph.microsoft.com/.default` — DO NOT CHANGE (breaks message delivery) |
| `AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__AGENTIC__SETTINGS__ALT_BLUEPRINT_NAME` | Fixed | `SERVICE_CONNECTION` — tells the SDK which connection to use for OBO |
| `CONNECTIONSMAP_0_SERVICEURL` | Fixed | `*` |
| `CONNECTIONSMAP_0_CONNECTION` | Fixed | `SERVICE_CONNECTION` |
| `USE_AGENTIC_AUTH` | Fixed | `true` |
| `AGENT_ID` | a365 CLI | Blueprint app ID |
| `AGENT365OBSERVABILITY__*` | a365 CLI | Observability config |

**WARNING:** Never change the SCOPES setting away from `https://graph.microsoft.com/.default` on Azure App Settings — this breaks message delivery entirely.

---

## Troubleshooting

### Error: 401 `PermissionDenied` — "principal lacks required data action `Microsoft.CognitiveServices/accounts/AIServices/agents/write`"

The teammate account (or App Service managed identity) doesn't have RBAC on the AI Services resource. Assign **Azure AI Developer** (not just Cognitive Services User) on both the account and project:

```bash
RESOURCE_ID=$(az cognitiveservices account show --name <ai-services-name> --resource-group <rg> --query id -o tsv)
TEAMMATE_ID=<teammate-object-id>

# Account level
az role assignment create --role "Azure AI Developer" --assignee $TEAMMATE_ID --scope $RESOURCE_ID
# Project level
az role assignment create --role "Azure AI Developer" --assignee $TEAMMATE_ID --scope "$RESOURCE_ID/projects/<project-name>"
```

Also assign to the **App Service managed identity** if you see its principal ID in the error:

```bash
MSI_ID=$(az webapp identity show --name <webAppName> --resource-group <rg> --query principalId -o tsv)
az role assignment create --role "Azure AI Developer" --assignee $MSI_ID --scope $RESOURCE_ID
az role assignment create --role "Azure AI Developer" --assignee $MSI_ID --scope "$RESOURCE_ID/projects/<project-name>"
```

Wait 1-5 minutes for RBAC propagation.

### Error: 401 — "Principal does not have access to API/Operation"

This is a more generic variant of the RBAC error above. Add **Cognitive Services User** as well:

```bash
az role assignment create --role "Cognitive Services User" --assignee $TEAMMATE_ID --scope $RESOURCE_ID
```

### Error: 400 — "ARA OBO token request failed with status BadRequest"

The OBO token exchange inside Foundry is failing. The most common causes:

1. **Missing `customBlueprintPermissions`** (most common): If `a365 setup all` ran without the `customBlueprintPermissions` block in `a365.config.json`, the blueprint won't have inheritable permissions for Azure ML Services / Cognitive Services. Fix: add the permissions to config and re-run `a365 setup all`.

2. **Admin consent not granted**: Check Azure Portal → Enterprise Apps → find the blueprint app → Permissions → verify consent is granted for Cognitive Services and Azure ML Services.

3. **Missing `ALT_BLUEPRINT_NAME`**: Ensure `AGENTAPPLICATION__USERAUTHORIZATION__HANDLERS__AGENTIC__SETTINGS__ALT_BLUEPRINT_NAME=SERVICE_CONNECTION` is set in `.env` and app settings.

4. **Agent identity missing OAuth2 grants**: If the agent instance was created via Admin Center (not `a365 create-instance`), the agent identity service principal may lack OAuth2 permission grants. Create them manually:

```bash
AGENT_IDENTITY_SP=<agent-identity-sp-object-id>
GRAPH_SP=<microsoft-graph-sp-object-id>

# Grant Graph delegated permissions
az rest --method POST --url "https://graph.microsoft.com/v1.0/oauth2PermissionGrants" \
  --body "{\"clientId\":\"$AGENT_IDENTITY_SP\",\"consentType\":\"AllPrincipals\",\"resourceId\":\"$GRAPH_SP\",\"scope\":\"User.Read.All Mail.Send Mail.ReadWrite Chat.Read Chat.ReadWrite Files.Read.All Sites.Read.All ChannelMessage.Read.All ChannelMessage.Send Files.ReadWrite.All\"}"

# Repeat for Work IQ Tools, Cognitive Services, Azure ML Services, Messaging Bot API, Observability
```

### Error: 404 — "Application '&lt;name&gt;' not found"

The Foundry agent URL is wrong. The agent code was using `/applications/<name>/protocols/openai` which is not the correct published endpoint. The correct approach is to use the standard `/openai/responses` endpoint with `agent_reference`:

```python
# Wrong — returns 404
base_url = f"{endpoint}/applications/{agent_name}/protocols/openai"
client.responses.create(model=model, input=input)

# Correct — use /openai endpoint with agent_reference
base_url = f"{endpoint}/openai"
client.responses.create(
    model=model,
    input=input,
    extra_body={"agent_reference": {"type": "agent_reference", "name": agent_name}},
)
```

### Error: 400 — "Model must match the agent's model '&lt;name&gt;' when agent is specified"

The `model` parameter in the API call doesn't match the model configured on the Foundry agent. Set `FOUNDRY_MODEL_NAME` in `.env` to the exact model name shown in the Foundry portal (e.g., `gpt-4.1-mini-1`).

### Error: "Copilot email search failed (500)" from Work IQ Mail

The Work IQ `SearchMessages` tool uses **Copilot semantic search**, which requires a **Microsoft 365 Copilot license** — an E5 license alone is **not sufficient**. Even after assigning the license, the semantic index can take **up to 24 hours** to provision for a new user.

**Immediate fix:** Update the Foundry agent instructions to use `SearchMessagesQueryParameters` (direct Graph query) instead of `SearchMessages` (semantic search), and use `$search` with KQL syntax instead of `$filter`:

```
## Email & Communication (Work IQ)

When asked to search, check, or respond to emails, always use SearchMessagesQueryParameters (NOT SearchMessages).

Query syntax rules:
- To list recent emails: queryParameters "?$orderby=receivedDateTime desc&$top=10"
- To search by subject: "?$search="subject:Escalation"&$top=10"
- To search by sender: "?$search="from:marco"&$top=10"
- General keyword: "?$search="refund complaint"&$top=10"
- NEVER use $filter with contains() on subject/body — Graph returns BadRequest
- NEVER combine $search with $filter or $orderby
- Always set preferTextBody to true
```

Or update via API:

```bash
# Create a new agent version with updated instructions
az rest --method POST \
  --url "$AZURE_AI_FOUNDRY_ENDPOINT/agents/<agent-name>/versions?api-version=2025-11-15-preview" \
  --resource "https://ai.azure.com" \
  --body @agent-update.json
```

**Long-term fix:** Assign the M365 Copilot license to the teammate and wait for provisioning:

```bash
TEAMMATE_ID=<teammate-object-id>
SKU_ID=$(az rest --method GET --url "https://graph.microsoft.com/v1.0/subscribedSkus" \
  --query "value[?skuPartNumber=='Microsoft_365_Copilot'].skuId" -o tsv)
az rest --method POST --url "https://graph.microsoft.com/v1.0/users/$TEAMMATE_ID/assignLicense" \
  --body "{\"addLicenses\":[{\"skuId\":\"$SKU_ID\"}],\"removeLicenses\":[]}"
```

Once the Copilot semantic index is provisioned (up to 24h), you can remove the instruction override and `SearchMessages` will work.

### Error: `tool_user_error` when Fabric Data Agent is queried

This means Foundry couldn't authenticate the user to Fabric. Check:
1. Blueprint inheritable permissions include **Microsoft Cognitive Services** (`user_impersonation`) and **Azure Machine Learning Services** (`user_impersonation`)
2. Teammate has **Azure AI Developer** RBAC role on the AI Services resource AND the project
3. Teammate has Viewer/Member access on the Fabric workspace and its data sources
4. Fabric data agent and Foundry project are in the same tenant
5. OAuth2 grants were configured for both Cognitive Services and Azure ML Services

### Error: Messages not delivered to the agent (agent is silent)

1. Check app is running: `curl https://<webAppName>.azurewebsites.net/api/messages` should return 200
2. Check messaging endpoint is registered: look in `a365.generated.config.json` for `messagingEndpoint`
3. Verify the SCOPES app setting is `https://graph.microsoft.com/.default` — **never change this** or message delivery breaks entirely
4. Check app logs for startup errors: `az webapp log tail --name <webAppName> --resource-group <rg>`
5. If logs show `⚠️ No auth env vars; running anonymous` — the `CONNECTIONS__SERVICE_CONNECTION__SETTINGS__*` env vars are missing or empty. Re-run `a365 setup all` or check `.env`.

### Error: "Access to tenant is denied" from Work IQ Teams/Mail

The A365 teammate account needs a **Microsoft 365 license WITH Teams** for Work IQ Teams tools. A license without Teams (e.g., "E5 no Teams") will only enable email but NOT Teams chat operations. Assign via:
- Admin Center → Agents → find the teammate → assign license
- Or via Graph API: `POST /users/{id}/assignLicense` with the M365 SKU ID

Exchange/Teams mailbox provisioning takes 5-10 minutes after license assignment.

### Error: 550 5.7.708 — "Access denied, traffic not accepted from this IP" (outbound email blocked)

Emails sent by the teammate via Work IQ show as "sent successfully" in Graph but never arrive at external recipients. The NDR shows `550 5.7.708` which means the teammate's mailbox is routed through Exchange Online's **High Risk Delivery Pool (HRDP)** — common for brand new `agentUser` accounts with zero sender reputation. **Internal delivery (same tenant) works fine.**

**Diagnosis:**
1. Go to https://security.microsoft.com/restrictedentities — if the teammate is listed, unblock it
2. If not listed (likely), the issue is HRDP routing for low-reputation senders

**Fix:**
1. **Enable DKIM signing**: https://security.microsoft.com → **Email & collaboration** → **Policies & rules** → **Threat policies** → **Email authentication settings** → **DKIM** → select your domain → enable
2. **Check outbound anti-spam policy**: same portal → **Anti-spam** → **Anti-spam outbound policy** — ensure it's not overly restrictive
3. **Wait 24-48 hours** — Microsoft auto-lifts HRDP routing once the mailbox builds sender reputation
4. **For demos**: send emails to internal `@yourdomain.onmicrosoft.com` addresses (internal delivery is unaffected)

### Monitoring the teammate's mailbox

The `agentUser` mailbox can't be signed into directly. To monitor the teammate's inbox, sent items, and bounce-back NDRs:

1. In **Exchange Admin Center** (https://admin.exchange.microsoft.com) → **Recipients** → **Mailboxes** → find the teammate
2. Under **Mailbox delegation**, add your own account as **Full Access**
3. In Outlook, open the teammate's mailbox as an additional account (File → Open & Export → Other User's Folder, or it may auto-appear in your folder list)

This lets you see sent emails, NDR bounce-backs, and incoming emails in the teammate's mailbox from your own Outlook.

### Error: "User is not authorized" (from Fabric)

The delegated user doesn't have access to the Fabric workspace. Add the A365 teammate account (e.g., `refundagentteammate@...`) as Viewer/Member in the Fabric workspace where the data agent lives.

### Email notifications not triggering the agent (502 Bad Gateway)

When someone emails the teammate, the A365 platform delivers a notification to the agent's messaging endpoint. This notification arrives as `channel_id: agents:email` with `activity.type: message` — meaning it hits the regular message handler, not a separate notification handler.

**The problem:** The message handler sends a `typing` activity indicator before processing. The `agents:email` channel does **not** support typing indicators, so the platform returns `502 Bad Gateway`, which crashes the entire handler before the agent can process the email.

**The fix:** Skip typing indicators when the channel is email:

```python
channel_id = getattr(context.activity, "channel_id", "") or ""
is_email = "email" in channel_id.lower()

if not is_email:
    await context.send_activity(Activity(type="typing"))
    # ... start typing loop
```

**Prerequisites for email notifications to work:**
1. **Notification URL** must be set in the Teams Developer Portal: go to `https://dev.teams.microsoft.com/tools/agent-blueprint/<blueprint-id>/configuration` → set **Agent Type** to **API Based** → set **Notification URL** to your messaging endpoint (e.g., `https://<webAppName>.azurewebsites.net/api/messages`) → Save
2. The teammate must have a **provisioned Exchange mailbox** (M365 E5/E3/Business Basic license assigned, wait 5-10 min for provisioning)
3. The agent code must handle `EmailResponse` for replies — the `host_agent_server.py` `on_agent_notification` handler wraps the response with `EmailResponse.create_email_response_activity()` for email channel replies
4. The `agents_sdk_config` from `load_configuration_from_env` must have the correct `CONNECTIONS__SERVICE_CONNECTION__SETTINGS__*` values for the A365 platform to authenticate the notification delivery

### Deploy timeout (504) or slow deploys

Normal on first deploy — Oryx builds Python dependencies (3-5 min). Retry the deploy command or check status at `https://<webAppName>.scm.azurewebsites.net/api/deployments/latest`.

**Critical:** Never use `az webapp deploy --clean true` — this wipes the Oryx build cache including pip packages, causing the app to crash with `No module named 'dotenv'`. If this happens, redeploy with `az webapp up` to trigger a full Oryx rebuild.

### WAM authentication fails during a365 CLI

The CLI falls back to device code flow. Tell user to open https://login.microsoft.com/device and enter the code displayed. If it times out, the CLI will ask for the client app ID directly.

### Error: "I processed your request but couldn't generate a response"

Foundry returned HTTP 200 but with only `mcp_approval_request` items (no assistant message). This means the MCP auto-approval logic isn't working. Check that `agent.py` has the approval loop that detects `mcp_approval_request` items and sends back `mcp_approval_response` with `approve: True`.

### Debugging tips

- **Enable app logging**: `az webapp log config --name <webAppName> --resource-group <rg> --application-logging filesystem --level information --docker-container-logging filesystem`
- **Tail live logs**: `az webapp log tail --name <webAppName> --resource-group <rg>`
- **Check token claims**: The agent logs `🔍 TOKEN CLAIMS:` with the OBO token details (oid, upn, aud, scp, idtyp). Look for `idtyp=user` to confirm it's a delegated token, not an app token.
- **Check MCP tool output**: The agent logs `🔧 MCP item:` with the full Foundry response output, including any tool errors from Work IQ or Fabric Data Agent.
- **List RBAC assignments**: `az role assignment list --scope <resource-id> --query "[].{principal:principalId,role:roleDefinitionName}" -o table`
- **List OAuth2 grants**: `az rest --method GET --url "https://graph.microsoft.com/v1.0/servicePrincipals/<sp-id>/oauth2PermissionGrants" --query "value[].{scope:scope}" -o table`

---

## Prerequisites for Fabric Data Agent to Work

- Foundry agent must have a **Fabric Data Agent** tool connection configured in Azure AI Foundry portal
- The Fabric data agent must be in the **same tenant** as the Foundry project
- Blueprint inheritable permissions must include:
  - **Microsoft Cognitive Services** (`7d312290-28c8-473c-a0ed-8e53749b6d6d`) — `user_impersonation`
  - **Azure Machine Learning Services** (`18a66f5f-dbdf-4c17-9dd7-1634712a9cbe`) — `user_impersonation`
- The delegated user (A365 teammate account) must have:
  - **`Azure AI Developer`** RBAC role on the AI Services resource AND the project
  - **Viewer or Member** access on the Fabric workspace
  - READ access on the Fabric data agent
  - READ access on the underlying data sources (Lakehouse, Warehouse, etc.)
- Service principal authentication is **NOT supported** — must use user identity (which is why OBO is required)
- The token scope must be `https://ai.azure.com/.default` (maps to Azure ML Services app `18a66f5f`)
- The code must handle **MCP approval requests** — Foundry returns `mcp_approval_request` items that must be approved before tool execution proceeds

---

## Important Implementation Notes

### MCP Tool Approval

Foundry's Responses API returns `mcp_approval_request` items when tools (Foundry IQ, Fabric Data Agent) need user consent. The agent must:
1. Detect `mcp_approval_request` items in the response output
2. Send back `mcp_approval_response` with `"approve": True` for each
3. Re-call the API with the approval responses appended to the input
4. Repeat until a final assistant message is returned

Without this, the agent returns "I processed your request but couldn't generate a response."

### Token Scope: `ai.azure.com` NOT `cognitiveservices.azure.com`

The Foundry agent endpoint (`services.ai.azure.com`) requires tokens with audience `https://ai.azure.com`. Tokens scoped to `cognitiveservices.azure.com` will get 403 Forbidden. The resource app ID for `ai.azure.com` is `18a66f5f-dbdf-4c17-9dd7-1634712a9cbe` (Azure Machine Learning Services).

---

## Shipment Dashboard (Frontend Web App)

A standalone web UI for the Refund Agent — separate from the A365/Teams bot. Provides a chat interface with a shipment visualization dashboard.

- **Local:** http://localhost:5173 (frontend) + http://localhost:8000 (backend)

### Architecture

```
Frontend (React/Vite)  →  WebSocket  →  Backend (FastAPI/Uvicorn)  →  Foundry Responses API  →  Agent Tools
     ↓                                      ↓                                                    ↓
  MSAL Login                         Bearer Token Passthrough                          Fabric IQ, WorkIQ,
  (Entra ID)                         (user token or managed identity)                  WorldGrounding, KB
```

**Key difference from A365 bot:** This app calls the same Foundry agent but through a browser-based UI with WebSocket instead of Teams.

### Tech Stack

| Component | Technology |
|-----------|-----------|
| Frontend | React 19, Vite 7, TypeScript, MSAL.js |
| Backend | Python 3.12, FastAPI, Uvicorn |
| HTTP Client | `requests` (NOT httpx — see Known Issues) |
| Auth (local) | Azure CLI credential (`az login`) |
| Auth (deployed) | Managed Identity + MSAL user token passthrough |
| Hosting | Azure Container Apps (Consumption) |

### Key Files

| File | Purpose |
|------|---------|
| `frontend/src/lib/auth.ts` | MSAL configuration and token acquisition |
| `frontend/src/hooks/useWebSocket.ts` | WebSocket connection with auth token |
| `frontend/src/App.tsx` | Main app with login/chat UI |
| `backend/main.py` | FastAPI app, serves frontend static files + WebSocket |
| `backend/agent_runner.py` | Calls Foundry Responses API |
| `backend/auth.py` | Azure credential chain (ManagedIdentity → CLI → Browser) |
| `backend/chat.py` | Handles WebSocket messages, passes user tokens |
| `Dockerfile` | Container image for deployment |
| `.dockerignore` | Excludes .git, node_modules, etc. from image |

---

### Running Locally

**Prerequisites:** Python 3.12+, Node.js 18+, Azure CLI logged in (`az login` with a user account in your tenant)

```bash
# 1. Install backend deps
cd dashboard/backend
pip install -r requirements.txt

# 2. Create backend/.env
cat > .env << EOF
AZURE_PROJECT_ENDPOINT=<your-foundry-project-endpoint>
FOUNDRY_AGENT_NAME=<your-foundry-agent-name>
EOF

# 3. Start backend
python -m uvicorn main:app --reload
# Backend runs at http://localhost:8000

# 4. In a new terminal — install and start frontend
cd dashboard/frontend
npm install
npm run dev
# Frontend runs at http://localhost:5173
```

Open http://localhost:5173, sign in with Microsoft, and start chatting.

**Important:** Locally, the backend uses your `az login` CLI credential (a user token). This is why OBO works locally — Foundry can exchange a user token for downstream MCP tool access. Managed Identity (app-only token) cannot do OBO.

---

### Deploying the Dashboard

The dashboard can be deployed to Azure Container Apps using the included `Dockerfile`.

```bash
# Build image in cloud
az acr build --registry <your-acr-name> --image shipment-dashboard:latest --file dashboard/Dockerfile .

# Update container app
az containerapp update --name <app-name> --resource-group <rg> --image <your-acr>.azurecr.io/shipment-dashboard:latest
```

**Required environment variables on the Container App:**

| Variable | Description |
|----------|-------------|
| `AZURE_PROJECT_ENDPOINT` | Your Foundry project endpoint |
| `FOUNDRY_AGENT_NAME` | The agent's display name in Foundry |
| `FOUNDRY_AGENT_VERSION` | (Optional) Pin to a specific agent version |

**RBAC:** The Container App's managed identity needs `Cognitive Services User` on the AI Services resource.

---

### Authentication (MSAL + Entra ID)

You need an **Entra ID app registration** with a **SPA** redirect URI configured.

**SPA Redirect URIs (configure on your app registration):**
- `http://localhost:5173` (local dev)
- `https://<your-deployed-url>` (deployed)

**Required API Permissions on the app registration:**
- Microsoft Graph — delegated permissions as needed
- WorkIQ (`ea9ffc3e-8a23-4a7d-836d-234d7c7565c1`) — `McpServers.Teams.All` and others
- Azure Machine Learning Services (`18a66f5f-dbdf-4c17-9dd7-1634712a9cbe`) — `user_impersonation`

**Auth Flow (Token Passthrough — not OBO):**
1. User clicks "Sign in" → MSAL redirect to Entra login
2. After login, frontend acquires token for `https://ai.azure.com/.default`
3. Token sent to backend as first WebSocket message: `{"type": "auth", "accessToken": "..."}`
4. Backend stores token per-connection and forwards it as a bearer token to Foundry API calls
5. Foundry internally exchanges the user token to access MCP tools (WorkIQ, Fabric IQ)

**We do NOT implement OBO ourselves.** We pass the user's token through to Foundry, and Foundry handles the downstream token exchange internally. This is why a user token is required — Foundry can't do this exchange with an app-only token (Managed Identity).

**Critical:** If the user token is not available (e.g., MSAL scope acquisition fails), the backend falls back to Managed Identity — but Managed Identity **cannot do OBO**, so MCP tools that require user identity (WorkIQ, Fabric) will fail with "ARA OBO token request failed".

---

### Known Issues & Errors (Deployment)

#### 1. `httpx` incompatibility on App Service / Container Apps

**Error:** `Client.__init__() got an unexpected keyword argument 'timeout'` or `module 'httpx' has no attribute 'Timeout'`

**Root cause:** The system Python on App Service has an old/incompatible `httpx` version that doesn't accept `timeout` in the constructor or has no `Timeout` class.

**Fix:** Replaced `httpx` with `requests` library throughout `agent_runner.py`. The `requests` library is universally available and compatible.

```python
# BAD — breaks on App Service
import httpx
with httpx.Client(timeout=120) as client:
    resp = client.post(url, json=payload)

# GOOD — works everywhere
import requests as http_client
resp = http_client.post(url, json=payload, timeout=120)
```

#### 2. API key auth incompatible with OBO tools

**Error:** `Tools configured with OBO auth are not supported with API key authentication`

**Root cause:** The Foundry agent's MCP tools (WorkIQ, Fabric IQ) require identity passthrough (OBO). API keys are app-level and have no user identity.

**Fix:** Always use bearer tokens (user token or managed identity token), never API keys. Removed `api-key` header logic from `agent_runner.py`.

#### 3. Managed Identity cannot do OBO

**Error:** `ARA OBO token request failed with status BadRequest`

**Root cause:** Managed Identity is an app-only token. Foundry can't exchange it for OBO tokens to call MCP tools that require user delegation (WorkIQ mail, Fabric data).

**Fix:** The frontend MSAL login provides a user-delegated token which is passed through to the backend via WebSocket. The backend uses this user token for Foundry API calls instead of the Managed Identity. Managed Identity is only used for startup validation (agent discovery/ping) where OBO is not needed.

#### 4. Container App managed identity not enabled

**Error:** `ChainedTokenCredential failed to retrieve a token from the included credentials`

**Root cause:** System-assigned managed identity was not enabled on the Container App.

**Fix:**
```bash
az containerapp identity assign --name <app-name> --resource-group <rg> --system-assigned
az role assignment create --assignee <principal-id> --role "Cognitive Services User" --scope <foundry-resource-id>
```

#### 5. MSAL redirect URI mismatch

**Error:** `AADSTS50011: The redirect URI specified in the request does not match` or `AADSTS9002326: Cross-origin token redemption is permitted only for the 'Single-Page Application' client-type`

**Root cause:** The redirect URI must be registered under the **SPA** platform (not Web) in the app registration.

**Fix:** Add redirect URIs via Graph API:
```bash
az rest --method PATCH --url "https://graph.microsoft.com/v1.0/applications/<object-id>" \
  --body '{"spa":{"redirectUris":["http://localhost:5173","https://your-app-url"]}}' \
  --headers "Content-Type=application/json"
```

#### 6. App Service VM quota limitations

**Error:** `SubscriptionIsOverQuotaForSku — Operation cannot be completed without additional quota`

**Root cause:** Some subscriptions have limited App Service VM quota in certain regions.

**Fix:** Use Azure Container Apps (Consumption plan) instead — no VM quota required. Or request a quota increase for your subscription.
