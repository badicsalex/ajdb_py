import pytest

from flask.testing import FlaskClient
from ajdb.structure import ActSet


def test_act_valid(client: FlaskClient, fake_db: ActSet) -> None:
    response = client.get('/act/2020. évi XD. törvény')
    response_str = response.data.decode('utf-8')
    act = fake_db.act('2020. évi XD. törvény')
    assert act.identifier in response_str
    assert act.subject in response_str
    assert act.preamble in response_str
    assert act.article("3").paragraph("1").text in response_str


def test_snippet_valid(client: FlaskClient, fake_db: ActSet) -> None:
    response = client.get('/snippet/2020. évi XD. törvény/3_1__')
    response_str = response.data.decode('utf-8')
    act = fake_db.act('2020. évi XD. törvény')
    assert act.article("3").paragraph("1").text in response_str
    assert act.article("3").paragraph("2").text not in response_str

    response = client.get('/snippet/2020. évi XD. törvény/3_1-2__')
    response_str = response.data.decode('utf-8')
    assert act.article("3").paragraph("1").text in response_str
    assert act.article("3").paragraph("2").text in response_str

    response = client.get('/snippet/2020. évi XD. törvény/3___')
    response_str = response.data.decode('utf-8')
    assert act.article("3").paragraph("1").text in response_str
    assert act.article("3").paragraph("2").text in response_str

    response = client.get('/snippet/2020. évi XD. törvény/2slashA___')
    response_str = response.data.decode('utf-8')
    assert act.article("2/A").paragraph().text in response_str


INVALID_CASES = (
    ('/act/2020. évi XX. törvény', 404),
    ('/act/Fully invalid', 404),  # TODO: Maybe 400?
    ('/snippet/2020. évi XD. törvény/4___', 404),
    ('/snippet/2020. évi XD. törvény/4-5___', 404),
    ('/snippet/2018. évi XD. törvény/3___', 404),
    ('/snippet/2020. évi XD. törvény/3_4-5__', 404),
    ('/snippet/2020. évi XD. törvény/___', 400),
    ('/snippet/2020. évi XD. törvény/3____', 400),
    ('/snippet/2020. évi XD. törvény/3__', 400),

    ('/snippet/2020. évi XD. törvény/INVALID', 400),
    ('/snippet/2020. évi XD. törvény/.____', 400),
    ('/snippet/2020. évi XD. törvény/1-.____', 400),
    ('/snippet/2020. évi XD. törvény/3_.__', 404),
    ('/snippet/2020. évi XD. törvény/3_1_._', 404),
    ('/snippet/2020. évi XD. törvény/3_5-.__', 404),
    ('/snippet/2020. évi XD. törvény/3_1_1-._', 404),

    # Paragraph doesn't have children
    ('/snippet/2020. évi XD. törvény/3_1_c_', 404),
    ('/snippet/2020. évi XD. törvény/3_1_1_', 404),
    ('/snippet/2020. évi XD. törvény/3_1_c-f_', 404),
    ('/snippet/2020. évi XD. törvény/3_1_1-2_', 404),
)


@pytest.mark.parametrize("url,expected_code", INVALID_CASES)
def test_act_invalid(client: FlaskClient, fake_db: ActSet, url: str, expected_code: int) -> None:
    _ = fake_db
    response = client.get(url)
    assert response.status_code == expected_code
