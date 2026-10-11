"""De filterregels, los van Home Assistant.

Hier staat wat er wél en niet doorkomt, en waarom. Los van de rest zodat het te
testen is zonder Home Assistant (zie tests/test_filters.py), en zodat er één
plek is die beslist: dezelfde code die een melding doorlaat, schrijft ook op
wáárom. Dat staat dan als `filter_reden` bij de melding — het antwoord op de
vraag die gebruikers het vaakst stellen: "waarom krijg ik deze?"
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from fnmatch import fnmatch
from functools import lru_cache
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

try:  # in Home Assistant
    from .const import DIENSTEN, SPOED_CODES
except ImportError:  # in de tests, zonder pakket
    from const import DIENSTEN, SPOED_CODES  # type: ignore[no-redef]

# De 25 veiligheidsregio's. Vast in de code: ze veranderen zelden, en zo werkt
# het instellen ook als de feed even niet bereikbaar is.
REGIOS: dict[str, str] = {
    "VR01": "Groningen", "VR02": "Fryslân", "VR03": "Drenthe",
    "VR04": "IJsselland", "VR05": "Twente", "VR06": "Noord- en Oost-Gelderland",
    "VR07": "Gelderland-Midden", "VR08": "Gelderland-Zuid", "VR09": "Utrecht",
    "VR10": "Noord-Holland-Noord", "VR11": "Zaanstreek-Waterland",
    "VR12": "Kennemerland", "VR13": "Amsterdam-Amstelland",
    "VR14": "Gooi en Vechtstreek", "VR15": "Haaglanden", "VR16": "Hollands-Midden",
    "VR17": "Rotterdam-Rijnmond", "VR18": "Zuid-Holland-Zuid", "VR19": "Zeeland",
    "VR20": "Midden- en West-Brabant", "VR21": "Brabant-Noord",
    "VR22": "Brabant-Zuidoost", "VR23": "Limburg-Noord", "VR24": "Limburg-Zuid",
    "VR25": "Flevoland",
}

# Mensen denken in provincies, de meldkamers in veiligheidsregio's. Elke
# veiligheidsregio ligt binnen één provincie, dus een provincie is gewoon een
# rijtje regio's.
PROVINCIES: dict[str, list[str]] = {
    "Groningen": ["VR01"],
    "Fryslân": ["VR02"],
    "Drenthe": ["VR03"],
    "Overijssel": ["VR04", "VR05"],
    "Flevoland": ["VR25"],
    "Gelderland": ["VR06", "VR07", "VR08"],
    "Utrecht": ["VR09"],
    "Noord-Holland": ["VR10", "VR11", "VR12", "VR13", "VR14"],
    "Zuid-Holland": ["VR15", "VR16", "VR17", "VR18"],
    "Zeeland": ["VR19"],
    "Noord-Brabant": ["VR20", "VR21", "VR22"],
    "Limburg": ["VR23", "VR24"],
}

# De straal gaat afgerond naar de server (zie Filter.params). Twee decimalen is
# hooguit ~0,7 km verschuiving; de server zoekt daarom iets ruimer, en wij
# rekenen hier de exacte afstand na.
_PUNT_DECIMALEN = 2
_STRAAL_MARGE_KM = 1.0

# Hoe oud een melding mag zijn voordat we hem "ingehaald" noemen: na een
# herstart of een internetstoring komen er oude meldingen binnen, en die wil je
# niet als nieuw op je telefoon.
INGEHAALD_NA_SECONDEN = 600


@lru_cache(maxsize=1)
def gemeenten() -> dict[str, str]:
    """Alle gemeenten met hun veiligheidsregio, gespeld zoals in de meldingen."""
    pad = Path(__file__).with_name("gemeenten.json")
    return json.loads(pad.read_text(encoding="utf-8"))


def provincie_van_regio(code: str | None) -> str | None:
    for naam, codes in PROVINCIES.items():
        if code in codes:
            return naam
    return None


def afstand_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Hemelsbrede afstand in kilometers."""
    p1, l1, p2, l2 = map(radians, (lat1, lon1, lat2, lon2))
    a = sin((p2 - p1) / 2) ** 2 + cos(p1) * cos(p2) * sin((l2 - l1) / 2) ** 2
    return 2 * 6371 * asin(sqrt(a))


def raakt(tekst: str, patronen: list[str]) -> str | None:
    """Het eerste patroon dat op de tekst slaat, of None.

    Een gewoon woord zoekt als deel van de regel: "brand" vindt ook
    "schoorsteenbrand". Zet je er een * of ? in, dan geldt het als patroon over
    de hele regel — dezelfde schrijfwijze als de filterbestanden van de
    ontvangers die je zelf draait: `A1 *Epe*`.
    """
    laag = tekst.lower()
    for p in patronen:
        p_laag = p.lower()
        if "*" in p_laag or "?" in p_laag:
            if fnmatch(laag, p_laag):
                return p
        elif p_laag in laag:
            return p
    return None


