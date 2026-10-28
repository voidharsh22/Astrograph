"""Data models representing code graph nodes, edges, and query structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# Supported Node Types
NODE_TYPE_REPOSITORY: str = "repository"
NODE_TYPE_DIRECTORY: str = "directory"
NODE_TYPE_FILE: str = "file"
NODE_TYPE_CLASS: str = "class"
NODE_TYPE_FUNCTION: str = "function"
NODE_TYPE_ASYNC_FUNCTION: str = "async_function"
NODE_TYPE_METHOD: str = "method"
NODE_TYPE_INTERFACE: str = "interface"
NODE_TYPE_TYPE_ALIAS: str = "type_alias"
NODE_TYPE_ENUM: str = "enum"

VALID_NODE_TYPES: frozenset[str] = frozenset(
    {
        NODE_TYPE_REPOSITORY,
        NODE_TYPE_DIRECTORY,
        NODE_TYPE_FILE,
        NODE_TYPE_CLASS,
        NODE_TYPE_FUNCTION,
        NODE_TYPE_ASYNC_FUNCTION,
        NODE_TYPE_METHOD,
        NODE_TYPE_INTERFACE,
        NODE_TYPE_TYPE_ALIAS,
        NODE_TYPE_ENUM,
    }
)

# Supported Edge Types
EDGE_TYPE_CONTAINS: str = "CONTAINS"
EDGE_TYPE_DEFINES: str = "DEFINES"
EDGE_TYPE_IMPORTS: str = "IMPORTS"
EDGE_TYPE_CALLS: str = "CALLS"
# Type-level relations (added for Java/Kotlin/Rust/TSX): inheritance and JSX component usage.
EDGE_TYPE_EXTENDS: str = "EXTENDS"
EDGE_TYPE_IMPLEMENTS: str = "IMPLEMENTS"
EDGE_TYPE_RENDERS: str = "RENDERS"

VALID_EDGE_TYPES: frozenset[str] = frozenset(
    {
        EDGE_TYPE_CONTAINS,
        EDGE_TYPE_DEFINES,
        EDGE_TYPE_IMPORTS,
        EDGE_TYPE_CALLS,
        EDGE_TYPE_EXTENDS,
        EDGE_TYPE_IMPLEMENTS,
        EDGE_TYPE_RENDERS,
    }
)

# Resolution Statuses
STATUS_RESOLVED: str = "resolved"
STATUS_AMBIGUOUS: str = "ambiguous"
STATUS_UNRESOLVED: str = "unresolved"
STATUS_EXTERNAL: str = "external"


@dataclass
class GraphNode:
    """Represents a vertex in the code graph."""

    id: str
    type: str
    name: str
    label: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize node to a JSON-compatible dictionary."""
        return {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            "label": self.label,
            "metadata": self.metadata,
        }


@dataclass
class GraphEdge:
    """Represents a directed relationship between two nodes in the code graph."""

    id: str
    source: str
    target: str
    type: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize edge to a JSON-compatible dictionary."""
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "type": self.type,
            "metadata": self.metadata,
        }


@dataclass
class UnresolvedReference:
    """Represents an import or call expression that could not be resolved to a unique local node."""

    kind: str  # "import", "call" or "relation" (inheritance / JSX usage)
    source_file: str
    expression: str
    status: str  # "external", "unresolved", "ambiguous"
    reason: str
    caller_id: Optional[str] = None
    target_name: Optional[str] = None
    lineno: Optional[int] = None
    col_offset: Optional[int] = None
    candidates: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize unresolved reference to a dictionary."""
        return {
            "kind": self.kind,
            "source_file": self.source_file,
            "caller_id": self.caller_id,
            "expression": self.expression,
            "target_name": self.target_name,
            "lineno": self.lineno,
            "col_offset": self.col_offset,
            "status": self.status,
            "candidates": self.candidates,
            "reason": self.reason,
        }


@dataclass
class GraphSummary:
    """Aggregate statistics for a constructed code graph."""

    node_count: int = 0
    edge_count: int = 0
    nodes_by_type: dict[str, int] = field(default_factory=dict)
    edges_by_type: dict[str, int] = field(default_factory=dict)
    resolved_calls: int = 0
    ambiguous_calls: int = 0
    unresolved_calls: int = 0
    resolved_imports: int = 0
    unresolved_imports: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize summary statistics."""
        return {
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "nodes_by_type": self.nodes_by_type,
            "edges_by_type": self.edges_by_type,
            "resolved_calls": self.resolved_calls,
            "ambiguous_calls": self.ambiguous_calls,
            "unresolved_calls": self.unresolved_calls,
            "resolved_imports": self.resolved_imports,
            "unresolved_imports": self.unresolved_imports,
        }


@dataclass
class CodeGraph:
    """Complete code graph representation."""

    schema_version: int
    repository: dict[str, str]
    summary: GraphSummary
    nodes: list[GraphNode] = field(default_factory=list)
    edges: list[GraphEdge] = field(default_factory=list)
    unresolved_references: list[UnresolvedReference] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize entire graph structure."""
        return {
            "schema_version": self.schema_version,
            "repository": self.repository,
            "summary": self.summary.to_dict(),
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "unresolved_references": [u.to_dict() for u in self.unresolved_references],
        }
