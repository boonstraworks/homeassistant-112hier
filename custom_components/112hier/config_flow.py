"""Instellen via de interface.

De bestaande P2000-integraties vragen om YAML-regels in configuration.yaml met
capcodes en regionummers die je zelf moet opzoeken. Dat is precies waar de
issues over gaan ("Krijg het niet werkend", "Regio vraag"). Hier klik je je
gebied bij elkaar — provincie, gemeente of een punt op de kaart — en zoek je je
kazerne op naam in plaats van capcodes van negen cijfers over te typen.
"""

from __future__ import annotations

import asyncio
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    BooleanSelector,
    LocationSelector,
    NumberSelector,
    NumberSelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from .const import (
    CONF_ALLEEN_SPOED,
    CONF_BASIS,
    CONF_BEVAT,
    CONF_CAPCODES,
    CONF_DIENSTEN,
    CONF_GEMEENTEN,
    CONF_INTERVAL,
    CONF_NEGEER,
    CONF_NEGEER_CAPCODES,
    CONF_PLAATS,
    CONF_POST_ZOEKEN,
    CONF_PROVINCIES,
    CONF_REGIOS,
    CONF_SPOED_STRAAL,
    CONF_STRAAL,
    DEFAULT_BASIS,
    DIENSTEN,
    DOMAIN,
    MIN_INTERVAL_SECONDEN,
    POSTEN_PAD,
)
from .filters import (
    MAX_CAPCODES,
    PROVINCIES,
    REGIOS,
    gemeenten,
    gemeenten_buiten_gebied,
    lijst,
    ongeldige_capcodes,
)

DIENST_LABEL = {"brandweer": "Brandweer", "ambulance": "Ambulance", "politie": "Politie", "knrm": "KNRM"}
# Wie "Den Haag" zoekt, vindt anders niets: de officiële naam is 's-Gravenhage.
GEMEENTE_ALIAS = {"'s-Gravenhage": "'s-Gravenhage (Den Haag)", "'s-Hertogenbosch": "'s-Hertogenbosch (Den Bosch)"}


# Vrije tekstvelden. Die krijgen hun huidige waarde als voorstel en niet als
# standaard: de interface stuurt een leeggemaakt veld niet mee, en een standaard
# vulde het dan stil weer aan. Zo bleef een gewiste woonplaats gewoon staan.
TEKSTVELDEN = (CONF_PLAATS, CONF_CAPCODES, CONF_BEVAT, CONF_NEGEER, CONF_NEGEER_CAPCODES)


def _voorstel(s: dict[str, Any], sleutel: str) -> dict[str, Any]:
    return {"suggested_value": s.get(sleutel, "") or ""}


