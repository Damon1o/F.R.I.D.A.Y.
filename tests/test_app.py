def test_app_boots(client):
    response = client.get("/calendar")
    assert response.status_code == 200
