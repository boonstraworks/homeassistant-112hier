"""Tests voor de filterregels (custom_components/112hier/filters.py).

Draaien zonder Home Assistant: `pytest tests/`. De map van de integratie heet
"112hier" en begint met een cijfer, dus die is niet als pakket te importeren;
we zetten hem daarom op het pad en laden filters.py los.
"""

import sys
from pathlib import Path

MAP = Path(__file__).resolve().parents[1] / "custom_components" / "112hier"
sys.path.insert(0, str(MAP))

import filters  # noqa: E402
from filters import (  # noqa: E402
    Filter,
    capcode9,
    gemeenten,
    gemeenten_buiten_gebied,
    ongeldige_capcodes,
    raakt,
)

ALLE_DIENSTEN = ["brandweer", "ambulance", "politie", "knrm"]
DAM = (52.3731, 4.8926)


def melding(**kw):
    m = {
        "id": 1,
        "bericht": "P 1 BDH-01 Brand woning Damrak Amsterdam 131234",
        "leesbaar": "Brandweer · brand woning",
        "dienst": "brandweer",
        "urgentie": "P 1",
        "plaats": "Amsterdam",
        "gemeente": "Amsterdam",
        "regio_code": "VR13",
        "locatie": {"lat": DAM[0], "lon": DAM[1]},
        "capcodes": ["001420999"],
    }
    m.update(kw)
    return m


# ── eigen post: OF, niet EN ───────────────────────────────────────────────

def test_eigen_post_met_gebied_vraagt_of_aan_de_server():
    f = Filter(regios=["VR13"], capcodes=["1420999"], diensten=ALLE_DIENSTEN)
    p = f.params(None)
    assert p["regio"] == "VR13"
    assert p["ook_capcodes"] == "001420999"
    assert "capcodes" not in p


def test_eigen_post_zonder_gebied_alleen_de_post():
    f = Filter(capcodes=["001420999"], diensten=ALLE_DIENSTEN)
    p = f.params(None)
    assert p["capcodes"] == "001420999"
    assert "ook_capcodes" not in p


def test_eigen_post_zonder_gebied_niet_op_dienst_of_trefwoord_bij_de_server():
    # De reddingsboot van je post valt onder KNRM; die moet ook door als je
    # alleen Brandweer aanvinkte.
    f = Filter(capcodes=["1420999"], diensten=["brandweer"], bevat=["brand"])
    p = f.params(None)
    assert "dienst" not in p
    assert "bevat" not in p
    assert f.reden(melding(dienst="knrm", bericht="KNRM boot")) == "eigen post (capcode 1420999)"


def test_eigen_post_komt_door_buiten_regio_en_dienst():
    f = Filter(regios=["VR13"], diensten=["ambulance"], capcodes=["1420999"])
    m = melding(regio_code="VR15", dienst="brandweer", capcodes=["1420999"])
    assert f.reden(m) == "eigen post (capcode 1420999)"


def test_negeren_wint_van_eigen_post():
    f = Filter(capcodes=["1420999"], negeer=["proefalarm"])
    m = melding(bericht="Proefalarm kazerne", capcodes=["1420999"])
    assert f.reden(m) is None


# ── regio, provincie, gemeente ───────────────────────────────────────────

def test_regio_reden_en_buiten_regio_valt_af():
    f = Filter(regios=["VR13"])
    assert f.reden(melding()) == "regio Amsterdam-Amstelland"
    assert f.reden(melding(regio_code="VR15")) is None


def test_provincie_wordt_regio_lijst():
    f = Filter(provincies=["Noord-Holland"])
    assert f.alle_regios == ["VR10", "VR11", "VR12", "VR13", "VR14"]
    assert f.lokaal_nodig  # meerdere regio's: breed ophalen, hier filteren
    assert "regio" not in f.params(None)
    assert f.reden(melding()) == "provincie Noord-Holland (regio Amsterdam-Amstelland)"
    assert f.reden(melding(regio_code="VR15")) is None


def test_regio_zonder_plek_zegt_dat_hij_van_de_meldkamer_komt():
    f = Filter(regios=["VR13"])
    r = f.reden(melding(gemeente=None))
    assert "regio van de meldkamer" in r


def test_gemeente_een_naar_server_meer_lokaal():
    een = Filter(gemeenten=["Amsterdam"])
    assert een.params(None)["gemeente"] == "Amsterdam"
    assert een.reden(melding()) == "gemeente Amsterdam"
    assert een.reden(melding(gemeente="Zaanstad")) is None
    twee = Filter(gemeenten=["Amsterdam", "Zaanstad"])
    assert "gemeente" not in twee.params(None)
    assert twee.lokaal_nodig


