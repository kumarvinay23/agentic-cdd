"""FDD dependency graph — cell → exhibits → sections → gates."""

from __future__ import annotations

from agetic_cdd_api.fdd_schemas import (
    DependencyEdge,
    DependencyGraph,
    ExhibitStoreDoc,
    ReportSpec,
)
from agetic_cdd_api.services_fdd_exhibit import cell_ref
from agetic_cdd_api.services_fdd_store import save_dependency_graph


def build_dependency_graph(
    *,
    run_id: str,
    store: ExhibitStoreDoc,
    spec: ReportSpec | None = None,
    gate_ids: list[str] | None = None,
) -> DependencyGraph:
    """Derive edges from exhibit cells and report_spec node references."""
    nodes: set[str] = set()
    edges: list[DependencyEdge] = []

    for ex in store.exhibits:
        ex_node = f"exhibit:{ex.exhibit_id}"
        nodes.add(ex_node)
        if ex.section_id:
            sec_node = f"section:{ex.section_id}"
            nodes.add(sec_node)
            edges.append(
                DependencyEdge(
                    from_id=ex_node,
                    to_id=sec_node,
                    kind="exhibit_to_section",
                )
            )
        for cell in ex.cells:
            cell_node = f"cell:{cell_ref(ex.exhibit_id, cell.cell_id)}"
            nodes.add(cell_node)
            edges.append(
                DependencyEdge(
                    from_id=cell_node,
                    to_id=ex_node,
                    kind="cell_to_exhibit",
                )
            )

    if spec is not None:
        for node in spec.nodes:
            spec_node = f"spec:{node.node_id}"
            nodes.add(spec_node)
            for ref in node.cell_refs:
                cell_node = f"cell:{ref}"
                nodes.add(cell_node)
                edges.append(
                    DependencyEdge(
                        from_id=cell_node,
                        to_id=spec_node,
                        kind="cell_to_spec",
                    )
                )
            if node.exhibit_id:
                ex_node = f"exhibit:{node.exhibit_id}"
                nodes.add(ex_node)
                edges.append(
                    DependencyEdge(
                        from_id=ex_node,
                        to_id=spec_node,
                        kind="exhibit_to_section",
                    )
                )

    for gate in gate_ids or ["G1", "G3", "G4", "G5", "G6", "G7"]:
        gate_node = f"gate:{gate}"
        nodes.add(gate_node)
        # Sections that exist feed gates (placeholder wiring for Phase 8).
        for n in list(nodes):
            if n.startswith("section:"):
                edges.append(
                    DependencyEdge(
                        from_id=n,
                        to_id=gate_node,
                        kind="section_to_gate",
                    )
                )

    # Stable order
    edges.sort(key=lambda e: (e.from_id, e.to_id, e.kind))
    return DependencyGraph(
        run_id=run_id,
        nodes=sorted(nodes),
        edges=edges,
    )


def dependents_of(graph: DependencyGraph, node_id: str) -> list[str]:
    """BFS of nodes reachable from ``node_id`` along dependency edges."""
    seen: set[str] = set()
    queue = [node_id]
    while queue:
        cur = queue.pop(0)
        for edge in graph.edges:
            if edge.from_id != cur:
                continue
            if edge.to_id in seen:
                continue
            seen.add(edge.to_id)
            queue.append(edge.to_id)
    return sorted(seen)


def rebuild_and_persist(
    deal_slug: str,
    *,
    run_id: str,
    store: ExhibitStoreDoc,
    spec: ReportSpec | None = None,
) -> DependencyGraph:
    graph = build_dependency_graph(run_id=run_id, store=store, spec=spec)
    return save_dependency_graph(graph, deal_slug)
