"""Aardbevingen in en rond Nederland, via 112hier.

Het KNMI meet elke trilling in de bodem. 112hier haalt de catalogus op, laat de
groevenschoten en explosies eruit en zet de aardbevingen op /api/aardbevingen —
met magnitude, epicentrum en of ze voelbaar waren (vanaf magnitude 2,0).

Deze coördinator leest die lijst en rekent uit of een voelbare beving dicht bij
jouw huis (de locatie uit de Home Assistant-instellingen) lag. Zo kun je bij een
beving in de buurt automatisch een bericht op elk scherm in huis krijgen — voor
Groningers, met de gaswinningsbevingen, geen theoretisch geval.
"""

from __future__ import annotations

import asyncio
import logging
from math import asin, cos, radians, sin, sqrt

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    AARDBEVING_INTERVAL,
    AARDBEVING_PAD,
    AARDBEVING_STRAAL_KM,
    DOMAIN,
    EVENT_AARDBEVING,
)

_LOGGER = logging.getLogger(__name__)


def afstand_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Afstand over het aardoppervlak tussen twee punten (haversine), in km."""
    r = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


class AardbevingCoordinator(DataUpdateCoordinator):
    """Haalt de aardbevingen van 112hier op en kijkt of ze dicht bij huis lagen."""

    def __init__(
        self,
        hass: HomeAssistant,
        basis: str,
        straal_km: float = AARDBEVING_STRAAL_KM,
        user_agent: str = "homeassistant-112hier",
    ) -> None:
        super().__init__(
            hass, _LOGGER, name=f"{DOMAIN}_aardbeving", update_interval=AARDBEVING_INTERVAL
        )
        self._url = basis.rstrip("/") + AARDBEVING_PAD
        self._ua = user_agent
        self._sessie = async_get_clientsession(hass)
        self._thuis = (hass.config.latitude, hass.config.longitude)
        self._straal = straal_km
        # Welke bevingen we al zagen (op id). Zo komt er alleen een event bij een
        # échte nieuwe beving, niet bij elke ronde over dezelfde lijst.
        self._gezien: set[str] | None = None
        self.bevingen: list[dict] = []
        # Oudere 112hier-installaties (eigen ontvanger) kennen deze lijst nog niet.
        self.beschikbaar = True
        self.fouten_op_rij = 0

    @property
    def bruikbaar(self) -> bool:
        """Mogen de entiteiten hun laatst bekende stand blijven tonen?"""
        return self.beschikbaar and (self.last_update_success or self.fouten_op_rij < 3)

    def afstand(self, b: dict) -> float | None:
        """Hoe ver lag het epicentrum van je huis? None als dat niet te bepalen is."""
        lat, lon = self._thuis
        if lat is None or lon is None or b.get("lat") is None or b.get("lon") is None:
            return None
        return afstand_km(lat, lon, b["lat"], b["lon"])

    def voor_thuis(self, b: dict) -> bool:
        """Een voelbare beving binnen de straal rond je huis."""
        if not b.get("voelbaar"):
            return False
        d = self.afstand(b)
        return d is not None and d <= self._straal

    async def _async_update_data(self) -> list[dict]:
        try:
            async with asyncio.timeout(20):
                antwoord = await self._sessie.get(self._url, headers={"User-Agent": self._ua})
                if antwoord.status == 404:
                    self.beschikbaar = False
                    return []
                if antwoord.status == 429:
                    return self.bevingen
                antwoord.raise_for_status()
                data = await antwoord.json()
        except aiohttp.ClientError as err:
            self.fouten_op_rij += 1
            raise UpdateFailed(f"112hier aardbevingen niet bereikbaar: {err}") from err
        except TimeoutError as err:
            self.fouten_op_rij += 1
            raise UpdateFailed("112hier aardbevingen reageerde niet op tijd") from err

        self.fouten_op_rij = 0
        self.beschikbaar = True
        bevingen = data.get("bevingen") or []
        for b in bevingen:
            # KNMI geeft de magnitude met veel decimalen; één is ruim genoeg.
            # De "voelbaar"-vlag komt van 112hier (op de ruwe waarde), dus dit
            # afronden verandert niets aan wat er wel of niet een alarm geeft.
            if b.get("magnitude") is not None:
                b["magnitude"] = round(b["magnitude"], 1)
            d = self.afstand(b)
            b["afstand_km"] = round(d, 1) if d is not None else None
            b["voor_jou"] = self.voor_thuis(b)

        ids = {b["id"] for b in bevingen if b.get("id")}
        if self._gezien is not None:
            # Oudste eerst, zodat automatiseringen ze in de goede volgorde zien.
            for b in sorted(bevingen, key=lambda x: x.get("tijd") or ""):
                if not b.get("id") or b["id"] in self._gezien:
                    continue
                self.hass.bus.async_fire(EVENT_AARDBEVING, {**b, "nieuw": True})
        # Eerste ronde: alleen onthouden, geen events over oude bevingen.
        self._gezien = ids
        self.bevingen = bevingen
        return bevingen
