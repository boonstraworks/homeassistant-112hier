# 112hier voor Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz)
[![Laatste versie](https://img.shields.io/github/v/release/boonstraworks/homeassistant-112hier?label=versie)](https://github.com/boonstraworks/homeassistant-112hier/releases)
[![Steun op Ko-fi](https://img.shields.io/badge/Ko--fi-steun%20112hier-72A4F2?logo=ko-fi&logoColor=white)](https://ko-fi.com/112hier)

Live 112-meldingen van brandweer, ambulance, politie en KNRM in Home Assistant,
met de gegevens van [112hier.nl](https://112hier.nl). Plus een seintje als er
een NL-Alert is voor het gebied waar je huis staat.

![De meldingen uit Noord-Holland komen binnen, met bij elke melding waarom hij er staat; rechts alle meldingen op de kaart](https://raw.githubusercontent.com/boonstraworks/homeassistant-112hier/main/docs/live.gif)

Instellen doe je via de interface: je kiest een provincie, gemeente, regio of
een straal rond je huis, en je zoekt je kazerne op naam. Geen capcodes
opzoeken, geen regels in `configuration.yaml`.

## Wat 112hier anders doet

- **Je ziet waarom een melding binnenkomt.** Bij elke melding staat de reden:
  "provincie Noord-Holland (regio Kennemerland)", "eigen post (capcode 1420999)",
  "binnen 3,2 km van je punt". Geen geraad meer bij een melding van ver weg.
- **Zes oproepen voor één brand zijn één incident**, met een samenvatting
  ("6 oproepen in 11 minuten, 2 diensten") en een event als het groter wordt.
- **Een pushbericht met een kaartje erin.** Vervolgoproepen voor hetzelfde
  incident werken één bericht bij, en oude meldingen na een storing worden
  overgeslagen.
- **Eerlijk over de ontvanger.** Valt die stil, dan zegt *Ontvangst 112hier* dat,
  en toont de kaart "storing" in plaats van "rustig".
- **NL-Alert voor jouw huis**, met het echte uitzendgebied. Het landelijke
  testbericht in juni en december zet niets in gang.
- **Aardbevingen in en rond Nederland**, van het KNMI: een melding bij een
  voelbare beving (vanaf magnitude 2,0) dicht bij huis — de gaswinningsbevingen
  in Groningen, een tektonische klap in Limburg of net over de grens.
- **Je kazerne zoeken op naam** in plaats van capcodes van negen cijfers
  overtypen.

## Wat je krijgt

**Een kaart voor je dashboard**

De meldingen zoals je ze op een meldkamerscherm zou willen zien: nieuwste
boven, een kleur per dienst, de urgentie ernaast, hoe lang geleden het was en
in het grijs waarom hij er staat. Hoort een melding bij een groter incident,
dan staat erbij hoeveel oproepen het al zijn. Klik op een regel en de melding
opent op 112hier.nl.

![Dashboardkaart en kaart met meldingen](https://raw.githubusercontent.com/boonstraworks/homeassistant-112hier/main/docs/dashboard.jpg)

```yaml
type: custom:card-112hier
entity: sensor.112_haaglanden_meldingen_bewaard
aantal: 8
reden: true        # het grijze regeltje "waarom zie ik deze?" (standaard aan)
```

De kaart wordt door de integratie zelf ingeladen — je hoeft niets toe te voegen
aan je Lovelace-bronnen. Ze staat gewoon in de lijst bij *Kaart toevoegen*.
Zegt Home Assistant dat `custom:card-112hier` niet bestaat, kijk dan bij
[Problemen](#problemen). Is 112hier even niet bereikbaar, of heeft de ontvanger
storing, dan staat dat bovenaan de kaart — nooit "rustig".

**Meldingen op de kaart**

Elke melding wordt een eigen `geo_location`-entiteit, dus je ziet ze allemaal
tegelijk op een kaart staan in plaats van één marker die door Nederland springt.
Valt een melding uit de lijst, dan verdwijnt de marker ook weer; ze stapelen zich
niet op in je entiteitenlijst.

```yaml
type: map
geo_location_sources:
  - 112hier
```

**Negen entiteiten**

| Entiteit | Waarde |
|---|---|
| Laatste melding | de meest recente melding in jouw gebied, met het icoon van de dienst |
| Meldingen bewaard | de laatste meldingen die door je filters kwamen (maximaal 30); de hele lijst staat in de attributen, en daar leest de dashboardkaart uit |
| Laatste incident | het laatste incident in je gebied: zes oproepen voor één brand als één gebeurtenis, met samenvatting en niveau |
| Spoed in de buurt | aan zolang er in het laatste kwartier een spoedmelding dichtbij was |
| Laatste NL-Alert | het meest recente NL-Alert in Nederland, met status, adviezen en of het jouw huis raakte |
| NL-Alert voor jouw locatie | aan zolang er een actief NL-Alert is waarvan het uitzendgebied jouw huis raakt |
| Laatste aardbeving | de meest recente aardbeving in en rond Nederland (KNMI), met magnitude, plaats, diepte en of hij voelbaar was |
| Voelbare aardbeving in de buurt | aan als er in het laatste uur een voelbare beving (vanaf magnitude 2,0) binnen ~80 km van je huis was |
| Ontvangst 112hier | aan zolang de ontvanger van 112hier meldingen binnenkrijgt; uit bij een storing |

De entiteit-id begint met de naam van je configuratie. Heet die "112 · Haaglanden",
dan wordt het bijvoorbeeld `sensor.112_haaglanden_laatste_melding` en
`binary_sensor.112_haaglanden_spoed_in_de_buurt`. Staat Home Assistant in een
andere taal dan Nederlands, dan krijgen ze de Engelse namen (`latest_dispatch`,
`urgent_nearby`, …).

*Spoed in de buurt* is bedoeld voor automatiseringen die je als *toestand* wilt
lezen in plaats van als gebeurtenis: "zet de lamp rood zolang dit aan staat", of
een conditie "alleen als er niks speelt". Hoe dichtbij "dichtbij" is stel je zelf
in.

De laatste melding heeft alles wat je nodig hebt in zijn attributen: `dienst`,
`urgentie`, `spoed` (true/false), `plaats`, `gemeente`, `straat`, `latitude`,
`longitude`, `nauwkeurigheid`, `afstand_km` (vanaf je huis), `capcodes`,
`eenheden`, `incident` (oproepen, niveau, samenvatting), `afbeelding` (een
kaartje van de plek), `filter_reden` en een `url` naar de melding.

**Een kant-en-klare melding op je telefoon**

Geen YAML nodig. Importeer de blueprint, kies je telefoon en je bent klaar:

[![Blueprint importeren](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fboonstraworks%2Fhomeassistant-112hier%2Fblob%2Fmain%2Fblueprints%2Fautomation%2F112hier%2Fmelding_op_je_telefoon.yaml)

- **Een kaartje van de plek** in het bericht, met een knop *Open kaart*.
- **Eén bericht per incident.** De eerste oproep is nog een losse melding;
  vanaf de tweede oproep voor dezelfde brand werken de vervolgoproepen één
  bericht bij. Op Android zoemt dat bijwerken niet opnieuw. Op iPhone is dit
  nog niet getest.
- **Spoed komt ook 's nachts door**: spoed gaat via een eigen meldingskanaal
  met hoge prioriteit, zodat de telefoon niet wacht tot het scherm aangaat.
- **Geen oude meldingen** na een internetstoring: alles ouder dan 15 minuten
  (instelbaar) gaat er niet uit.
- Je stelt in hoe ver van huis het mag zijn, welke urgenties meetellen, of
  meldingen zonder adres ook door mogen, en of je 's nachts met rust gelaten
  wilt worden — met een uitzondering voor de hoogste urgentie, zodat een
  reanimatie om drie uur 's nachts wél doorkomt.

**Events waar je automatiseringen aan hangt**

Bij elke nieuwe melding gaat er een `112hier_melding` de bus op, met dezelfde
gegevens als de sensor (ook `latitude`, `longitude`, `spoed` en
`nauwkeurigheid`) plus `filter_reden`, `leeftijd_s` (hoe oud de melding is) en
`ingehaald` (true als hij pas na een internetstoring binnenkwam; meldingen van
tijdens een herstart van Home Assistant komen niet als event). Dat is handiger
dan op een sensor triggeren, omdat je dan niets mist als er twee meldingen kort
na elkaar binnenkomen.

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
             and (trigger.event.data.afstand_km or 99) < 10
             and not trigger.event.data.ingehaald }}
    action:
      - action: light.turn_on
        target: { entity_id: light.woonkamer }
        data: { color_name: red, flash: short }
```

Bij een nieuw incident en als het groter wordt (klein → middel → groot) komt er
een `112hier_incident`, met `type: nieuw` of `type: opgeschaald`, de
samenvatting, het aantal oproepen en de diensten.

## NL-Alert

NL-Alert is het waarschuwingssysteem van de overheid: bij een brand met veel rook,
een gaswolk of een andere crisis krijgt elke telefoon in het gebied een bericht.
112hier houdt die berichten bij, met het **uitzendgebied**, en de integratie
rekent uit of jouw huis (de locatie uit de Home Assistant-instellingen) daarbinnen ligt.

- *NL-Alert voor jouw locatie* gaat aan bij een actief alert voor jouw huis,
  en weer uit als het is opgeheven of afgelopen.
- *Laatste NL-Alert* toont het laatste alert in heel Nederland; in de attributen
  staan de adviezen, de status, `voor_jou` en `test`.
- Het event `112hier_nl_alert` komt bij elk nieuw alert, en ook bij een herhaling of
  opheffing. Met `voor_jou: true` als het jouw huis raakt.
- Het **landelijke testbericht** (de eerste maandag van juni en december) zet de
  schakelaar niet aan: het event krijgt `test: true` mee.

De blueprint **NL-Alert voor jouw huis** zet bij een alert meteen de ventilatie, WTW of
airco uit die je kiest — het advies bij rook en gas — en stuurt je een bericht. Na de
opheffing kan hij alles weer aanzetten. Begon het alert terwijl Home Assistant
herstartte, dan merkt hij dat na het opstarten alsnog.

[![Blueprint importeren](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fboonstraworks%2Fhomeassistant-112hier%2Fblob%2Fmain%2Fblueprints%2Fautomation%2F112hier%2Fnl_alert_thuis.yaml)

Let op: dit vervangt het NL-Alert op je telefoon niet. 112hier haalt de alerts elke twee
minuten op uit de openbare lijst van de overheid, en de integratie kijkt ook elke twee
minuten. Het kan dus een paar minuten duren; je telefoon krijgt ze direct. Die
openbare lijst is niet officieel gedocumenteerd en heeft geen garantie.

## Aardbevingen

Het KNMI meet elke trilling in de bodem. 112hier haalt de catalogus op, laat de
groevenschoten en explosies eruit en houdt de aardbevingen in en rond Nederland
bij — de gaswinningsbevingen in Groningen, de tektonische bevingen in Limburg en
net over de grens in België en Duitsland. De integratie kent je thuislocatie en
rekent uit of een **voelbare** beving (vanaf magnitude 2,0) dicht bij je huis lag.

- *Laatste aardbeving* toont de meest recente beving in en rond Nederland; in de
  attributen staan `magnitude`, `plaats`, `diepte_km`, `soort` (`earthquake` of
  `induced`), `voelbaar`, `voor_jou` en `afstand_km` (vanaf je huis).
- *Voelbare aardbeving in de buurt* gaat aan bij een voelbare beving binnen
  ongeveer 80 km van je huis, en na een uur vanzelf weer uit.
- Het event `112hier_aardbeving` komt bij elke nieuwe beving, met `voelbaar` en
  `voor_jou`. Hang hier je automatisering aan.

De blueprint **Aardbeving in de buurt** stuurt je een bericht met de magnitude,
de plaats en de afstand, en kan lampen of een scène inschakelen.

[![Blueprint importeren](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fboonstraworks%2Fhomeassistant-112hier%2Fblob%2Fmain%2Fblueprints%2Fautomation%2F112hier%2Faardbeving_in_de_buurt.yaml)

Let op: dit is geen officiële bron. Voor het laatste nieuws en advies bij een
beving kijk je op [knmi.nl](https://www.knmi.nl/nederland-nu/seismologie/aardbevingen).
112hier haalt de catalogus elke vijf minuten op; een beving verschijnt kort nadat
het KNMI hem heeft bepaald.

## Installeren

Nodig: Home Assistant 2024.8 of nieuwer.

**Via HACS** (aanbevolen)

[![Openen in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=boonstraworks&repository=homeassistant-112hier&category=integration)

Met de knop hierboven gaat het in één keer. Liever met de hand:

1. HACS → ⋮ (rechtsboven) → *Aangepaste repositories*
2. Plak `https://github.com/boonstraworks/homeassistant-112hier`, kies type *Integratie* en klik *Toevoegen*
3. Zoek op "112hier", klik *Downloaden* en herstart Home Assistant
4. Instellingen → Apparaten & diensten → Integratie toevoegen → **112hier**

**Handmatig**

Kopieer `custom_components/112hier` naar je `config`-map en herstart.

## Bijwerken

HACS kijkt zelf of er een nieuwe versie is. Is die er, dan staat bovenaan
*Instellingen* een melding "Update beschikbaar" voor 112hier, met wat er
veranderd is. Klik op *Bijwerken*, herstart Home Assistant en ververs je
browser (Ctrl+F5), zodat ook de nieuwste dashboardkaart wordt geladen. Wat er
per versie veranderde staat bij de [releases](https://github.com/boonstraworks/homeassistant-112hier/releases).

Van 1.3 naar 1.4: had je een gebied én je eigen post ingesteld, dan kreeg je
tot nu toe alleen de oproepen van je post binnen dat gebied. Vanaf 1.4 krijg je,
zoals altijd al bedoeld was, je gebied plús je post. Wil je alleen je post, maak
het gebied dan leeg.

## Instellingen

| Instelling | Betekenis |
|---|---|
| Provincies | een hele provincie in één keer; dat is een rijtje veiligheidsregio's |
| Veiligheidsregio's | losse regio's; laat alles leeg voor heel Nederland |
| Gemeenten | alleen meldingen uit deze gemeenten (de officiële grens) |
| Woonplaats | alleen meldingen in die plaats |
| Punt + straal | alles binnen zoveel kilometer van een plek op de kaart; het punt staat standaard op je huis |
| Diensten | brandweer, ambulance, politie, KNRM |
| Alleen spoed | alleen A0, A1, P 1 en PRIO 1 |
| Zoek je post | typ een plaats of post ("Alkmaar", "Tankautospuit Haarlem") en vink in de volgende stap je pagers aan |
| Eigen post volgen | capcodes van je kazerne — die oproepen komen **altijd** door, naast je gebied: ook daarbuiten en buiten je diensten |
| Trefwoord | alleen meldingen waarin een bepaald woord staat, bijvoorbeeld `reanimatie,beknelling` |
| Negeren | nooit tonen als dit in het bericht staat, bijvoorbeeld `testoproep` |
| Capcodes negeren | nooit tonen voor deze codes, bijvoorbeeld een pieper die de hele regio meepiept |
| Spoed in de buurt | binnen hoeveel km een spoedmelding *Spoed in de buurt* aanzet |
| Hoe vaak kijken | standaard elke 30 seconden |

![Je post zoeken op naam en de pagers aanvinken](https://raw.githubusercontent.com/boonstraworks/homeassistant-112hier/main/docs/post-kiezen.jpg)

Laat je alles leeg, dan krijg je heel Nederland. Dat zijn er zo'n 4.000 per dag —
kies op zijn minst een provincie of regio.

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

## Wat gaat er naar 112hier

Om de juiste meldingen op te halen stuurt de integratie elke 30 seconden je
filterkeuzes mee: provincie of regio, gemeente, woonplaats, dienst, trefwoorden,
de capcodes van je eigen post, en je punt — afgerond op zo'n kilometer, met een
iets grotere straal; de precieze afstand rekent Home Assistant zelf uit. Bij
*Zoek je post* gaat de zoektekst mee, en je telefoon haalt het kaartje voor een
pushbericht zelf op bij 112hier. Je *Negeren*-lijsten, je exacte punt en je
thuislocatie blijven in Home Assistant.

112hier bewaart daar niets van: per dag alleen een teller met een dagelijks
wisselende code (geen IP-adres) en de versie van de integratie, om te weten
hoeveel installaties er draaien.

## Waarom zie ik deze melding?

Kijk naar `filter_reden` (in de attributen, in het event en in het grijze
regeltje op de kaart). Krijg je meldingen van buiten je provincie, dan is het
meestal een van deze:

- **Eigen post.** Oproepen voor je eigen capcodes komen altijd door, ook als je
  post buiten je gebied rijdt. Reden: "eigen post (capcode …)".
- **Een straal over de grens.** Een straal van 20 km rond Zwolle reikt tot in
  Gelderland en Drenthe.
- **Plek onbekend.** Kan een melding niet op de kaart, dan krijgt hij de regio van
  de meldkamer die alarmeerde — en sinds de samenvoegingen werkt één meldkamer
  soms voor meerdere regio's. Reden: "… plek onbekend: regio van de meldkamer".
- **Het NL-Alert op je kaart.** *Laatste NL-Alert* is landelijk en heeft
  coördinaten, dus hij staat op de standaardkaart van Home Assistant, ook als
  hij aan de andere kant van het land is.

## Overstappen van de P2000-sensor van cyberjunky

Gebruik je nu [`cyberjunky/home-assistant-p2000`](https://github.com/cyberjunky/home-assistant-p2000)
(`platform: p2000` in `configuration.yaml`)? Zo neem je je instellingen mee:

| cyberjunky (YAML) | 112hier (in de interface) |
|---|---|
| `regios: 13` | *Veiligheidsregio's* → Amsterdam-Amstelland, of in één keer een hele *Provincie* |
| `disciplines: Brandweerdiensten` | *Diensten* → Brandweer |
| `radius: 10000` (in **meters**) | *Straal* 10 (in **kilometers**) |
| `latitude` / `longitude` | *Punt op de kaart* (staat standaard op je huis) |
| `capcodes: 1403001` | *Zoek je post* op naam, of de capcode bij *Eigen post volgen* |
| `contains: GRIP` | *Alleen als het bericht dit bevat* → `GRIP` |
| `nolocation: false` | kies een straal: dan komen alleen meldingen met een plek door |
| `scan_interval: 20` | *Hoe vaak kijken* → 20 |
| `name: Amsterdam` | de naam komt vanzelf ("112 · Amsterdam-Amstelland"); wijzigen kan bij het apparaat |

In automatiseringen: de sensorwaarde is bij 112hier de leesbare regel
(*Laatste melding*), `discipline` heet `dienst`, `capcode` heet `capcodes`, en
`latitude`/`longitude` heten hetzelfde. Trigger liever op het event
`112hier_melding` dan op de sensor, dan mis je geen twee meldingen kort na
elkaar. Haal daarna de `platform: p2000`-regels uit `configuration.yaml` en
herstart.

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
- **regio uit de gemeente** (de officiële CBS-indeling), niet uit de meldkamer
  die alarmeerde
- **incidenten**, zodat zes oproepen voor één brand als één gebeurtenis te
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
er iets op bouwt. Valt de ontvanger stil, dan zie je dat aan *Ontvangst 112hier*.

Niet elke regio stuurt een adres mee. In Haaglanden en Amsterdam-Amstelland
heeft ruim 95% van de meldingen een straatnaam; in Brabant-Noord en
Midden- en West-Brabant stuurt de meldkamer alleen de plaatsnaam en is er dus
geen straat om te tonen.

Er zit geen garantie op en geen serviceafspraak. Dit is een hobbyontvanger, geen
C2000-aansluiting — **bouw er niets mee waar levens van afhangen, en bel bij nood 112.**

## Problemen

**"Custom element doesn't exist: card-112hier"** — de kaart zit in de
integratie sinds versie 1.2. Werk bij (zie hierboven), herstart en ververs je
browser met Ctrl+F5. In de app op je telefoon: sluit de app helemaal af en open
hem opnieuw.

**Heel veel `geo_location`-entiteiten** — tot en met versie 1.3.0 bleven oude
kaartmarkers in de entiteitenlijst staan, tot Home Assistant er niets meer bij
wilde zetten. Werk bij naar 1.3.1 of nieuwer: bij de eerste start ruimt de
integratie ze zelf op.

**Een reparatiemelding over "Meldingen bewaard" na de update naar 1.4** — die
sensor hield een statistiek bij die niets zei (het getal is vrijwel altijd 30).
Die is weg; open de melding onder *Instellingen → Reparaties* en kies daar
voor het opruimen van de oude statistiek (vóór Home Assistant 2024.10:
*Ontwikkelhulpmiddelen → Statistieken*, bij de foutmelding van die sensor).

**Meldingen van buiten je gebied** — zie [Waarom zie ik deze melding?](#waarom-zie-ik-deze-melding)

Iets anders? Meld het bij de [issues](https://github.com/boonstraworks/homeassistant-112hier/issues).

## De feed zelf

De integratie leest [`https://112hier.nl/feed.json`](https://112hier.nl/feed.json).
Die is vrij te gebruiken, ook zonder Home Assistant: geen sleutel, geen account,
maximaal 30 verzoeken per minuut. Documentatie op
[112hier.nl/feed](https://112hier.nl/feed).

## Steun 112hier

De integratie en de site zijn gratis en blijven dat, zonder reclame bij
spoedmeldingen. De ontvanger, de server en de stroom kosten wel geld. Vind je
het handig, dan help je met een kopje koffie om alles draaiende te houden.

[![Steun 112hier op Ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/112hier)

## Licentie

MIT. 112hier is een merk van [Boonstra Works](https://boonstraworks.nl).
