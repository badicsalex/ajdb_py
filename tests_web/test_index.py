from flask.testing import FlaskClient
from ajdb.structure import ActSet


def test_index(client: FlaskClient, fake_db: ActSet) -> None:
    response = client.get('/')
    response_str = response.data.decode('utf-8')
    assert "Alex Jogi Adatbázisa" in response_str
    assert fake_db.acts[0].identifier in response_str
