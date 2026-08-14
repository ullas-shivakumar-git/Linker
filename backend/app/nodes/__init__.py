# Importing this package registers every built-in node type on the
# registry (each module below calls @register_node at import time).
from app.nodes.triggers import manual  # noqa: F401
from app.nodes.ai import claude_node  # noqa: F401
from app.nodes.actions import http_request  # noqa: F401
from app.nodes.logic import if_branch  # noqa: F401
from app.nodes.logic import set_transform  # noqa: F401
