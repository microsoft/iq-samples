"""
Response Parser for Fabric Data Agent Output

Parses the natural language responses from the Fabric Data Agent and
extracts structured data for graph visualization.

Fabric agent responses include:
- Natural language text explaining query results
- Citation markers like [N:0+source] (Unicode brackets)
- Markdown tables with query results
- Entity references (delivery IDs, hub names, driver names, etc.)

This parser:
1. Strips citation markers from the narrative text
2. Extracts markdown tables into structured data
3. Detects entity references and maps them to graph nodes/edges
4. Returns a structured dict for the frontend graph visualization
"""

import logging
import re
from typing import Optional

logger = logging.getLogger(__name__)

# Regex patterns for parsing

# Citation markers: Unicode brackets with source refs
# Examples: [7:0+source], [12:3+source]
CITATION_PATTERN = re.compile(r"\u3010\d+:\d+\u2020source\u3011")

# Markdown table row: | col1 | col2 | col3 |
TABLE_ROW_PATTERN = re.compile(r"^\s*\|(.+)\|\s*$", re.MULTILINE)

# Table separator row: |---|---|---|
TABLE_SEP_PATTERN = re.compile(r"^\s*\|[-\s:|]+\|\s*$", re.MULTILINE)

# Entity ID patterns for detection
ENTITY_PATTERNS = {
    "package": re.compile(r"\b(PKG-\d+|DEL\d+)\b", re.IGNORECASE),
    "hub": re.compile(r"\b(HUB-[A-Z]{2,4}|Hub[\s-]?(?:Seattle|Denver|Chicago|Atlanta|Miami))\b", re.IGNORECASE),
    "driver": re.compile(r"\b(DRV-\d+)\b", re.IGNORECASE),
    "customer": re.compile(r"\b(CUST-\d+)\b", re.IGNORECASE),
    "handoff": re.compile(r"\b(HO-\d+)\b", re.IGNORECASE),
}

# Map hub display names to IDs
HUB_NAME_TO_ID = {
    "hub seattle": "HUB-SEA",
    "hub-seattle": "HUB-SEA",
    "hub denver": "HUB-DEN",
    "hub-denver": "HUB-DEN",
    "hub chicago": "HUB-CHI",
    "hub-chicago": "HUB-CHI",
    "hub atlanta": "HUB-ATL",
    "hub-atlanta": "HUB-ATL",
    "hub miami": "HUB-MIA",
    "hub-miami": "HUB-MIA",
}

# Node type configuration for graph visualization
NODE_TYPE_CONFIG = {
    "package": {"color": "#4FC3F7", "shape": "box"},
    "hub": {"color": "#81C784", "shape": "hexagon"},
    "driver": {"color": "#FFB74D", "shape": "diamond"},
    "customer": {"color": "#CE93D8", "shape": "ellipse"},
    "handoff": {"color": "#FFD54F", "shape": "circle"},
}


def strip_citations(text: str) -> str:
    """Remove Fabric citation markers from text."""
    return CITATION_PATTERN.sub("", text).strip()


def extract_markdown_tables(text: str) -> list[list[dict]]:
    """
    Extract markdown tables from text and parse into structured data.

    Returns a list of tables, where each table is a list of row dicts
    with column headers as keys.
    """
    tables = []
    lines = text.split("\n")
    i = 0

    while i < len(lines):
        # Look for a table header row (line with | delimiters)
        if TABLE_ROW_PATTERN.match(lines[i]):
            header_line = lines[i]

            # Check if next line is a separator
            if i + 1 < len(lines) and TABLE_SEP_PATTERN.match(lines[i + 1]):
                # Parse header
                headers = [
                    h.strip() for h in header_line.strip().strip("|").split("|")
                ]

                # Parse data rows
                rows = []
                j = i + 2  # Skip header and separator
                while j < len(lines) and TABLE_ROW_PATTERN.match(lines[j]):
                    if TABLE_SEP_PATTERN.match(lines[j]):
                        j += 1
                        continue
                    cells = [
                        c.strip() for c in lines[j].strip().strip("|").split("|")
                    ]
                    if len(cells) == len(headers):
                        row = dict(zip(headers, cells))
                        rows.append(row)
                    j += 1

                if rows:
                    tables.append(rows)
                i = j
                continue

        i += 1

    return tables


