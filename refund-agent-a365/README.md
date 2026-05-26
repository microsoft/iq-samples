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

### Step 2: Create the Foundry Agent with 3 IQs

You can set up the agent **manually via the portal** or **programmatically via the setup script**.

#### Option A: Use the Setup Script (recommended)

The script automates Foundry agent creation with SDK-supported tools (Foundry IQ + Fabric IQ). Work IQ must still be configured in the portal after.

```bash
# Install script dependencies
pip install -r scripts/requirements.txt

# Discover your project connections (find Fabric connection ID)
python scripts/setup_foundry_agent.py --connections

# Set connection IDs in agent/.env:
#   FABRIC_CONNECTION_ID=/subscriptions/.../connections/<name>
#   BING_CONNECTION_NAME=<optional>

# Create the agent (with optional knowledge files for Foundry IQ)
python scripts/setup_foundry_agent.py --knowledge-files docs/refund-policy.pdf

# Then follow the printed instructions to add Work IQ in the portal
```

See `scripts/setup_foundry_agent.py --help` for all options (`--list`, `--delete`, `--connections`).

#### Option B: Manual Portal Setup

In the Azure AI Foundry portal (https://ai.azure.com), open your project and create a new agent.

#### 2.1 — Create the Agent

1. Open your project → **Agents** → **+ New agent**
2. Choose model: `gpt-4.1` (or `gpt-4.1-mini` — must match the `FOUNDRY_MODEL_NAME` in `.env`)
3. Give it a display name (e.g., `Refund-agent`) — you'll need this for `.env`
4. Set agent **Instructions** (system prompt) — copy the contents of [`agent-instructions.md`](agent-instructions.md) and paste into the Instructions field

#### 2.2 — Set Up Foundry IQ (Knowledge / Grounding)

Foundry IQ gives the agent access to your own documents (e.g., refund policies, product catalogs) via retrieval-augmented generation (RAG).

1. In the agent's **Tools** section, click **+ Add tool** → **Knowledge (Foundry IQ)**
2. Upload your knowledge files:
   - For this sample: upload a PDF with Contoso's refund policy (return windows, approval thresholds, exceptions)
   - Supported formats: PDF, DOCX, TXT, MD, HTML
3. Configure the knowledge source:
   - **Name**: e.g., `refund-policies`
   - **Description**: "Contoso refund and return policies, eligibility rules, and approval thresholds"
   - The description helps the agent decide WHEN to use this knowledge source
4. Click **Save**

The agent will now automatically search these documents when users ask about refund policies, return windows, or approval rules.

> **Tip:** You can also connect an Azure AI Search index as a Foundry IQ source for larger document collections.

#### 2.3 — Set Up Work IQ (Teams + Email)

Work IQ lets the agent read/send Teams messages and emails on behalf of the A365 teammate account.

1. In the agent's **Tools** section, click **+ Add tool** → **Work IQ**
2. Select the capabilities to enable:
   - **Teams**: Read and send Teams messages, search chats
   - **Mail**: Read, send, and search emails via Outlook/Exchange
3. Click **Save**

**Important:** Work IQ tools require **user identity passthrough (OBO)**. The A365 platform provides the user token via `AgenticUserAuthorization`, and Foundry forwards it to Work IQ. This is why:
- The teammate account needs an **M365 license with Teams** (see Step 7)
- The blueprint must have `customBlueprintPermissions` for Work IQ (`ea9ffc3e`) — see Step 4.2
- The `SearchMessages` tool uses Copilot semantic search (needs M365 Copilot license). If unavailable, use `SearchMessagesQueryParameters` instead — see the agent instructions in [`agent-instructions.md`](agent-instructions.md)

#### 2.4 — Set Up Fabric IQ (Data Agent)

Fabric IQ connects the agent to your data in Microsoft Fabric (Lakehouse, Warehouse, SQL endpoint) through a Fabric Data Agent.

**Step A — Prepare your data in Fabric:**

1. Go to https://app.fabric.microsoft.com and open (or create) a workspace
2. Create a **Lakehouse** with your data tables:
   - For this sample: tables like `packages`, `customers`, `hubs`, `drivers`, `handoffs`, `payments`
   - Upload data via CSV, notebooks, or the OneLake DFS API
   - Each table becomes queryable via SQL
3. (Optional) Create a **Knowledge Graph** for relationship traversal:
   - Define node types (e.g., Package, Hub, Driver, Customer) and edge types (e.g., processed_at, driven_by)
   - Graph enables multi-hop queries like "trace this package's full journey" that are hard with flat SQL

**Step B — Create the Fabric Data Agent:**

1. In the workspace, click **+ New** → **Data Agent** (preview)
2. Give it a descriptive name (e.g., `contoso-logistics-data`)
3. **Add datasources** — select which Fabric items the agent can query:
   - Your Lakehouse (SQL queries for analytics, payments, aggregations)
   - Your Knowledge Graph (GQL queries for relationship traversal) — if created
4. **Configure each datasource** (this is critical for quality):
   - **Description**: Explain what the data contains (e.g., "Relational lakehouse containing package delivery data: hubs, drivers, customers, packages, handoffs, and payments")
   - **Instructions**: Provide the full schema — table names, column names with types, primary/foreign keys, and common join patterns. The more detail you give, the better the agent's SQL/GQL queries will be
   - **Select tables/elements**: Choose which tables or graph elements the agent can access
5. **Add AI instructions** (agent-level): Write routing logic that tells the agent when to use which datasource. For example:
   - "Use Lakehouse for payment queries, counts, and aggregations"
   - "Use Knowledge Graph for journey tracing and relationship traversal"
   - "Use BOTH when the question involves tracking AND financial data"
6. **Add example queries** (few-shot): Import example question → SQL/GQL pairs via the portal UI or JSON import. These dramatically improve query accuracy
7. **Test** queries in the Data Agent playground to verify it works
8. **Publish** the data agent — this creates a published version that Foundry can connect to

> **Tip:** You can also create and configure a Fabric Data Agent programmatically via the Fabric REST API (`POST /v1/workspaces/{workspaceId}/DataAgents` + `updateDefinition`). See the [fabriciq-foundry-viz](https://github.com/aycabas/fabriciq-foundry-viz) repo for scripted examples.

**Step C — Connect to your Foundry agent:**

1. In Azure AI Foundry, go to **Management center** → **Connected resources** → **+ New connection** → **Microsoft Fabric**
2. Select the published Fabric Data Agent — this creates a connection resource
3. Note the **connection ID** (full ARM path: `/subscriptions/.../connections/<name>`)
4. Back in the Foundry agent's **Tools** section, click **+ Add tool** → **Fabric Data Agent**
5. Select the connection you just created
   - The Fabric Data Agent must be in the **same tenant** as the Foundry project
6. Click **Save**

**Required permissions for Fabric IQ:**
- The A365 teammate account needs **Viewer** or **Member** access on the Fabric workspace (see Step 8)
- Blueprint must have inheritable permissions for **Microsoft Cognitive Services** and **Azure Machine Learning Services** (see Step 4.2)
- The delegated user must have READ access on the underlying data sources (Lakehouse, Warehouse, etc.)
- The token scope must be `https://ai.azure.com/.default` — Foundry internally handles the OBO exchange to Fabric

> **Tip:** You can also add **Grounding with Bing Search** as a tool in the Foundry portal. This lets the agent search the web for real-time information (e.g., shipping delays, product recalls). No additional permissions are needed — just add the tool and save.

#### 2.5 — Verify the Agent

Before proceeding with A365 setup, test the agent in the Foundry playground:

1. Click **Test** in the Foundry agent page
2. Try queries that exercise each IQ:
   - **Foundry IQ**: "What is the refund policy for digital products?"
   - **Fabric IQ**: "Show me recent orders for Mike Johnson"
   - **Work IQ**: "Check my recent emails about refund requests"
3. If MCP approval dialogs appear, approve them — the A365 agent code handles this automatically in production
4. Note the agent's **display name** — you'll set this as `FOUNDRY_AGENT_NAME` in `.env`

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

For all known errors, fixes, debugging tips, and implementation notes, see **[TROUBLESHOOTING.md](TROUBLESHOOTING.md)**.

Covers: RBAC/permission errors, OBO token failures, Foundry agent errors, Work IQ (email/Teams) issues, Fabric Data Agent setup, deployment problems, and dashboard-specific errors.

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

### Known Issues & Errors

See **[TROUBLESHOOTING.md](TROUBLESHOOTING.md#dashboard-specific-errors)** for all dashboard-specific deployment errors including httpx incompatibility, MSAL redirect issues, managed identity setup, and quota limitations.

