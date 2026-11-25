import pytest


@pytest.mark.parametrize("encoding", ["urlencoded", "multipart"])
def test_login_accepts_form_credentials(client, encoding):
    api, _, _ = client
    credentials = {"username": "intern", "password": "password"}
    if encoding == "multipart":
        body = {"files": {key: (None, value) for key, value in credentials.items()}}
    else:
        body = {"data": credentials}

    response = api.post("/api/auth/login", **body)

    assert response.status_code == 200
    token = response.json()["access_token"]
    authenticated = api.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert authenticated.status_code == 200
    assert authenticated.json()["username"] == "intern"