def _schema(hass, standaard: dict[str, Any] | None = None) -> vol.Schema:
    s = standaard or {}
    # Het punt staat standaard op wat er al was, en anders op je huis. Vroeger
    # was het veld leeg, en een straal zonder versleept punt verdween dan stil.
    lat = s.get("lat", hass.config.latitude)
    lon = s.get("lon", hass.config.longitude)
    punt = (
        vol.Optional("punt", default={"latitude": lat, "longitude": lon})
        if lat is not None and lon is not None
        else vol.Optional("punt")
    )
    return vol.Schema(
        {
            vol.Optional(CONF_PROVINCIES, default=s.get(CONF_PROVINCIES, [])): SelectSelector(
                SelectSelectorConfig(
                    options=[SelectOptionDict(value=p, label=p) for p in PROVINCIES],
                    multiple=True,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(CONF_REGIOS, default=s.get(CONF_REGIOS, [])): SelectSelector(
                SelectSelectorConfig(
                    options=[SelectOptionDict(value=c, label=n) for c, n in REGIOS.items()],
                    multiple=True,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(CONF_GEMEENTEN, default=s.get(CONF_GEMEENTEN, [])): SelectSelector(
                SelectSelectorConfig(
                    options=[
                        SelectOptionDict(value=g, label=GEMEENTE_ALIAS.get(g, g)) for g in gemeenten()
                    ],
                    multiple=True,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Optional(CONF_PLAATS, description=_voorstel(s, CONF_PLAATS)): TextSelector(),
            punt: LocationSelector(),
            vol.Optional(CONF_STRAAL, default=s.get(CONF_STRAAL, 0)): NumberSelector(
                NumberSelectorConfig(min=0, max=100, step=1, unit_of_measurement="km")
            ),
            vol.Optional(CONF_DIENSTEN, default=s.get(CONF_DIENSTEN, DIENSTEN)): SelectSelector(
                SelectSelectorConfig(
                    options=[SelectOptionDict(value=d, label=DIENST_LABEL[d]) for d in DIENSTEN],
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            ),
            vol.Optional(CONF_ALLEEN_SPOED, default=s.get(CONF_ALLEEN_SPOED, False)): BooleanSelector(),
            # Zoek je kazerne op naam; in de volgende stap vink je de pagers aan.
            vol.Optional(CONF_POST_ZOEKEN, default=""): TextSelector(),
            # Oproepen voor deze codes komen altijd door, ook buiten je gebied.
            vol.Optional(CONF_CAPCODES, description=_voorstel(s, CONF_CAPCODES)): TextSelector(),
            vol.Optional(CONF_BEVAT, description=_voorstel(s, CONF_BEVAT)): TextSelector(),
            # Wegstrepen wat je nooit wilt zien. Testoproepen zijn het klassieke
            # geval: die gaan elke week over de lijn.
            vol.Optional(CONF_NEGEER, description=_voorstel(s, CONF_NEGEER)): TextSelector(),
            vol.Optional(
                CONF_NEGEER_CAPCODES, description=_voorstel(s, CONF_NEGEER_CAPCODES)
            ): TextSelector(),
            # Hoe dichtbij een spoedmelding moet zijn voordat de schakelaar
            # "Spoed in de buurt" aangaat. Nul betekent: alles wat je filters
            # doorlaat telt mee — genoeg voor wie al op één plaats filtert.
            vol.Optional(CONF_SPOED_STRAAL, default=s.get(CONF_SPOED_STRAAL, 0)): NumberSelector(
                NumberSelectorConfig(min=0, max=100, step=1, unit_of_measurement="km")
            ),
            vol.Optional(CONF_INTERVAL, default=s.get(CONF_INTERVAL, 30)): NumberSelector(
                NumberSelectorConfig(min=MIN_INTERVAL_SECONDEN, max=600, step=5, unit_of_measurement="s")
            ),
            vol.Optional(CONF_BASIS, default=s.get(CONF_BASIS, DEFAULT_BASIS)): TextSelector(),
        }
    )


def _titel(gegevens: dict[str, Any]) -> str:
    """Een naam waaraan je de configuratie herkent in de lijst."""
    if gegevens.get(CONF_PLAATS):
        return f"112 · {gegevens[CONF_PLAATS]}"
    gem = gegevens.get(CONF_GEMEENTEN) or []
    if len(gem) == 1:
        return f"112 · gemeente {gem[0]}"
    if gem:
        return f"112 · {len(gem)} gemeenten"
    if gegevens.get(CONF_STRAAL):
        return f"112 · {int(gegevens[CONF_STRAAL])} km rond je punt"
    prov = gegevens.get(CONF_PROVINCIES) or []
    regios = gegevens.get(CONF_REGIOS) or []
    if len(prov) == 1 and not regios:
        return f"112 · {prov[0]}"
    if len(regios) == 1 and not prov:
        return f"112 · {REGIOS.get(regios[0], regios[0])}"
    if prov or regios:
        delen = []
        if prov:
            delen.append(f"{len(prov)} provincie{'s' if len(prov) > 1 else ''}")
        if regios:
            delen.append(f"{len(regios)} regio's")
        return "112 · " + " en ".join(delen)
    if lijst(gegevens.get(CONF_CAPCODES)) and not ongeldige_capcodes(gegevens.get(CONF_CAPCODES)):
        return "112 · eigen post"
    return "112 · heel Nederland"


class _Gedeeld:
    """Wat het eerste instellen en "Configureren" gemeen hebben."""

    hass: Any
    _gegevens: dict[str, Any]
    _posten: list[dict]

    async def _laad_lijsten(self) -> None:
        """De gemeentenlijst inlezen buiten de hoofdlus van Home Assistant.

        Het is een bestand van een paar kilobyte, maar lezen van schijf hoort niet
        in de event loop; daarna staat de lijst in het geheugen.
        """
        await self.hass.async_add_executor_job(gemeenten)

    def _verwerk(self, user_input: dict[str, Any]) -> dict[str, Any]:
        """Het punt als lat/lon bewaren, ook als de straal (nog) nul is.

        Zo onthoudt "Configureren" waar je punt stond. Vroeger viel het punt bij
        elke keer opslaan weg zodra de straal op nul stond.
        """
        data = dict(user_input)
        punt = data.pop("punt", None)
        if punt and punt.get("latitude") is not None:
            data["lat"] = punt.get("latitude")
            data["lon"] = punt.get("longitude")
        data.pop(CONF_POST_ZOEKEN, None)
        # Een leeggemaakt tekstveld komt niet mee in de invoer: dan is het leeg.
        for sleutel in TEKSTVELDEN:
            data.setdefault(sleutel, "")
        return data

    @staticmethod
    def _controleer(data: dict[str, Any]) -> dict[str, str]:
        """Invoer die nooit iets oplevert, meteen in het formulier melden."""
        fouten: dict[str, str] = {}
        if ongeldige_capcodes(data.get(CONF_CAPCODES)):
            fouten[CONF_CAPCODES] = "ongeldige_capcode"
        elif len(lijst(data.get(CONF_CAPCODES))) > MAX_CAPCODES:
            fouten[CONF_CAPCODES] = "te_veel_capcodes"
        if ongeldige_capcodes(data.get(CONF_NEGEER_CAPCODES)):
            fouten[CONF_NEGEER_CAPCODES] = "ongeldige_capcode"
        if gemeenten_buiten_gebied(
            data.get(CONF_GEMEENTEN) or [], data.get(CONF_REGIOS) or [], data.get(CONF_PROVINCIES) or []
        ):
            fouten[CONF_GEMEENTEN] = "gemeente_buiten_gebied"
        return fouten

    async def _zoek_posten(self, basis: str, vraag: str) -> list[dict] | None:
        """Posten op naam bij 112hier. None = de site gaf geen antwoord."""
        try:
            sessie = async_get_clientsession(self.hass)
            async with asyncio.timeout(15):
                antwoord = await sessie.get(
                    basis.rstrip("/") + POSTEN_PAD,
                    params={"q": vraag},
                    headers={"User-Agent": "homeassistant-112hier"},
                )
                if antwoord.status != 200:
                    return None
                data = await antwoord.json()
        except Exception:  # noqa: BLE001 — elke fout betekent hier hetzelfde
            return None
        return [p for p in data if isinstance(p, dict) and p.get("capcode")] if isinstance(data, list) else None

    def _post_schema(self) -> vol.Schema:
        opties: dict[str, str] = {}
        for p in self._posten:
            codes = ",".join(p.get("capcodes") or [p["capcode"]])
            dienst = DIENST_LABEL.get(p.get("dienst") or "", "")
            label = f"{p.get('naam') or ''} — {p.get('wat') or ''}"
            if dienst:
                label += f" ({dienst})"
            opties.setdefault(codes, label)
        # Optioneel met een lege standaard: bij een verplicht veld vinkt Home
        # Assistant zelf de eerste optie aan, en dan volg je een pager die je
        # niet koos.
        return vol.Schema(
            {
                vol.Optional("posten", default=[]): SelectSelector(
                    SelectSelectorConfig(
                        options=[SelectOptionDict(value=v, label=l) for v, l in opties.items()],
                        multiple=True,
                        mode=SelectSelectorMode.LIST,
                    )
                )
            }
        )

    def _voeg_posten_toe(self, gekozen: list[str]) -> bool:
        """Gekozen pagers bij de capcodes zetten. False als het er te veel worden."""
        bestaand = lijst(self._gegevens.get(CONF_CAPCODES))
        nieuw = [c for groep in gekozen for c in groep.split(",") if c]
        samen = list(dict.fromkeys([*bestaand, *nieuw]))
        if len(samen) > MAX_CAPCODES:
            return False
        self._gegevens[CONF_CAPCODES] = ", ".join(samen)
        return True


class HierConfigFlow(_Gedeeld, config_entries.ConfigFlow, domain=DOMAIN):
    """Eerste keer instellen."""

    VERSION = 1

    def __init__(self) -> None:
        self._gegevens = {}
        self._posten = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        fouten: dict[str, str] = {}
        await self._laad_lijsten()

        if user_input is not None:
            basis = (user_input.get(CONF_BASIS) or DEFAULT_BASIS).rstrip("/")
            # Meteen controleren of de feed antwoordt: een typefout in het adres
            # merk je anders pas als de sensor "onbekend" blijft.
            try:
                sessie = async_get_clientsession(self.hass)
                antwoord = await sessie.get(f"{basis}/feed.json?limiet=1", timeout=15)
                if antwoord.status != 200:
                    fouten["base"] = "geen_verbinding"
                else:
                    data = await antwoord.json()
                    if "meldingen" not in data:
                        fouten["base"] = "geen_feed"
            except Exception:  # noqa: BLE001 — elke fout betekent hier hetzelfde
                fouten["base"] = "geen_verbinding"
            fouten.update(self._controleer(self._verwerk(user_input)))

            zoek = (user_input.get(CONF_POST_ZOEKEN) or "").strip()
            if not fouten and zoek:
                posten = await self._zoek_posten(basis, zoek)
                if posten is None:
                    fouten[CONF_POST_ZOEKEN] = "posten_fout"
                elif not posten:
                    fouten[CONF_POST_ZOEKEN] = "geen_posten"
                else:
                    self._gegevens = {**self._verwerk(user_input), CONF_BASIS: basis}
                    self._posten = posten
                    return await self.async_step_post()

            if not fouten:
                self._gegevens = {**self._verwerk(user_input), CONF_BASIS: basis}
                return self.async_create_entry(title=_titel(self._gegevens), data=self._gegevens)

            # Bij een fout het formulier terug mét wat er al was ingevuld.
            return self.async_show_form(
                step_id="user", data_schema=_schema(self.hass, self._verwerk(user_input)), errors=fouten
            )

        return self.async_show_form(step_id="user", data_schema=_schema(self.hass), errors=fouten)

    async def async_step_post(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            if not self._voeg_posten_toe(user_input.get("posten") or []):
                return self.async_show_form(
                    step_id="post", data_schema=self._post_schema(), errors={"base": "te_veel_capcodes"}
                )
            return self.async_create_entry(title=_titel(self._gegevens), data=self._gegevens)
        return self.async_show_form(step_id="post", data_schema=self._post_schema())

    @staticmethod
    @callback
    def async_get_options_flow(entry: config_entries.ConfigEntry):
        return HierOptionsFlow(entry)


class HierOptionsFlow(_Gedeeld, config_entries.OptionsFlow):
    """Achteraf je keuzes aanpassen zonder opnieuw toe te voegen."""

    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry
        self._gegevens = {}
        self._posten = []

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        huidig = {**self._entry.data, **self._entry.options}
        fouten: dict[str, str] = {}
        await self._laad_lijsten()

        if user_input is not None:
            zoek = (user_input.get(CONF_POST_ZOEKEN) or "").strip()
            self._gegevens = self._verwerk(user_input)
            fouten.update(self._controleer(self._gegevens))
            if zoek and not fouten:
                basis = self._gegevens.get(CONF_BASIS) or huidig.get(CONF_BASIS) or DEFAULT_BASIS
                posten = await self._zoek_posten(basis, zoek)
                if posten is None:
                    fouten[CONF_POST_ZOEKEN] = "posten_fout"
                elif not posten:
                    fouten[CONF_POST_ZOEKEN] = "geen_posten"
                else:
                    self._posten = posten
                    return await self.async_step_post()
            if not fouten:
                return self.async_create_entry(title="", data=self._gegevens)
            return self.async_show_form(
                step_id="init", data_schema=_schema(self.hass, self._gegevens), errors=fouten
            )

        return self.async_show_form(step_id="init", data_schema=_schema(self.hass, huidig))

    async def async_step_post(self, user_input: dict[str, Any] | None = None):
        if user_input is not None:
            if not self._voeg_posten_toe(user_input.get("posten") or []):
                return self.async_show_form(
                    step_id="post", data_schema=self._post_schema(), errors={"base": "te_veel_capcodes"}
                )
            return self.async_create_entry(title="", data=self._gegevens)
        return self.async_show_form(step_id="post", data_schema=self._post_schema())
