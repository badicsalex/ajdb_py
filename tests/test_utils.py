# Copyright 2020, Alex Badics, All Rights Reserved

from ajdb.utils import LruDict


def test_lru_dict() -> None:
    lru_dict: LruDict[int, str] = LruDict(5)
    lru_dict[1] = 'a'
    lru_dict[2] = 'b'
    lru_dict[3] = 'c'
    lru_dict[4] = 'd'
    lru_dict[5] = 'e'
    assert ''.join(lru_dict.values()) == 'abcde'
    lru_dict[6] = 'f'
    assert ''.join(lru_dict.values()) == 'bcdef'
    assert lru_dict[3] == 'c'
    assert ''.join(lru_dict.values()) == 'bdefc'

    lru_dict.update([(5, 'E'), (11, 'x')])

    assert ''.join(lru_dict.values()) == 'dfcEx'
    lru_dict[3] = 'C'
    assert ''.join(lru_dict.values()) == 'dfExC'
    assert lru_dict[5] == 'E'
    assert ''.join(lru_dict.values()) == 'dfxCE'
    del lru_dict[4]
    assert ''.join(lru_dict.values()) == 'fxCE'

    assert lru_dict.get(23) is None
    assert lru_dict.get(11) == 'x'
    assert ''.join(lru_dict.values()) == 'fCEx'
