from fastapi.testclient import TestClient
from datapilot.main import app


client = TestClient(app)
VALID_UUID = "00000000-0000-0000-0000-000000000000"


def test_health_check():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "DataPilot",
        "version": "0.1.0",
    }


def test_preview_rejects_zero_limit():
    response = client.get(
        f"/datasets/{VALID_UUID}/preview",
        params={"limit": 0},
    )
    assert response.status_code == 422


def test_summary_rejects_invalid_dataset_id():
    response = client.get(
        "/datasets/not-a-valid-uuid/summary"
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "dataset_id格式错误"