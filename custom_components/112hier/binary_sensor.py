"""Een aan/uit-schakelaar voor "er is nu spoed in de buurt".

Waarom naast de gewone sensor: een automatisering op een sensor-toestand moet
zelf uitrekenen of de melding spoed was en hoe ver weg, en blijft daarna niets
weten. Een binary_sensor is een toestand die je kunt aflezen, in een conditie
kunt gebruiken ("alleen als het lampje nog rood staat") en in de geschiedenis
kunt terugzien.

Hij gaat aan bij een spoedmelding binnen de straal die je koos, en na een
kwartier vanzelf weer uit — een uitruk is dan afgelopen of allang opgeschaald.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_point_in_time
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .aardbevingen import AardbevingCoordinator
from .const import ATTRIBUTIE, CONF_SPOED_STRAAL, DOMAIN, SPOED_CODES
from .coordinator import HierCoordinator
from .nlalert import NlAlertCoordinator

# Hoe lang de schakelaar aan blijft na een spoedmelding.
AAN_MINUTEN = 15
# Een aardbeving is één moment, geen toestand die loopt. We laten de schakelaar
# daarom een uur aanstaan, lang genoeg om er een bericht of een scène aan te
# hangen en om hem in de geschiedenis terug te zien.
BEVING_AAN_MINUTEN = 60


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: HierCoordinator = hass.data[DOMAIN][entry.entry_id]
    inst = {**entry.data, **entry.options}
    straal = float(inst.get(CONF_SPOED_STRAAL) or 0)
    nla: NlAlertCoordinator = hass.data[f"{DOMAIN}_nla"][entry.entry_id]
    aardb: AardbevingCoordinator = hass.data[f"{DOMAIN}_aardbeving"][entry.entry_id]
    async_add_entities(
        [
            SpoedInDeBuurt(coordinator, entry, straal),
            NlAlertThuis(nla, entry),
            VoelbareBevingInDeBuurt(aardb, entry),
            Ontvangst(coordinator, entry),
        ]
    )


class SpoedInDeBuurt(CoordinatorEntity[HierCoordinator], BinarySensorEntity):
    """Aan zolang er kort geleden een spoedmelding dichtbij was."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTIE
    _attr_translation_key = "spoed_in_de_buurt"
    _attr_device_class = BinarySensorDeviceClass.SAFETY
    _attr_icon = "mdi:car-emergency"

    def __init__(
        self, coordinator: HierCoordinator, entry: ConfigEntry, straal: float
    ) -> None:
        super().__init__(coordinator)
        self._straal = straal
        self._tot: datetime | None = None
        self._aanleiding: dict | None = None
        self._timer = None
        self._attr_unique_id = f"{entry.entry_id}_spoed"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="112hier.nl",
            model="P2000-meldingen",
            configuration_url="https://112hier.nl/feed",
        )

    def _telt_mee(self, m: dict) -> bool:
        if (m.get("urgentie") or "") not in SPOED_CODES:
            return False
        # Geen straal ingesteld: alles wat door je filters komt telt mee. Wie
        # al op één regio filtert heeft aan "in mijn gebied" genoeg.
        if not self._straal:
            return True
        afstand = m.get("afstand_km")
        # Zonder coördinaten weten we de afstand niet. Die melding meetellen zou
        # de schakelaar laten aanslaan op iets dat honderd kilometer verderop
        # kan liggen, dus die laten we hier buiten.
        return afstand is not None and afstand <= self._straal

    @callback
    def _handle_coordinator_update(self) -> None:
        for m in self.coordinator.meldingen:
            if not self._telt_mee(m):
                continue
            tijd = dt_util.parse_datetime(m.get("ontvangen") or "")
            if not tijd:
                continue
            tot = tijd + timedelta(minutes=AAN_MINUTEN)
            if self._tot is None or tot > self._tot:
                self._tot, self._aanleiding = tot, m
                self._plan_uit(tot)
            break
        super()._handle_coordinator_update()

    def _plan_uit(self, tot: datetime) -> None:
        """Zelf een moment plannen waarop we weer uitgaan.

        Zonder dit blijft de schakelaar aan staan tot de volgende melding
        binnenkomt, en in een rustige regio kan dat uren duren.
        """
        if self._timer:
            self._timer()

        @callback
        def _uit(_now) -> None:
            self._timer = None
            self.async_write_ha_state()

        self._timer = async_track_point_in_time(self.hass, _uit, tot)

    async def async_will_remove_from_hass(self) -> None:
        if self._timer:
            self._timer()
            self._timer = None

    @property
    def is_on(self) -> bool:
        return self._tot is not None and dt_util.utcnow() < self._tot

    @property
    def extra_state_attributes(self) -> dict:
        if not self.is_on or not self._aanleiding:
            return {"straal_km": self._straal or None}
        m = self._aanleiding
        return {
            "straal_km": self._straal or None,
            "aanleiding": m.get("leesbaar") or m.get("bericht"),
            "urgentie": m.get("urgentie"),
            "dienst": m.get("dienst"),
            "plaats": m.get("plaats"),
            "straat": m.get("straat"),
            "afstand_km": m.get("afstand_km"),
            "tot": self._tot.isoformat() if self._tot else None,
            "url": m.get("url"),
            "filter_reden": m.get("filter_reden"),
        }


