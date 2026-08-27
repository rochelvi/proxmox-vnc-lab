import pytest
from sqlalchemy import select
from starlette.websockets import WebSocketDisconnect

from app.config import Settings
from app.models import VMAssignment
from app.routers import templates as templates_router
from app.routers import vms as vms_router
from tests.conftest import login


def test_login_jwt_and_me(client):
    api, _, _ = client
    token = login(api)
    response = api.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["username"] == "intern"
    assert response.json()["can_change_password"] is True


def test_change_password_updates_credentials(client):
    api, _, _ = client
    token = login(api)
    headers = {"Authorization": f"Bearer {token}"}
    response = api.post(
        "/api/auth/password",
        headers=headers,
        json={"current_password": "password", "new_password": "new-password"},
    )
    assert response.status_code == 204
    assert api.post(
        "/api/auth/login", json={"username": "intern", "password": "password"}
    ).status_code == 401
    assert api.post(
        "/api/auth/login", json={"username": "intern", "password": "new-password"}
    ).status_code == 200


def test_change_password_rejects_wrong_current_password(client):
    api, _, _ = client
    token = login(api)
    response = api.post(
        "/api/auth/password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "wrong-password", "new_password": "new-password"},
    )
    assert response.status_code == 400
    assert api.post(
        "/api/auth/login", json={"username": "intern", "password": "password"}
    ).status_code == 200


def test_change_password_rejects_short_password(client):
    api, _, _ = client
    token = login(api)
    response = api.post(
        "/api/auth/password",
        headers={"Authorization": f"Bearer {token}"},
        json={"current_password": "password", "new_password": "short"},
    )
    assert response.status_code == 422


def test_change_password_requires_authentication(client):
    api, _, _ = client
    response = api.post(
        "/api/auth/password",
        json={"current_password": "password", "new_password": "new-password"},
    )
    assert response.status_code == 401


def test_unauthorized_access(client):
    api, _, _ = client
    assert api.get("/api/vms").status_code == 401
    assert api.get("/api/auth/me").status_code == 401


def test_assign_list_stop_delete(client):
    api, stub, session_factory = client
    token = login(api)
    headers = {"Authorization": f"Bearer {token}"}
    created = api.post("/api/vms", headers=headers)
    assert created.status_code == 201
    vmid = created.json()["vmid"]
    assert created.json()["status"] == "running"
    assert api.get("/api/vms", headers=headers).json()[0]["vmid"] == vmid
    stopped = api.post(f"/api/vms/{vmid}/stop", headers=headers)
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "stopped"
    deleted = api.delete(f"/api/vms/{vmid}", headers=headers)
    assert deleted.status_code == 204
    with session_factory() as db:
        assert db.scalar(select(VMAssignment).where(VMAssignment.vmid == vmid)) is None
    assert ("delete", vmid) in stub.calls


def test_ownership_is_enforced(client):
    api, _, _ = client
    token = login(api)
    created = api.post("/api/vms", headers={"Authorization": f"Bearer {token}"})
    vmid = created.json()["vmid"]
    other_token = login(api, "other")
    assert api.post(
        f"/api/vms/{vmid}/stop", headers={"Authorization": f"Bearer {other_token}"}
    ).status_code == 403


def test_vnc_endpoint_shape(client):
    api, _, _ = client
    token = login(api)
    headers = {"Authorization": f"Bearer {token}"}
    vmid = api.post("/api/vms", headers=headers).json()["vmid"]
    response = api.get(f"/api/vms/{vmid}/vnc", headers=headers)
    assert response.status_code == 200
    assert response.json() == {
        "ticket": "ticket-for-test",
        "port": 5901,
        "ws_path": f"/api/vms/{vmid}/ws",
        "password": "ticket-for-test",
    }


def test_templates_endpoint_and_explicit_assignment(client, monkeypatch):
    api, stub, _ = client
    settings = Settings(templates="9000:Ubuntu 22.04, 9001:Debian 12")
    monkeypatch.setattr(vms_router, "get_settings", lambda: settings)
    monkeypatch.setattr(templates_router, "get_settings", lambda: settings)
    token = login(api)
    headers = {"Authorization": f"Bearer {token}"}
    assert api.get("/api/templates", headers=headers).json() == [
        {"vmid": 9000, "label": "Ubuntu 22.04"},
        {"vmid": 9001, "label": "Debian 12"},
    ]
    response = api.post("/api/vms", headers=headers, json={"template_vmid": 9001})
    assert response.status_code == 201
    body = response.json()
    assert body["template_vmid"] == 9001
    assert body["template_label"] == "Debian 12"
    assert stub.calls[0][3] == 9001


