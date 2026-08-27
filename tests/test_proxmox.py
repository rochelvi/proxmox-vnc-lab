from app.config import Settings
from app.proxmox import ProxmoxService


class Resources:
    def get(self, **kwargs):
        return [{"vmid": 100}, {"vmid": 102}]


class Cluster:
    resources = Resources()


class FakeAPI:
    cluster = Cluster()


def test_vmid_allocation_skips_pve_and_database_ids(db_session):
    settings = Settings(
        pve_host="pve",
        clone_vmid_min=100,
        clone_vmid_max=103,
        pve_token_id="u!t",
        pve_token_secret="secret",
    )
    service = ProxmoxService(settings)
    service._api = FakeAPI()
    from app.models import VMAssignment

    db_session.add(VMAssignment(user_id=1, vmid=101, node="pve", name="reserved", status="stopped"))
    db_session.commit()
    assert service.next_free_vmid(db_session) == 103