def capcode9(c) -> str:
    """Capcodes worden met en zonder voorloopnullen geschreven; de laatste negen cijfers zijn de pager."""
    cijfers = "".join(ch for ch in str(c) if ch.isdigit())
    return cijfers.zfill(9)[-9:]


def lijst(waarde) -> list[str]:
    """Komma-gescheiden invoer opknippen; lege stukken eruit."""
    if isinstance(waarde, (list, tuple)):
        return [str(x).strip() for x in waarde if str(x).strip()]
    return [deel.strip() for deel in str(waarde or "").split(",") if deel.strip()]


# De feed neemt hooguit zoveel capcodes per verzoek mee.
MAX_CAPCODES = 40


def ongeldige_capcodes(waarde) -> list[str]:
    """De stukken uit een capcodeveld die geen capcode zijn.

    Een capcode is 5 tot 10 cijfers. Wie er een plaatsnaam in typt, bedoelt
    "Zoek je post"; dat vangen we af in plaats van het stil te negeren — dan
    kreeg je namelijk heel Nederland terwijl de naam "eigen post" zei.
    """
    fout = []
    for deel in lijst(waarde):
        cijfers = "".join(ch for ch in deel if ch.isdigit())
        if any(ch.isalpha() for ch in deel) or not 5 <= len(cijfers) <= 10:
            fout.append(deel)
    return fout


def gemeenten_buiten_gebied(gekozen: list[str], regios: list[str], provincies: list[str]) -> list[str]:
    """Gemeenten die niet in de gekozen provincies of regio's liggen.

    Een gemeente en een provincie samen betekent "alleen die gemeente, en dan
    alleen als hij in die provincie ligt". Ligt hij erbuiten, dan komt er nooit
    iets door; dat melden we in het formulier in plaats van stil niets te tonen.
    """
    gebied = set(regios) | {c for p in provincies for c in PROVINCIES.get(p, [])}
    if not gebied:
        return []
    alle = gemeenten()
    return [g for g in gekozen if alle.get(g) not in gebied]


