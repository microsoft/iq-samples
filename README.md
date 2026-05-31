# IQ Samples

End-to-end samples showcasing **Foundry IQ**, **Fabric IQ**, **Work IQ**, and **Web IQ** integrations in AI agents.

> 📚 **New to the IQs?** Start with **[The Microsoft IQ Series](https://github.com/microsoft/iq-series)** — a guided learning series that explains Foundry IQ, Fabric IQ, Work IQ, and Web IQ from the ground up. Then come back here to build with them.
>
> 💬 **Questions or stuck?** Ask in the **[IQ Discussions](https://aka.ms/iq/discussions)** — we (and the community) are there to help.

## Samples

| Sample | Description | Stack |
|--------|-------------|-------|
| [Refund Agent (A365)](./refund-agent-a365/) | A365 agent wrapping an Azure AI Foundry agent with Fabric Data Agent, Foundry IQ knowledge, and Work IQ (Teams/email) — deployed to Microsoft Teams | Python 3.11+, A365 SDK, React/Vite dashboard |
| [Travel Agent (Hosted, Foundry IQ + Work IQ)](./travel-agent-hosted/) | A hosted Azure AI Foundry agent (Agent Framework SDK) grounded with Foundry IQ travel policies and Work IQ Mail — answers with both standing policy and recent email overrides, with an evaluation suite | Python 3.12, Agent Framework SDK, pytest-agent-evals |

## Getting Started

### Prerequisites

- **Azure subscription** with access to [Azure AI Foundry](https://ai.azure.com)
- **Microsoft 365 tenant** enrolled in the [Frontier Preview Program](https://adoption.microsoft.com/copilot/frontier-program/)
- **Azure CLI** (`az login`) and **A365 CLI** ([install guide](https://learn.microsoft.com/en-us/microsoft-agent-365/developer/install-cli))
- **Python 3.11+** (for agent samples)
- **Node.js 18+** (for dashboard frontends)

### Quick Start

1. **Clone the repo:**
   ```bash
   git clone https://github.com/microsoft/iq-samples.git
   cd iq-samples
   ```

2. **Pick a sample** from the table above and navigate to its folder

3. **Follow the sample's README** — each sample has step-by-step setup instructions covering:
   - Creating and configuring the Foundry agent with IQ tools
   - Setting up Foundry IQ (knowledge/RAG), Work IQ (Teams/email), and Fabric IQ (data agent)
   - A365 teammate provisioning and deployment
   - Troubleshooting common errors

> **Tip:** Each sample also includes a `TROUBLESHOOTING.md` with solutions for all known errors. If you get stuck, check there first.

## Learn More & Get Help

- 📚 **[The Microsoft IQ Series](https://github.com/microsoft/iq-series)** — a guided learning series covering Foundry IQ, Fabric IQ, Work IQ, and Web IQ. The best place to understand the concepts before (or while) building these samples.
- 💬 **[IQ Discussions](https://aka.ms/iq/discussions)** — ask questions, share what you built, and get help from the team and community.
- 🐛 **Issues** — found a bug in a sample? Open an issue in this repo.

## Contributing

This project welcomes contributions and suggestions. Most contributions require you to agree to a
Contributor License Agreement (CLA) declaring that you have the right to, and actually do, grant us
the rights to use your contribution. For details, visit [Contributor License Agreements](https://cla.opensource.microsoft.com).

When you submit a pull request, a CLA bot will automatically determine whether you need to provide
a CLA and decorate the PR appropriately (e.g., status check, comment). Simply follow the instructions
provided by the bot. You will only need to do this once across all repos using our CLA.

This project has adopted the [Microsoft Open Source Code of Conduct](https://opensource.microsoft.com/codeofconduct/).
For more information see the [Code of Conduct FAQ](https://opensource.microsoft.com/codeofconduct/faq/) or
contact [opencode@microsoft.com](mailto:opencode@microsoft.com) with any additional questions or comments.

## Trademarks

This project may contain trademarks or logos for projects, products, or services. Authorized use of Microsoft
trademarks or logos is subject to and must follow
[Microsoft's Trademark & Brand Guidelines](https://www.microsoft.com/legal/intellectualproperty/trademarks/usage/general).
Use of Microsoft trademarks or logos in modified versions of this project must not cause confusion or imply Microsoft sponsorship.
Any use of third-party trademarks or logos are subject to those third-party's policies.
