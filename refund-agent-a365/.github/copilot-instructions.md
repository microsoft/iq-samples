# Copilot Instructions — Refund Agent (A365 + 3IQs)

## Scope

This sample is part of the `microsoft/iq-samples` repo. **Only read and modify files within this folder** (`refund-agent-a365/`). Do not touch other samples or root-level governance files (LICENSE, CODE_OF_CONDUCT.md, SECURITY.md, SUPPORT.md).

## Project Identity

This is a **Python agent** that wraps an **Microsoft Foundry agent** (with Fabric Data Agent + Work IQ tools) and publishes it to **Microsoft Teams / M365 Copilot** via the **Microsoft Agent 365 (A365)** SDK. The Foundry agent handles all intelligence; this project is the A365 hosting wrapper that adds Teams messaging, notifications, observability, and user identity passthrough (OBO).

## Tech Stack

| Component | Technology |
|-----------|-----------|
| **Agent host** | Python 3.11+, A365 SDK (`microsoft-agents-*` packages), aiohttp |
| **Dashboard backend** | Python, FastAPI |
| **Dashboard frontend** | React, TypeScript, Vite |
| **Deployment** | Azure App Service (Linux), Microsoft Foundry |

## Key Files

| File | Purpose |
|------|---------|
| `agent/agent.py` | Core agent logic — connects to Foundry agent via OBO token, streams responses |
| `agent/agent_interface.py` | A365 activity handler — receives Teams messages, routes to agent.py |
| `agent/host_agent_server.py` | aiohttp server entry point for A365 |
| `agent/start_with_generic_host.py` | Generic host launcher (used as Azure startup command) |
| `agent/token_cache.py` | OBO token acquisition and caching |
| `agent/.env.template` | Environment variable template — copy to `.env` and fill in values |
| `agent/a365.config.example.json` | A365 CLI config template |
| `agent-instructions.md` | **Foundry agent system prompt** (paste into Microsoft Foundry UI — this is NOT code) |
| `dashboard/` | Full-stack demo dashboard (FastAPI backend + React frontend) |
| `azure.yaml` | Azure Developer CLI deployment descriptor |
| `scripts/setup_foundry_agent.py` | Programmatic Foundry agent creation with IQ tools (uses azure-ai-agents SDK) |
| `scripts/requirements.txt` | Dependencies for the setup script (separate from agent deps) |

## Setup Script

`scripts/setup_foundry_agent.py` programmatically creates the Foundry agent with SDK-supported IQ tools (FileSearchTool for Foundry IQ, FabricTool for Fabric IQ). Work IQ has no SDK class and must be configured in the portal. The script depends on `scripts/requirements.txt` (separate from the agent's requirements). Auth uses `az login` (AzureCliCredential), not the API key.

## What NOT to Touch

- **`agent-instructions.md`** contains the Foundry agent's system prompt. It is documentation for the AI Foundry portal, not executable code. Do not refactor or "fix" it.
- **`.env` files** are gitignored. Never create or commit them. Use `.env.template` for documenting required variables.
- **Do not add or remove A365 SDK packages** without understanding the A365 hosting contract.

## Dependencies

```bash
# Agent
cd agent && pip install -r requirements.txt

# Dashboard backend
cd dashboard/backend && pip install -r requirements.txt

# Dashboard frontend
cd dashboard/frontend && npm install
```

## Troubleshooting & Known Errors

**IMPORTANT:** When encountering any errors during setup, deployment, or runtime, **always check [`TROUBLESHOOTING.md`](../TROUBLESHOOTING.md) first** before debugging blind. It contains solutions for all known issues including:
- RBAC/permission errors (401, 403)
- OBO token failures (ARA OBO, BadRequest)
- Foundry agent errors (404, model mismatch)
- Work IQ issues (email search, tenant denied, 502 on email channel)
- Fabric Data Agent failures (tool_user_error, prerequisites)
- Deployment issues (timeout, quota, WAM auth)
- Dashboard errors (httpx, MSAL redirect, managed identity)

## Security

- All secrets go in `.env` (gitignored) — never hardcode API keys, connection strings, or tokens
- OBO token flow is security-critical — changes to `token_cache.py` or auth logic need careful review
- The A365 config contains tenant and app IDs — use the example file, never commit real values
