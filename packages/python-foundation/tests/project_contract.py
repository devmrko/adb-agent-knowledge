"""Portable business HTTP contract; accepts an authenticated httpx-compatible client."""


def verify_project_contract(client):
    response = client.post("/api/v1/projects", json={"name": "Shared contract"})
    assert response.status_code == 201, response.text
    created = response.json()
    assert set(created) == {"id", "name", "version"}
    assert created["version"] == 0
    assert response.headers["location"].endswith("/api/v1/projects/" + created["id"])
    path = "/api/v1/projects/" + created["id"]
    assert client.get(path).json() == created
    listing = client.get("/api/v1/projects?page=0").json()
    assert set(listing) == {"items", "page", "size", "total"}
    assert listing["page"] == 0 and listing["size"] == 20
    assert any(item["id"] == created["id"] for item in listing["items"])
    renamed = client.put(path, json={"name": "Updated", "version": 0})
    assert renamed.status_code == 200 and renamed.json()["version"] == 1
    conflict = client.put(path, json={"name": "Stale", "version": 0})
    assert conflict.status_code == 409 and conflict.json()["code"] == "PROJECT_VERSION_CONFLICT"
    invalid = client.post("/api/v1/projects", json={"name": " "})
    assert invalid.status_code == 400 and invalid.json()["code"] == "VALIDATION_FAILED"
    assert client.delete(path).status_code == 204
    missing = client.get(path)
    assert missing.status_code == 404 and missing.json()["code"] == "PROJECT_NOT_FOUND"
    assert missing.headers["x-request-id"] == missing.json()["requestId"]
    assert missing.headers["content-type"].startswith("application/problem+json")