def test_unknown_template_is_rejected(client):
    api, _, _ = client
    token = login(api)
    response = api.post(
        "/api/vms", headers={"Authorization": f"Bearer {token}"}, json={"template_vmid": 9999}
    )
    assert response.status_code == 400
    assert "Unknown template VMID" in response.json()["detail"]


def test_assignment_without_body_uses_default_template(client, monkeypatch):
    api, stub, _ = client
    settings = Settings(templates="9000:Ubuntu 22.04,9001:Debian 12")
    monkeypatch.setattr(vms_router, "get_settings", lambda: settings)
    token = login(api)
    response = api.post("/api/vms", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 201
    assert response.json()["template_vmid"] == 9000
    assert stub.calls[0][3] == 9000


def test_user_can_create_multiple_vms(client):
    api, _, _ = client
    token = login(api)
    headers = {"Authorization": f"Bearer {token}"}
    first = api.post("/api/vms", headers=headers)
    second = api.post("/api/vms", headers=headers)
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["vmid"] != second.json()["vmid"]
    assert len(api.get("/api/vms", headers=headers).json()) == 2


def test_listing_drops_assignments_missing_in_proxmox(client):
    api, stub, session_factory = client
    token = login(api)
    headers = {"Authorization": f"Bearer {token}"}
    vmid = api.post("/api/vms", headers=headers).json()["vmid"]
    stub.missing.add(vmid)
    assert api.get("/api/vms", headers=headers).json() == []
    with session_factory() as db:
        assert db.scalar(select(VMAssignment).where(VMAssignment.vmid == vmid)) is None


@pytest.mark.parametrize("path", ["start", "stop"])
def test_power_actions_drop_assignments_missing_in_proxmox(client, path):
    api, stub, session_factory = client
    token = login(api)
    headers = {"Authorization": f"Bearer {token}"}
    vmid = api.post("/api/vms", headers=headers).json()["vmid"]
    stub.missing.add(vmid)
    response = api.post(f"/api/vms/{vmid}/{path}", headers=headers)
    assert response.status_code == 404
    with session_factory() as db:
        assert db.scalar(select(VMAssignment).where(VMAssignment.vmid == vmid)) is None


def test_delete_succeeds_when_vm_already_gone(client):
    api, stub, session_factory = client
    token = login(api)
    headers = {"Authorization": f"Bearer {token}"}
    vmid = api.post("/api/vms", headers=headers).json()["vmid"]
    stub.missing.add(vmid)
    assert api.delete(f"/api/vms/{vmid}", headers=headers).status_code == 204
    with session_factory() as db:
        assert db.scalar(select(VMAssignment).where(VMAssignment.vmid == vmid)) is None


def test_vnc_drops_assignment_missing_in_proxmox(client):
    api, stub, session_factory = client
    token = login(api)
    headers = {"Authorization": f"Bearer {token}"}
    vmid = api.post("/api/vms", headers=headers).json()["vmid"]
    stub.missing.add(vmid)
    assert api.get(f"/api/vms/{vmid}/vnc", headers=headers).status_code == 404
    with session_factory() as db:
        assert db.scalar(select(VMAssignment).where(VMAssignment.vmid == vmid)) is None


@pytest.mark.parametrize(
    "query",
    ["port=5901&vncticket=ticket", "port=5901&vncticket=ticket&token=invalid"],
)
def test_vnc_websocket_closes_without_valid_token(client, query):
    api, _, _ = client
    with pytest.raises(WebSocketDisconnect) as error:
        with api.websocket_connect(f"/api/vms/101/ws?{query}") as websocket:
            websocket.receive()
    assert error.value.code == 4401


def test_vnc_websocket_closes_for_non_owner(client):
    api, _, _ = client
    owner_token = login(api)
    vmid = api.post("/api/vms", headers={"Authorization": f"Bearer {owner_token}"}).json()["vmid"]
    other_token = login(api, "other")
    with pytest.raises(WebSocketDisconnect) as error:
        with api.websocket_connect(
            f"/api/vms/{vmid}/ws?port=5901&vncticket=ticket&token={other_token}"
        ) as websocket:
            websocket.receive()
    assert error.value.code == 4403
