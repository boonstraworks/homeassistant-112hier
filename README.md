# 112hier voor Home Assistant

Live 112-meldingen van brandweer, ambulance, politie en KNRM in Home Assistant,
met de gegevens van [112hier.nl](https://112hier.nl).

Instellen doe je via de interface: je klikt je regio's, diensten en eventueel een
straal rond je huis bij elkaar. Geen capcodes opzoeken, geen regels in
`configuration.yaml`.

## Wat je krijgt

**Een kaart voor je dashboard**

De meldingen zoals je ze op een meldkamerscherm zou willen zien: nieuwste
boven, een kleur per dienst, de urgentie ernaast en hoe lang geleden het was.
Klik op een regel en de melding opent op de kaart.

```yaml
type: custom:card-112hier
entity: sensor.112_haaglanden_meldingen_bewaard
aantal: 8
```

De kaart wordt door de integratie zelf ingeladen — je hoeft niets toe te voegen
aan je Lovelace-bronnen. Ze staat gewoon in de lijst bij *Kaart toevoegen*.

**Meldingen op de kaart**

Elke melding wordt een eigen `geo_location`-entiteit, dus je ziet ze allemaal
tegelijk op een kaart staan in plaats van één marker die door Nederland springt.

```yaml
type: map
geo_location_sources:
  - 112hier
hours_to_show: 2
```

**Drie entiteiten**

| Entiteit | Waarde |
|---|---|
| `sensor.laatste_melding` | de meest recente melding in jouw gebied |
| `sensor.meldingen_bewaard` | hoeveel er sinds het opstarten binnenkwamen, met de hele lijst in de attributen |
| `binary_sensor.spoed_in_de_buurt` | aan zolang er in het laatste kwartier een spoedmelding dichtbij was |
| `sensor.laatste_nl_alert` | het meest recente NL-Alert in Nederland, met status, adviezen en of het jouw huis raakte |
| `binary_sensor.nl_alert_voor_jouw_locatie` | aan zolang er een actief NL-Alert is waarvan het uitzendgebied jouw huis raakt |

Die laatste is bedoeld voor automatiseringen die je als *toestand* wilt lezen
in plaats van als gebeurtenis: "zet de lamp rood zolang dit aan staat", of een
conditie "alleen als er niks speelt". Hoe dichtbij "dichtbij" is stel je zelf
in.

De laatste melding heeft alles wat je nodig hebt in zijn attributen: `dienst`,
`urgentie`, `spoed` (true/false), `plaats`, `straat`, `latitude`, `longitude`,
`nauwkeurigheid`, `afstand_km` (vanaf je huis), `capcodes`, `eenheden`,
`incident_id` en een `url` naar de melding op de kaart.

**Een kant-en-klare melding op je telefoon**

Geen YAML nodig. Importeer de blueprint, kies je telefoon en je bent klaar:

[![Blueprint importeren](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fstevenb211%2Fhomeassistant-112hier%2Fblob%2Fmain%2Fblueprints%2Fautomation%2F112hier%2Fmelding_op_je_telefoon.yaml)

Je stelt in hoe ver van huis het mag zijn, welke urgenties meetellen, of
meldingen zonder adres ook door mogen, en of je 's nachts met rust gelaten wilt
worden — met een uitzondering voor de hoogste urgentie, zodat een reanimatie om
drie uur 's nachts wél doorkomt.

**Een event waar je automatiseringen aan hangt**

Bij elke nieuwe melding gaat er een `112hier_melding` de bus op, met dezelfde
gegevens. Dat is handiger dan op een sensor triggeren, omdat je dan niets mist
als er twee meldingen kort na elkaar binnenkomen.

```yaml
automation:
  - alias: "Lamp rood bij spoed in mijn buurt"
    trigger:
      - platform: event
        event_type: 112hier_melding
    condition:
      - condition: template
        value_template: >
          {{ trigger.event.data.urgentie in ['A0', 'A1', 'P 1']
             and (trigger.event.data.afstand_km or 99) < 10 }}
    action:
      - service: light.turn_on
        target: { entity_id: light.woonkamer }
        data: { color_name: red, flash: short }
      - service: notify.mobile_app_telefoon
        data:
          title: "{{ trigger.event.data.urgentie }} in {{ trigger.event.data.plaats }}"
          message: "{{ trigger.event.data.leesbaar }}"
          data:
            url: "{{ trigger.event.data.url }}"
```

De melding op een kaart zetten:

```yaml
type: map
entities:
  - entity: sensor.laatste_melding
```

## NL-Alert

NL-Alert is het waarschuwingssysteem van de overheid: bij een brand met veel rook,
een gaswolk of een andere crisis krijgt elke telefoon in het gebied een bericht.
112hier houdt die berichten bij, met het **uitzendgebied**, en de integratie
rekent uit of jouw huis (de locatie uit de Home Assistant-instellingen) daarbinnen ligt.

- `binary_sensor.nl_alert_voor_jouw_locatie` gaat aan bij een actief alert voor jouw huis,
  en weer uit als het is opgeheven of afgelopen.
- `sensor.laatste_nl_alert` toont het laatste alert in heel Nederland; in de attributen
  staan de adviezen, de status en `voor_jou`.
- Het event `112hier_nl_alert` komt bij elk nieuw alert, en ook bij een herhaling of
  opheffing. Met `voor_jou: true` als het jouw huis raakt.

De blueprint **NL-Alert voor jouw huis** zet bij een alert meteen de ventilatie, WTW of
airco uit die je kiest — het advies bij rook en gas — en stuurt je een bericht. Na de
opheffing kan hij alles weer aanzetten.

[![Blueprint importeren](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fstevenb211%2Fhomeassistant-112hier%2Fblob%2Fmain%2Fblueprints%2Fautomation%2F112hier%2Fnl_alert_thuis.yaml)

Let op: dit vervangt het NL-Alert op je telefoon niet. 112hier haalt de alerts elke twee
minuten op uit de openbare lijst van de overheid; je telefoon krijgt ze direct.

## Installeren

**Via HACS** (aanbevolen)

1. HACS → Integraties → ⋮ → Aangepaste repositories
2. Voeg `https://github.com/stevenb211/homeassistant-112hier` toe, categorie *Integratie*
3. Zoek op "112hier", installeer, herstart Home Assistant
4. Instellingen → Apparaten & diensten → Integratie toevoegen → **112hier**

**Handmatig**

Kopieer `custom_components/112hier` naar je `config`-map en herstart.

## Instellingen

| Instelling | Betekenis |
|---|---|
| Veiligheidsregio's | laat leeg voor heel Nederland |
| Diensten | brandweer, ambulance, politie, KNRM |
| Woonplaats | alleen meldingen in die plaats |
| Punt + straal | alles binnen zoveel kilometer van een plek op de kaart |
| Eigen post volgen | capcodes van je kazerne — die oproepen komen **altijd** door, ook buiten je regio en buiten je diensten |
| Trefwoord | alleen meldingen waarin een bepaald woord staat, bijvoorbeeld `reanimatie,beknelling` |
| Negeren | nooit tonen als dit in het bericht staat, bijvoorbeeld `testoproep` |
| Capcodes negeren | nooit tonen voor deze codes, bijvoorbeeld een pieper die de hele regio meepiept |
| Alleen spoed | alleen A0, A1, P 1 en PRIO 1 |
| Spoed in de buurt | binnen hoeveel km een spoedmelding `binary_sensor.spoed_in_de_buurt` aanzet |
| Hoe vaak kijken | standaard elke 30 seconden |

Laat je alles leeg, dan krijg je heel Nederland. Dat zijn er honderden per dag —
kies op zijn minst een regio.

Trefwoord en Negeren nemen een komma-gescheiden lijstje. Een gewoon woord zoekt
als deel van de regel, dus `brand` vindt ook "schoorsteenbrand". Zet je er een
`*` of `?` in, dan geldt het als patroon over de hele regel — dezelfde
schrijfwijze als de `match_text.txt`-bestanden van de ontvangers die je zelf
draait, zodat je een bestaand lijstje kunt overnemen:

```
*Dordrecht*, *ZWIJND*, A1 *
```

Negeren gaat vóór alles, ook vóór je eigen post: een testoproep naar je eigen
kazerne is nog steeds een testoproep.

Wil je meerdere gebieden apart bijhouden — je eigen dorp én de kazerne van je
schoonzus — voeg de integratie dan gewoon twee keer toe. Elke configuratie
krijgt een eigen apparaat met eigen sensoren en een eigen naam.

## Dit, of zelf een ontvanger bouwen?

Er zijn goede projecten waarmee je P2000 zelf uit de lucht haalt met een
RTL-SDR-stick. Die keuze gaat niet over wie beter is, maar over wat je wilt.

**Een eigen ontvanger** hoort wat jouw antenne haalt. Staat die bij jou op
zolder, dan is de ontvangst in jouw eigen straat waarschijnlijk beter dan wat
wij je kunnen geven. Je bent van niemand afhankelijk en het blijft werken als
onze site eruit ligt. Je hebt er wel hardware voor nodig, een plek voor een
antenne, en meestal Home Assistant OS of Supervised — op HA Container of Core
draait een add-on niet.

**Deze integratie** heeft geen hardware nodig en draait op elke variant van
Home Assistant. Je installeert hem en je bent klaar: geen stick, geen antenne,
geen databases die je eerst zelf moet vullen, geen API-sleutel voor
geocodering. De verrijking is al gedaan en verbetert voor iedereen tegelijk:

- **dienst uit de capcodes**, niet uit de berichtkop — die kop is niet
  waterdicht, meldkamer Amsterdam-Amstelland stuurt politie-oproepen met "P 1"
- **straatnamen getoetst aan alle 171.664 Nederlandse straatnamen**, dus ook
  "Balatonmeer" en "Het Zand" komen eruit, niet alleen wat op ‑straat eindigt
- **coördinaten met een nauwkeurigheidsniveau** erbij: adres, straat, postcode
  of alleen de woonplaats — zodat je weet hoe hard dat punt is
- **`incident_id`**, zodat zes oproepen voor één brand als één gebeurtenis te
  herkennen zijn

Het eerlijke antwoord: wil je je eigen kazerne volgen en woon je ergens waar
onze ontvangst matig is, neem dan een stick. Wil je meldingen in Home Assistant
zonder er een hobbyproject van te maken, dan is dit sneller klaar en leest het
resultaat beter.

## Eerlijk over de beperkingen

Eén antenne op één plek. Wat die niet haalt, staat ook niet in deze integratie.
Hoe goed dat gaat wordt gemeten en gepubliceerd: berichten per uur, het aandeel
dat op de kaart komt en de langste stilte staan op
[112hier.nl/ontvangst](https://112hier.nl/ontvangst). Kijk daar even voordat je
er iets op bouwt.

Niet elke regio stuurt een adres mee. In Haaglanden en Amsterdam-Amstelland
heeft ruim 95% van de meldingen een straatnaam; in Brabant-Noord en
Midden- en West-Brabant stuurt de meldkamer alleen de plaatsnaam en is er dus
geen straat om te tonen.

Er zit geen garantie op en geen serviceafspraak. Dit is een hobbyontvanger, geen
C2000-aansluiting — **bouw er niets mee waar levens van afhangen, en bel bij nood 112.**

## De feed zelf

De integratie leest [`https://112hier.nl/feed.json`](https://112hier.nl/feed.json).
Die is vrij te gebruiken, ook zonder Home Assistant: geen sleutel, geen account,
maximaal 30 verzoeken per minuut. Documentatie op
[112hier.nl/feed](https://112hier.nl/feed).

## Licentie

MIT. 112hier is een merk van [Boonstra Works](https://boonstraworks.nl).
