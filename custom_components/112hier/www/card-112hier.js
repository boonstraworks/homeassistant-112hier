/**
 * De 112hier-kaart voor je Lovelace-dashboard.
 *
 * Twee sensoren zijn genoeg om automatiseringen op te bouwen, maar ze laten
 * zich slecht lezen: de standaardkaart toont één regel tekst en daaronder een
 * rij attributen. Deze kaart toont de meldingen zoals je ze op een
 * meldkamerscherm zou willen zien — nieuwste boven, kleur per dienst, urgentie
 * ernaast, en hoe lang geleden het was.
 *
 * Hij wordt door de integratie zelf ingeladen, dus je hoeft niets toe te
 * voegen aan je Lovelace-bronnen.
 *
 * De naam is `card-112hier` en niet `112hier-card`: een custom element mag
 * volgens de HTML-spec niet met een cijfer beginnen, en de browser weigert de
 * registratie dan zonder dat je in Home Assistant iets misgaan ziet.
 *
 * Gebruik:
 *   type: custom:card-112hier
 *   entity: sensor.112_haaglanden_meldingen_bewaard
 *   aantal: 8            (optioneel, standaard 8)
 *   alleen_spoed: false  (optioneel)
 *   reden: true          (optioneel; grijs regeltje "waarom zie ik deze?")
 *   titel: "112 in de buurt"  (optioneel)
 */

const KLEUR = {
  brandweer: '#ea580c',
  ambulance: '#dc2626',
  politie: '#2563eb',
  knrm: '#0891b2',
};

const ICOON = {
  brandweer: 'mdi:fire',
  ambulance: 'mdi:heart-pulse',
  politie: 'mdi:police-badge',
  knrm: 'mdi:lifebuoy',
};

