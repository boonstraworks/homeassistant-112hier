"""Haalt de meldingen op en deelt ze met de entiteiten.

Eén coördinator per configuratie: hij pollt de feed, onthoudt welk id hij als
laatste zag en vraagt daarna alleen nog wat nieuwer is. Zo blijft het verkeer
klein, ook als je elke 30 seconden kijkt.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from fnmatch import fnmatch

import asyncio

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, EVENT_MELDING, FEED_PAD, SPOED_CODES

_LOGGER = logging.getLogger(__name__)

MAX_BEWAARD = 30


def raakt(tekst: str, patronen: list[str]) -> bool:
    """Waar als één van de patronen op de tekst slaat.

    Een gewoon woord zoekt als deel van de regel: "brand" vindt ook
    "schoorsteenbrand". Zet je er een * of ? in, dan geldt het als patroon over
    de hele regel — dezelfde schrijfwijze als de filterbestanden van de
    ontvangers die je zelf draait, zodat je een bestaand lijstje kunt
    overnemen: `A1 *Epe*`.
    """
    laag = tekst.lower()
    for p in patronen:
        p = p.lower()
        if "*" in p or "?" in p:
            if fnmatch(laag, p):
                return True
        elif p in laag:
            return True
    return False


class HierCoordinator(DataUpdateCoordinator):
    """Pollt de 112hier-feed en houdt de laatste meldingen bij."""

    def __init__(
        self,
        hass: HomeAssistant,
        basis: str,
        interval: timedelta,
        regios: list[str] | None = None,
        diensten: list[str] | None = None,
        plaats: str | None = None,
        punt: tuple[float, float] | None = None,
        straal: float | None = None,
        alleen_spoed: bool = False,
        capcodes: list[str] | None = None,
        bevat: list[str] | None = None,
        negeer: list[str] | None = None,
        negeer_capcodes: list[str] | None = None,
    ) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=interval)
        self._basis = basis.rstrip("/")
        self._regios = regios or []
        self._diensten = diensten or []
        self._plaats = plaats
        self._punt = punt
        self._straal = straal
        self._alleen_spoed = alleen_spoed
        self._capcodes = capcodes or []
        self._bevat = bevat or []
        self._negeer = negeer or []
        self._negeer_capcodes = negeer_capcodes or []
        # Thuislocatie uit de Home Assistant-instellingen, om de afstand te
        # kunnen berekenen. Die staat er altijd; iemand heeft hem bij de
        # installatie ingevuld.
        self._thuis = (hass.config.latitude, hass.config.longitude)
        self._sessie = async_get_clientsession(hass)
        # Het hoogste id dat we al gezien hebben. Blijft None tot de eerste ronde:
        # dan halen we een klein blok op om iets te tonen te hebben, zonder de
        # hele geschiedenis als "nieuw" de bus op te gooien.
        self._laatste_id: int | None = None
        self.meldingen: list[dict] = []

    def _url(self) -> str:
        p: list[str] = []
        # De feed kent één regio en één dienst per verzoek. Bij meerdere keuzes
        # halen we breder op en filteren we hier — maar dan moet de limiet wél
        # omhoog: met tien landelijke meldingen hield een filter op twee regio's
        # er in de praktijk nul over.
        breed = len(self._regios) > 1 or len(self._diensten) > 1

        if self._laatste_id is not None:
            p.append(f"sinds={self._laatste_id}")
            p.append("limiet=100")
        else:
            p.append("limiet=100" if breed else "limiet=10")

        if len(self._regios) == 1:
            p.append(f"regio={self._regios[0]}")
        if len(self._diensten) == 1:
            p.append(f"dienst={self._diensten[0]}")
        if self._plaats:
            p.append(f"plaats={self._plaats}")
        if self._punt and self._straal:
            p.append(f"lat={self._punt[0]}&lon={self._punt[1]}&straal={self._straal}")
        if self._capcodes:
            p.append("capcodes=" + ",".join(self._capcodes))
        # Jokertekens kan de feed niet aan; zodra er één patroon tussen zit
        # halen we breder op en doen we het filteren hieronder zelf.
        if self._bevat and not any("*" in w or "?" in w for w in self._bevat):
            p.append("bevat=" + ",".join(self._bevat))
        return f"{self._basis}{FEED_PAD}?" + "&".join(p)

    def _afstand(self, m: dict) -> float | None:
        """Hemelsbrede afstand van je huis tot de melding, in kilometers."""
        locatie = m.get("locatie") or {}
        if locatie.get("lat") is None or self._thuis[0] is None:
            return None
        from math import asin, cos, radians, sin, sqrt

        lat1, lon1 = radians(self._thuis[0]), radians(self._thuis[1])
        lat2, lon2 = radians(locatie["lat"]), radians(locatie["lon"])
        a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
        return round(2 * 6371 * asin(sqrt(a)), 1)

    def _past(self, m: dict) -> bool:
        """Filters die de feed niet zelf kan doen.

        De volgorde is: eerst wegstrepen wat je nooit wilt zien, dan je eigen
        post erdoor, dan de gewone filters. Negeren wint dus van alles — een
        testoproep naar je eigen kazerne is nog steeds een testoproep.

        Volg je een eigen post, dan komt die er verder altijd door: ook buiten
        je regio, ook buiten de diensten die je koos, ook als je "alleen spoed"
        aanstaat. Anders mis je de oproep van je kazerne omdat hij een P 2 was.
        """
        tekst = f"{m.get('bericht') or ''} {m.get('leesbaar') or ''}"
        codes = [str(c).lstrip("0") for c in (m.get("capcodes") or [])]

        if self._negeer and raakt(tekst, self._negeer):
            return False
        if self._negeer_capcodes:
            weg = {c.lstrip("0") for c in self._negeer_capcodes}
            if any(c in weg for c in codes):
                return False

        if self._capcodes:
            mijn = {c.lstrip("0") for c in self._capcodes}
            if any(c in mijn for c in codes):
                return True

        if self._regios and m.get("regio_code") not in self._regios:
            return False
        if self._diensten and m.get("dienst") not in self._diensten:
            return False
        if self._alleen_spoed and (m.get("urgentie") or "") not in SPOED_CODES:
            return False
        if self._bevat and not raakt(tekst, self._bevat):
            return False
        return True

    async def _async_update_data(self) -> list[dict]:
        try:
            async with asyncio.timeout(20):
                antwoord = await self._sessie.get(
                    self._url(), headers={"User-Agent": "homeassistant-112hier"}
                )
                if antwoord.status == 429:
                    # Te vaak gevraagd. Geen fout: we slaan deze ronde over en
                    # houden wat we hadden, anders verdwijnt de sensor even.
                    _LOGGER.debug("112hier: limiet bereikt, deze ronde overgeslagen")
                    return self.meldingen
                antwoord.raise_for_status()
                data = await antwoord.json()
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"112hier niet bereikbaar: {err}") from err
        except TimeoutError as err:
            raise UpdateFailed("112hier reageerde niet op tijd") from err

        binnen = [m for m in data.get("meldingen", []) if self._past(m)]
        eerste_ronde = self._laatste_id is None

        if data.get("laatste_id"):
            self._laatste_id = max(self._laatste_id or 0, int(data["laatste_id"]))

        if binnen:
            # Afstand tot je huis erbij; handig in automatiseringen ("alleen als
            # het binnen 5 km is") en op de kaart.
            for m in binnen:
                m["afstand_km"] = self._afstand(m)
            # Nieuwste eerst, zodat de sensor altijd de meest recente toont.
            binnen.sort(key=lambda m: m["id"], reverse=True)
            self.meldingen = (binnen + self.meldingen)[:MAX_BEWAARD]

            # Bij de allereerste ronde geen events: anders krijg je bij het
            # opstarten van Home Assistant meteen tien meldingen op je telefoon
            # over dingen die allang voorbij zijn.
            if not eerste_ronde:
                for m in reversed(binnen):
                    self.hass.bus.async_fire(EVENT_MELDING, m)

        return self.meldingen
