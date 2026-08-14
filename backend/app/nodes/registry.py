from app.nodes.base import BaseNode

_REGISTRY: dict[str, type[BaseNode]] = {}


def register_node(cls: type[BaseNode]) -> type[BaseNode]:
    if cls.node_type in _REGISTRY:
        raise ValueError(f"Node type '{cls.node_type}' is already registered")
    _REGISTRY[cls.node_type] = cls
    return cls


def get_node_class(node_type: str) -> type[BaseNode]:
    try:
        return _REGISTRY[node_type]
    except KeyError:
        raise KeyError(f"Unknown node type: '{node_type}'") from None


def list_node_types() -> list[dict]:
    """Powers GET /node-types (Milestone 1.6) — the frontend's node palette
    and config forms are built entirely from this, with no per-node-type
    frontend code.
    """
    return [
        {
            "node_type": cls.node_type,
            "category": cls.category,
            "display_name": cls.display_name,
            "description": cls.description,
            "config_schema": cls.config_model.model_json_schema(),
        }
        for cls in _REGISTRY.values()
    ]
