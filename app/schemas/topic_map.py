from typing import List, Literal, Any

from pydantic import BaseModel

# Enumeration of supported ontological block types
NodeKind = Literal[
    "categorization",
    "relationship",
    "weighting",
    "sentiment",
    "classification",
    "summarization",
]


class Node(BaseModel):
    """A single ontological building block placed on the topic map canvas."""

    id: str  # Client-side UUID
    kind: NodeKind
    label: str
    config: dict[str, Any] = {}


class Edge(BaseModel):
    """Directed connection between two nodes."""

    source: str  # id of upstream node
    target: str  # id of downstream node


class TopicMap(BaseModel):
    """Complete topic map payload sent between frontend and backend."""

    topic_name: str
    nodes: List[Node]
    edges: List[Edge] 