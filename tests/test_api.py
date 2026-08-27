from sqlalchemy import select

from app.models import VMAssignment
from tests.conftest import login


def test_login_jwt_and_me(client):
    api, _, _ = client
    token = login(api)
    response = api.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["username"] == "intern"


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
