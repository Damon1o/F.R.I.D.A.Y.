def test_dashboard_page_renders(client):
    response = client.get("/")
    assert response.status_code == 200
