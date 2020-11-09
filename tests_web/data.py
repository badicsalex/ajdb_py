import attr

from hun_law.structure import Part
from hun_law.utils import Date
from ajdb.structure import ActWM, ArticleWM, ParagraphWM, AlphabeticPointWM, SaeMetadata

TEST_ACT1 = ActWM(
    identifier="2020. évi XD. törvény",
    subject="A tesztelésről",
    preamble="A tesztelés fontosssága miatt tesztelős törvényt hoztunk.",
    publication_date=Date(2020, 1, 1),
    interesting_dates=(),
    children=(
        Part(identifier="1", title="", special=True),
        ArticleWM(
            identifier="1",
            children=(
                ParagraphWM(
                    text="A teszt törvénynek vannak bekezdései.",
                    metadata=SaeMetadata(),
                ),
            )
        ),
        Part(identifier="2", title="", special=True),
        ArticleWM(
            identifier="2",
            children=(
                ParagraphWM(
                    text="A teszt törvénynek vannak bekezdései.",
                    metadata=SaeMetadata(),
                ),
            )
        ),
        ArticleWM(
            identifier="2/A",
            children=(
                ParagraphWM(
                    text="A teszt törvényben vannak '/'-es idk.",
                    metadata=SaeMetadata(),
                ),
            )
        ),
        ArticleWM(
            identifier="3",
            children=(
                ParagraphWM(
                    identifier="1",
                    text="A teszt törvénynek van valamiféle bekezdései.",
                    metadata=SaeMetadata(),
                ),
                ParagraphWM(
                    identifier="2",
                    text="A teszt törvénynek különleges bekezdései.",
                    metadata=SaeMetadata(),
                ),
            )
        ),
        ArticleWM(
            identifier="4",
            children=(
                ParagraphWM(
                    intro="Fontosak az",
                    children=(
                        AlphabeticPointWM(
                            identifier="a",
                            text="pontok, és az",
                            metadata=SaeMetadata(),
                        ),
                        AlphabeticPointWM(
                            identifier="b",
                            text="alpontok",
                            metadata=SaeMetadata(),
                        ),
                    ),
                    wrap_up="helyes megjelenítése.",
                    metadata=SaeMetadata(),
                ),
            )
        ),
    )
)

TEST_ACT2 = attr.evolve(TEST_ACT1, identifier="2019. évi XD. törvény", publication_date=Date(2019, 1, 1))