@dataclass
class Filter:
    """Wat iemand heeft ingesteld, en wat dat betekent voor elke melding."""

    regios: list[str] = field(default_factory=list)
    provincies: list[str] = field(default_factory=list)
    gemeenten: list[str] = field(default_factory=list)
    diensten: list[str] = field(default_factory=list)
    plaats: str | None = None
    punt: tuple[float, float] | None = None
    straal: float | None = None
    alleen_spoed: bool = False
    capcodes: list[str] = field(default_factory=list)
    bevat: list[str] = field(default_factory=list)
    negeer: list[str] = field(default_factory=list)
    negeer_capcodes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        # Een provincie is een rijtje regio's; samen met losse regio's één lijst.
        alle = list(dict.fromkeys(
            [*self.regios, *(c for p in self.provincies for c in PROVINCIES.get(p, []))]
        ))
        self._alle_regios = alle
        # Alle vier de diensten aangevinkt is hetzelfde als geen dienstfilter.
        self._diensten = [] if set(self.diensten) >= set(DIENSTEN) else list(self.diensten)
        self._capcodes = {capcode9(c) for c in self.capcodes if capcode9(c) != "000000000"}
        self._negeer_capcodes = {capcode9(c) for c in self.negeer_capcodes}

    # ── wat er naar de server gaat ─────────────────────────────────────────

    @property
    def alle_regios(self) -> list[str]:
        return self._alle_regios

    @property
    def gebied(self) -> bool:
        """Is er een gebied gekozen? Zo niet, dan is het heel Nederland."""
        return bool(self._alle_regios or self.gemeenten or self.plaats or self._straal_actief)

    @property
    def _straal_actief(self) -> bool:
        return bool(self.straal and self.punt)

    @property
    def lokaal_nodig(self) -> bool:
        """Moeten we breder ophalen en hier filteren?

        De feed kent per verzoek één regio, één dienst en één gemeente, en geen
        jokertekens. Bij meer keuzes halen we breder op; dan moet de limiet wel
        omhoog, anders blijft er na het filteren niets over.
        """
        return (
            len(self._alle_regios) > 1
            or len(self._diensten) > 1
            or len(self.gemeenten) > 1
            or any("*" in w or "?" in w for w in self.bevat)
        )

    @property
    def _alleen_post(self) -> bool:
        """Alleen een eigen post, zonder gebied."""
        return bool(self._capcodes) and not self.gebied

    def params(self, sinds: int | None) -> dict[str, str]:
        """De querystring voor /feed.json."""
        p: dict[str, str] = {}
        if sinds is not None:
            p["sinds"] = str(sinds)
            p["limiet"] = "100"
        else:
            p["limiet"] = "100" if self.lokaal_nodig else "10"
        if len(self._alle_regios) == 1:
            p["regio"] = self._alle_regios[0]
        # Volg je alleen je eigen post, dan filtert de server níet op dienst of
        # trefwoord: die oproepen komen altijd door, ook als de reddingsboot van
        # je post onder KNRM valt en je alleen Brandweer aanvinkte. Wat er verder
        # binnenkomt, filteren we hier.
        if len(self._diensten) == 1 and not self._alleen_post:
            p["dienst"] = self._diensten[0]
        if self.plaats:
            p["plaats"] = self.plaats
        if len(self.gemeenten) == 1:
            p["gemeente"] = self.gemeenten[0]
        if self._straal_actief:
            # Afgerond: de server hoeft niet tot op de meter te weten waar je
            # woont. Hij zoekt iets ruimer; de exacte afstand rekenen wij na.
            p["lat"] = f"{self.punt[0]:.{_PUNT_DECIMALEN}f}"
            p["lon"] = f"{self.punt[1]:.{_PUNT_DECIMALEN}f}"
            p["straal"] = f"{float(self.straal) + _STRAAL_MARGE_KM:g}"
        if self._capcodes:
            # Met een gebied: je gebied OF je eigen post. Zonder gebied: alleen
            # je eigen post.
            p["ook_capcodes" if self.gebied else "capcodes"] = ",".join(sorted(self._capcodes))
        if self.bevat and not self._alleen_post and not any("*" in w or "?" in w for w in self.bevat):
            p["bevat"] = ",".join(self.bevat)
        return p

    # ── wat er hier doorkomt, en waarom ───────────────────────────────────

    def reden(self, m: dict) -> str | None:
        """Waarom deze melding doorkomt, of None als hij niet door mag.

        De volgorde: eerst wegstrepen wat je nooit wilt zien, dan je eigen post
        erdoor, dan de gewone filters. Negeren wint dus van alles — een
        testoproep naar je eigen kazerne is nog steeds een testoproep.
        """
        tekst = f"{m.get('bericht') or ''} {m.get('leesbaar') or ''}"
        codes = [capcode9(c) for c in (m.get("capcodes") or [])]

        if self.negeer and raakt(tekst, self.negeer):
            return None
        if self._negeer_capcodes and any(c in self._negeer_capcodes for c in codes):
            return None

        eigen = next((c for c in codes if c in self._capcodes), None)
        if eigen:
            return f"eigen post (capcode {eigen.lstrip('0') or '0'})"

        redenen: list[str] = []
        code = m.get("regio_code")
        if self._alle_regios:
            if code not in self._alle_regios:
                return None
            naam = REGIOS.get(code, code)
            prov = provincie_van_regio(code)
            if prov in self.provincies and code not in self.regios:
                deel = f"provincie {prov} (regio {naam})"
            else:
                deel = f"regio {naam}"
            if not m.get("gemeente"):
                # Zonder bekende plek komt de regio van de meldkamer die
                # alarmeerde, en die werkt soms voor meerdere regio's.
                deel += ", plek onbekend: regio van de meldkamer"
            redenen.append(deel)
        if self.gemeenten:
            if m.get("gemeente") not in self.gemeenten:
                return None
            redenen.append(f"gemeente {m.get('gemeente')}")
        if self.plaats:
            redenen.append(f"woonplaats {m.get('plaats') or m.get('gemeente') or self.plaats}")
        if self._straal_actief:
            locatie = m.get("locatie") or {}
            if locatie.get("lat") is None or locatie.get("lon") is None:
                return None
            d = afstand_km(self.punt[0], self.punt[1], locatie["lat"], locatie["lon"])
            if d > float(self.straal):
                return None
            redenen.append(f"binnen {d:.1f} km van je punt".replace(".", ","))
        if self._diensten and m.get("dienst") not in self._diensten:
            return None
        if self.alleen_spoed and (m.get("urgentie") or "") not in SPOED_CODES:
            return None
        if self.bevat:
            woord = raakt(tekst, self.bevat)
            if not woord:
                return None
            redenen.append(f"trefwoord '{woord}'")

        if not any(r.startswith(("regio", "provincie", "gemeente", "woonplaats", "binnen")) for r in redenen):
            redenen.insert(0, "geen gebiedsfilter: heel Nederland")
        return " · ".join(redenen)