def detect_entities(text: str) -> dict[str, set[str]]:
    """
    Detect entity references in text.

    Returns a dict mapping entity type to a set of entity IDs found.
    """
    entities = {}
    for entity_type, pattern in ENTITY_PATTERNS.items():
        matches = set(pattern.findall(text))
        if entity_type == "hub":
            # Normalize hub names to IDs
            normalized = set()
            for match in matches:
                lower = match.lower()
                if lower in HUB_NAME_TO_ID:
                    normalized.add(HUB_NAME_TO_ID[lower])
                elif match.upper().startswith("HUB-"):
                    normalized.add(match.upper())
                else:
                    normalized.add(match)
            matches = normalized

        if matches:
            entities[entity_type] = matches

    return entities


def build_graph_nodes(entities: dict[str, set[str]]) -> list[dict]:
    """Build graph node objects from detected entities."""
    nodes = []
    seen = set()

    for entity_type, entity_ids in entities.items():
        config = NODE_TYPE_CONFIG.get(entity_type, {})
        for entity_id in entity_ids:
            node_key = f"{entity_type}:{entity_id}"
            if node_key in seen:
                continue
            seen.add(node_key)

            nodes.append({
                "id": entity_id,
                "type": entity_type,
                "label": entity_id,
                "color": config.get("color", "#90A4AE"),
                "shape": config.get("shape", "circle"),
            })

    return nodes


def build_graph_edges(
    entities: dict[str, set[str]],
    table_data: Optional[list[list[dict]]] = None,
) -> list[dict]:
    """
    Build graph edges from detected entities and table data.

    Infers relationships:
    - handoff -> hub (atHub)
    - handoff -> driver (byDriver)
    - handoff -> package (hasHandoff)
    - package -> customer (via sender/recipient in table)
    """
    edges = []
    seen = set()

    if not table_data:
        # Without table data, infer simple co-occurrence edges
        # If we see a package and hubs, connect them
        packages = entities.get("package", set())
        hubs = entities.get("hub", set())
        drivers = entities.get("driver", set())

        for pkg in packages:
            for hub in hubs:
                edge_key = f"{pkg}->{hub}"
                if edge_key not in seen:
                    seen.add(edge_key)
                    edges.append({
                        "source": pkg,
                        "target": hub,
                        "label": "routed through",
                    })

            for driver in drivers:
                edge_key = f"{pkg}->{driver}"
                if edge_key not in seen:
                    seen.add(edge_key)
                    edges.append({
                        "source": pkg,
                        "target": driver,
                        "label": "handled by",
                    })

        return edges

    # With table data, try to extract explicit relationships
    for table in table_data:
        for row in table:
            row_lower = {k.lower(): v for k, v in row.items()}

            # Extract entity IDs from table row (handle various column name formats)
            handoff_id = (
                row_lower.get("handoff_id") or row_lower.get("handoff id")
                or row_lower.get("handoff")
            )
            hub_id = (
                row_lower.get("hub_id") or row_lower.get("hub id")
                or row_lower.get("hub")
            )
            driver_id = (
                row_lower.get("driver_id") or row_lower.get("driver id")
                or row_lower.get("driver")
            )
            package_id = (
                row_lower.get("package_id") or row_lower.get("package id")
                or row_lower.get("delivery_id") or row_lower.get("delivery id")
                or row_lower.get("package") or row_lower.get("delivery")
            )

            if handoff_id and hub_id:
                edge_key = f"{handoff_id}->{hub_id}"
                if edge_key not in seen:
                    seen.add(edge_key)
                    edges.append({
                        "source": handoff_id,
                        "target": hub_id,
                        "label": "atHub",
                    })

            if handoff_id and driver_id:
                edge_key = f"{handoff_id}->{driver_id}"
                if edge_key not in seen:
                    seen.add(edge_key)
                    edges.append({
                        "source": handoff_id,
                        "target": driver_id,
                        "label": "byDriver",
                    })

            if package_id and handoff_id:
                edge_key = f"{package_id}->{handoff_id}"
                if edge_key not in seen:
                    seen.add(edge_key)
                    edges.append({
                        "source": package_id,
                        "target": handoff_id,
                        "label": "hasHandoff",
                    })
            elif package_id and hub_id and not handoff_id:
                # Direct package -> hub if no handoff intermediate
                edge_key = f"{package_id}->{hub_id}"
                if edge_key not in seen:
                    seen.add(edge_key)
                    edges.append({
                        "source": package_id,
                        "target": hub_id,
                        "label": "routed through",
                    })

    return edges


def detect_refund_recommendation(text: str) -> bool:
    """Detect if the agent response recommends or mentions a refund."""
    lower = text.lower()
    refund_phrases = [
        "refund", "reimburs", "compensat", "money back",
    ]
    return any(phrase in lower for phrase in refund_phrases)


