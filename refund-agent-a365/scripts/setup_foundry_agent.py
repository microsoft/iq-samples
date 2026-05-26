#!/usr/bin/env python3
"""
Create a Foundry agent for the Refund Agent sample with IQ tools.

Automates Foundry agent creation with SDK-supported tools:
  - Foundry IQ  (FileSearchTool)  — upload knowledge files for RAG
  - Fabric IQ   (FabricTool)      — connect to a Fabric Data Agent
  - Bing Search (BingGroundingTool) — optional web grounding

Work IQ (Teams + email) has no SDK class and must be configured in the
Azure AI Foundry portal after creation.  The script prints portal steps.

Usage:
    # First time — discover your project connections:
    python scripts/setup_foundry_agent.py --connections

    # Create agent (Fabric IQ only):
    python scripts/setup_foundry_agent.py

    # Create agent with Foundry IQ knowledge files:
    python scripts/setup_foundry_agent.py --knowledge-files docs/refund-policy.pdf

    # List / delete existing agents:
    python scripts/setup_foundry_agent.py --list
    python scripts/setup_foundry_agent.py --delete

Prerequisites:
    pip install -r scripts/requirements.txt
    az login
    Set required env vars in agent/.env (see agent/.env.template)
"""

import argparse
import os
import sys

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_SAMPLE_DIR = os.path.dirname(_SCRIPT_DIR)
_ENV_PATH = os.path.join(_SAMPLE_DIR, "agent", ".env")
_INSTRUCTIONS_PATH = os.path.join(_SAMPLE_DIR, "agent-instructions.md")

# Load env
if os.path.exists(_ENV_PATH):
    load_dotenv(_ENV_PATH)
else:
    load_dotenv(os.path.join(_SAMPLE_DIR, "agent", ".env.template"))

# ---------------------------------------------------------------------------
# Configuration (from env)
# ---------------------------------------------------------------------------
AGENT_NAME = os.getenv("FOUNDRY_AGENT_NAME", "refund-agent")
MODEL = os.getenv("FOUNDRY_MODEL_NAME", "gpt-4.1")
ENDPOINT = os.getenv("AZURE_AI_FOUNDRY_ENDPOINT", "").strip()
FABRIC_CONNECTION_ID = os.getenv("FABRIC_CONNECTION_ID", "").strip()
BING_CONNECTION_NAME = os.getenv("BING_CONNECTION_NAME", "").strip()


