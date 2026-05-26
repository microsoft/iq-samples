# Copyright (c) Microsoft. All rights reserved.

"""Entry point — starts the A365 generic host with the RefundAgent."""

import sys

try:
    from agent import RefundAgent
    from host_agent_server import create_and_run_host
except ImportError as e:
    print(f"Import error: {e}")
    print("Please ensure you're running from the correct directory")
    sys.exit(1)


def main():
    """Start the generic host with RefundAgent."""
    try:
        print("Starting Refund Agent...")
        print()
        create_and_run_host(RefundAgent)
    except Exception as e:
        print(f"❌ Failed to start server: {e}")
        import traceback
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    exit(main())
