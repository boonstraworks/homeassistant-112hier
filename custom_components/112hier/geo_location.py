"""Elke melding als eigen punt op de kaart.

Waarom dit er is: met alleen een sensor krijg je één marker die telkens
verspringt naar de nieuwste melding. Dat ziet er op een kaart uit als één
incident dat door Nederland zwerft. Home Assistant heeft hier een eigen soort
entiteit voor — `geo_location` — die bedoeld is voor gebeurtenissen met een
plaats en een houdbaarheidsdatum. Aardbevingen en natuurbranden werken zo ook.

Elke melding wordt een eigen entiteit die verdwijnt zodra hij uit de lijst
loopt, zodat de kaart laat zien wat er nú speelt.
"""

from __future__ import annotations

from urllib.parse import quote

from homeassistant.components.geo_location import GeolocationEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTRIBUTIE, DIENST_ICOON, DOMAIN, GEEN_DIENST_ICOON, SPOED_CODES
from .coordinator import HierCoordinator

BRON = "112hier"

# Kleur per dienst, gelijk aan die op 112hier.nl zodat de kaart in Home
# Assistant er hetzelfde uitziet als de site.
KLEUR = {
    "brandweer": "#ea580c",
    "ambulance": "#dc2626",
    "politie": "#2563eb",
    "knrm": "#0891b2",
}

# Een eenvoudige vorm per dienst: de contour van het voertuig is bij 24 pixels
# toch niet te zien, dus een gevulde cirkel met een letter leest beter.
LETTER = {"brandweer": "B", "ambulance": "A", "politie": "P", "knrm": "K"}


def _icoon_uri(dienst: str | None) -> str:
    """Een gekleurd rondje als data-URI, zodat de kaart iets te tonen heeft.

    Home Assistant kan hier geen mdi-icoon gebruiken: de kaart valt terug op
    initialen van de naam als er geen `entity_picture` is.
    """
    kleur = KLEUR.get(dienst or "", "#64748b")
    letter = LETTER.get(dienst or "", "?")
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>"
        f"<circle cx='16' cy='16' r='15' fill='{kleur}'/>"
        "<text x='16' y='22' font-family='system-ui,sans-serif' font-size='17' "
        f"font-weight='700' fill='#fff' text-anchor='middle'>{letter}</text></svg>"
    )
    return "data:image/svg+xml;utf8," + quote(svg)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: HierCoordinator = hass.data[DOMAIN][entry.entry_id]
    beheer = Beheer(hass, coordinator, entry, async_add_entities)
    entry.async_on_unload(coordinator.async_add_listener(beheer.bijwerken))
    beheer.bijwerken()


class Beheer:
    """Houdt bij welke meldingen een marker hebben en ruimt oude op."""

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: HierCoordinator,
        entry: ConfigEntry,
        toevoegen: AddEntitiesCallback,
    ) -> None:
        self._hass = hass
        self._coordinator = coordinator
        self._entry = entry
        self._toevoegen = toevoegen
        self._bekend: dict[int, MeldingOpKaart] = {}

    @callback
    def bijwerken(self) -> None:
        meldingen = {
            m["id"]: m
            for m in self._coordinator.meldingen
            if (m.get("locatie") or {}).get("lat") is not None
        }

        nieuw = [
            MeldingOpKaart(self._entry, m)
            for mid, m in meldingen.items()
            if mid not in self._bekend
        ]
        if nieuw:
            for e in nieuw:
                self._bekend[e.melding_id] = e
            self._toevoegen(nieuw)

        # Uit beeld: de coördinator bewaart een beperkt aantal meldingen, en wat
        # daar afvalt hoort ook van de kaart te verdwijnen.
        for mid in [x for x in self._bekend if x not in meldingen]:
            entiteit = self._bekend.pop(mid)
            # Een marker die Home Assistant nooit heeft toegevoegd (hass is dan
            # None) valt ook niet te verwijderen; dat gaf een fout in het log.
            if entiteit.hass is not None:
                self._hass.async_create_task(entiteit.async_remove())


class MeldingOpKaart(GeolocationEvent):
    """Eén melding als punt op de kaart."""

    _attr_should_poll = False
    _attr_source = BRON
    # Elke marker is een eigen entiteit; het ruwe bericht en de eenheden hoeven
    # niet voor elk van die tientallen per dag in de database.
    _unrecorded_attributes = frozenset({"bericht", "eenheden"})
    _attr_attribution = ATTRIBUTIE
    _attr_unit_of_measurement = UnitOfLength.KILOMETERS

    def __init__(self, entry: ConfigEntry, melding: dict) -> None:
        self._melding = melding
        self.melding_id: int = melding["id"]
        # Bewust geen unique_id. Met een unique_id zet Home Assistant elke marker
        # voorgoed in het entiteitenregister; bij honderden meldingen per dag zat
        # dat na een paar dagen aan de grens van tienduizend, waarna er voor deze
        # integratie niets meer bij kon. Een marker leeft maar kort en heeft geen
        # instellingen die bewaard moeten blijven.
        locatie = melding.get("locatie") or {}
        self._attr_latitude = locatie.get("lat")
        self._attr_longitude = locatie.get("lon")
        self._attr_name = (melding.get("leesbaar") or melding.get("bericht") or "Melding")[:80]
        # De afstand ís de waarde van een geo_location-entiteit. Zonder deze
        # staat er "Onbekend" bij elke marker.
        self._attr_distance = melding.get("afstand_km")
        # De kaart maakt van een naam zonder plaatje initialen — "Ambulance ·
        # directe inzet" werd zo "A·d". Een klein gekleurd icoontje als
        # entity_picture geeft de kaart iets om te tonen, en dan zie je in één
        # oogopslag welke dienst het is.
        self._attr_entity_picture = _icoon_uri(melding.get("dienst"))

    @property
    def icon(self) -> str:
        return DIENST_ICOON.get(self._melding.get("dienst") or "", GEEN_DIENST_ICOON)

    @property
    def extra_state_attributes(self) -> dict:
        m = self._melding
        locatie = m.get("locatie") or {}
        return {
            "id": m.get("id"),
            "bericht": m.get("bericht"),
            "dienst": m.get("dienst"),
            "urgentie": m.get("urgentie"),
            "spoed": (m.get("urgentie") or "") in SPOED_CODES,
            "plaats": m.get("plaats"),
            "straat": m.get("straat"),
            "regio": m.get("regio"),
            "nauwkeurigheid": locatie.get("precisie"),
            "eenheden": [e.get("label") for e in (m.get("eenheden") or [])],
            "afstand_km": m.get("afstand_km"),
            "incident_id": m.get("incident_id"),
            "incident": (m.get("incident") or {}).get("samenvatting"),
            "ontvangen": m.get("ontvangen"),
            "url": m.get("url"),
            "filter_reden": m.get("filter_reden"),
        }
