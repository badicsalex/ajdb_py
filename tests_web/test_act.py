from flask.testing import FlaskClient
from ajdb.structure import ActSet


def test_act_invalid(client: FlaskClient, fake_db: ActSet) -> None:
    _ = fake_db
    response = client.get('/act/2020. évi XX. törvény')
    assert response.status_code == 404


def test_act_valid(client: FlaskClient, fake_db: ActSet) -> None:
    response = client.get('/act/2020. évi XD. törvény')
    response_str = response.data.decode('utf-8')
    act = fake_db.act('2020. évi XD. törvény')
    assert act.identifier in response_str
    assert act.subject in response_str
    assert act.preamble in response_str
    assert act.article("3").paragraph("1").text in response_str