/** "net nu", "4 min", "2 uur" — korter leest op een dashboard beter dan een klok. */
function geleden(iso) {
  if (!iso) return '';
  const sec = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (sec < 60) return 'net nu';
  if (sec < 3600) return `${Math.floor(sec / 60)} min`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} uur`;
  return `${Math.floor(sec / 86400)} d`;
}

function veilig(s) {
  return String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

// Geeft de URL alleen terug als het een echt http(s)-webadres is; blokkeert o.a. javascript:-schema's uit een zelfingestelde feed.
function webUrl(u) {
  try {
    const ontleed = new URL(String(u));
    return (ontleed.protocol === 'https:' || ontleed.protocol === 'http:') ? ontleed.href : null;
  } catch (e) {
    return null;
  }
}

class HierCard extends HTMLElement {
  static getStubConfig(hass) {
    // Bij "kaart toevoegen" meteen de juiste sensor invullen, anders staat de
    // gebruiker tegen een lege kaart aan te kijken en moet hij zelf zoeken.
    const kandidaat = Object.keys(hass.states).find(
      (e) => e.startsWith('sensor.') && hass.states[e].attributes.meldingen,
    );
    return { type: 'custom:card-112hier', entity: kandidaat || '', aantal: 8 };
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error('Kies de sensor "Meldingen bewaard" van 112hier.');
    }
    this._config = { aantal: 8, alleen_spoed: false, reden: true, ...config };
    this._vorigeSleutel = null;
    this._vorigeStaat = undefined;
    if (!this.shadowRoot) this.attachShadow({ mode: 'open' });
    // Een gewijzigde configuratie (bijvoorbeeld in de editor) meteen tonen.
    if (this._hass) this._teken();
  }

  getCardSize() {
    return 1 + Math.min(this._config.aantal, 8);
  }

  set hass(hass) {
    // Home Assistant zet `hass` opnieuw bij élke statuswijziging in het hele
    // huis — een lamp, een temperatuur. Alleen als onze eigen sensor een nieuw
    // object is, is er iets voor deze kaart veranderd. Zonder deze check werd
    // de lijst steeds opnieuw opgebouwd: hij knipperde, een hover verdween en
    // een klik op een wandtablet kwam soms niet aan.
    const staat = this._config ? hass.states[this._config.entity] : undefined;
    const eerder = this._hass;
    this._hass = hass;
    if (eerder && staat === this._vorigeStaat) return;
    this._vorigeStaat = staat;
    this._teken();
  }

  connectedCallback() {
    // Terug op deze weergave: de tijden meteen bijwerken, niet pas over 30 s.
    this._teken(true);
    // De tijden ("4 min") lopen anders pas door als er een nieuwe melding komt.
    this._tik = setInterval(() => this._teken(true), 30000);
  }

  disconnectedCallback() {
    clearInterval(this._tik);
  }

  _teken(alleenTijden = false) {
    if (!this._hass || !this._config) return;
    const staat = this._hass.states[this._config.entity];
    if (!staat) {
      this.shadowRoot.innerHTML = this._omhulsel(
        `<div class="leeg">Sensor <code>${veilig(this._config.entity)}</code> bestaat niet.</div>`,
      );
      return;
    }

    // Kan Home Assistant 112hier niet bereiken, dan heeft de sensor geen
    // attributen. Dat is geen "rustig": we tonen dan de laatst bekende lijst met
    // een waarschuwing erboven.
    const onbereikbaar = ['unavailable', 'unknown'].includes(staat.state);
    let alle = staat.attributes.meldingen;
    if (onbereikbaar || !alle) alle = this._laatsteMeldingen || [];
    else this._laatsteMeldingen = alle;

    // Het nieuwste aantal oproepen per incident. Oudere rijen van hetzelfde
    // incident hadden anders nog de stand van toen ze binnenkwamen.
    this._actueel = {};
    for (const m of alle) {
      const i = m.incident;
      if (i && i.id != null && !(i.id in this._actueel)) this._actueel[i.id] = i;
    }

    let meldingen = alle;
    if (this._config.alleen_spoed) meldingen = meldingen.filter((m) => m.spoed);
    meldingen = meldingen.slice(0, this._config.aantal);

    // Alleen opnieuw opbouwen als er werkelijk iets veranderd is; anders
    // knippert de kaart elke keer dat Home Assistant een update stuurt.
    const ontvanger = onbereikbaar ? null : (staat.attributes.ontvanger || null);
    const storing = !!(ontvanger && ontvanger.storing);
    const sleutel = meldingen.map((m) => {
      const i = m.incident && this._actueel[m.incident.id];
      return `${m.id}:${(i && i.oproepen) || ''}`;
    }).join(',') + (storing ? '|storing' : '') + (onbereikbaar ? '|weg' : '');
    if (alleenTijden && sleutel === this._vorigeSleutel) {
      this.shadowRoot.querySelectorAll('.tijd').forEach((el) => {
        el.textContent = geleden(el.dataset.tijd);
      });
      return;
    }
    this._vorigeSleutel = sleutel;

    const titel = this._config.titel || this._naam(staat);
    // Bij een storing is "niets binnengekomen" niet hetzelfde als "rustig".
    const leeg = onbereikbaar
      ? 'Home Assistant kan 112hier nu niet bereiken.'
      : storing
        ? 'Er komt nu niets binnen: de ontvanger van 112hier heeft storing.'
        : 'Rustig op dit moment. Er is nog niets binnengekomen dat aan je filters voldoet.';
    const rijen = meldingen.length
      ? meldingen.map((m) => this._rij(m)).join('')
      : `<div class="leeg">${leeg}</div>`;
    let waarschuwing = '';
    if (onbereikbaar) {
      waarschuwing = '<div class="storing">Geen verbinding met 112hier. Er kunnen meldingen ontbreken.</div>';
    } else if (storing) {
      waarschuwing = `<div class="storing">Ontvanger heeft storing${ontvanger.storing_sinds ? ` sinds ${veilig(this._klok(ontvanger.storing_sinds))}` : ''}. Er kunnen meldingen ontbreken.</div>`;
    }

    this.shadowRoot.innerHTML = this._omhulsel(`
      <div class="kop">
        <span class="naam">${veilig(titel)}</span>
        <span class="telling">${meldingen.length}</span>
      </div>
      ${waarschuwing}
      <div class="lijst">${rijen}</div>
    `);

    this.shadowRoot.querySelectorAll('.rij.klikbaar').forEach((el) => {
      const openen = () => {
        const doel = webUrl(el.dataset.url);
        if (doel) window.open(doel, '_blank', 'noopener');
      };
      el.addEventListener('click', openen);
      el.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openen(); }
      });
    });
  }

  /** De naam van het apparaat, niet die van de sensor.
   *
   * `friendly_name` is "112 · heel Nederland Meldingen bewaard": de naam van
   * de configuratie met die van de entiteit erachter geplakt. Op een kaart
   * die toch al een lijst meldingen toont is dat laatste stuk ruis.
   */
  _naam(staat) {
    const apparaatId = this._hass.entities?.[this._config.entity]?.device_id;
    const apparaat = apparaatId && this._hass.devices?.[apparaatId];
    return (apparaat && (apparaat.name_by_user || apparaat.name))
      || staat.attributes.friendly_name
      || '112-meldingen';
  }

  /** "21:14", of "ma 12 okt 21:14" als het niet vandaag was. Een storing kan dagen duren. */
  _klok(iso) {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return '';
    const vandaag = d.toDateString() === new Date().toDateString();
    return vandaag
      ? d.toLocaleTimeString('nl-NL', { hour: '2-digit', minute: '2-digit' })
      : d.toLocaleString('nl-NL', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
  }

  _rij(m) {
    const kleur = KLEUR[m.dienst] || '#64748b';
    const icoon = ICOON[m.dienst];
    const plek = [m.straat, m.plaats].filter(Boolean).join(', ');
    const afstand = m.afstand_km != null ? `${m.afstand_km} km` : '';
    // Zes oproepen voor één brand: dat zie je hier aan "6 oproepen", met de
    // nieuwste stand van het incident.
    const actueel = m.incident && this._actueel ? (this._actueel[m.incident.id] || m.incident) : m.incident;
    const inc = actueel && actueel.oproepen > 1 ? actueel : null;
    const incLabel = inc ? `${inc.oproepen} oproepen${inc.niveau === 'groot' ? ' · grote inzet' : ''}` : '';
    // Alleen rijen met een echt webadres zijn klikbaar: die krijgen cursor, hover en toetsenbordtoegang.
    const klikbaar = !!webUrl(m.url);
    return `
      <div class="rij${m.spoed ? ' spoed' : ''}${klikbaar ? ' klikbaar' : ''}" data-url="${veilig(m.url || '')}"${klikbaar ? ' tabindex="0" role="link"' : ''}>
        <span class="streep" style="background:${kleur}"></span>
        ${icoon ? `<ha-icon class="dienst-icoon" icon="${icoon}" style="color:${kleur}"></ha-icon>` : ''}
        <div class="inhoud">
          <div class="boven">
            ${m.urgentie ? `<span class="code" style="background:${kleur}">${veilig(m.urgentie)}</span>` : ''}
            <span class="tekst">${veilig(m.tekst || '')}</span>
          </div>
          <div class="onder">
            ${plek ? `<span>${veilig(plek)}</span>` : ''}
            ${afstand ? `<span class="punt">·</span><span>${veilig(afstand)}</span>` : ''}
            ${m.regio ? `<span class="punt">·</span><span>${veilig(m.regio)}</span>` : ''}
            ${incLabel ? `<span class="inc${inc.niveau === 'groot' ? ' groot' : ''}" title="${veilig(inc.samenvatting || '')}">${veilig(incLabel)}</span>` : ''}
          </div>
          ${this._config.reden && m.reden ? `<div class="reden">${veilig(m.reden)}</div>` : ''}
        </div>
        <span class="tijd" data-tijd="${veilig(m.tijd || '')}">${geleden(m.tijd)}</span>
      </div>`;
  }

  _omhulsel(binnen) {
    return `
      <style>
        ha-card { padding: 12px 0 4px; overflow: hidden; }
        .kop {
          display: flex; align-items: baseline; gap: 8px;
          padding: 0 16px 10px; border-bottom: 1px solid var(--divider-color, #e0e0e0);
        }
        .naam { font-size: 1.05rem; font-weight: 600; color: var(--primary-text-color); }
        .telling {
          margin-left: auto; font-size: .8rem; color: var(--secondary-text-color);
          background: var(--secondary-background-color, #f1f1f1);
          border-radius: 999px; padding: 1px 8px;
        }
        .lijst { display: flex; flex-direction: column; }
        .rij {
          display: flex; align-items: flex-start; gap: 10px;
          padding: 9px 16px 9px 0; cursor: default;
          border-bottom: 1px solid var(--divider-color, #ececec);
        }
        .rij:last-child { border-bottom: none; }
        .rij.klikbaar { cursor: pointer; }
        .rij.klikbaar:hover { background: var(--secondary-background-color, #f7f7f7); }
        .rij.klikbaar:focus-visible { outline: 2px solid var(--primary-color, #2563eb); outline-offset: -2px; }
        .streep { width: 4px; align-self: stretch; border-radius: 0 3px 3px 0; flex: 0 0 4px; }
        .dienst-icoon { --mdc-icon-size: 18px; flex: 0 0 auto; margin-top: 1px; }
        .inhoud { flex: 1; min-width: 0; }
        .boven { display: flex; align-items: baseline; gap: 7px; }
        .code {
          flex: 0 0 auto; color: #fff; font-size: .7rem; font-weight: 700;
          letter-spacing: .02em; border-radius: 4px; padding: 1px 5px; white-space: nowrap;
        }
        .tekst {
          color: var(--primary-text-color); font-size: .92rem; line-height: 1.35;
          display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;
          overflow: hidden;
        }
        .onder {
          margin-top: 2px; font-size: .78rem; color: var(--secondary-text-color);
          display: flex; flex-wrap: wrap; gap: 4px;
        }
        .punt { opacity: .5; }
        .tijd {
          flex: 0 0 auto; font-size: .75rem; color: var(--secondary-text-color);
          padding-top: 2px; white-space: nowrap;
        }
        .spoed .tekst { font-weight: 600; }
        .reden {
          margin-top: 2px; font-size: .72rem; color: var(--secondary-text-color);
          opacity: .8; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .inc {
          margin-left: 2px; padding: 0 6px; border-radius: 999px; font-size: .7rem;
          border: 1px solid var(--divider-color, #d0d0d0); color: var(--secondary-text-color);
        }
        .inc.groot { border-color: #dc2626; color: #dc2626; font-weight: 600; }
        .storing {
          margin: 8px 16px 0; padding: 8px 10px; border-radius: 8px; font-size: .82rem;
          background: rgba(234, 88, 12, .12); color: var(--primary-text-color);
          border-left: 3px solid #ea580c;
        }
        .leeg {
          padding: 18px 16px; color: var(--secondary-text-color);
          font-size: .88rem; line-height: 1.45;
        }
        code { font-size: .85em; }
      </style>
      <ha-card>${binnen}</ha-card>`;
  }
}

if (!customElements.get('card-112hier')) {
  customElements.define('card-112hier', HierCard);

  // Zo verschijnt de kaart in de lijst bij "Kaart toevoegen" in plaats van dat
  // je de naam uit je hoofd moet typen.
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: 'card-112hier',
    name: '112hier — meldingen',
    description: 'De laatste 112-meldingen uit jouw gebied, nieuwste boven.',
    preview: true,
    documentationURL: 'https://github.com/boonstraworks/homeassistant-112hier',
  });

  // eslint-disable-next-line no-console
  console.info('%ccard-112hier%c geladen', 'color:#ef4444;font-weight:700', '');
}
