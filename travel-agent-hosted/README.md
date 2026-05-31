# Travel Agent — Foundry IQ + Work IQ (hosted)

A **hosted Microsoft Foundry agent**, built with the **Microsoft Agent Framework SDK**, that helps employees with corporate travel. It is grounded with two IQ tools:

- **Foundry IQ** — a knowledge base of corporate travel policies (booking approvals, preferred vendors, per diems, international requirements).
- **Work IQ Mail** — searches the employee's email for recent policy updates, budget freezes, and temporary overrides — so the agent answers with *both* the standing policy **and** what changed this quarter.

The result: ask *"What's the travel budget for New York?"* and instead of guessing, the agent cites the standing hotel policy from the knowledge base **and** flags the temporary budget freeze sitting in the employee's inbox — and points out the conflict.

> **How this differs from `refund-agent-a365`:** that sample hosts a Foundry agent on **Microsoft Agent 365 (Teams)** with **Fabric IQ + Work IQ**. This sample is a **Foundry-hosted** agent (Agent Framework SDK, Responses protocol) with **Foundry IQ + Work IQ** — a different hosting model and IQ combination, plus an evaluation suite.

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│  Microsoft Foundry — Hosted Agent (Responses protocol)    │
│                                                          │
│  agent/agent.py  ──►  FoundryChatClient + Agent          │
│        │                  (system prompt = the brains)   │
│        │                                                 │
│   agent.manifest.yaml declares the tools:                │
│     • knowledge: Foundry IQ (travel policies)            │
│     • tool:      WorkIQMail (email, OBO auth)            │
│                                                          │
│   The hosting platform injects both tools + handles OBO  │
└─────────────────────────────────────────────────────────┘
```

The agent's **intelligence** is the system prompt in `agent/agent.py`. The **tools** are declared in `agent/agent.manifest.yaml` and injected by the Foundry hosting layer — they are *not* instantiated in code. Because **Work IQ Mail requires OBO** (on-behalf-of) auth, the agent only works fully when **deployed** (hosted), not when run locally.

---

## 🚀 Fastest path: build it with GitHub Copilot CLI

This sample spans an Microsoft Foundry project, a Foundry IQ knowledge base, a Work IQ Mail connection, a hosted deployment, and an evaluation suite. Instead of clicking through every step, let **[GitHub Copilot CLI](https://docs.github.com/en/copilot/concepts/agents/about-copilot-cli)** drive it.

```bash
# 1. Install GitHub Copilot CLI (requires a GitHub Copilot subscription)
npm install -g @github/copilot

# 2. Clone and enter the sample
git clone https://github.com/microsoft/iq-samples.git
cd iq-samples/travel-agent-hosted

# 3. Launch Copilot CLI in this folder
copilot
```

Then paste this prompt:

> Read the README.md and .github/copilot-instructions.md in this folder end to end. I want to stand up this hosted Travel Agent on my own Azure tenant. Help me, step by step:
> 1. Verify prerequisites (az login, an Microsoft Foundry project, a deployed chat model, an M365 license with mail for Work IQ).
> 2. Create a Foundry IQ knowledge base from `knowledge/travel-policies.json` and name it to match the `knowledge.id` in `agent/agent.manifest.yaml`.
> 3. Configure the Work IQ Mail tool connection (OBO) in my Foundry project.
> 4. Fill in `agent/.env` from the template, then deploy the hosted agent.
> 5. Test it in the hosted agent playground, then run the evals in `evals/` against the deployed agent.
> Run the commands where you can, explain each step, and pause for values only I can provide. Never commit secrets.

---

## Setup Instructions

### Prerequisites

- **Azure CLI** logged in (`az login`)
- An **Microsoft Foundry project** ([ai.azure.com](https://ai.azure.com)) with a deployed chat model (e.g. `gpt-4.1`)
- An **Azure AI Search** service (backs the Foundry IQ knowledge base)
- A **Microsoft 365 mailbox / license** for the test user (Work IQ Mail searches real email) — a tenant enrolled in the [Frontier Preview Program](https://adoption.microsoft.com/copilot/frontier-program/)
- **Python 3.12+**

### 1. Configure environment

```bash
cd travel-agent-hosted
cp agent/.env.template agent/.env
# edit agent/.env — set FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL
```

### 2. Create the Foundry IQ knowledge base

Create a knowledge base in your Foundry project from `knowledge/travel-policies.json`, then make sure the knowledge resource **name matches** the `knowledge.id` declared in `agent/agent.manifest.yaml`:

```yaml
resources:
  - kind: knowledge
    id: travel-policies-kb      # ← must match your knowledge base name
