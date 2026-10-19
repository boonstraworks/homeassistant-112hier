"""De sensoren: laatste melding, de bewaarde lijst, het laatste incident en NL-Alert."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
# DeviceInfo woont in device_registry, niet in een eigen device_info-module —
# die laatste bestaat niet en liet de integratie stukgaan bij het opzetten.
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .aardbevingen import AardbevingCoordinator
from .const import ATTRIBUTIE, DIENST_ICOON, DOMAIN, GEEN_DIENST_ICOON, SPOED_CODES
from .coordinator import HierCoordinator
from .nlalert import NlAlertCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator: HierCoordinator = hass.data[DOMAIN][entry.entry_id]
    nla: NlAlertCoordinator = hass.data[f"{DOMAIN}_nla"][entry.entry_id]
    aardb: AardbevingCoordinator = hass.data[f"{DOMAIN}_aardbeving"][entry.entry_id]
    async_add_entities(
        [
            LaatsteMelding(coordinator, entry),
            AantalMeldingen(coordinator, entry),
            LaatsteIncident(coordinator, entry),
            LaatsteNlAlert(nla, entry),
            LaatsteAardbeving(aardb, entry),
        ]
    )


def _incident_kort(inc: dict | None) -> dict | None:
    """Het incident in een paar velden: genoeg voor een kaart of een bericht."""
    if not isinstance(inc, dict):
        return None
    return {
        "id": inc.get("id"),
        "niveau": inc.get("niveau"),
        "niveau_naam": inc.get("niveau_naam"),
        "samenvatting": inc.get("samenvatting"),
        "oproepen": inc.get("oproepen"),
    }


class Basis(CoordinatorEntity[HierCoordinator], SensorEntity):
    """Gedeelde eigenschappen van de meldingsensoren."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTIE

    def __init__(self, coordinator: HierCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="112hier.nl",
            model="P2000-meldingen",
            configuration_url="https://112hier.nl/feed",
        )


