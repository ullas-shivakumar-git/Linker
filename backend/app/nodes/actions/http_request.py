from __future__ import annotations

from typing import Optional

import httpx

from app.engine.templating import render_template
from app.nodes.base import BaseNode, NodeConfig
from app.nodes.registry import register_node


class HttpRequestConfig(NodeConfig):
    url: str
    method: str = "GET"
    headers: dict[str, str] = {}
    body: Optional[str] = None
    credential_id: Optional[str] = None
    timeout_seconds: float = 30.0


@register_node
class HttpRequestNode(BaseNode):
    node_type = "http_request"
    category = "action"
    display_name = "HTTP Request"
    description = (
        "Makes an outbound HTTP request. url, headers, and body all support "
        "{{ nodes.X.field }} / {{ trigger.field }} templating."
    )
    config_model = HttpRequestConfig
    is_retryable = True
    is_ai_repairable = True

    def execute(self, inputs: dict, context) -> dict:
        url = render_template(self.config.url, context)
        headers = {key: render_template(value, context) for key, value in self.config.headers.items()}
        body = render_template(self.config.body, context) if self.config.body else None

        response = httpx.request(
            method=self.config.method,
            url=url,
            headers=headers,
            content=body,
            timeout=self.config.timeout_seconds,
        )
        # Raises httpx.HTTPStatusError on 4xx/5xx — the executor's
        # retry/AI-repair wrapper catches it like any other node failure.
        response.raise_for_status()

        try:
            parsed_body = response.json()
        except ValueError:
            parsed_body = response.text

        return {
            "status_code": response.status_code,
            "body": parsed_body,
            "headers": dict(response.headers),
        }
