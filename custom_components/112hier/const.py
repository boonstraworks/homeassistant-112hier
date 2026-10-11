"""Constanten voor de 112hier-integratie."""

from datetime import timedelta

DOMAIN = "112hier"

# Waar de feed staat. Instelbaar, zodat je desgewenst je eigen ontvanger kunt
# gebruiken zonder de code aan te passen.
DEFAULT_BASIS = "https://112hier.nl"
FEED_PAD = "/feed.json"
# De NL-Alerts van de overheid, met uitzendgebied (sinds 112hier oktober 2026).
NLA_PAD = "/api/nl-alerts"

# De feed staat 30 verzoeken per minuut toe. Elke 30 seconden kijken is ruim
# binnen die grens en snel genoeg: een uitruk duurt minuten, geen seconden.
DEFAULT_INTERVAL = timedelta(seconds=30)
MIN_INTERVAL_SECONDEN = 15
# NL-Alerts komen een paar keer per week; elke twee minuten kijken is ruim genoeg.
NLA_INTERVAL = timedelta(minutes=2)

CONF_BASIS = "basis"
CONF_REGIOS = "regios"
CONF_DIENSTEN = "diensten"
CONF_PLAATS = "plaats"
CONF_STRAAL = "straal"
CONF_ALLEEN_SPOED = "alleen_spoed"
CONF_INTERVAL = "interval"
# Je eigen kazerne of post volgen. Oproepen hiervoor komen altijd door, ook
# buiten je regio en buiten de diensten die je koos — dat is het hele punt.
CONF_CAPCODES = "capcodes"
CONF_BEVAT = "bevat"
# Wat je juist nooit wilt zien. Testoproepen komen elke week langs en zijn bij
# elke P2000-ontvanger de eerste vraag die mensen stellen. Negeren gaat vóór
# alles, ook vóór je eigen post: een testoproep naar je eigen kazerne blijft
# een testoproep.
CONF_NEGEER = "negeer"
CONF_NEGEER_CAPCODES = "negeer_capcodes"
# Binnen hoeveel kilometer een spoedmelding de schakelaar "spoed in de buurt"
# aan mag zetten. 0 = alles wat door je filters komt telt mee.
CONF_SPOED_STRAAL = "spoed_straal"

# Urgenties die als spoed tellen. A0 is de hoogste ambulance-urgentie en hoort
# er dus bij — die ontbrak lang in dit soort lijstjes omdat hij zeldzaam is.
SPOED_CODES = {"A0", "A1", "P 1", "PRIO 1"}

DIENSTEN = ["brandweer", "ambulance", "politie", "knrm"]

# Het event dat wij op de bus zetten bij elke nieuwe melding. Hier hang je je
# automatiseringen aan.
EVENT_MELDING = "112hier_melding"
# Bij elk nieuw NL-Alert (en bij herhaling of opheffing). Met "voor_jou": true
# als je huis binnen het uitzendgebied ligt.
EVENT_NL_ALERT = "112hier_nl_alert"

ATTRIBUTIE = "Gegevens van 112hier.nl"
