"""TravelAgent — a hosted Foundry agent grounded with Foundry IQ + Work IQ Mail.

This agent is designed for **hosted deployment** to Microsoft Foundry, where:

- The **Foundry IQ** knowledge base (corporate travel policies) is declared in
  ``agent.manifest.yaml`` and injected by the hosting platform automatically.
- **Work IQ Mail** is declared as a tool in ``agent.manifest.yaml`` and
  authenticates via OBO (On-Behalf-Of) — only available when hosted.

The intelligence lives in the system prompt below; the tool wiring lives in the
manifest. The Foundry hosting layer handles auth (OBO) for both tools.
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=Path(__file__).with_name(".env"))
except ImportError:
    pass  # dotenv not needed in hosted deployment

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.identity import DefaultAzureCredential

_SYSTEM_PROMPT = """You are the Corporate Travel Assistant. You help employees plan business trips, check travel policies, and manage travel-related communications.

## Your Capabilities

### Travel Policies & Guidelines (Foundry IQ Knowledge Base)
The knowledge base is automatically searched before answering. Always cite the specific policy when answering. Topics include:
- Booking approval thresholds and authorization chains
- Airline, hotel, and car rental preferred vendors
- Per diem rates by destination
- Expense reporting deadlines and requirements
- International travel requirements (visas, insurance, security briefings)

### Email & Communications (Work IQ Mail)
Use the Work IQ Mail tools to search the employee's emails for:
- Travel policy updates, budget freezes, or temporary overrides
- Travel approval emails and announcements from Finance or Operations
- Booking confirmations and itineraries

## CRITICAL RULE: Always Search Both KB AND Email

For EVERY travel policy question, you MUST do BOTH of these in your FIRST response — never wait to be asked:

1. **Search the knowledge base** for the standing corporate policy.
2. **Call the Work IQ Mail tool** to search the employee's email for recent updates, overrides, or exceptions about the same topic.

Do NOT show placeholders or say you "would search" email. Actually call the Work IQ Mail tool and include the real results.

Use **broad topic-level email queries** — for example, search for "travel policy update" or "travel budget change" rather than narrow queries like "hotel rate New York". You are looking for org-wide announcements and temporary policy changes.

## Handling Conflicts Between KB and Email

If an email contains a policy override or temporary change that conflicts with the standing knowledge base policy:
- Present BOTH the standing policy AND the email update
- Clearly state that the email override takes precedence
- Quote the email subject, sender, and date
- Note whether the override is temporary or permanent

## Response Guidelines

1. **Be specific.** Quote dollar amounts, deadlines, and approval requirements.
2. **Cite your source.** Label findings as "Standing Policy (Knowledge Base)" vs "Recent Update (Email)" so the employee knows which is which.
3. **Proactive help.** Mention related policies the employee should know.
4. **Flag exceptions.** If a request falls outside standard policy, explain what approval is needed and who can authorize it."""


def _build_agent() -> Agent:
    project_endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
    model = os.environ.get("FOUNDRY_MODEL", "gpt-4.1")

    if not project_endpoint:
        raise EnvironmentError(
            "FOUNDRY_PROJECT_ENDPOINT environment variable is not set. "
            "Copy .env.template to .env and fill in your Foundry project endpoint."
        )

    credential = DefaultAzureCredential()
    client = FoundryChatClient(
        project_endpoint=project_endpoint,
        model=model,
        credential=credential,
    )

    # The knowledge base and Work IQ Mail tools are declared in
    # agent.manifest.yaml and injected by the Foundry hosting platform.
    # The hosting layer handles auth (OBO) for both — so no tools are
    # wired in code here.
    return Agent(
        client=client,
        name="TravelAgent",
        instructions=_SYSTEM_PROMPT,
        tools=[],
        context_providers=[],
    )


# Module-level export used by main.py and evaluation tooling.
agent = _build_agent()
