# Copyright (c) Microsoft. All rights reserved.

"""TravelAgent host entry point — Foundry IQ + Work IQ Mail (hosted).

Uses the Microsoft Agent Framework SDK with two tools declared in the manifest:
- A Foundry IQ knowledge base (corporate travel policies)
- Work IQ Mail (employee email search)

Hosted via ResponsesHostServer from agent-framework-foundry-hosting, which
provides the /readiness endpoint required by the Foundry platform.

Required environment variables:
    FOUNDRY_PROJECT_ENDPOINT: Foundry project endpoint
    FOUNDRY_MODEL:            Model deployment name (e.g., gpt-4.1)
"""

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv(dotenv_path=Path(__file__).with_name(".env"))
except ImportError:
    pass  # dotenv not needed in hosted deployment

from agent_framework_foundry_hosting import ResponsesHostServer
from agent import agent


def main():
    server = ResponsesHostServer(agent)
    server.run()


if __name__ == "__main__":
    main()