```

### 3. Configure the Work IQ Mail tool

Configure the **Work IQ Mail** tool in your Foundry project with an OBO (user-identity passthrough) connection. The manifest references it by id:

```yaml
  - kind: tool
    id: WorkIQMail
```

> Work IQ Mail authenticates **on behalf of the signed-in user**, so it only returns results for a hosted agent invoked with a user token — it will not work in a purely local run.

### 4. Install dependencies & deploy

```bash
cd agent
pip install -r requirements.txt
```

Deploy the hosted agent using `agent/agent.yaml` + `agent/Dockerfile` (Foundry Toolkit sidebar → **Deploy to Microsoft Foundry**, or your preferred deployment path). The deploy produces a hosted agent named **`travel-agent`** (display name **`TravelAgent`**).

### 5. Test it

In the **hosted agent playground**, ask:

```
What's the travel budget for New York?
```

The agent should cite the standing hotel policy (**$250/night** from the knowledge base) **and** surface the temporary budget-freeze override from email (**$200/night**), flagging which one takes precedence.

---

## Evaluation

The `evals/` suite runs against the **deployed** agent and scores whether it produces complete, grounded answers — using both the knowledge base and email.

```bash
cd evals
cp .env.template .env          # set FOUNDRY_PROJECT_ENDPOINT + judge-model vars
pip install -r requirements.txt
pytest test_travel_agent.py
```

**Evaluators:**

| Evaluator | What it checks |
|-----------|----------------|
| `intent_resolution` | Built-in — did the agent actually address the question? |
| `policy_completeness` | Custom (deterministic) — did the answer include the correct standing-policy facts? (threshold 0.4) |
| `email_awareness` | Custom — did the answer include the email override facts? (threshold 0.6) |

`evals/evaluators.py` contains the deterministic grader and the ground-truth facts. The test cases in `evals/data.jsonl` each pair a **standing policy** with a **temporary email override**, so a fully grounded agent (knowledge + email) scores highest.

> **Keep knowledge and evals in sync.** `knowledge/travel-policies.json` and the ground truth in `evals/` are intentionally aligned (hotel cap **$250/night**, meal per diem **$75/day**, etc.). If you change a policy value in one place, update the other or the evals will break.

---

## Project Structure

```
travel-agent-hosted/
├── agent/
│   ├── agent.py                 # Agent definition + system prompt
│   ├── main.py                  # Host entry point (ResponsesHostServer)
│   ├── agent.yaml               # Hosting descriptor (kind: hosted)
│   ├── agent.manifest.yaml      # Declares model + Foundry IQ + Work IQ Mail
│   ├── Dockerfile / startup.sh  # Container build + start
│   ├── requirements.txt
│   └── .env.template
├── evals/
│   ├── test_travel_agent.py     # pytest-agent-evals suite
│   ├── evaluators.py            # Custom policy_completeness grader
│   ├── conftest.py              # Hosted-agent endpoint routing patch
│   ├── tracing_setup.py         # Optional OpenTelemetry tracing
│   ├── data.jsonl               # Test cases (policy + email override)
│   ├── pytest.ini
│   ├── requirements.txt
│   └── .env.template
├── knowledge/
│   └── travel-policies.json     # Source content for the Foundry IQ KB
├── .github/copilot-instructions.md
└── README.md
```

---

## Security

- All secrets go in `.env` (gitignored) — never hardcode endpoints, API keys, or tokens.
- Prefer `az login` / `DefaultAzureCredential` over API keys for Azure AI Search.
- Work IQ Mail uses OBO — auth is handled by the Foundry hosting layer, not in code.
