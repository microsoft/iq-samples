# Troubleshooting — Refund Agent (A365 + 3IQs)

> **For coding agents:** Always check this file when encountering errors during setup, deployment, or runtime. Most issues have known solutions documented below.

## Table of Contents

- [RBAC and Permission Errors](#rbac-and-permission-errors)
- [OBO Token Errors](#obo-token-errors)
- [Foundry Agent Errors](#foundry-agent-errors)
- [Work IQ Errors](#work-iq-errors)
- [Fabric Data Agent Errors](#fabric-data-agent-errors)
- [Deployment Errors](#deployment-errors)
- [Dashboard-Specific Errors](#dashboard-specific-errors)
- [Implementation Notes](#implementation-notes)
- [Debugging Tips](#debugging-tips)

---

## RBAC and Permission Errors

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

### Error: "User is not authorized" (from Fabric)

The delegated user doesn't have access to the Fabric workspace. Add the A365 teammate account (e.g., `refundagentteammate@...`) as Viewer/Member in the Fabric workspace where the data agent lives.

---

## OBO Token Errors

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

---

## Foundry Agent Errors

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

### Error: "I processed your request but couldn't generate a response"

Foundry returned HTTP 200 but with only `mcp_approval_request` items (no assistant message). This means the MCP auto-approval logic isn't working. Check that `agent.py` has the approval loop that detects `mcp_approval_request` items and sends back `mcp_approval_response` with `approve: True`.

---

## Work IQ Errors

### Error: Work IQ works in the Foundry playground but fails in Teams / headless (`oauth_consent_request` loop, hallucinated answers)

**Symptom:** In the Foundry **playground** the agent reads Teams/Outlook fine, but once published to **Teams via A365** (or any non-interactive caller) it never actually calls Work IQ — it hallucinates an answer, or the Responses API keeps returning `oauth_consent_request` items that can't be satisfied.

**Root cause — the connection's `authType`.** This is the single most common demo-breaker. A Foundry MCP tool connection can authenticate three ways:

| `authType` | How it authenticates | Works headless (Teams/A365)? |
|------------|---------------------|------------------------------|
| `OAuth2` | **Interactive** human consent in a browser | ❌ No — needs a UI; fails with `oauth_consent_request` |
| `UserEntraToken` | **Identity passthrough** — forwards the caller's Entra token (OBO) and mints a token for the connection's `audience` | ✅ Yes |
| `CustomKeys` | Static API key (app-level, no user identity) | ✅ but no user identity — Work IQ rejects it |

When you add Work IQ from the portal, the default is often **`OAuth2`**, which only works interactively (hence "fine in the playground"). For the agentic A365 path you must use **`UserEntraToken`**.

> `CustomKeys` is the *correct* choice for tools that aren't scoped to a user — e.g. **Web IQ** (web grounding, `https://api.microsoft.ai/v3/mcp`) authenticates with a static `x-apikey` and needs no identity. The rule of thumb: user-data tools (Work IQ, Fabric IQ) → `UserEntraToken`; public/service tools (Web IQ) → `CustomKeys`.

**Fix — recreate the connection as `UserEntraToken`.** The portal form is schema-driven and won't create a credential-less passthrough connection, so PUT it directly to ARM:

```bash
# Get an ARM token: az account get-access-token --resource https://management.azure.com
az rest --method PUT \
  --url "https://management.azure.com/subscriptions/<SUB_ID>/resourceGroups/<RG>/providers/Microsoft.CognitiveServices/accounts/<ACCOUNT>/projects/<PROJECT>/connections/WorkIQ?api-version=2025-06-01" \
  --body '{
    "properties": {
      "authType": "UserEntraToken",
      "category": "RemoteTool",
      "target": "https://workiq.svc.cloud.microsoft/mcp",
      "audience": "fdcc1f02-fc51-4226-8753-f668596af7f7",
      "group": "GenericProtocol",
      "isSharedToAll": false,
      "metadata": { "type": "custom_MCP" }
    }
  }'
```

Key fields:
- **`target`** — the Work IQ MCP endpoint (`https://workiq.svc.cloud.microsoft/mcp`).
- **`audience`** — the resource appId Foundry mints the OBO token for. For unified Work IQ this is `fdcc1f02-fc51-4226-8753-f668596af7f7` (`api://workiq.svc.cloud.microsoft`, scope `WorkIQAgent.Ask`). `UserEntraToken` stores **no** credential — only the `audience` matters.

Verify with `GET …/connections/WorkIQ?api-version=2025-06-01` and confirm `authType: UserEntraToken`.

> **Note — no app-only auth to Work IQ.** You cannot authenticate Work IQ with an app-only (client-credentials / Managed Identity) token — agentic apps are blocked with `AADSTS82001`. The principal Work IQ authenticates is always the **user** (delegated/OBO). The blueprint, agent-instance, and Work IQ resource app registrations are plumbing; the caller is the teammate user.

> **Note — `ask` is read-only.** The unified Work IQ MCP exposes a single `ask` tool (read-only retrieval over Teams/Outlook/files). **Sending** mail or Teams messages uses separate *action* tools with a different `audience` (`ea9ffc3e-8a23-4a7d-836d-234d7c7565c1`, the Agent 365 resource) — e.g. Mail → `https://agent365.svc.cloud.microsoft/agents/servers/mcp_MailTools`. If the agent can read but not send, you're missing those action-tool connections.

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

---

## Fabric Data Agent Errors

### Error: `tool_user_error` when Fabric Data Agent is queried

This means Foundry couldn't authenticate the user to Fabric. Check:
1. Blueprint inheritable permissions include **Microsoft Cognitive Services** (`user_impersonation`) and **Azure Machine Learning Services** (`user_impersonation`)
2. Teammate has **Azure AI Developer** RBAC role on the AI Services resource AND the project
3. Teammate has Viewer/Member access on the Fabric workspace and its data sources
4. Fabric data agent and Foundry project are in the same tenant
5. OAuth2 grants were configured for both Cognitive Services and Azure ML Services

### Prerequisites for Fabric Data Agent

- Foundry agent must have a **Fabric Data Agent** tool connection configured in Microsoft Foundry portal
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

## Deployment Errors

### Deploy timeout (504) or slow deploys

Normal on first deploy — Oryx builds Python dependencies (3-5 min). Retry the deploy command or check status at `https://<webAppName>.scm.azurewebsites.net/api/deployments/latest`.

**Critical:** Never use `az webapp deploy --clean true` — this wipes the Oryx build cache including pip packages, causing the app to crash with `No module named 'dotenv'`. If this happens, redeploy with `az webapp up` to trigger a full Oryx rebuild.

### Messages not delivered to the agent (agent is silent)

1. Check app is running: `curl https://<webAppName>.azurewebsites.net/api/messages` should return 200
2. Check messaging endpoint is registered: look in `a365.generated.config.json` for `messagingEndpoint`
3. Verify the SCOPES app setting is `https://graph.microsoft.com/.default` — **never change this** or message delivery breaks entirely
4. Check app logs for startup errors: `az webapp log tail --name <webAppName> --resource-group <rg>`
5. If logs show `⚠️ No auth env vars; running anonymous` — the `CONNECTIONS__SERVICE_CONNECTION__SETTINGS__*` env vars are missing or empty. Re-run `a365 setup all` or check `.env`.

### WAM authentication fails during a365 CLI

The CLI falls back to device code flow. Tell user to open https://login.microsoft.com/device and enter the code displayed. If it times out, the CLI will ask for the client app ID directly.

### App Service VM quota limitations

**Error:** `SubscriptionIsOverQuotaForSku — Operation cannot be completed without additional quota`

**Root cause:** Some subscriptions have limited App Service VM quota in certain regions.

**Fix:** Use Azure Container Apps (Consumption plan) instead — no VM quota required. Or request a quota increase for your subscription.

---

## Dashboard-Specific Errors

### `httpx` incompatibility on App Service / Container Apps

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

### API key auth incompatible with OBO tools

**Error:** `Tools configured with OBO auth are not supported with API key authentication`

**Root cause:** The Foundry agent's MCP tools (WorkIQ, Fabric IQ) require identity passthrough (OBO). API keys are app-level and have no user identity.

**Fix:** Always use bearer tokens (user token or managed identity token), never API keys. Removed `api-key` header logic from `agent_runner.py`.

### Managed Identity cannot do OBO

**Error:** `ARA OBO token request failed with status BadRequest`

**Root cause:** Managed Identity is an app-only token. Foundry can't exchange it for OBO tokens to call MCP tools that require user delegation (WorkIQ mail, Fabric data).

**Fix:** The frontend MSAL login provides a user-delegated token which is passed through to the backend via WebSocket. The backend uses this user token for Foundry API calls instead of the Managed Identity. Managed Identity is only used for startup validation (agent discovery/ping) where OBO is not needed.

### Container App managed identity not enabled

**Error:** `ChainedTokenCredential failed to retrieve a token from the included credentials`

**Root cause:** System-assigned managed identity was not enabled on the Container App.

**Fix:**
```bash
az containerapp identity assign --name <app-name> --resource-group <rg> --system-assigned
az role assignment create --assignee <principal-id> --role "Cognitive Services User" --scope <foundry-resource-id>
```

### MSAL redirect URI mismatch

**Error:** `AADSTS50011: The redirect URI specified in the request does not match` or `AADSTS9002326: Cross-origin token redemption is permitted only for the 'Single-Page Application' client-type`

**Root cause:** The redirect URI must be registered under the **SPA** platform (not Web) in the app registration.

**Fix:** Add redirect URIs via Graph API:
```bash
az rest --method PATCH --url "https://graph.microsoft.com/v1.0/applications/<object-id>" \
  --body '{"spa":{"redirectUris":["http://localhost:5173","https://your-app-url"]}}' \
  --headers "Content-Type=application/json"
```

---

## Implementation Notes

### MCP Tool Approval

Foundry's Responses API returns `mcp_approval_request` items when tools (Foundry IQ, Fabric Data Agent) need user consent. The agent must:
1. Detect `mcp_approval_request` items in the response output
2. Send back `mcp_approval_response` with `"approve": True` for each
3. Re-call the API with the approval responses appended to the input
4. Repeat until a final assistant message is returned

Without this, the agent returns "I processed your request but couldn't generate a response."

**Gotcha — don't re-submit non-replayable output items.** When continuing after an approval, only re-send output items that are valid as Responses API *input*. Tool-specific output items (e.g. a **Fabric Data Agent** call item) are **not** valid input and cause:

```
400 invalid_value — Invalid value: 'fab…_call' … param: input[N].
Supported values are: … 'mcp_approval_request', 'mcp_approval_response',
'mcp_call', 'mcp_list_tools', 'message', 'reasoning', … 'web_search_call'.
```

This bites when Fabric IQ runs alongside another tool (e.g. Foundry IQ): the Fabric call item lands in `output`, gets echoed back as `input`, and the next call is rejected *before* the real tool runs. Filter the re-submitted items to the allowed input-type allow-list (see `_ALLOWED_INPUT_ITEM_TYPES` in `agent/agent.py` and `dashboard/backend/agent_runner.py`); keep only messages, reasoning, approval responses, etc.

### Token Scope: `ai.azure.com` NOT `cognitiveservices.azure.com`

The Foundry agent endpoint (`services.ai.azure.com`) requires tokens with audience `https://ai.azure.com`. Tokens scoped to `cognitiveservices.azure.com` will get 403 Forbidden. The resource app ID for `ai.azure.com` is `18a66f5f-dbdf-4c17-9dd7-1634712a9cbe` (Azure Machine Learning Services).

---

## Debugging Tips

- **Enable app logging**: `az webapp log config --name <webAppName> --resource-group <rg> --application-logging filesystem --level information --docker-container-logging filesystem`
- **Tail live logs**: `az webapp log tail --name <webAppName> --resource-group <rg>`
- **Check token claims**: The agent logs `🔍 TOKEN CLAIMS:` with the OBO token details (oid, upn, aud, scp, idtyp). Look for `idtyp=user` to confirm it's a delegated token, not an app token.
- **Check MCP tool output**: The agent logs `🔧 MCP item:` with the full Foundry response output, including any tool errors from Work IQ or Fabric Data Agent.
- **List RBAC assignments**: `az role assignment list --scope <resource-id> --query "[].{principal:principalId,role:roleDefinitionName}" -o table`
- **List OAuth2 grants**: `az rest --method GET --url "https://graph.microsoft.com/v1.0/servicePrincipals/<sp-id>/oauth2PermissionGrants" --query "value[].{scope:scope}" -o table`
