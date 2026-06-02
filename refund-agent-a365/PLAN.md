# PLAN.md — Refund Agent for A365

> **Origin:** Amanda Silver's refund agent vision (BRK240 session script). This plan treats the repository as a from-scratch build, documenting every layer of the system so that a developer (or an AI agent) can reconstruct the entire application end-to-end.

> **Repository layout (microsoft/iq-samples):** This plan is the from-scratch vision. In the committed sample the code lives under three top-level folders — `agent/` (the A365 hosting wrapper), `dashboard/` (FastAPI backend + React frontend), and `scripts/` (Foundry agent setup) — with `agent-instructions.md`, `azure.yaml`, `README.md`, and `TROUBLESHOOTING.md` at the root. The Fabric ontology / semantic model and the Foundry IQ, Work IQ, Fabric IQ, and **Web IQ** tool connections are configured in the Microsoft Foundry and Microsoft Fabric portals (wired via `scripts/setup_foundry_agent.py`), not committed as local `infra/`, `ontology/`, or `manifest/` folders. The file paths in the layer sections below describe the conceptual design; see the [File Map](#13-file-map) for the actual tree.

---

## Table of Contents

1. [Vision & Principles](#1-vision--principles)
2. [Architecture Overview](#2-architecture-overview)
3. [Layer 1 — Enterprise Context Ingestion](#3-layer-1--enterprise-context-ingestion)
4. [Layer 2 — Spec-Driven Agent Scaffold](#4-layer-2--spec-driven-agent-scaffold)
5. [Layer 3 — Enterprise Knowledge Grounding (Foundry IQ)](#5-layer-3--enterprise-knowledge-grounding-foundry-iq)
6. [Layer 4 — Business Ontology & Data Reasoning (Fabric IQ)](#6-layer-4--business-ontology--data-reasoning-fabric-iq)
7. [Layer 5 — Work System Integration (Work IQ)](#7-layer-5--work-system-integration-work-iq)
8. [Layer 6 — Embodied Agent with Identity & Governance](#8-layer-6--embodied-agent-with-identity--governance)
9. [Frontend — Dashboard & Chat UI](#9-frontend--dashboard--chat-ui)
10. [Infrastructure & Deployment](#10-infrastructure--deployment)
11. [Data & Ontology Bootstrap](#11-data--ontology-bootstrap)
12. [Testing & Validation](#12-testing--validation)
13. [File Map](#13-file-map)
14. [Open Issues & Risks](#14-open-issues--risks)

---

## 1. Vision & Principles

Amanda Silver's core thesis: **don't build a refund bot with prompts — build a system that understands the company the way an employee does.**

The refund agent should:

- **Start from real work context** — an email, a ticket, an escalation — not a hand-written prompt.
- **Auto-generate its own spec** from that context, then execute against it.
- **Ground itself in enterprise knowledge** — policies, docs, runbooks.
- **Reason over structured business data** — orders, shipments, payments, delivery networks.
- **Connect to work systems** — email, Teams, calendars, chat history.
- **Run as an embodied agent** inside Teams/A365 with governed identity, permissions, and trust controls.

### Design Principles

| Principle | Implication |
|-----------|------------|
| Context-first | Agent reads real artifacts (email, ticket) before acting |
| Spec-driven | Plan → action, not ad-hoc prompting |
| Enterprise-grounded | Every answer traces to a policy, doc, or data record |
| Ontology-aware | Agent reasons over entity graphs, not just text |
| Embodied | Agent lives inside Teams as a first-class participant |
| Governed | Two layers of identity control; audit trail; permission scoping |

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Teams / A365 Host                     │
│  (agent/host_agent_server.py + agent/agent.py)          │
│  - Receives messages & notifications from Teams         │
│  - Maintains per-user conversation state                │
│  - Exchanges user token for OBO token                   │
│  - Auto-approves MCP approval requests                  │
└──────────────────────┬──────────────────────────────────┘
                       │ OpenAI Responses API
                       ▼
┌─────────────────────────────────────────────────────────┐
│              Microsoft Foundry Agent                      │
│  - System prompt from agent-instructions.md             │
│  - Connected to:                                        │
│    ├─ Foundry IQ (enterprise knowledge store)           │
│    ├─ Fabric IQ  (ontology + structured data)           │
│    └─ Work IQ    (M365 Graph: mail, Teams, calendar)    │
│  - MCP tool servers: Mail, Teams                        │
└──────────────────────┬──────────────────────────────────┘
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
   ┌───────────┐ ┌──────────┐ ┌──────────┐
   │ Foundry IQ│ │ Fabric IQ│ │ Work IQ  │
   │ (docs,    │ │ (graph,  │ │ (mail,   │
   │  policies)│ │  tables, │ │  Teams,  │
   │           │ │  model)  │ │  calendar│
   └───────────┘ └──────────┘ └──────────┘

┌─────────────────────────────────────────────────────────┐
│              FastAPI Backend (dashboard/backend/)         │
│  - WebSocket /ws endpoint for chat                      │
│  - /voice endpoint for Voice Live API relay             │
│  - Calls Foundry Responses API directly                 │
│  - Parses agent responses → tables, entities, graphs    │
│  - Detects "refund recommended" signals                 │
└──────────────────────┬──────────────────────────────────┘
                       │ WebSocket
                       ▼
┌─────────────────────────────────────────────────────────┐
│              React Frontend (dashboard/frontend/)         │
│  - MSAL Entra authentication                            │
│  - Chat UI with typing indicators                       │
│  - Shipment dashboard (tables, entity cards, routes)    │
│  - Voice toggle (Web Audio + Voice Live)                │
│  - "Grant Refund" action button                         │
└─────────────────────────────────────────────────────────┘
```

### Technology Stack

| Layer | Technology |
|-------|-----------|
| Host runtime | Python 3.11+, aiohttp, Microsoft Agents SDK |
| AI orchestration | Microsoft Foundry, OpenAI Responses API |
| Backend API | Python, FastAPI, uvicorn, WebSocket |
| Frontend | React 19, TypeScript, Vite, MSAL.js |
| Auth | Entra ID, MSAL, OBO token exchange |
| Data platform | Microsoft Fabric (Lakehouse, Direct Lake, Graph) |
| Infrastructure | Azure Bicep, App Service (Linux) |
| Deployment | Docker, azd (Azure Developer CLI) |

---

## 3. Layer 1 — Enterprise Context Ingestion

**Goal:** The agent starts from real work artifacts — not prompts. A customer escalation email, a support ticket, or a Teams thread becomes the input that drives everything.

### What to Build

| Component | File(s) | Description |
|-----------|---------|-------------|
| Work IQ email reader | `agent.py`, `agent-instructions.md` | Agent reads escalation emails from the user's mailbox via Work IQ / Microsoft Graph |
| Context extraction | `agent-instructions.md` | System prompt instructs agent to extract: customer name, order ID, issue description, sentiment, urgency |
| Spec auto-generation | `agent.py` | Agent produces a structured "refund investigation spec" from the extracted context |

### Implementation Steps

1. **Configure MCP tool servers** in `ToolingManifest.json`:
   - Mail server: read/search emails from the user's mailbox
   - Teams server: read relevant channel/chat messages
2. **Write the system prompt** (`agent-instructions.md`) to instruct the agent:
   - On first contact, ask "Would you like me to check your recent escalations?"
   - Search for emails from known escalation addresses or with refund-related subjects
   - Extract structured fields: `customer_name`, `order_id`, `issue_summary`, `urgency_level`
   - Produce a one-paragraph "investigation plan" before taking action
3. **Implement context caching** in `agent.py`:
   - Store extracted context per conversation so subsequent turns don't re-read the email
   - Key the cache by `(user_id, conversation_id)`
4. **Handle the "no email found" path**:
   - Agent falls back to asking the user to describe the issue manually
   - Still produces the same structured spec format

### Acceptance Criteria

- [ ] Agent can read an email from the user's inbox and extract customer + order details
- [ ] Agent produces a structured investigation spec before taking action
- [ ] If no email found, agent gracefully falls back to manual input
- [ ] Extracted context persists across conversation turns

---

## 4. Layer 2 — Spec-Driven Agent Scaffold

**Goal:** The core agent framework — plan then act. The agent always produces an explicit plan artifact before executing refund logic.

### What to Build

| Component | File(s) | Description |
|-----------|---------|-------------|
| Agent host wrapper | `host_agent_server.py` | aiohttp server that wraps the agent for Teams/A365 |
| Agent interface | `agent_interface.py` | Abstract base class: `initialize()`, `process_user_message()`, `cleanup()` |
| Refund agent core | `agent.py` | Concrete agent: conversation state, Foundry API calls, OBO auth, MCP auto-approval |
| Entry point | `start_with_generic_host.py` | Bootstraps `RefundAgent` inside the generic host |
| Agent instructions | `agent-instructions.md` | Full system prompt with refund investigation workflow |
| MCP manifest | `ToolingManifest.json` | Tool server declarations (Mail, Teams) |
| Config | `a365.config.json` | Tenant, subscription, app registration, permissions |

### Implementation Steps

1. **Define the agent interface** (`agent_interface.py`):
   ```python
   class AgentInterface(ABC):
       async def initialize(self, context) -> None: ...
       async def process_user_message(self, turn_context) -> str: ...
       async def cleanup(self) -> None: ...
   ```

2. **Build the host server** (`host_agent_server.py`):
   - aiohttp web application
   - POST `/api/messages` — receives Teams activity payloads
   - POST `/api/notifications` — receives proactive notifications
   - GET `/health` — health check
   - Middleware: authentication validation, typing indicator management
   - Observability: Azure Monitor + OpenTelemetry tracing

3. **Implement the RefundAgent** (`agent.py`):
   - `initialize()`: create Foundry client, load agent instructions, set up OBO credential
   - `process_user_message()`:
     1. Get or create conversation history for user
     2. Append user message
     3. Call Foundry Responses API with full history + tools
     4. Handle tool calls (MCP approval auto-grant, function calls)
     5. Parse response and return text
   - `cleanup()`: flush state, close connections
   - **OBO token exchange**: exchange the user's Teams token for an AI Foundry-scoped token
   - **MCP auto-approval**: detect `mcp_approval_request` events and auto-approve them

4. **Write the system prompt** (`agent-instructions.md`):
   - Role: "You are a refund investigation agent for [Company]"
   - Workflow:
     1. Read escalation context (email/manual)
     2. Look up order + shipment data
     3. Check refund policy
     4. Analyze delivery network for anomalies
     5. Recommend approve/deny with justification
     6. If approved, draft refund email to customer
   - Constraints: always cite policy, never auto-approve above threshold, cc supervisor for high-value refunds

5. **Configure MCP tools** (`ToolingManifest.json`):
   ```json
   {
     "mcpServers": [
       { "name": "Mail", "endpoint": "..." },
       { "name": "Teams", "endpoint": "..." }
     ]
   }
   ```

6. **Set up config templates** (`a365.config.example.json`):
   - Document every field: tenant ID, client ID, Foundry endpoint, agent name, permissions
   - Provide `.env.template` with all required environment variables

### Acceptance Criteria

- [ ] Host server starts, passes health check, accepts Teams activities
- [ ] Agent loads instructions and connects to Foundry
- [ ] Conversation state persists across turns within a session
- [ ] OBO token exchange works for authenticated users
- [ ] MCP approval requests are auto-approved
- [ ] Agent follows plan→action workflow (never acts without stating intent)

---

## 5. Layer 3 — Enterprise Knowledge Grounding (Foundry IQ)

**Goal:** The agent's answers are grounded in enterprise documents — refund policies, SLAs, customer service runbooks, escalation procedures. It never hallucinates policy.

### What to Build

| Component | Location | Description |
|-----------|----------|-------------|
| Foundry IQ knowledge store | Microsoft Foundry (cloud) | Index of enterprise documents: refund policies, SLAs, procedures |
| Agent grounding config | Foundry agent settings | Connect agent to knowledge store for RAG |
| Policy citation format | `agent-instructions.md` | Instruct agent to always cite document + section |

### Implementation Steps

1. **Prepare knowledge documents**:
   - Refund policy document (thresholds, time limits, approval chains)
   - SLA definitions (delivery windows, compensation tiers)
   - Escalation procedures (when to involve supervisor, legal)
   - Customer communication templates

2. **Create Foundry IQ knowledge store**:
   - Upload documents to Microsoft Foundry
   - Configure chunking strategy (prefer semantic chunking for policy docs)
   - Enable the knowledge store as a grounding source on the agent

3. **Update system prompt** to enforce grounding:
   - "When referencing policy, always cite the document name and section number"
   - "If you cannot find a relevant policy, say so explicitly — never invent policy"
   - "For refund amounts above $500, quote the exact policy threshold"

4. **Add governance metadata**:
   - Tag each document with classification level
   - Configure Foundry to respect document-level permissions
   - Log which documents were cited in each response

### Acceptance Criteria

- [ ] Agent retrieves relevant policy sections when evaluating a refund
- [ ] Every policy claim includes a citation (document + section)
- [ ] Agent explicitly states when no matching policy is found
- [ ] Document access respects permission boundaries

---

## 6. Layer 4 — Business Ontology & Data Reasoning (Fabric IQ)

**Goal:** The agent reasons over structured business data — orders, shipments, deliveries, payments, customer history — through a semantic ontology, not raw SQL.

### What to Build

| Component | File(s) | Description |
|-----------|---------|-------------|
| Ontology graph definition | `ontology/graph_definition/*.json` | Node/edge types: hubs, drivers, customers, packages, handoffs, payments |
| Sample data generators | `scripts/generate_sample_data.py`, `scripts/generate_payment_data.py` | Create canonical CSV data for the delivery network |
| Lakehouse uploader | `scripts/upload_lakehouse_data.py` | Push CSVs to Fabric OneLake |
| Semantic model | `ontology/semantic_model/*.tmdl`, `model.bim` | Direct Lake semantic model for BI + agent queries |
| Fabric data agent | Fabric portal (cloud) | Agent that queries the ontology on behalf of the refund agent |

### Ontology Entities

```
Customer ──places──▶ Order ──contains──▶ Package
                                            │
                                        picked_up_by
                                            │
                                            ▼
                                         Driver
                                            │
                                      handed_off_at
                                            │
                                            ▼
                        Hub ──connected_to──▶ Hub
                                            │
                                        delivered_to
                                            │
                                            ▼
                                        Customer

Order ──has──▶ Payment (amount, method, status, refund_eligible)
```

### Implementation Steps

1. **Define the graph schema** (`ontology/graph_definition/`):
   - `nodes.json`: Customer, Order, Package, Driver, Hub, Payment
   - `edges.json`: places, contains, picked_up_by, handed_off_at, connected_to, delivered_to, has_payment
   - Each node/edge type includes: properties, data types, source Delta table

2. **Generate sample data** (`scripts/`):
   - `generate_sample_data.py`:
     - 50 customers, 200 orders, 300 packages
     - 10 hubs with realistic connection topology
     - 20 drivers with route assignments
     - Handoff events with timestamps and status
   - `generate_payment_data.py`:
     - Payment records linked to orders
     - Mix of statuses: completed, pending, refunded, disputed
     - Refund eligibility flags based on delivery status

3. **Upload to Fabric Lakehouse** (`scripts/upload_lakehouse_data.py`):
   - Connect to Fabric REST API
   - Create/update Delta tables in target Lakehouse
   - Handle auth via Azure credential chain
   - Fallback: print manual upload instructions if API unavailable

4. **Build semantic model** (`ontology/semantic_model/`):
   - Direct Lake model pointing at Lakehouse Delta tables
   - Relationships matching the ontology graph
   - Measures: total_order_value, refund_rate, avg_delivery_time, late_delivery_pct
   - NOTE: Direct Lake creation via REST API is currently portal-dependent (see open issues)

5. **Create Fabric data agent** (cloud config):
   - Point at the semantic model
   - Enable natural language → query translation
   - Connect to the Foundry agent as a tool/sub-agent

6. **Wire into the refund agent** (`agent-instructions.md`):
   - "To look up order details, query the Fabric data agent"
   - "To check delivery status, trace the package through the hub network"
   - "To verify payment status, query the payment records"

### Acceptance Criteria

- [ ] Ontology graph definition covers all entity types and relationships
- [ ] Sample data is realistic and internally consistent
- [ ] Data uploads to Fabric Lakehouse successfully
- [ ] Semantic model exposes meaningful measures
- [ ] Agent can answer: "What is the delivery status of order X?"
- [ ] Agent can answer: "Show me the shipment route for package Y"
- [ ] Agent can answer: "Is this customer eligible for a refund based on delivery history?"

---

## 7. Layer 5 — Work System Integration (Work IQ)

**Goal:** The agent connects to the user's work context — email, Teams, calendar — to understand the full picture around a refund request.

### What to Build

| Component | File(s) | Description |
|-----------|---------|-------------|
| MCP Mail tool | `ToolingManifest.json` | Read/search/send emails |
| MCP Teams tool | `ToolingManifest.json` | Read/post Teams messages |
| Work IQ queries | `agent-instructions.md` | Prompt patterns for extracting work context |
| Email drafting | `agent-instructions.md` | Agent drafts customer-facing refund emails |

### Implementation Steps

1. **Configure MCP tool servers**:
   - Mail: read inbox, search by sender/subject, send replies, manage drafts
   - Teams: read channel messages, post updates, send direct messages

2. **Define Work IQ query patterns** in system prompt:
   - "Search for emails from [customer] or about order [ID]"
   - "Check if there are prior refund requests from this customer"
   - "Look for internal discussion threads about this escalation"
   - "Find the original order confirmation email"

3. **Implement email drafting workflow**:
   - Agent composes refund approval/denial email
   - Includes: decision, justification, policy citation, next steps
   - Agent presents draft to user for review before sending
   - CC rules: supervisor for high-value, legal for disputed

4. **Add Teams notification capability**:
   - Post refund decisions to a designated channel
   - Tag relevant team members
   - Include summary card with order details + decision

### Acceptance Criteria

- [ ] Agent reads relevant emails from user's mailbox
- [ ] Agent finds prior refund history for the same customer
- [ ] Agent drafts refund response emails with proper formatting
- [ ] Agent never sends email without user approval
- [ ] Agent can post decision summaries to Teams channels

---

## 8. Layer 6 — Embodied Agent with Identity & Governance

**Goal:** The agent runs as a first-class participant in Teams with governed identity, scoped permissions, and audit trails.

### What to Build

| Component | File(s) | Description |
|-----------|---------|-------------|
| Teams manifest | `manifest/manifest.json` | App registration for Teams |
| Agentic user template | `manifest/agenticUserTemplateManifest.json` | Agent identity in A365 |
| A365 config | `a365.config.json` | Tenant, permissions, identity settings |
| Auth layer | `local_authentication_options.py`, `token_cache.py` | Token management and auth config |
| Two-layer identity | `agent.py` + Foundry config | App identity + delegated user identity |

### Implementation Steps

1. **Create Teams app manifest** (`manifest/manifest.json`):
   - App name, description, icons
   - Bot registration with messaging endpoint
   - Permissions: Mail.Read, Mail.Send, Chat.Read, ChannelMessage.Send
   - Activity protocol for A365 host

2. **Configure agentic user template** (`manifest/agenticUserTemplateManifest.json`):
   - Define the agent's identity profile
   - Set capability boundaries
   - Configure auto-approval policies (which MCP actions can be auto-approved)

3. **Implement two-layer identity control** (`agent.py`):
   - **Layer 1 — App identity**: the agent's own service principal
     - Used for: accessing Foundry, reading knowledge stores, querying Fabric
     - Scoped to: AI services, data platforms
   - **Layer 2 — Delegated user identity**: OBO token from the human user
     - Used for: reading the user's email, posting as the user, accessing user-scoped data
     - Scoped to: Mail, Teams, user-consented resources
   - Token exchange flow:
     1. User authenticates to Teams
     2. Teams passes user token to agent host
     3. Agent exchanges for OBO token scoped to Foundry
     4. Foundry uses OBO for downstream M365 calls

4. **Add audit logging**:
   - Log every refund decision with: timestamp, user, order, amount, decision, policy cited
   - Log every email sent with: recipient, subject, content hash
   - Log every MCP tool invocation with: tool name, parameters, result summary
   - Ship logs to Azure Monitor / App Insights

5. **Configure permission boundaries**:
   - Agent cannot approve refunds above $X without supervisor confirmation
   - Agent cannot send emails to external recipients
   - Agent cannot access mailboxes other than the authenticated user's
   - All boundaries enforced at both prompt level and Entra permission level

### Acceptance Criteria

- [ ] Agent appears as a named bot in Teams
- [ ] Agent authenticates with both app and delegated identity
- [ ] OBO token exchange works end-to-end
- [ ] All refund decisions are audit-logged
- [ ] Permission boundaries are enforced (prompt + Entra)
- [ ] Agent cannot exceed its scoped permissions

---

## 9. Frontend — Dashboard & Chat UI

**Goal:** A web-based dashboard that provides chat, voice, and visual shipment tracking alongside the Teams experience.

### What to Build

| Component | File(s) | Description |
|-----------|---------|-------------|
| App shell | `dashboard/frontend/src/App.tsx` | Main layout: chat + dashboard + voice |
| Auth | `dashboard/frontend/src/lib/auth.ts` | MSAL Entra authentication |
| Chat UI | `dashboard/frontend/src/hooks/useWebSocket.ts`, `dashboard/frontend/src/lib/websocket.ts` | WebSocket chat with backend |
| Voice UI | `dashboard/frontend/src/hooks/useVoice.ts`, `dashboard/frontend/src/components/VoiceToggle.tsx` | Voice Live API relay |
| Shipment dashboard | `dashboard/frontend/src/components/ShipmentDashboard.tsx` | Tables, entity cards, package route visualization |
| Typing indicator | `dashboard/frontend/src/components/TypingIndicator.tsx` | Shows agent thinking state |
| Types | `dashboard/frontend/src/types/scenario.ts` | TypeScript interfaces for domain entities |

### Implementation Steps

1. **Set up React + Vite project** (`dashboard/frontend/`):
   - React 19, TypeScript, Vite
   - MSAL.js for Entra auth
   - CSS modules or Tailwind for styling

2. **Implement MSAL authentication** (`dashboard/frontend/src/lib/auth.ts`):
   - Configure MSAL with tenant ID, client ID
   - Request scopes: `https://ai.azure.com/.default`
   - Handle login/logout, token refresh
   - Pass token to backend via WebSocket auth message

3. **Build WebSocket chat** (`dashboard/frontend/src/hooks/useWebSocket.ts`):
   - Connect to backend `/ws` on mount
   - Send `auth` message with MSAL token first
   - Handle message types: `text`, `thinking`, `tool_calling`, `shipment_data`, `error`
   - Auto-reconnect on disconnect
   - Message history in React state

4. **Build voice interface** (`dashboard/frontend/src/hooks/useVoice.ts`):
   - Connect to backend `/voice`
   - Capture microphone audio (PCM16)
   - Play returned audio
   - Handle transcript events, tool events, status events
   - Mute/unmute toggle

5. **Build shipment dashboard** (`dashboard/frontend/src/components/ShipmentDashboard.tsx`):
   - Render parsed shipment data from agent responses
   - Tables: order details, package tracking, delivery history
   - Entity cards: customer info, driver info, hub info
   - Package route visualization (hub-to-hub path)
   - **"Grant Refund" button**: trigger refund workflow (currently UI-only — needs backend wiring)

6. **Wire the Grant Refund button**:
   - Send refund approval message to backend
   - Backend forwards to agent as a user action
   - Agent executes refund workflow (policy check → email draft → confirmation)
   - UI shows progress and final status

### Acceptance Criteria

- [ ] User can authenticate via MSAL and see the dashboard
- [ ] Chat works over WebSocket with typing indicators
- [ ] Voice input/output works via Voice Live relay
- [ ] Shipment data renders as tables and route visualizations
- [ ] Grant Refund button triggers the full refund workflow
- [ ] UI handles disconnects and errors gracefully

---

## 10. Infrastructure & Deployment

**Goal:** One-command deployment to Azure via `azd up`.

### What to Build

| Component | File(s) | Description |
|-----------|---------|-------------|
| Bicep templates | `infra/main.bicep` | App Service Plan + Web App |
| ARM compiled | `infra/main.json` | Compiled ARM template |
| Azure Developer CLI config | `azure.yaml` | Service definition for azd |
| Dockerfile | `Dockerfile` | Multi-stage: build frontend, run backend |
| Startup scripts | `run.sh`, `startup.sh` | Install deps, start uvicorn |
| Env config | `.env.template` | All required environment variables |

### Implementation Steps

1. **Define Bicep infrastructure** (`infra/main.bicep`):
   - Linux App Service Plan (B1 or higher)
   - Web App with Python 3.11+ runtime
   - App settings:
     - `AZURE_PROJECT_ENDPOINT` — Foundry project endpoint
     - `FOUNDRY_AGENT_NAME` — agent name in Foundry
     - `SCM_DO_BUILD_DURING_DEPLOYMENT=true`
     - `WEBSITES_PORT=8000`
   - System-assigned managed identity
   - CORS configuration for frontend origin

2. **Build the Dockerfile**:
   - Stage 1: `node:20` — build frontend (`npm ci && npm run build`)
   - Stage 2: `python:3.11` — install backend deps, copy frontend dist, run uvicorn
   - Expose port 8000

3. **Configure azure.yaml**:
   ```yaml
   name: shipment-dashboard
   services:
     web:
       project: .
       host: appservice
       language: python
   ```

4. **Write startup scripts**:
   - `run.sh`: install backend + frontend deps, build frontend, start uvicorn
   - `startup.sh`: production startup (deps already installed in Docker)

5. **Document all environment variables** (`.env.template`):
   ```
   AZURE_PROJECT_ENDPOINT=
   FOUNDRY_AGENT_NAME=
   AZURE_TENANT_ID=
   AZURE_CLIENT_ID=
   AZURE_CLIENT_SECRET=
   APPLICATIONINSIGHTS_CONNECTION_STRING=
   ```

### Acceptance Criteria

- [ ] `azd up` deploys the full application
- [ ] App Service starts and passes health check
- [ ] Frontend is served as static files from the backend
- [ ] Environment variables are properly configured
- [ ] Managed identity has access to required Azure resources

---

## 11. Data & Ontology Bootstrap

**Goal:** Scripts to generate, upload, and configure all data and ontology artifacts from scratch.

### Implementation Steps

1. **Generate sample data** (`scripts/generate_sample_data.py`):
   - Customers, orders, packages, drivers, hubs, hub connections, handoffs
   - Output: CSV files in `ontology/sample_data/`

2. **Generate payment data** (`scripts/generate_payment_data.py`):
   - Payment records linked to orders
   - Mix of statuses and refund eligibility
   - Output: CSV in `ontology/sample_data/`

3. **Upload to Fabric** (`scripts/upload_lakehouse_data.py`):
   - Authenticate to Fabric REST API
   - Create/update Delta tables
   - Upload CSVs
   - Fallback: manual upload instructions

4. **Define graph ontology** (`ontology/graph_definition/`):
   - Map Delta tables to graph nodes/edges
   - Define properties and types for each entity

5. **Build semantic model** (`ontology/semantic_model/`):
   - TMDL definitions for Direct Lake model
   - Relationships, hierarchies, measures
   - NOTE: model creation may require portal steps (see open issues)

### Acceptance Criteria

- [ ] `python scripts/generate_sample_data.py` produces consistent CSV files
- [ ] `python scripts/generate_payment_data.py` produces payment records
- [ ] `python scripts/upload_lakehouse_data.py` uploads to Fabric or provides manual steps
- [ ] Graph definition matches the ontology diagram
- [ ] Semantic model is queryable

---

## 12. Testing & Validation

### Test Strategy

| Level | What | How |
|-------|------|-----|
| Unit | Response parser, auth helpers | pytest |
| Integration | WebSocket chat flow, agent runner | pytest + httpx |
| E2E | Full chat conversation with mocked Foundry | Playwright (frontend) |
| Manual | Teams bot interaction | Sideload manifest in Teams |

### Key Test Scenarios

1. **Happy path refund**: email found → order looked up → policy checked → refund approved → email drafted
2. **Refund denied**: policy threshold exceeded → denial with justification
3. **No email found**: fallback to manual input → same workflow
4. **High-value refund**: above threshold → supervisor notification required
5. **Repeat customer**: prior refund history found → flagged for review
6. **Voice interaction**: same workflow via voice input/output
7. **Auth failure**: expired token → graceful re-auth prompt

---

## 13. File Map

```
refund-agent-a365/
├── PLAN.md                          # This file (the from-scratch vision)
├── README.md                        # Setup & deployment guide
├── TROUBLESHOOTING.md               # Known errors & fixes (check first)
├── agent-instructions.md            # Foundry agent system prompt (portal, not code)
├── azure.yaml                       # azd deployment descriptor (App Service)
├── .dockerignore
├── .github/
│   └── copilot-instructions.md      # Sample-specific coding-agent directions
│
├── agent/                           # A365 hosting wrapper (Python)
│   ├── agent.py                     # Core agent — Foundry wrapper, OBO, MCP auto-approve
│   ├── agent_interface.py           # A365 activity handler
│   ├── host_agent_server.py         # aiohttp host server entry point
│   ├── start_with_generic_host.py   # Generic host launcher (Azure startup command)
│   ├── token_cache.py               # OBO token acquisition & caching
│   ├── local_authentication_options.py  # Local auth config helper
│   ├── ToolingManifest.json         # MCP tool server declarations
│   ├── a365.config.example.json     # A365 CLI config template
│   ├── .env.template                # Env var template (copy to .env, gitignored)
│   ├── pyproject.toml               # Python project metadata
│   └── requirements.txt             # Agent dependencies
│
├── dashboard/                       # Full-stack demo (FastAPI + React)
│   ├── Dockerfile                   # Multi-stage build (frontend + backend)
│   ├── run.sh                       # Dev startup script
│   ├── startup.sh                   # Production startup script
│   ├── backend/
│   │   ├── main.py                  # FastAPI app setup
│   │   ├── chat.py                  # WebSocket chat endpoint
│   │   ├── voice.py                 # Voice Live API relay
│   │   ├── auth.py                  # Azure credential helpers
│   │   ├── agent_runner.py          # Foundry Responses API caller
│   │   ├── response_parser.py       # Parse agent output → structured data
│   │   └── requirements.txt         # Backend dependencies
│   └── frontend/
│       ├── src/
│       │   ├── App.tsx              # Main app shell
│       │   ├── main.tsx             # React entry point
│       │   ├── components/          # ShipmentDashboard, VoiceToggle, TypingIndicator
│       │   ├── hooks/               # useWebSocket, useVoice
│       │   ├── lib/                 # auth, websocket, audioUtils
│       │   └── types/               # scenario
│       ├── e2e/                     # Playwright specs
│       ├── package.json
│       ├── vite.config.ts
│       ├── playwright.config.ts
│       └── tsconfig.json
│
└── scripts/
    ├── setup_foundry_agent.py       # Programmatic Foundry agent creation (IQ tools)
    └── requirements.txt             # Setup-script dependencies (separate from agent)
```

---

## 14. Open Issues & Risks

| # | Issue | Impact | Mitigation |
|---|-------|--------|------------|
| 1 | Fabric graph load via REST API not yet available | Cannot automate graph creation | Use Fabric portal manually; script generates definition files for import |
| 2 | Direct Lake semantic model creation is portal-dependent | Cannot fully automate ontology setup | Document portal steps; provide TMDL files for import |
| 3 | "Grant Refund" button is UI-only | Refund workflow not end-to-end | Wire button to send refund action message through agent |
| 4 | OBO token exchange requires specific Entra app registration | Auth setup is complex | Provide step-by-step setup guide in README |
| 5 | API key auth disabled in some tenants | Agent cannot connect to Foundry | Use managed identity; document both auth paths |
| 6 | Rate limits on Foundry API | Agent may be throttled under load | Implement retry with exponential backoff (already in agent_runner.py) |
| 7 | Frontier license required for some Foundry features | Not all tenants have access | Document required licenses; provide degraded-mode fallback |
| 8 | Production resources must not be touched | Risk of accidental production impact | Separate dev/staging/prod configs; document guardrails in README |

---

## Build Order (Recommended)

The layers should be built in this order, as each depends on the previous:

1. **Layer 2 — Agent Scaffold** (host + agent framework)
2. **Layer 4 — Ontology & Data** (data foundation — can parallelize with Layer 2)
3. **Layer 1 — Context Ingestion** (needs agent framework from Layer 2)
4. **Layer 3 — Knowledge Grounding** (needs agent from Layer 2, benefits from data in Layer 4)
5. **Layer 5 — Work Integration** (needs agent + knowledge grounding)
6. **Frontend — Dashboard** (can parallelize with Layers 3-5)
7. **Infrastructure — Deployment** (can parallelize with Layers 3-5)
8. **Layer 6 — Identity & Governance** (last — wraps everything in trust controls)
9. **Testing** (continuous, but formal validation at the end)
