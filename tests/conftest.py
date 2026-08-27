import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base, get_db
from app.main import app
from app.models import User, VMAssignment
from app.proxmox import ProxmoxVMNotFound, get_proxmox_service
from app.security import hash_password


@pytest.fixture
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    with TestingSession() as db:
        db.add(User(username="owner", password_hash=hash_password("password")))
        db.commit()
        yield db
    Base.metadata.drop_all(engine)


class StubProxmox:
    def __init__(self):
        self.calls: list[tuple] = []
        self.next_id = 101
        self.statuses: dict[int, str] = {}
        self.missing: set[int] = set()

    def _check_exists(self, vmid: int) -> None:
        if vmid in self.missing:
            raise ProxmoxVMNotFound(vmid, f"ВМ {vmid} больше не существует в Proxmox")

    def next_free_vmid(self, db=None) -> int:
        used = set(db.scalars(select(VMAssignment.vmid)).all()) if db else set()
        while self.next_id in used:
            self.next_id += 1
        return self.next_id

    def clone_template(self, vmid, name, template_vmid=None):
        self.calls.append(("clone", vmid, name, template_vmid))
        self.statuses[vmid] = "stopped"

    def start(self, vmid):
        self._check_exists(vmid)
        self.calls.append(("start", vmid))
        self.statuses[vmid] = "running"

    def stop(self, vmid):
        self._check_exists(vmid)
        self.calls.append(("stop", vmid))
        self.statuses[vmid] = "stopped"

    def delete(self, vmid):
        self._check_exists(vmid)
        self.calls.append(("delete", vmid))
        self.statuses.pop(vmid, None)

    def status(self, vmid):
        self._check_exists(vmid)
        return {"status": self.statuses.get(vmid, "unknown")}

    def vncproxy(self, vmid):
        self._check_exists(vmid)
        self.calls.append(("vncproxy", vmid))
        return {"ticket": "ticket-for-test", "port": 5901}


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    stub = StubProxmox()

    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_proxmox_service] = lambda: stub
    with TestingSession() as db:
        db.add(User(username="intern", password_hash=hash_password("password")))
        db.add(User(username="other", password_hash=hash_password("password")))
        db.commit()
    with TestClient(app) as test_client:
        yield test_client, stub, TestingSession
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)


def login(client, username="intern"):
    response = client.post("/api/auth/login", json={"username": username, "password": "password"})
    assert response.status_code == 200
    return response.json()["access_token"]
