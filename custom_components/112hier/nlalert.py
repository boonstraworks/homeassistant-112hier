"""NL-Alert: de waarschuwingen van de overheid, via 112hier.

NL-Alert komt via het mobiele netwerk binnen op elke telefoon in een gebied.
112hier houdt de berichten bij, met het uitzendgebied als veelhoek, en zet ze op
/api/nl-alerts. Deze coördinator haalt die lijst op en rekent uit of jouw huis
(de locatie uit de Home Assistant-instellingen) binnen een gebied ligt.

Zo kun je bij een NL-Alert voor jouw huis automatisch de ventilatie uitzetten —
precies wat het advies bij een brand met veel rook of een gaswolk is.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, EVENT_NL_ALERT, NLA_INTERVAL, NLA_PAD

_LOGGER = logging.getLogger(__name__)


def binnen(lat: float, lon: float, veelhoek: list) -> bool:
    """Ligt het punt binnen de veelhoek? Veelhoek als [[lat, lon], ...] (straalmethode)."""
    binnen_ = False
    j = len(veelhoek) - 1
    for i, (yi, xi) in enumerate(veelhoek):
        yj, xj = veelhoek[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            binnen_ = not binnen_
        j = i
    return binnen_


def is_test(alert: dict) -> bool:
    """Is dit het landelijke test- of controlebericht?

    Elke eerste maandag van juni en december gaat er een NL-Alert naar heel
    Nederland. Dat mag nooit de ventilatie uitzetten of een alarm op je telefoon
    geven. 112hier zet er soort "test" op; we kijken ook zelf naar de tekst, voor
    het geval een oudere 112hier dat nog niet doet.
    """
    if (alert.get("soort") or "") == "test":
        return True
    toelichting = alert.get("toelichting") or []
    if isinstance(toelichting, str):
        toelichting = [toelichting]
    tekst = " ".join([str(alert.get("kop") or ""), *map(str, toelichting)]).lower()
    return any(w in tekst for w in ("testbericht", "controlebericht", "test message"))


class NlAlertCoordinator(DataUpdateCoordinator):
    """Haalt de NL-Alerts van 112hier op en kijkt of ze jouw huis raken."""

    def __init__(
        self, hass: HomeAssistant, basis: str, user_agent: str = "homeassistant-112hier"
    ) -> None:
        super().__init__(hass, _LOGGER, name=f"{DOMAIN}_nl_alert", update_interval=NLA_INTERVAL)
        self._url = basis.rstrip("/") + NLA_PAD
        self._ua = user_agent
        self._sessie = async_get_clientsession(hass)
        self._thuis = (hass.config.latitude, hass.config.longitude)
        # Welke berichten we al zagen, als (gebeurtenis, aantal berichten). Zo komt
        # er ook een event als een lopend alert wordt opgeheven of herhaald.
        self._gezien: set[tuple[str, int]] | None = None
        self.alerts: list[dict] = []
        # Oudere 112hier-installaties (eigen ontvanger) kennen deze lijst nog niet.
        self.beschikbaar = True
        # Mislukte rondes op rij. Eén hapering mag de schakelaar niet meteen
        # "niet beschikbaar" maken: begint een alert precies dan, dan zag een
        # automatisering de overgang naar "aan" niet.
        self.fouten_op_rij = 0

    @property
    def bruikbaar(self) -> bool:
        """Mogen de entiteiten hun laatst bekende stand blijven tonen?"""
        return self.beschikbaar and (self.last_update_success or self.fouten_op_rij < 3)

    def voor_thuis(self, alert: dict) -> bool:
        lat, lon = self._thuis
        if lat is None or lon is None:
            return False
        return any(binnen(lat, lon, v) for v in (alert.get("gebied") or []) if len(v) >= 3)

    async def _async_update_data(self) -> list[dict]:
        try:
            async with asyncio.timeout(20):
                antwoord = await self._sessie.get(self._url, headers={"User-Agent": self._ua})
                if antwoord.status == 404:
                    self.beschikbaar = False
                    return []
                if antwoord.status == 429:
                    return self.alerts
                antwoord.raise_for_status()
                data = await antwoord.json()
        except aiohttp.ClientError as err:
            self.fouten_op_rij += 1
            raise UpdateFailed(f"112hier NL-Alert niet bereikbaar: {err}") from err
        except TimeoutError as err:
            self.fouten_op_rij += 1
            raise UpdateFailed("112hier NL-Alert reageerde niet op tijd") from err

        self.fouten_op_rij = 0
        self.beschikbaar = True
        alerts = data.get("alerts") or []
        for a in alerts:
            a["voor_jou"] = self.voor_thuis(a)
            a["test"] = is_test(a)

        sleutels = {(a["id"], len(a.get("berichten") or [])) for a in alerts}
        if self._gezien is not None:
            # Oudste eerst, zodat automatiseringen ze in de goede volgorde zien.
            for a in sorted(alerts, key=lambda x: x.get("laatst") or ""):
                sleutel = (a["id"], len(a.get("berichten") or []))
                if sleutel in self._gezien:
                    continue
                nieuw = not any(g[0] == a["id"] for g in self._gezien)
                # Het gebied laten we weg: dat is groot en hoort niet op de eventbus.
                self.hass.bus.async_fire(
                    EVENT_NL_ALERT,
                    {**{k: v for k, v in a.items() if k != "gebied"}, "nieuw": nieuw},
                )
        # Eerste ronde: alleen onthouden, geen events over oude alerts.
        self._gezien = sleutels
        self.alerts = alerts
        return alerts