def _load_instructions() -> str:
    """Load the agent system prompt from agent-instructions.md."""
    if not os.path.exists(_INSTRUCTIONS_PATH):
        sys.exit(f"ERROR: Instructions file not found: {_INSTRUCTIONS_PATH}")
    with open(_INSTRUCTIONS_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _get_client():
    """Return an AIProjectClient using Azure CLI credentials."""
    from azure.ai.projects import AIProjectClient
    from azure.identity import AzureCliCredential

    if not ENDPOINT:
        sys.exit(
            "ERROR: AZURE_AI_FOUNDRY_ENDPOINT is not set.\n"
            "Set it in agent/.env or as an environment variable.\n"
            "Format: https://<account>.services.ai.azure.com/api/projects/<project>"
        )
    return AIProjectClient(
        endpoint=ENDPOINT,
        credential=AzureCliCredential(),
    )


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def list_connections():
    """List all connections in the Foundry project."""
    client = _get_client()
    print("Listing connections in project...\n")
    try:
        for conn in client.connections.list():
            d = conn.as_dict() if hasattr(conn, "as_dict") else vars(conn)
            print(f"  Name: {d.get('name', 'N/A')}")
            print(f"    ID:   {d.get('id', 'N/A')}")
            print(f"    Type: {d.get('connection_type', d.get('type', 'N/A'))}")
            print()
    except Exception as e:
        print(f"Error: {e}")


def list_agents():
    """List all agents in the project."""
    client = _get_client()
    print("Listing agents in project...\n")
    found = False
    for agent in client.agents.list_agents():
        found = True
        print(f"  Name: {agent.name}")
        print(f"    ID:    {agent.id}")
        print(f"    Model: {agent.model}")
        print()
    if not found:
        print("  (no agents found)")


def delete_agent():
    """Delete agent(s) matching AGENT_NAME."""
    client = _get_client()
    print(f"Looking for agent '{AGENT_NAME}'...")
    deleted = 0
    for agent in client.agents.list_agents():
        if agent.name == AGENT_NAME:
            print(f"  Deleting {agent.id} ({agent.name})...")
            client.agents.delete_agent(agent.id)
            deleted += 1
    print(f"Deleted {deleted} agent(s)." if deleted else f"No agent named '{AGENT_NAME}' found.")


def create_agent(knowledge_files: list[str] | None = None):
    """Create the Foundry agent with all available IQ tools."""
    from azure.ai.agents.models import (
        FileSearchTool,
        FabricTool,
        BingGroundingTool,
        FilePurpose,
    )

    client = _get_client()

    # --- Check for existing agent -------------------------------------------
    print(f"Checking for existing agent '{AGENT_NAME}'...")
    for agent in client.agents.list_agents():
        if agent.name == AGENT_NAME:
            print(f"  Agent already exists: {agent.id}")
            print(f"  Use --delete first to recreate.")
            _save_env("FOUNDRY_AGENT_NAME", AGENT_NAME)
            return

    # --- Load instructions (system prompt) -----------------------------------
    instructions = _load_instructions()
    print(f"Loaded instructions ({len(instructions):,} chars)")

    # --- Build tool lists ----------------------------------------------------
    tools = []
    tool_resources = {}

    # 1) Foundry IQ — knowledge files for RAG
    if knowledge_files:
        print("\n📚 Setting up Foundry IQ (knowledge)...")
        file_ids = []
        for path in knowledge_files:
            if not os.path.exists(path):
                print(f"  WARNING: File not found, skipping: {path}")
                continue
            print(f"  Uploading: {path}")
            uploaded = client.agents.files.upload_and_poll(
                file_path=path, purpose=FilePurpose.AGENTS
            )
            file_ids.append(uploaded.id)
            print(f"    File ID: {uploaded.id}")

        if file_ids:
            vs = client.agents.vector_stores.create_and_poll(
                file_ids=file_ids, name=f"{AGENT_NAME}-knowledge"
            )
            print(f"  Vector store: {vs.id}")
            file_search = FileSearchTool(vector_store_ids=[vs.id])
            tools.append(file_search)
            tool_resources.update(
                file_search.resources if hasattr(file_search, "resources") else {}
            )
    else:
        print("\n📚 Foundry IQ: No --knowledge-files provided, skipping FileSearchTool.")
        print("   You can add knowledge later in the Foundry portal.")

    # 2) Fabric IQ — connect to Fabric Data Agent
    if FABRIC_CONNECTION_ID:
        print("\n🔗 Setting up Fabric IQ...")
        fabric = FabricTool(connection_id=FABRIC_CONNECTION_ID)
        tools.append(fabric)
        print(f"  Connection: ...{FABRIC_CONNECTION_ID[-50:]}")
    else:
        print("\n🔗 Fabric IQ: FABRIC_CONNECTION_ID not set, skipping FabricTool.")
        print("   Run --connections to find your Fabric connection ID.")

    # 3) Bing Grounding — optional web search
    if BING_CONNECTION_NAME:
        print("\n🌐 Setting up Bing Grounding...")
        # Look up connection by name to get full ID
        try:
            conn = client.connections.get(connection_name=BING_CONNECTION_NAME)
            conn_id = conn.id
            bing = BingGroundingTool(connection_id=conn_id)
            tools.append(bing)
            print(f"  Connection: {BING_CONNECTION_NAME}")
        except Exception as e:
            print(f"  WARNING: Could not find Bing connection '{BING_CONNECTION_NAME}': {e}")
    else:
        print("\n🌐 Bing Grounding: BING_CONNECTION_NAME not set, skipping (optional).")

    # --- Merge tool definitions ----------------------------------------------
    from azure.ai.agents.models import get_tool_definitions, get_tool_resources

    merged_tools = get_tool_definitions(tools) if tools else []
    merged_resources = get_tool_resources(tools) if tools else {}

    # --- Create the agent ----------------------------------------------------
    print(f"\n🚀 Creating agent '{AGENT_NAME}' with model '{MODEL}'...")
    create_kwargs = dict(
        model=MODEL,
        name=AGENT_NAME,
        instructions=instructions,
        tools=merged_tools,
        headers={"x-ms-enable-preview": "true"},
    )
    if merged_resources:
        create_kwargs["tool_resources"] = merged_resources

    agent = client.agents.create_agent(**create_kwargs)

    print(f"\n✅ Agent created successfully!")
    print(f"  Agent ID:   {agent.id}")
    print(f"  Agent Name: {agent.name}")
    print(f"  Model:      {agent.model}")
    print(f"  Tools:      {len(merged_tools)} tool definition(s)")

    _save_env("FOUNDRY_AGENT_NAME", agent.name)

    # --- Print Work IQ instructions ------------------------------------------
    _print_work_iq_instructions()


def _print_work_iq_instructions():
    """Print manual steps for configuring Work IQ in the portal."""
    print(
        """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 NEXT STEP: Configure Work IQ (Teams + Email) in the portal

Work IQ has no SDK support — you must configure it manually:

1. Open Azure AI Foundry → your project → Agents
2. Click on your agent (refund-agent)
3. Under "Knowledge and tools" → click "+ Add"
4. Select "Microsoft 365" (Work IQ)
5. Grant the required permissions when prompted
6. Save the agent

After this, your agent can search Teams messages and Outlook emails
using the queries defined in agent-instructions.md.

See TROUBLESHOOTING.md if you encounter OBO or permission errors.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"""
    )


def _save_env(key: str, value: str):
    """Safely update a key in agent/.env."""
    if not os.path.exists(_ENV_PATH):
        print(f"  (agent/.env not found — set {key}={value} manually)")
        return

    with open(_ENV_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # Replace existing or append
    lines = content.split("\n")
    replaced = False
    for i, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            replaced = True
            break
    if not replaced:
        lines.append(f"{key}={value}")

    with open(_ENV_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"  Updated agent/.env: {key}={value}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Create a Foundry agent for the Refund Agent sample with IQ tools",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/setup_foundry_agent.py --connections
  python scripts/setup_foundry_agent.py --knowledge-files docs/policy.pdf
  python scripts/setup_foundry_agent.py --list
  python scripts/setup_foundry_agent.py --delete
        """,
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--delete", action="store_true", help="Delete existing agent by name")
    group.add_argument("--list", action="store_true", help="List all agents in the project")
    group.add_argument("--connections", action="store_true", help="List project connections")
    parser.add_argument(
        "--knowledge-files",
        nargs="+",
        metavar="FILE",
        help="PDF/MD files to upload as Foundry IQ knowledge (enables RAG)",
    )

    args = parser.parse_args()

    if args.connections:
        list_connections()
    elif args.list:
        list_agents()
    elif args.delete:
        delete_agent()
    else:
        create_agent(knowledge_files=args.knowledge_files)


if __name__ == "__main__":
    main()
