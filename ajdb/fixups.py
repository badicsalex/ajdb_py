# Copyright 2020, Alex Badics, All Rights Reserved
from typing import Dict, Any
import attr

from hun_law.structure import Act, SubArticleElement, Reference, EnforcementDate, DaysAfterPublication
from hun_law.utils import Date


REPLACEMENT_FIXUPS: Dict[Reference, Dict[str, Any]] = {
    Reference('2013. évi CXXXV. törvény', '21'): {
        # E törvény a kihirdetését követő napon lép hatályba.
        # E törvény 15. § (2) bekezdése és 15. § (4) bekezdése 2013. szeptember 1-jén
        # a 15. § (9) bekezdése 2013. november 1-jén lép hatályba.
        # E törvény 15. § (10) bekezdése 2016. július 1-jén
        # a 15. § (18) bekezdése 2014. január 1-jén lép hatályba.
        # A törvény 14. § (1) bekezdés 2. mondata a jelen törvény hatályba lépését követő 45. napon – vagy ha ez munkaszüneti nap – akkor a következő munkanapon lép hatályba.
        "semantic_data": (
            EnforcementDate(position=None, date=DaysAfterPublication()),
            EnforcementDate(position=Reference(None, "15", "2"), date=Date(2013, 9, 1)),
            EnforcementDate(position=Reference(None, "15", "4"), date=Date(2013, 9, 1)),
            EnforcementDate(position=Reference(None, "15", "9"), date=Date(2013, 11, 1)),
            EnforcementDate(position=Reference(None, "15", "10"), date=Date(2016, 7, 1)),
            EnforcementDate(position=Reference(None, "15", "18"), date=Date(2014, 1, 1)),
            # TODO: the magic "second sentence of" thing.
        )
    },
    Reference('2013. évi CCXXXVIII. törvény', '93', '1'): {
        # Ez a törvény – a (2) bekezdésben meghatározott kivétellel – az országgyűlési képviselők 2014. évi általános választása kitűzésének napján lép hatályba.
        # https://www.keh.hu/sajtokozlemenyek/1833-X&pnr=1
        "semantic_data": (
            EnforcementDate(position=None, date=Date(2014, 1, 18)),
        )
    }
}


def fixup_applier(reference: Reference, sae: SubArticleElement) -> SubArticleElement:
    if reference in REPLACEMENT_FIXUPS:
        return attr.evolve(sae, **REPLACEMENT_FIXUPS[reference])
    return sae


def apply_fixups(act: Act) -> Act:
    return act.map_saes(fixup_applier)
