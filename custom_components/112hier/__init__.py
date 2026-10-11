"""112hier — live 112-meldingen in Home Assistant."""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import (
    CONF_ALLEEN_SPOED,
    CONF_BEVAT,
    CONF_CAPCODES,
    CONF_BASIS,
    CONF_DIENSTEN,
    CONF_INTERVAL,
    CONF_NEGEER,
    CONF_NEGEER_CAPCODES,
    CONF_PLAATS,
    CONF_REGIOS,
    CONF_STRAAL,
    DEFAULT_BASIS,
    DOMAIN,
    MIN_INTERVAL_SECONDEN,
)
from .coordinator import HierCoordinator
from .nlalert import NlAlertCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.GEO_LOCATION,
]

KAART_URL = "/112hier/card-112hier.js"


def _lijst(waarde) -> list[str]:
    """Komma-gescheiden invoer opknippen; lege stukken eruit."""
    return [deel.strip() for deel in str(waarde or "").split(",") if deel.strip()]


async def _zorg_voor_kaart(hass: HomeAssistant) -> None:
    """De Lovelace-kaart meeleveren en zelf inladen.

    Bij de meeste integraties met een eigen kaart moet je hem handmatig als
    bron toevoegen onder Instellingen → Dashboards → Bronnen. Dat is een stap
    waar mensen op vastlopen, dus doen we het zelf. Eén keer per Home
    Assistant, niet per configuratie.
    """
    if hass.data.get(f"{DOMAIN}_kaart"):
        return
    hass.data[f"{DOMAIN}_kaart"] = True

    bestand = Path(__file__).parent / "www" / "card-112hier.js"
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(KAART_URL, str(bestand), True)]
        )
        # De versie in de URL zorgt dat de browser na een update de nieuwe kaart
        # ophaalt in plaats van de oude uit zijn cache.
        integratie = await async_get_integration(hass, DOMAIN)
        add_extra_js_url(hass, f"{KAART_URL}?v={integratie.version}")
    except Exception:  # noqa: BLE001 — zonder kaart werkt de rest gewoon door
        _LOGGER.warning(
            "112hier: de dashboardkaart kon niet worden ingeladen. "
            "De sensoren en de kaartweergave werken wel."
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Eén coördinator per configuratie opzetten."""
    # Opties winnen van de oorspronkelijke invoer: zo werkt "Configureren" in de UI.
    inst = {**entry.data, **entry.options}

    straal = float(inst.get(CONF_STRAAL) or 0)
    punt = None
    if straal and inst.get("lat") is not None and inst.get("lon") is not None:
        punt = (float(inst["lat"]), float(inst["lon"]))

    seconden = max(MIN_INTERVAL_SECONDEN, int(inst.get(CONF_INTERVAL) or 30))

    coordinator = HierCoordinator(
        hass,
        basis=inst.get(CONF_BASIS) or DEFAULT_BASIS,
        interval=timedelta(seconds=seconden),
        regios=inst.get(CONF_REGIOS) or [],
        diensten=inst.get(CONF_DIENSTEN) or [],
        plaats=(inst.get(CONF_PLAATS) or "").strip().lower().replace(" ", "-") or None,
        punt=punt,
        straal=straal or None,
        alleen_spoed=bool(inst.get(CONF_ALLEEN_SPOED)),
        capcodes=_lijst(inst.get(CONF_CAPCODES)),
        bevat=_lijst(inst.get(CONF_BEVAT)),
        negeer=_lijst(inst.get(CONF_NEGEER)),
        negeer_capcodes=_lijst(inst.get(CONF_NEGEER_CAPCODES)),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    # NL-Alert loopt naast de meldingen. Een fout of een oudere 112hier zonder
    # NL-Alert mag het opzetten niet tegenhouden: dan blijven die twee entiteiten
    # gewoon leeg.
    nla = NlAlertCoordinator(hass, inst.get(CONF_BASIS) or DEFAULT_BASIS)
    await nla.async_refresh()
    hass.data.setdefault(f"{DOMAIN}_nla", {})[entry.entry_id] = nla
    await _zorg_voor_kaart(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Bij het wijzigen van opties opnieuw laden, anders blijft het oude filter staan.
    entry.async_on_unload(entry.add_update_listener(_herlaad))
    return True


async def _herlaad(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ontladen = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ontladen:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        hass.data.get(f"{DOMAIN}_nla", {}).pop(entry.entry_id, None)
    return ontladen
