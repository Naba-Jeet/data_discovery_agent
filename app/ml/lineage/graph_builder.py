# app/ml/lineage/graph_builder.py

import networkx as nx
import pandas as pd
from typing import Optional


def build_lineage_graph(
    edges: list[dict],
    node_metadata: Optional[dict] = None,
) -> nx.DiGraph:
    """
    Build a directed lineage graph from edge definitions.

    Args:
        edges:          List of {"source": str, "target": str, "relation": str}
        node_metadata:  Optional dict of {node_name: {key: value}} for extra context

    Returns:
        nx.DiGraph
    """
    G = nx.DiGraph()

    for edge in edges:
        source   = edge["source"]
        target   = edge["target"]
        relation = edge.get("relation", "feeds")

        G.add_edge(source, target, relation=relation)

        # Attach metadata to nodes if provided
        if node_metadata:
            if source in node_metadata:
                G.nodes[source].update(node_metadata[source])
            if target in node_metadata:
                G.nodes[target].update(node_metadata[target])

    return G


def trace_upstream(G: nx.DiGraph, node: str) -> list[str]:
    """All tables/nodes that feed into this node."""
    if node not in G:
        return []
    return list(nx.ancestors(G, node))


def trace_downstream(G: nx.DiGraph, node: str) -> list[str]:
    """All tables/nodes that this node feeds into."""
    if node not in G:
        return []
    return list(nx.descendants(G, node))


def impact_analysis(G: nx.DiGraph, node: str) -> dict:
    """
    Full impact report for a given node.
    Useful for: "What breaks if I change this table?"
    """
    if node not in G:
        return {"error": f"Node '{node}' not found in lineage graph"}

    upstream   = trace_upstream(G, node)
    downstream = trace_downstream(G, node)

    # Shortest paths to all downstream nodes
    paths = {}
    for target in downstream:
        try:
            paths[target] = nx.shortest_path(G, node, target)
        except nx.NetworkXNoPath:
            paths[target] = []

    return {
        "node":              node,
        "upstream_count":    len(upstream),
        "downstream_count":  len(downstream),
        "upstream":          upstream,
        "downstream":        downstream,
        "impact_paths":      paths,
    }


def graph_summary(G: nx.DiGraph) -> dict:
    """High-level summary of the lineage graph."""
    return {
        "total_nodes": G.number_of_nodes(),
        "total_edges": G.number_of_edges(),
        "root_nodes":  [n for n in G.nodes if G.in_degree(n) == 0],   # no parents
        "leaf_nodes":  [n for n in G.nodes if G.out_degree(n) == 0],  # no children
    }