# Copilot Instructions — Travel Agent (Foundry IQ + Work IQ)

## Scope

This sample is part of the `microsoft/iq-samples` repo. **Only read and modify files within this folder** (`travel-agent-hosted/`). Do not touch other samples or root-level governance files (LICENSE, CODE_OF_CONDUCT.md, SECURITY.md, SUPPORT.md).

## Project Identity

This is a **hosted Microsoft Foundry agent** built with the **Microsoft Agent Framework SDK**. It is a corporate travel assistant grounded with two IQ tools:

- **Foundry IQ** — a knowledge base of corporate travel policies (agentic retrieval).
- **Work IQ Mail** — searches the employee's email for recent policy updates, budget freezes, and temporary overrides (via OBO / on-behalf-of auth).

The agent's intelligence lives in the system prompt in `agent/agent.py`. The tool wiring (knowledge base + Work IQ Mail) is declared in `agent/agent.manifest.yaml` and injected by the Foundry hosting platform — **the tools are not instantiated in code**. Because Work IQ Mail requires OBO, the agent only works fully when **deployed** (hosted), not locally.

## Tech Stack

| Component | Technology |
|-----------|-----------|
| **Agent host** | Python 3.12, Agent Framework SDK (`agent-framework-*`), `agent-framework-foundry-hosting` |
| **Protocol** | Responses (`ResponsesHostServer`) |
| **Deployment** | Microsoft Foundry hosted agent (`agent.yaml` + `Dockerfile`) |
| **Evaluation** | `pytest-agent-evals` against the deployed agent |

## Key Files

| File | Purpose |
|------|---------|
| `agent/agent.py` | Agent definition + system prompt. Builds a `FoundryChatClient` + `Agent`. |
| `agent/main.py` | Host entry point — runs `ResponsesHostServer(agent)`. |
| `agent/agent.manifest.yaml` | Declares the model, the Foundry IQ `knowledge` resource, and the `WorkIQMail` tool. **This is where tools are wired.** |
| `agent/agent.yaml` | Container/hosting descriptor (kind: hosted, resources, env vars). |
| `agent/Dockerfile` / `agent/startup.sh` | Container build + startup. |
| `agent/.env.template` | Copy to `.env` and fill in your Foundry endpoint + model. |
| `evals/` | Evaluation suite (`pytest-agent-evals`) run against the **deployed** agent. |
| `evals/evaluators.py` | Custom `policy_completeness` grader (deterministic, fact-based). |
| `evals/data.jsonl` | Test cases with ground truth (standing policy + email override). |
| `knowledge/travel-policies.json` | Source content for the Foundry IQ knowledge base. |

## What NOT to Touch

- **`.env` files** are gitignored. Never create or commit them. Use `.env.template` for documenting required variables.
- **Do not hardcode** Foundry endpoints, search endpoints, tenant IDs, or API keys anywhere. Placeholders only.
- **Knowledge base ↔ eval consistency:** `knowledge/travel-policies.json` and `evals/evaluators.py`/`evals/data.jsonl` are intentionally aligned (e.g. hotel cap $250/night, meal per diem $75/day). If you change a policy value in one, update the other or the evals will break.

## Setup (high level — see README.md for full steps)

1. `az login`
2. Create a Foundry IQ knowledge base from `knowledge/travel-policies.json` (name it to match the `knowledge.id` in `agent/agent.manifest.yaml`).
3. Configure the Work IQ Mail tool in the Foundry project (OBO connection).
4. `cp agent/.env.template agent/.env` and fill in values.
5. Deploy the hosted agent (`agent/agent.yaml` + `Dockerfile`).
6. Test in the Foundry hosted agent playground.
7. Run evals from `evals/` against the deployed agent.

## Security

- All secrets go in `.env` (gitignored) — never hardcode API keys, connection strings, or tokens.
- Prefer `az login` / `DefaultAzureCredential` over API keys for Azure AI Search.
- Work IQ Mail uses OBO — auth is handled by the Foundry hosting layer, not in code.
