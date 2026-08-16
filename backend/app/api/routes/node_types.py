from fastapi import APIRouter

import app.nodes  # noqa: F401 — import for side effect: registers all built-in node types
from app.nodes.registry import list_node_types

router = APIRouter(tags=["node-types"])


@router.get("/node-types")
async def get_node_types() -> list[dict]:
    return list_node_types()
