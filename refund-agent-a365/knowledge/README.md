# Foundry IQ Knowledge Documents

These are the enterprise knowledge documents the agent grounds on via **Foundry IQ**
(retrieval-augmented generation). They are the source files behind the agent's
knowledge sources — refund/return policies, procurement contracts, and product specs.

## Folder → Knowledge source mapping

Each folder is indexed into its own Azure AI Search index and attached to the Foundry
agent as a separate knowledge source:

| Folder | Azure AI Search index | Contents |
|--------|----------------------|----------|
| `policies/` | `policies-ks` | Refund/return, shipping SLA, warranty, privacy, quality, sustainability, code of conduct |
| `procurements/` | `procurement-ks` | Vendor agreements, supplier contracts, logistics, manufacturing standards |
| `products/` | `products-ks` | ZavaCore product specifications and plans |

> The refund agent's policy assessments are driven primarily by
> `policies/refund-and-return-policy.md`.

## How Foundry IQ is set up in this sample

Foundry IQ here uses **Azure Blob Storage → Azure AI Search → agent knowledge source**
(not files uploaded directly to the agent):

1. **Upload** these markdown files to an Azure Blob Storage container (one virtual
   folder per category, matching the layout above).
2. **Create an Azure AI Search index** over the blob container for each category
   (`policies-ks`, `procurement-ks`, `products-ks`).
3. **Attach each index** to the Foundry agent: in the Azure AI Foundry portal, open the
   agent → **Knowledge and tools** → **+ Add** → **Azure AI Search Index** → select the
   index. Give each source a clear **name** and **description** (the description tells the
   agent *when* to use that source).

Once attached, the agent automatically searches these documents when a user asks about
refund policies, shipping timelines, warranties, vendors, or product details.

> **Alternative (simpler) setup:** For a smaller demo you can skip Azure AI Search and
> upload individual files directly as Foundry IQ knowledge (FileSearchTool). See the
> repository README's "Set Up Foundry IQ" section.
