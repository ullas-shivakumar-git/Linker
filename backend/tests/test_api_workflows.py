import uuid


async def _create_workspace(client) -> tuple[str, str]:
    response = await client.post(
        "/workspaces",
        json={"owner_email": f"test-{uuid.uuid4()}@example.com", "workspace_name": "Test Workspace"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    return body["workspace_id"], body["user_id"]


_TWO_NODE_GRAPH = {
    "nodes": [
        {"id": "trig", "type": "manual_trigger", "config": {}},
        {
            "id": "transform",
            "type": "set_transform",
            "config": {"mappings": [{"output_key": "greeting", "value_template": "hello {{ trigger.name }}"}]},
        },
    ],
    "edges": [{"source": "trig", "target": "transform"}],
}


async def test_create_workflow(client):
    workspace_id, user_id = await _create_workspace(client)

    response = await client.post(
        f"/workspaces/{workspace_id}/workflows",
        json={"name": "Greeter", "graph": _TWO_NODE_GRAPH, "created_by": user_id},
    )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["name"] == "Greeter"
    assert body["current_version_id"] is not None


async def test_create_workflow_rejects_a_cyclic_graph(client):
    workspace_id, user_id = await _create_workspace(client)
    cyclic_graph = {
        "nodes": [{"id": "a", "type": "manual_trigger", "config": {}}, {"id": "b", "type": "manual_trigger", "config": {}}],
        "edges": [{"source": "a", "target": "b"}, {"source": "b", "target": "a"}],
    }

    response = await client.post(
        f"/workspaces/{workspace_id}/workflows",
        json={"name": "Bad Workflow", "graph": cyclic_graph, "created_by": user_id},
    )

    assert response.status_code == 400


async def test_get_workflow_includes_current_graph(client):
    workspace_id, user_id = await _create_workspace(client)
    create_resp = await client.post(
        f"/workspaces/{workspace_id}/workflows",
        json={"name": "Greeter", "graph": _TWO_NODE_GRAPH, "created_by": user_id},
    )
    workflow_id = create_resp.json()["id"]

    response = await client.get(f"/workspaces/{workspace_id}/workflows/{workflow_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["version_number"] == 1
    assert [n["id"] for n in body["graph"]["nodes"]] == ["trig", "transform"]


async def test_update_workflow_creates_a_new_version(client):
    workspace_id, user_id = await _create_workspace(client)
    create_resp = await client.post(
        f"/workspaces/{workspace_id}/workflows",
        json={"name": "Greeter", "graph": _TWO_NODE_GRAPH, "created_by": user_id},
    )
    workflow_id = create_resp.json()["id"]

    single_node_graph = {"nodes": [{"id": "trig", "type": "manual_trigger", "config": {}}], "edges": []}
    response = await client.put(
        f"/workspaces/{workspace_id}/workflows/{workflow_id}",
        json={"graph": single_node_graph, "created_by": user_id},
    )

    assert response.status_code == 200
    get_resp = await client.get(f"/workspaces/{workspace_id}/workflows/{workflow_id}")
    assert get_resp.json()["version_number"] == 2


async def test_execute_workflow_end_to_end(client):
    workspace_id, user_id = await _create_workspace(client)
    create_resp = await client.post(
        f"/workspaces/{workspace_id}/workflows",
        json={"name": "Greeter", "graph": _TWO_NODE_GRAPH, "created_by": user_id},
    )
    workflow_id = create_resp.json()["id"]

    response = await client.post(
        f"/workspaces/{workspace_id}/workflows/{workflow_id}/execute",
        json={"trigger_payload": {"name": "Ullas"}},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "succeeded"
    assert len(body["steps"]) == 2

    steps_by_id = {s["node_id"]: s for s in body["steps"]}
    assert steps_by_id["trig"]["status"] == "succeeded"
    assert steps_by_id["transform"]["status"] == "succeeded"
    assert steps_by_id["transform"]["output"]["greeting"] == "hello Ullas"


async def test_execute_nonexistent_workflow_returns_404(client):
    workspace_id, _ = await _create_workspace(client)
    fake_workflow_id = uuid.uuid4()

    response = await client.post(
        f"/workspaces/{workspace_id}/workflows/{fake_workflow_id}/execute",
        json={"trigger_payload": {}},
    )

    assert response.status_code == 404


async def test_credentials_are_never_returned_in_plaintext(client):
    workspace_id, user_id = await _create_workspace(client)

    create_resp = await client.post(
        f"/workspaces/{workspace_id}/credentials",
        json={
            "name": "My Anthropic Key",
            "type": "anthropic_api_key",
            "value": "sk-ant-super-secret-value",
            "created_by": user_id,
        },
    )
    assert create_resp.status_code == 201
    assert "value" not in create_resp.text
    assert "sk-ant-super-secret-value" not in create_resp.text

    list_resp = await client.get(f"/workspaces/{workspace_id}/credentials")
    assert list_resp.status_code == 200
    assert "sk-ant-super-secret-value" not in list_resp.text
    body = list_resp.json()
    assert body[0]["name"] == "My Anthropic Key"
