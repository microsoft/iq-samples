# Sample Data for Fabric Lakehouse

This folder contains the dataset to populate the Microsoft Fabric Lakehouse used by the Fabric Data Agent.

## CSV Files (Lakehouse Tables)

| File | Description |
|------|-------------|
| `customers.csv` | Customer records (individual and business) |
| `packages.csv` | Package shipments with origin, destination, status |
| `drivers.csv` | Delivery drivers |
| `hubs.csv` | Distribution hubs in the network |
| `hub_connections.csv` | Routes connecting hubs |
| `handoffs.csv` | Package handoff events between hubs/drivers |
| `payments.csv` | Payment and refund records |

## JSON Files (Example Queries)

| File | Description |
|------|-------------|
| `example_queries_lakehouse.json` | Few-shot SQL query examples for the Lakehouse datasource |
| `example_queries_graph.json` | Few-shot GQL query examples for the Knowledge Graph datasource |

## Usage

1. Upload the CSV files to your Fabric Lakehouse (via notebook, Fabric UI, or REST API)
2. Import the example query JSON files into your Fabric Data Agent configuration to improve query accuracy
