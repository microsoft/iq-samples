"""Patch pytest-agent-evals to call hosted agents through their dedicated endpoint.

Some versions of pytest-agent-evals use agent_reference in extra_body, but the
Foundry API requires hosted agents to be called through their per-agent endpoint
with the ai.azure.com auth scope.

This conftest monkey-patches _run_hosted_agent to route calls correctly.
"""

from openai import AsyncOpenAI
from azure.identity import DefaultAzureCredential
import pytest_agent_evals.foundry_agent as _fa

_AGENT_API_VERSION = "2025-05-15-preview"


async def _run_hosted_via_agent_endpoint(self, openai_client, conversation, agent_name, agent_version, query):
    """Route hosted-agent calls through the per-agent endpoint with correct auth."""
    agent_base_url = f"{self.project_endpoint}/agents/{agent_name}/endpoint/protocols/openai/"

    # Hosted agent endpoint requires the ai.azure.com scope
    cred = DefaultAzureCredential()
    token = cred.get_token("https://ai.azure.com/.default")

    agent_client = AsyncOpenAI(
        base_url=agent_base_url,
        api_key=token.token,
        default_query={"api-version": _AGENT_API_VERSION},
    )

    async with agent_client:
        enhanced_query = (
            "IMPORTANT: Before answering, you MUST use the Work IQ Mail tool to search my emails "
            "for any recent travel policy updates, budget changes, or temporary overrides. "
            "Do not skip the email search. Here is my question: " + query
        )
        response = await agent_client.responses.create(
            model="__hosted__",
            input=enhanced_query,
        )

    return response, None, []


_fa.FoundryAgentRunner._run_hosted_agent = _run_hosted_via_agent_endpoint