class NlAlertThuis(CoordinatorEntity[NlAlertCoordinator], BinarySensorEntity):
    """Aan zolang er een actief NL-Alert is waarvan het uitzendgebied jouw huis raakt.

    "Jouw huis" is de locatie uit de Home Assistant-instellingen. Het gebied is
    het gebied waarin telefoons het alert kregen. Gaat uit zodra het alert is
    opgeheven of afgelopen. Hang hier je automatisering aan: ventilatie uit,
    ramen dicht, een melding op elk scherm in huis.
    """

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTIE
    _attr_translation_key = "nl_alert_thuis"
    _attr_device_class = BinarySensorDeviceClass.SAFETY
    _attr_icon = "mdi:alert-octagram"

    def __init__(self, coordinator: NlAlertCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_nl_alert_thuis"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    def _actief(self) -> dict | None:
        for a in self.coordinator.alerts:
            # Het landelijke testbericht (juni en december) gaat naar heel
            # Nederland. Zonder deze uitzondering ging bij iedereen de ventilatie uit.
            if a.get("status") == "actief" and a.get("voor_jou") and not a.get("test"):
                return a
        return None

    @property
    def available(self) -> bool:
        # Niet super().available: die wordt bij één mislukte ronde al onwaar.
        return self.coordinator.bruikbaar

    @property
    def is_on(self) -> bool:
        return self._actief() is not None

    @property
    def extra_state_attributes(self) -> dict:
        a = self._actief()
        if not a:
            return {}
        return {
            "kop": a.get("kop"),
            "soort": a.get("soort"),
            "adviezen": a.get("adviezen"),
            "start": a.get("start"),
            "url": a.get("url"),
            "bron_url": a.get("bron_url"),
            "incident_url": (a.get("incident") or {}).get("url"),
        }


class VoelbareBevingInDeBuurt(
    CoordinatorEntity[AardbevingCoordinator], BinarySensorEntity
):
    """Aan als er kort geleden een voelbare aardbeving dicht bij huis was.

    "Dicht bij huis" is binnen ~80 km van de locatie uit de Home
    Assistant-instellingen; "voelbaar" is vanaf magnitude 2,0. Gaat na een uur
    vanzelf weer uit. Vooral in Groningen (de gaswinningsbevingen) iets om een
    bericht of een scène aan te hangen.
    """

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTIE
    _attr_translation_key = "voelbare_beving_in_de_buurt"
    _attr_device_class = BinarySensorDeviceClass.VIBRATION
    _attr_icon = "mdi:pulse"

    def __init__(self, coordinator: AardbevingCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._tot: datetime | None = None
        self._aanleiding: dict | None = None
        self._timer = None
        self._attr_unique_id = f"{entry.entry_id}_beving_dichtbij"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    @callback
    def _handle_coordinator_update(self) -> None:
        for b in self.coordinator.bevingen:
            if not b.get("voor_jou"):
                continue
            tijd = dt_util.parse_datetime(b.get("tijd") or "")
            if not tijd:
                continue
            tot = tijd + timedelta(minutes=BEVING_AAN_MINUTEN)
            if self._tot is None or tot > self._tot:
                self._tot, self._aanleiding = tot, b
                self._plan_uit(tot)
            break
        super()._handle_coordinator_update()

    def _plan_uit(self, tot: datetime) -> None:
        """Zelf plannen wanneer we weer uitgaan; anders blijft hij staan tot de
        volgende beving, en dat kan maanden duren."""
        if self._timer:
            self._timer()

        @callback
        def _uit(_now) -> None:
            self._timer = None
            self.async_write_ha_state()

        self._timer = async_track_point_in_time(self.hass, _uit, tot)

    async def async_will_remove_from_hass(self) -> None:
        if self._timer:
            self._timer()
            self._timer = None

    @property
    def available(self) -> bool:
        # Niet super().available: die wordt bij één mislukte ronde al onwaar.
        return self.coordinator.bruikbaar

    @property
    def is_on(self) -> bool:
        return self._tot is not None and dt_util.utcnow() < self._tot

    @property
    def extra_state_attributes(self) -> dict:
        if not self.is_on or not self._aanleiding:
            return {}
        b = self._aanleiding
        return {
            "magnitude": b.get("magnitude"),
            "plaats": b.get("plaats"),
            "soort": b.get("soort"),
            "diepte_km": b.get("diepte_km"),
            "afstand_km": b.get("afstand_km"),
            "tijd": b.get("tijd"),
            "tot": self._tot.isoformat() if self._tot else None,
            "url": b.get("url"),
        }


class Ontvangst(CoordinatorEntity[HierCoordinator], BinarySensorEntity):
    """Ontvangt 112hier nu meldingen? Aan = ja, uit = storing.

    112hier luistert met één eigen ontvanger. Valt die stil, dan is "geen
    meldingen" niet hetzelfde als "rustig" — en dat hoor je te kunnen zien. De
    schakelaars voor spoed en NL-Alert blijven daarbij gewoon zoals ze zijn
    (NL-Alert komt bovendien niet van de ontvanger); deze entiteit zegt alleen
    of je op de P2000-meldingen kunt rekenen.
    """

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTIE
    _attr_translation_key = "ontvangst"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: HierCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_ontvangst"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    @property
    def available(self) -> bool:
        # Een oudere feed (of een eigen ontvanger) zegt niets over de ontvanger.
        return super().available and self.coordinator.ontvanger is not None

    @property
    def is_on(self) -> bool:
        return not (self.coordinator.ontvanger or {}).get("storing")

    @property
    def extra_state_attributes(self) -> dict:
        o = self.coordinator.ontvanger or {}
        return {
            "storing_sinds": o.get("storing_sinds"),
            "stil_minuten": o.get("stil_minuten"),
        }