def _detect_stuck_location(text: str, entities: dict[str, set[str]]) -> Optional[str]:
    """Detect where a package is stuck from the text."""
    hubs = entities.get("hub", set())

    stuck_patterns = [
        r"(?:stuck|delayed|held|stopped|sitting|waiting|stranded)\s+(?:at|in)\s+(\S+)",
        r"(?:currently|last\s+seen|last\s+known)\s+(?:at|in)\s+(\S+)",
    ]

    for pattern in stuck_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            location = match.group(1)
            for hub in hubs:
                if hub.upper() in location.upper() or location.upper() in hub.upper():
                    return hub
            if re.match(r"HUB-[A-Z]+", location, re.IGNORECASE):
                return location.upper()

    return None


def extract_package_route(
    text: str,
    entities: dict[str, set[str]],
    table_data: Optional[list[list[dict]]] = None,
) -> tuple[list[dict], Optional[str]]:
    """
    Extract or infer package route for visualization.

    Returns (route_stops, stuck_location).
    Each stop: {"location": str, "type": str, "status": str}
    """
    stuck_at = _detect_stuck_location(text, entities)

    hubs = sorted(entities.get("hub", set()))

    route: list[dict] = []

    route.append({"location": "Origin", "type": "origin", "status": "completed"})

    if hubs:
        found_stuck = False
        for hub in hubs:
            if stuck_at and hub.upper() == stuck_at.upper():
                route.append({"location": hub, "type": "hub", "status": "stuck"})
                found_stuck = True
            elif found_stuck:
                route.append({"location": hub, "type": "hub", "status": "upcoming"})
            else:
                route.append({"location": hub, "type": "hub", "status": "completed"})

        if not found_stuck:
            route[-1]["status"] = "stuck"
    else:
        route.append({"location": "In Transit", "type": "hub", "status": "stuck"})

    route.append({"location": "Destination", "type": "destination", "status": "upcoming"})

    if not stuck_at and hubs:
        stuck_at = next(
            (s["location"] for s in route if s["status"] == "stuck"), None
        )

    return route, stuck_at


def parse_agent_response(response_text: str) -> dict:
    """
    Parse a Fabric Data Agent response into structured data for visualization.

    Args:
        response_text: Raw text response from the Fabric Data Agent

    Returns:
        {
            "narrative": str,
            "table_data": list | None,
            "graph_update": { "newNodes": list, "newEdges": list },
            "refund_recommended": bool,
            "package_route": list | None,
            "stuck_at": str | None,
            "package_id": str | None,
        }
    """
    if not response_text:
        return {
            "narrative": "",
            "table_data": None,
            "graph_update": {"newNodes": [], "newEdges": []},
            "refund_recommended": False,
            "package_route": None,
            "stuck_at": None,
            "package_id": None,
        }

    # 1. Strip citation markers
    narrative = strip_citations(response_text)

    # 2. Extract markdown tables
    tables = extract_markdown_tables(response_text)
    table_data = tables if tables else None

    # 3. Detect entities in the full response
    entities = detect_entities(response_text)

    # Also detect entities in table data
    if table_data:
        for table in table_data:
            for row in table:
                for value in row.values():
                    row_entities = detect_entities(str(value))
                    for etype, eids in row_entities.items():
                        if etype in entities:
                            entities[etype].update(eids)
                        else:
                            entities[etype] = eids

    # 4. Build graph nodes and edges
    nodes = build_graph_nodes(entities)
    edges = build_graph_edges(entities, table_data)

    # 5. Detect refund recommendation
    refund_recommended = detect_refund_recommendation(response_text)

    # 6. Extract package route if refund recommended
    package_route = None
    stuck_at = None
    if refund_recommended:
        package_route, stuck_at = extract_package_route(
            response_text, entities, table_data
        )

    package_ids = sorted(entities.get("package", set()))

    logger.debug(
        f"Parsed response: {len(nodes)} nodes, {len(edges)} edges, "
        f"{len(tables)} tables, entities={list(entities.keys())}, "
        f"refund={refund_recommended}"
    )

    return {
        "narrative": narrative,
        "table_data": table_data,
        "graph_update": {
            "newNodes": nodes,
            "newEdges": edges,
        },
        "refund_recommended": refund_recommended,
        "package_route": package_route,
        "stuck_at": stuck_at,
        "package_id": package_ids[0] if package_ids else None,
    }
