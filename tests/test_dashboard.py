def test_dashboard_page_renders_cards_and_chat(client):
    response = client.get("/")
    assert response.status_code == 200
    body = response.data.decode()
    assert "Planned Absences" in body
    assert "Future Events" in body
    assert "Onboarding" in body
    assert 'id="dash-chat"' in body