def test_gemeentenlijst_compleet():
    g = gemeenten()
    assert len(g) == 342
    assert g["Amsterdam"] == "VR13"
    assert g["'s-Gravenhage"] == "VR15"


def test_gemeente_buiten_gekozen_provincie():
    assert gemeenten_buiten_gebied(["Almere"], [], ["Noord-Holland"]) == ["Almere"]
    assert gemeenten_buiten_gebied(["Amsterdam"], [], ["Noord-Holland"]) == []
    assert gemeenten_buiten_gebied(["Almere"], [], []) == []  # geen gebied gekozen


# ── straal en punt ───────────────────────────────────────────────────────

def test_straal_gaat_afgerond_en_ruimer_naar_de_server():
    f = Filter(punt=(52.3731234, 4.8926543), straal=5)
    p = f.params(None)
    assert p["lat"] == "52.37" and p["lon"] == "4.89"
    assert p["straal"] == "6"


def test_straal_rekent_exact_na():
    f = Filter(punt=DAM, straal=5)
    dichtbij = melding(locatie={"lat": DAM[0] + 0.01, "lon": DAM[1]})   # ~1,1 km
    ver = melding(locatie={"lat": DAM[0] + 0.06, "lon": DAM[1]})        # ~6,7 km
    zonder = melding(locatie=None)
    assert f.reden(dichtbij).startswith("binnen 1,1 km")
    assert f.reden(ver) is None
    assert f.reden(zonder) is None


def test_straal_zonder_punt_doet_niets():
    # __init__.py vult dan het huis in; zonder punt is er geen straalfilter.
    f = Filter(straal=5)
    assert "straal" not in f.params(None)
    assert f.reden(melding()).startswith("geen gebiedsfilter")


# ── diensten, spoed, trefwoorden ─────────────────────────────────────────

def test_alle_diensten_is_geen_filter():
    f = Filter(diensten=ALLE_DIENSTEN)
    assert "dienst" not in f.params(None)
    assert not f.lokaal_nodig
    assert f.params(None)["limiet"] == "10"


def test_een_dienst_naar_server_en_lokaal_gecontroleerd():
    f = Filter(diensten=["ambulance"])
    assert f.params(None)["dienst"] == "ambulance"
    assert f.reden(melding(dienst="brandweer")) is None


def test_alleen_spoed():
    f = Filter(alleen_spoed=True)
    assert f.reden(melding(urgentie="P 2")) is None
    assert f.reden(melding(urgentie="A1")) is not None


def test_trefwoord_met_jokerteken_lokaal():
    f = Filter(bevat=["*Damrak*"])
    assert "bevat" not in f.params(None)
    assert f.lokaal_nodig
    assert f.reden(melding()) == "geen gebiedsfilter: heel Nederland · trefwoord '*Damrak*'"


def test_trefwoord_zonder_jokerteken_naar_server():
    f = Filter(bevat=["reanimatie", "brand"])
    assert f.params(None)["bevat"] == "reanimatie,brand"


def test_geen_filter_heel_nederland():
    assert Filter().reden(melding()) == "geen gebiedsfilter: heel Nederland"


# ── bijhalen ─────────────────────────────────────────────────────────────

def test_sinds_vraagt_meer_op():
    p = Filter().params(1234)
    assert p["sinds"] == "1234" and p["limiet"] == "100"


# ── invoer controleren ───────────────────────────────────────────────────

def test_ongeldige_capcodes():
    assert ongeldige_capcodes("1420999, 001420999") == []
    assert ongeldige_capcodes("Alkmaar") == ["Alkmaar"]
    assert ongeldige_capcodes("1420999, 12") == ["12"]
    assert ongeldige_capcodes("") == []


# ── hulpjes ──────────────────────────────────────────────────────────────

def test_capcode9():
    assert capcode9("1420999") == "001420999"
    assert capcode9("0001420999") == "001420999"
    assert capcode9(" 001420999 ") == "001420999"


def test_raakt_geeft_het_woord_terug():
    assert raakt("Brand woning", ["reanimatie", "brand"]) == "brand"
    assert raakt("Brand woning", ["*woning"]) == "*woning"
    assert raakt("Brand woning", ["reanimatie"]) is None


def test_provincies_dekken_alle_regios_precies_een_keer():
    codes = [c for lijst in filters.PROVINCIES.values() for c in lijst]
    assert sorted(codes) == sorted(filters.REGIOS)
    assert len(codes) == len(set(codes)) == 25
