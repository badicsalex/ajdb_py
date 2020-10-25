# Copyright 2020, Alex Badics, All Rights Reserved
from pathlib import Path
# For typing only
from _pytest.monkeypatch import MonkeyPatch

import attr

from hun_law.structure import Act, Article, Book, Reference,\
    Paragraph, AlphabeticPoint, AlphabeticSubpoint, NumericPoint,\
    EnforcementDate, DaysAfterPublication
from hun_law.utils import Date
from hun_law import dict2object

from ajdb.config import AJDBConfig
from ajdb.structure import ActWMProxy, ArticleWMProxy, ArticleWM, ParagraphWM, AlphabeticPointWM, SaeMetadata
from ajdb.amender import ActConverter

from tests.utils import add_fake_semantic_data

TEST_ACT = Act(
    identifier="2345. évi XD. törvény",
    publication_date=Date(2345, 6, 7),
    subject="A tesztelésről",
    preamble="A tesztelés nagyon fontos, és egyben kötelező",
    children=(
        Book(identifier="1", title="Egyszerű dolgok"),
        Article(
            identifier="1:1",
            title="Az egyetlen cikk, aminek cime van.",
            children=(
                Paragraph(
                    text="Ez a törvény kihirdetését követő napon lép hatályba.",
                    semantic_data=(
                        EnforcementDate(position=None, date=DaysAfterPublication()),
                    )
                ),
            )
        ),
        Article(
            identifier="1:2",
            children=(
                Paragraph(
                    identifier="1",
                    text="Valami valami"
                ),
                Paragraph(
                    identifier="2",
                    intro="Egy felsorolás legyen",
                    wrap_up="minden esetben.",
                    children=(
                        AlphabeticPoint(
                            identifier="a",
                            text="többelemű"
                        ),
                        AlphabeticPoint(
                            identifier="b",
                            intro="kellően",
                            children=(
                                AlphabeticSubpoint(
                                    identifier="ba",
                                    text="átláthatatlan"
                                ),
                                AlphabeticSubpoint(
                                    identifier="bb",
                                    text="komplex"
                                ),
                            )
                        )
                    )
                ),
            )
        ),
        Book(identifier="2", title="Amended stuff in english"),
        Article(
            identifier="2:1",
            children=(
                Paragraph(
                    text="Nothing fancy yet"
                ),
            )
        ),
        Article(
            identifier="2:1/A",
            children=(
                Paragraph(
                    text="Added after the fact"
                ),
            )
        ),
        Article(
            identifier="2:2",
            children=(
                Paragraph(
                    identifier="1",
                    intro="This can legally be after 2:1/A. Also, ",
                    wrap_up="Can also be amended",
                    children=(
                        NumericPoint(
                            identifier="1",
                            text="Paragraphs",
                        ),
                        NumericPoint(
                            identifier="1a",
                            text="Numeric points",
                        ),
                        NumericPoint(
                            identifier="2",
                            text="Alphabetic points",
                        ),
                    )
                ),
            )
        ),
    )
)

TEST_ACT = add_fake_semantic_data(TEST_ACT)
TEST_ARTICLE = ArticleWM(
    identifier="2:3",
    children=(
        ParagraphWM(
            text="Added after the fact 2",
            semantic_data=(),
            outgoing_references=(),
            act_id_abbreviations=(),
            metadata=SaeMetadata()
        ),
    ),
)

TEST_POINT = AlphabeticPointWM(
    text="Changed point",
    semantic_data=(),
    outgoing_references=(),
    act_id_abbreviations=(),
    metadata=SaeMetadata()
)


def test_persistence_simple(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(AJDBConfig, "STORAGE_PATH", tmp_path)

    act = ActConverter.convert_hun_law_act(TEST_ACT)
    proxy = ActWMProxy.save_act(act)
    serialized_proxy = dict2object.to_dict(proxy, ActWMProxy)
    proxy = dict2object.to_object(serialized_proxy, ActWMProxy)
    assert proxy.act.to_simple_act() == TEST_ACT


def test_persistence_determinismy(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(AJDBConfig, "STORAGE_PATH", tmp_path)
    act = ActConverter.convert_hun_law_act(TEST_ACT)

    # This test might be a pain to maintain, but it's an important canary,
    # that shows if we broke all previous serializations

    article_proxy = ArticleWMProxy.save_article(TEST_ARTICLE)
    assert article_proxy.key == "bbe216b9ac07cde307fe725cf26a4265"

    proxy = ActWMProxy.save_act(act)
    assert proxy.key == "974241f76d9aade8956f239790f6affe"


def test_persistence_object_storage(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.setattr(AJDBConfig, "STORAGE_PATH", tmp_path)
    act = ActConverter.convert_hun_law_act(TEST_ACT)
    ActWMProxy.save_act(act)

    act_objects = tuple((tmp_path / 'acts').rglob('*.json.gz'))
    assert len(act_objects) == 1, "Act storage uses a single blob"
    article_objects = tuple((tmp_path / 'articles').rglob('*.json.gz'))
    assert len(article_objects) == 5, "Article storage uses as many blobs as there are articles"

    proxy = ActWMProxy.save_act(act)
    act_objects = tuple((tmp_path / 'acts').rglob('*.json.gz'))
    assert len(act_objects) == 1, "Resaving an Act does not increase blob count"
    article_objects = tuple((tmp_path / 'articles').rglob('*.json.gz'))
    assert len(article_objects) == 5, "Resaving an Act does not increase article blob count"

    new_act = attr.evolve(proxy.act, children=proxy.act.children + (TEST_ARTICLE, ))
    print(new_act)
    ActWMProxy.save_act(new_act)
    act_objects = tuple((tmp_path / 'acts').rglob('*.json.gz'))
    assert len(act_objects) == 2, "Changing an Act creates new blob"
    article_objects = tuple((tmp_path / 'articles').rglob('*.json.gz'))
    assert len(article_objects) == 6, "Adding a new Article only adds the article blob"

    new_act_2 = new_act.map_saes(lambda _r, _sae: TEST_POINT, Reference("2345. évi XD. törvény", '1:2', '2', 'a'))
    ActWMProxy.save_act(new_act_2)
    act_objects = tuple((tmp_path / 'acts').rglob('*.json.gz'))
    assert len(act_objects) == 3, "Changing an Act creates new blob"
    article_objects = tuple((tmp_path / 'articles').rglob('*.json.gz'))
    assert len(article_objects) == 7, "Changing an Article only adds that article's blob"
