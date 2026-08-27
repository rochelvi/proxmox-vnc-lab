from app.config import Settings
from app.proxmox import ProxmoxService, ProxmoxVMNotFound


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


def test_missing_vm_error_is_mapped_to_vm_not_found():
    service = ProxmoxService(Settings(pve_host="pve"))
    error = service._error(
        RuntimeError("task failed: unable to find configuration file for VM 1000 on node 'pve-ctf'"),
        vmid=1000,
    )
    assert isinstance(error, ProxmoxVMNotFound)
    assert error.status_code == 404
    assert error.vmid == 1000


def test_other_errors_stay_bad_gateway():
    service = ProxmoxService(Settings(pve_host="pve"))
    error = service._error(TimeoutError("Proxmox task timed out"), vmid=1000)
    assert not isinstance(error, ProxmoxVMNotFound)
    assert error.status_code == 502
