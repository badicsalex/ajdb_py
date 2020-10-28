from flask.testing import FlaskClient


def test_index(client: FlaskClient) -> None:
    response = client.get('/')
    assert "Alex Jogi Adatbázisa" in response.data.decode('utf-8')
