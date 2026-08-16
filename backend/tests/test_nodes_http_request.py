import httpx
import pytest

from app.engine.context import ExecutionContext
from app.nodes.actions.http_request import HttpRequestConfig, HttpRequestNode


def _fake_request(method, url, *, headers=None, content=None, timeout=None):
    """Stands in for httpx.request() so this test suite is hermetic — no
    real network call. (A real live call against httpbin.org was used
    once, manually, to prove the node works end to end; a permanent test
    suite should not depend on an external service being reachable.)
    """
    request = httpx.Request(method, url, headers=headers, content=content)
    if "should-500" in url:
        return httpx.Response(500, request=request, text="server error")
    return httpx.Response(
        200,
        request=request,
        json={"method": method, "url": str(url), "headers": dict(headers or {}), "body": content},
    )


def test_http_request_renders_templated_url_and_body(monkeypatch):
    monkeypatch.setattr(httpx, "request", _fake_request)

    ctx = ExecutionContext(workspace_id="w1", trigger_payload={"value": "hello", "id": "42"})
    node = HttpRequestNode(
        HttpRequestConfig(
            url="https://example.com/items/{{ trigger.id }}",
            method="POST",
            body="value={{ trigger.value }}",
        )
    )

    output = node.execute({}, ctx)

    assert output["status_code"] == 200
    assert output["body"]["url"] == "https://example.com/items/42"
    assert output["body"]["method"] == "POST"
    assert output["body"]["body"] == "value=hello"


def test_http_request_renders_templated_headers(monkeypatch):
    monkeypatch.setattr(httpx, "request", _fake_request)

    ctx = ExecutionContext(workspace_id="w1", trigger_payload={"token": "abc123"})
    node = HttpRequestNode(
        HttpRequestConfig(url="https://example.com/", headers={"Authorization": "Bearer {{ trigger.token }}"})
    )

    output = node.execute({}, ctx)

    assert output["body"]["headers"]["Authorization"] == "Bearer abc123"


def test_http_request_raises_on_error_status(monkeypatch):
    monkeypatch.setattr(httpx, "request", _fake_request)

    ctx = ExecutionContext(workspace_id="w1", trigger_payload={})
    node = HttpRequestNode(HttpRequestConfig(url="https://example.com/should-500"))

    with pytest.raises(httpx.HTTPStatusError):
        node.execute({}, ctx)