class LaatsteMelding(Basis):
    """De meest recente melding die aan je filters voldoet."""

    _attr_translation_key = "laatste_melding"
    # Het ruwe bericht, de capcodes en de eenheden staan in de attributen voor
    # automatiseringen, maar horen niet bij elke wijziging in de database.
    _unrecorded_attributes = frozenset({"bericht", "capcodes", "eenheden", "incident"})

    def __init__(self, coordinator: HierCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_laatste"

    @property
    def icon(self) -> str:
        """Het icoon van de dienst: een brandweerauto bij een brandmelding, enz."""
        meldingen = self.coordinator.meldingen
        dienst = (meldingen[0].get("dienst") or "") if meldingen else ""
        return DIENST_ICOON.get(dienst, GEEN_DIENST_ICOON)

    @property
    def native_value(self) -> str | None:
        """De leesbare regel, afgekapt: een sensorwaarde mag niet te lang zijn.

        Home Assistant bewaart de toestand in de database en weigert waarden
        boven de 255 tekens. Het hele bericht staat in de attributen.
        """
        meldingen = self.coordinator.meldingen
        if not meldingen:
            return None
        m = meldingen[0]
        tekst = m.get("leesbaar") or m.get("bericht") or ""
        return tekst[:250]

    @property
    def extra_state_attributes(self) -> dict:
        meldingen = self.coordinator.meldingen
        if not meldingen:
            return {}
        m = meldingen[0]
        locatie = m.get("locatie") or {}
        return {
            "id": m.get("id"),
            "bericht": m.get("bericht"),
            "dienst": m.get("dienst"),
            "urgentie": m.get("urgentie"),
            "urgentie_uitleg": m.get("urgentie_uitleg"),
            "spoed": (m.get("urgentie") or "") in SPOED_CODES,
            "plaats": m.get("plaats"),
            "gemeente": m.get("gemeente"),
            "straat": m.get("straat"),
            "regio": m.get("regio"),
            "regio_code": m.get("regio_code"),
            # Met deze twee kun je de melding op een kaart-card zetten.
            "latitude": locatie.get("lat"),
            "longitude": locatie.get("lon"),
            "nauwkeurigheid": locatie.get("precisie"),
            "capcodes": m.get("capcodes"),
            "eenheden": [e.get("label") for e in (m.get("eenheden") or [])],
            "afstand_km": m.get("afstand_km"),
            "incident_id": m.get("incident_id"),
            "incident": _incident_kort(m.get("incident")),
            "ontvangen": m.get("ontvangen"),
            "url": m.get("url"),
            # Kaartje van de plek, voor in een pushbericht.
            "afbeelding": m.get("afbeelding"),
            # Waarom deze melding doorkwam: "regio Haaglanden", "eigen post", …
            "filter_reden": m.get("filter_reden"),
        }


class AantalMeldingen(Basis):
    """De laatste meldingen die door je filters kwamen (maximaal 30).

    De waarde is het aantal; de lijst zelf staat in de attributen. Daar leest de
    dashboardkaart uit. Geen statistiek: het getal is vrijwel altijd 30 en een
    grafiek daarvan zegt niets.
    """

    _attr_icon = "mdi:format-list-bulleted"
    _attr_translation_key = "aantal"
    # De lijst is tot ~15 KB; die hoort niet bij elke update in de database.
    _unrecorded_attributes = frozenset({"meldingen", "ontvanger"})

    def __init__(self, coordinator: HierCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_aantal"

    @property
    def native_value(self) -> int:
        return len(self.coordinator.meldingen)

    @property
    def extra_state_attributes(self) -> dict:
        """De hele lijst.

        Hier leest onze eigen kaart uit, en je kunt er met een template-card
        zelf iets mee bouwen. Genoeg velden om een rij te tonen zonder dat je
        de melding nog ergens hoeft op te halen.
        """
        return {
            "ontvanger": self.coordinator.ontvanger,
            "meldingen": [
                {
                    "id": m.get("id"),
                    "tijd": m.get("ontvangen"),
                    "dienst": m.get("dienst"),
                    "urgentie": m.get("urgentie"),
                    "urgentie_uitleg": m.get("urgentie_uitleg"),
                    "spoed": (m.get("urgentie") or "") in SPOED_CODES,
                    "tekst": m.get("leesbaar") or m.get("bericht"),
                    "plaats": m.get("plaats"),
                    "straat": m.get("straat"),
                    "regio": m.get("regio"),
                    "afstand_km": m.get("afstand_km"),
                    "incident_id": m.get("incident_id"),
                    "incident": _incident_kort(m.get("incident")),
                    "reden": m.get("filter_reden"),
                    "url": m.get("url"),
                }
                for m in self.coordinator.meldingen
            ],
        }


class LaatsteIncident(Basis):
    """Het laatste incident in je gebied: zes oproepen voor één brand als één gebeurtenis.

    112hier voegt oproepen die bij elkaar horen samen tot een incident, met een
    samenvatting ("6 oproepen in 11 minuten, 2 diensten") en een niveau. Groeit
    het incident, dan komt er een event `112hier_incident` met type
    "opgeschaald".
    """

    _attr_translation_key = "laatste_incident"
    _unrecorded_attributes = frozenset({"diensten", "afbeelding"})

    def __init__(self, coordinator: HierCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_incident"

    def _laatste(self) -> tuple[dict, dict] | None:
        for m in self.coordinator.meldingen:
            if isinstance(m.get("incident"), dict):
                return m, m["incident"]
        return None

    @property
    def icon(self) -> str:
        gevonden = self._laatste()
        niveau = gevonden[1].get("niveau") if gevonden else None
        return {
            "groot": "mdi:alarm-light",
            "middel": "mdi:alarm-light-outline",
        }.get(niveau or "", "mdi:map-marker-alert-outline")

    @property
    def native_value(self) -> str | None:
        gevonden = self._laatste()
        if not gevonden:
            return None
        m, inc = gevonden
        return (inc.get("titel") or m.get("leesbaar") or m.get("bericht") or "")[:250]

    @property
    def extra_state_attributes(self) -> dict:
        gevonden = self._laatste()
        if not gevonden:
            return {}
        m, inc = gevonden
        return {
            "incident_id": inc.get("id"),
            "samenvatting": inc.get("samenvatting"),
            "niveau": inc.get("niveau"),
            "niveau_naam": inc.get("niveau_naam"),
            "oproepen": inc.get("oproepen"),
            "diensten": inc.get("diensten"),
            "oefening": inc.get("oefening"),
            "actief": inc.get("actief"),
            "plaats": m.get("plaats"),
            "afstand_km": m.get("afstand_km"),
            "url": inc.get("url"),
            "afbeelding": inc.get("afbeelding"),
        }


class LaatsteNlAlert(CoordinatorEntity[NlAlertCoordinator], SensorEntity):
    """Het meest recente NL-Alert in Nederland, met of het jouw huis raakte.

    Landelijk, niet gefilterd op je regio: een NL-Alert is zeldzaam (een paar per
    week) en wie er een krijgt, wil weten wat er speelt. Of het jou aangaat staat
    in "voor_jou" — en in de schakelaar "NL-Alert voor jouw locatie".
    """

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTIE
    _attr_icon = "mdi:alert-octagram-outline"
    _attr_translation_key = "laatste_nl_alert"

    def __init__(self, coordinator: NlAlertCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_nl_alert"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    @property
    def available(self) -> bool:
        # Niet super().available: die wordt bij één mislukte ronde al onwaar.
        return self.coordinator.bruikbaar

    @property
    def native_value(self) -> str | None:
        alerts = self.coordinator.alerts
        return (alerts[0].get("kop") or "")[:250] if alerts else None

    @property
    def extra_state_attributes(self) -> dict:
        alerts = self.coordinator.alerts
        if not alerts:
            return {}
        a = alerts[0]
        centrum = a.get("centrum") or {}
        incident = a.get("incident") or {}
        return {
            "id": a.get("id"),
            "status": a.get("status"),
            "soort": a.get("soort"),
            "test": a.get("test"),
            "adviezen": a.get("adviezen"),
            "toelichting": a.get("toelichting"),
            "start": a.get("start"),
            "laatst": a.get("laatst"),
            "voor_jou": a.get("voor_jou"),
            "latitude": centrum.get("lat"),
            "longitude": centrum.get("lon"),
            "incident_url": incident.get("url"),
            "bron_url": a.get("bron_url"),
            "url": a.get("url"),
            "actief_elders": [x.get("kop") for x in alerts if x.get("status") == "actief"],
            # Staat deze op je kaart, ver van huis? Dan is dat geen melding uit
            # je gebied: dit is het laatste NL-Alert van heel Nederland.
            "filter_reden": "landelijk: het laatste NL-Alert in heel Nederland, niet gefilterd op jouw gebied",
        }


class LaatsteAardbeving(CoordinatorEntity[AardbevingCoordinator], SensorEntity):
    """De meest recente aardbeving in en rond Nederland, met magnitude en plaats.

    Landelijk, niet op je gebied gefilterd: een beving is zeldzaam en wie er een
    voelt wil weten wat het was. Of hij dicht bij jou lag staat in "voor_jou" en
    "afstand_km" — en in de schakelaar "Voelbare aardbeving in de buurt". De
    waarde is de magnitude; de rest (plaats, diepte, soort) staat in de attributen.
    """

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTIE
    _attr_icon = "mdi:pulse"
    _attr_translation_key = "laatste_aardbeving"
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: AardbevingCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_aardbeving"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    @property
    def available(self) -> bool:
        # Niet super().available: die wordt bij één mislukte ronde al onwaar.
        return self.coordinator.bruikbaar

    @property
    def native_value(self) -> float | None:
        bevingen = self.coordinator.bevingen
        return bevingen[0].get("magnitude") if bevingen else None

    @property
    def extra_state_attributes(self) -> dict:
        bevingen = self.coordinator.bevingen
        if not bevingen:
            return {}
        b = bevingen[0]
        return {
            "id": b.get("id"),
            "magnitude": b.get("magnitude"),
            "magtype": b.get("magtype"),
            "plaats": b.get("plaats"),
            # 'earthquake' (natuurlijk) of 'induced' (bv. gaswinning).
            "soort": b.get("soort"),
            "voelbaar": b.get("voelbaar"),
            "voor_jou": b.get("voor_jou"),
            "afstand_km": b.get("afstand_km"),
            "diepte_km": b.get("diepte_km"),
            "tijd": b.get("tijd"),
            "latitude": b.get("lat"),
            "longitude": b.get("lon"),
            "url": b.get("url"),
            "filter_reden": "landelijk: de laatste beving in en rond Nederland, niet gefilterd op jouw gebied",
        }
