"""Haalt de meldingen op en deelt ze met de entiteiten.

Eén coördinator per configuratie: hij pollt de feed, onthoudt welk id hij als
laatste zag en vraagt daarna alleen nog wat nieuwer is. Zo blijft het verkeer
klein, ook als je elke 30 seconden kijkt.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN, EVENT_INCIDENT, EVENT_MELDING, FEED_PAD, NIVEAU_ORDE, SPOED_CODES
from .filters import INGEHAALD_NA_SECONDEN, Filter, afstand_km

_LOGGER = logging.getLogger(__name__)

MAX_BEWAARD = 30
# Hoeveel incidenten we onthouden om opschaling te zien. Een incident duurt
# hooguit een paar uur; tweehonderd is voor een landelijke configuratie ruim.
MAX_INCIDENTEN = 200


class HierCoordinator(DataUpdateCoordinator):
    """Pollt de 112hier-feed en houdt de laatste meldingen bij."""

    def __init__(
        self,
        hass: HomeAssistant,
        basis: str,
        interval: timedelta,
        filter_: Filter,
        user_agent: str = "homeassistant-112hier",
    ) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=interval)
        self._basis = basis.rstrip("/")
        self.filter = filter_
        self._ua = user_agent
        # Thuislocatie uit de Home Assistant-instellingen, om de afstand te
        # kunnen berekenen. Die staat er altijd; iemand heeft hem bij de
        # installatie ingevuld.
        self._thuis = (hass.config.latitude, hass.config.longitude)
        self._sessie = async_get_clientsession(hass)
        # Het hoogste id dat we al gezien hebben. Blijft None tot het eerste
        # antwoord: dan halen we een klein blok op om iets te tonen te hebben,
        # zonder de hele geschiedenis als "nieuw" de bus op te gooien.
        self._laatste_id: int | None = None
        self.meldingen: list[dict] = []
        # incident-id → hoogste niveau dat we zagen, om opschaling te herkennen.
        self._incidenten: dict[int, int] = {}
        # Wat de feed over de ontvanger zegt; None bij een feed die dat niet kent.
        self.ontvanger: dict | None = None

    def _afstand(self, m: dict) -> float | None:
        """Hemelsbrede afstand van je huis tot de melding, in kilometers."""
        locatie = m.get("locatie") or {}
        if locatie.get("lat") is None or self._thuis[0] is None:
            return None
        return round(afstand_km(self._thuis[0], self._thuis[1], locatie["lat"], locatie["lon"]), 1)

    async def _async_update_data(self) -> list[dict]:
        try:
            async with asyncio.timeout(20):
                # params= in plaats van zelf aan elkaar plakken: een trefwoord of
                # plaatsnaam met een & of spatie brak anders stil de URL.
                antwoord = await self._sessie.get(
                    self._basis + FEED_PAD,
                    params=self.filter.params(self._laatste_id),
                    headers={"User-Agent": self._ua},
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

        self.ontvanger = data.get("ontvanger") if isinstance(data.get("ontvanger"), dict) else None

        binnen: list[dict] = []
        for m in data.get("meldingen", []):
            reden = self.filter.reden(m)
            if reden is None:
                continue
            m["filter_reden"] = reden
            binnen.append(m)

        eerste_ronde = self._laatste_id is None
        if data.get("laatste_id") is not None:
            self._laatste_id = max(self._laatste_id or 0, int(data["laatste_id"]))

        nu = dt_util.utcnow()
        for m in binnen:
            # Afstand tot je huis; handig in automatiseringen ("alleen als het
            # binnen 5 km is") en op de kaart.
            m["afstand_km"] = self._afstand(m)
            # Dezelfde namen als de sensor "Laatste melding", zodat een
            # automatisering op het event met trigger.event.data.latitude werkt.
            locatie = m.get("locatie") or {}
            m["latitude"] = locatie.get("lat")
            m["longitude"] = locatie.get("lon")
            m["nauwkeurigheid"] = locatie.get("precisie")
            m["spoed"] = (m.get("urgentie") or "") in SPOED_CODES
            tijd = dt_util.parse_datetime(m.get("ontvangen") or "")
            m["leeftijd_s"] = int((nu - tijd).total_seconds()) if tijd else None
            # Na een herstart of storing komen oude meldingen alsnog binnen. Die
            # krijgen een vlag, zodat een pushbericht ze kan overslaan.
            m["ingehaald"] = bool(m["leeftijd_s"] is not None and m["leeftijd_s"] > INGEHAALD_NA_SECONDEN)

        if binnen:
            # Nieuwste eerst, zodat de sensor altijd de meest recente toont.
            binnen.sort(key=lambda m: m["id"], reverse=True)
            self.meldingen = (binnen + self.meldingen)[:MAX_BEWAARD]

        # Bij de allereerste ronde geen events: anders krijg je bij het
        # opstarten van Home Assistant meteen tien meldingen op je telefoon
        # over dingen die allang voorbij zijn.
        for m in reversed(binnen):
            if not eerste_ronde:
                self.hass.bus.async_fire(EVENT_MELDING, m)
            self._volg_incident(m, stil=eerste_ronde)

        return self.meldingen

    def _volg_incident(self, m: dict, stil: bool) -> None:
        """Event bij een nieuw incident en bij opschaling (klein → middel → groot).

        Zes oproepen voor één brand zijn één gebeurtenis. Elke vervolgoproep
        brengt de stand van het incident mee; daaraan zien we of het groeit,
        zonder dat er een extra verzoek nodig is.
        """
        inc = m.get("incident")
        if not isinstance(inc, dict) or not inc.get("id"):
            return
        iid = int(inc["id"])
        niveau = NIVEAU_ORDE.get(inc.get("niveau") or "", 0)
        # Eruit en er weer in: zo staat een incident dat net weer een oproep
        # kreeg achteraan, en valt bij een volle lijst het oudste weg.
        vorig = self._incidenten.pop(iid, None)
        self._incidenten[iid] = max(niveau, vorig or 0)
        if len(self._incidenten) > MAX_INCIDENTEN:
            self._incidenten.pop(next(iter(self._incidenten)))
        if stil:
            return
        if vorig is None:
            # Na een herstart kennen we lopende incidenten nog niet. Begon dit
            # incident al eerder, dan is het niet "nieuw": alleen onthouden.
            eerste = dt_util.parse_datetime(inc.get("eerste") or "")
            if eerste and (dt_util.utcnow() - eerste).total_seconds() > INGEHAALD_NA_SECONDEN:
                return
            soort = "nieuw"
        elif niveau > vorig:
            soort = "opgeschaald"
        else:
            return
        self.hass.bus.async_fire(
            EVENT_INCIDENT,
            {
                "type": soort,
                **inc,
                "melding_id": m.get("id"),
                "plaats": m.get("plaats"),
                "straat": m.get("straat"),
                "afstand_km": m.get("afstand_km"),
                "filter_reden": m.get("filter_reden"),
                "ingehaald": m.get("ingehaald"),
            },
        )
