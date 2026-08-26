import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { isValidElement } from 'react'
import { baueKomponentenBloecke } from './KomponentenSektionen'
import { KOMPONENTEN_IDENTITAET } from '../lib'
import type { Block } from '../components/blocks'
import type { ParkApi } from '../components/park'
import type { AktuellerMonatResponse } from '../api/aktuellerMonat'
import type { StundenWert } from '../api/energie_profil'
import { socTagWerte, baueTagKomponentenUndFinanz } from './TagKomponenten'
import { aktuellerMonat, tagWerte } from '../test/factories'

/** Park-Stub: nichts geparkt — für die Bauer-Aufrufe mit expliziter Periode. */
const NOOP_PARK_STUB: ParkApi = {
  aktiv: false, istGeparkt: () => false, park: () => {}, entparke: () => {}, zuruecksetzen: () => {}, geparkt: [],
  registriere: () => () => {}, parkbareAnzahl: 0,
}

/** Park-Stub: alles geparkt (Element-Park-Doktrin — leerer Block verschwindet). */
const ALLES_GEPARKT: ParkApi = {
  aktiv: true, istGeparkt: () => true, park: () => {}, entparke: () => {}, zuruecksetzen: () => {}, geparkt: [],
  registriere: () => () => {}, parkbareAnzahl: 0,
}

// Basis = nichts aktiv; Tests aktivieren gezielt einzelne Komponenten. Genau
// das ist die Nullstellung der Factory — die Aufzählung von Hand entfällt.
const d = (over: Partial<AktuellerMonatResponse> = {}) => aktuellerMonat(2026, 8, over)

describe('baueKomponentenBloecke — Aktiv-Gating', () => {
  it('keine Komponente aktiv → keine Blöcke', () => {
    expect(baueKomponentenBloecke(d())).toHaveLength(0)
  })

  it('nur aktive Komponenten erscheinen, in kanonischer Reihenfolge', () => {
    const bloecke = baueKomponentenBloecke(d({
      speicher_ladung_kwh: 99, speicher_vollzyklen: 7.7, speicher_wirkungsgrad_prozent: 73,
      wp_strom_kwh: 330, wp_waerme_kwh: 1240,
    }))
    expect(bloecke.map((b) => b.id)).toEqual(['k-speicher', 'k-waermepumpe'])
    // Sektions-Kopf-Identität kommt aus dem SoT (#3b', TYP_COLORS-Kanon) —
    // gegen die Quelle prüfen, kein hardcodiertes Duplikat.
    expect(bloecke[0].farbe).toBe(KOMPONENTEN_IDENTITAET['speicher'].farbe)
    expect(bloecke[1].farbe).toBe(KOMPONENTEN_IDENTITAET['waermepumpe'].farbe)
    expect(bloecke[1].title).toBe('Wärme/Klima')
  })

  it('Speicher-Summary trägt Ladung/Zyklen/η', () => {
    const b = baueKomponentenBloecke(d({ speicher_ladung_kwh: 99, speicher_vollzyklen: 7.7, speicher_wirkungsgrad_prozent: 73 }))[0]
    expect(b.summary).toMatch(/99 kWh geladen/)
    expect(b.summary).toMatch(/7,7 Zyklen/)
    expect(b.summary).toMatch(/73 % η/)
  })

  it('WP-Summary trägt die JAZ — aus dem Backend, nicht selbst gerechnet', () => {
    // ⚠ **Diese Probe hieß bis 26.08.2026 „JAZ (Wärme ÷ Strom)" und setzte nur
    // die beiden Mengen.** Damit hat sie genau die Client-Formel verteidigt,
    // die Befund W-3 ausmacht: Der Quotient entstand hier, **ohne** die
    // Belastbarkeits-Sperre, die Komponenten-Hub und Cockpit-Übersicht
    // anwenden — dieselbe Anlage zeigte im Hub „—" und im Cockpit eine Zahl.
    //
    // **Ihr Gegenstand bleibt gültig und sie bleibt stehen:** Die Summary soll
    // die JAZ tragen. Geändert hat sich nur, **woher** die Zahl kommt — der
    // Layer liefert sie fertig (`core/berechnungen/waermepumpe_kennzahl`).
    // [[feedback_keine_folge_aenderung_zurueckdrehen]]
    const b = baueKomponentenBloecke(d({
      wp_strom_kwh: 330, wp_waerme_kwh: 1254, wp_jaz: 3.8,
    }))[0]
    expect(b.summary).toMatch(/JAZ 3,80/)
  })

  it('WP-Summary zeigt KEINE JAZ, wenn der Layer sie sperrt', () => {
    // Die Gegenprobe, die vorher unmöglich war: Bei abgeleiteter Wärme liefert
    // das Backend `wp_jaz: null` — und die Summary nennt dann auch keine.
    // Vorher rechnete der Client 1254/330 trotzdem aus.
    const b = baueKomponentenBloecke(d({
      wp_strom_kwh: 330, wp_waerme_kwh: 1254, wp_jaz: null,
    }))[0]
    expect(b.summary).not.toMatch(/JAZ/)
    expect(b.summary).toMatch(/1\.254 kWh Wärme/)
  })

  it('alle fünf Komponenten aktiv → fünf Blöcke (Sonstiges = Erzeuger-Variante)', () => {
    const bloecke = baueKomponentenBloecke(d({
      speicher_ladung_kwh: 99, wp_strom_kwh: 330, emob_ladung_kwh: 62,
      bkw_erzeugung_kwh: 612,
      sonstiges_geraete: [{ bezeichnung: 'Mini-BHKW', kategorie: 'erzeuger', erzeugung_kwh: 320 }],
    }))
    // Default-Reihenfolge = INVESTITION_TYP_ORDER (SoT): Speicher → Balkonkraftwerk
    // → Wärmepumpe → E-Mobilität → Sonstiges (BKW vor WP).
    expect(bloecke.map((b) => b.id)).toEqual(['k-speicher', 'k-bkw', 'k-waermepumpe', 'k-emob', 'k-sonstiges-erzeuger'])
  })

  it('Sonstiges-Sonderdarstellung: 2 feste Blöcke (Erzeuger/Verbraucher), pro Gerät eigene Werte-Zeile', () => {
    const bloecke = baueKomponentenBloecke(d({
      sonstiges_geraete: [
        { bezeichnung: 'Mini-BHKW', kategorie: 'erzeuger', erzeugung_kwh: 120 },
        { bezeichnung: 'Heizstab Warmwasser', kategorie: 'verbraucher', verbrauch_kwh: 80 },
      ],
    }))
    // Feste, generische Block-Titel (NICHT der Gerätename) — der Gerätename steht
    // PRO Gerät im Block-Inhalt.
    expect(bloecke.map((b) => b.id)).toEqual(['k-sonstiges-erzeuger', 'k-sonstiges-verbraucher'])
    expect(bloecke[0].title).toBe('Sonstiges – Erzeuger')
    expect(bloecke[1].title).toBe('Sonstiges – Verbraucher')
    // Pro-Gerät-Zeile: Bezeichnung erscheint im gerenderten Block-Inhalt.
    renderBlock(bloecke, 'k-sonstiges-verbraucher')
    expect(screen.getByText('Heizstab Warmwasser')).toBeInTheDocument()
  })

  it('Sonstiges (Doktrin 2026-07-08): alle Kacheln eines Geräts geparkt → Block verschwindet', () => {
    // Je Kachel einzeln parkbar; sind ALLE Kacheln ALLER Geräte geparkt, blendet
    // der Aufrufer den Block aus (früher: pro Gerät ein gebündeltes Park-Element).
    const bloecke = baueKomponentenBloecke(d({
      sonstiges_geraete: [{ bezeichnung: 'Heizstab Warmwasser', kategorie: 'verbraucher', verbrauch_kwh: 80 }],
    }), ALLES_GEPARKT)
    expect(bloecke.find((b) => b.id === 'k-sonstiges-verbraucher')).toBeUndefined()
  })

  it('Sonstiges nur Erzeuger → nur Erzeuger-Block (generischer Titel)', () => {
    const bloecke = baueKomponentenBloecke(d({
      sonstiges_geraete: [{ bezeichnung: 'Mini-BHKW', kategorie: 'erzeuger', erzeugung_kwh: 120 }],
    }))
    expect(bloecke.map((b) => b.id)).toEqual(['k-sonstiges-erzeuger'])
    expect(bloecke[0].title).toBe('Sonstiges – Erzeuger')
  })

  it('Element-Park: alle Elemente geparkt → keine Blöcke (Block-Hide-Doktrin)', () => {
    const data = d({
      speicher_ladung_kwh: 99, wp_strom_kwh: 330, emob_ladung_kwh: 62, bkw_erzeugung_kwh: 612,
      sonstiges_geraete: [{ bezeichnung: 'Mini-BHKW', kategorie: 'erzeuger', erzeugung_kwh: 320 }],
    })
    expect(baueKomponentenBloecke(data, ALLES_GEPARKT)).toHaveLength(0)
  })
})

// E-Gegencheck: periodensinnvolle IST-Detailwerte in die Komponenten-Blöcke übernommen.
function renderBlock(bloecke: Block[], id: string) {
  const b = bloecke.find((x) => x.id === id)!
  const node = b.render(false)
  if (!isValidElement(node)) throw new Error('render() ergab kein Element')
  return render(node)
}

describe('Komponenten-Detail (E-Gegencheck)', () => {
  it('Speicher: Netzladung + Bilanz + Wirkungsverluste (€)', () => {
    const bloecke = baueKomponentenBloecke(d({
      speicher_ladung_kwh: 100, speicher_entladung_kwh: 90, speicher_ladung_netz_kwh: 0,
      einspeise_preis_cent: 8, netzbezug_preis_cent: 30,
    }))
    renderBlock(bloecke, 'k-speicher')
    // F-22: „davon" ist Pflicht — die Netzladung ist eine TEILMENGE der Ladung
    // (Vertrag in core/field_definitions.py). Ohne das Wort las ein Tester die
    // beiden Zeilen als Doppelzählung und meldete sie als Fehler.
    expect(screen.getByText('davon aus dem Netz (Arbitrage)')).toBeInTheDocument()
    expect(screen.getByText(/Bilanz \(Entladung − Ladung\)/)).toBeInTheDocument()
    // Verlust 10 kWh × 100 % PV × 8 ct = 0,80 €
    expect(screen.getByText('Wirkungsverluste (Opportunitätskosten)')).toBeInTheDocument()
    expect(screen.getByText('−0,80 €')).toBeInTheDocument()
  })

  it('Wärmepumpe: #238 Kompressor-Starts + Betriebsstunden (Σ Monat) + Strom-Split', () => {
    const bloecke = baueKomponentenBloecke(d({
      wp_strom_kwh: 330, wp_waerme_kwh: 1254,
      wp_starts_max_tag: 5, wp_starts_summe_monat: 120,
      wp_betriebsstunden_max_tag: 8.5, wp_betriebsstunden_summe_monat: 210,
      wp_strom_heizen_kwh: 200, wp_strom_warmwasser_kwh: 130,
    }))
    renderBlock(bloecke, 'k-waermepumpe')
    expect(screen.getByText('Kompressor-Starts')).toBeInTheDocument()
    expect(screen.getByText('120')).toBeInTheDocument()
    expect(screen.getByText('Betriebsstunden')).toBeInTheDocument()
    expect(screen.getByText('Stromverbrauch · davon Heizung')).toBeInTheDocument()
    expect(screen.getByText('Stromverbrauch · davon Warmwasser')).toBeInTheDocument()
  })

  // N-327 (Klausnn #263 + dietmar1968 T89667, beide 24.08.2026): Die Aufteilung
  // stand im Cockpit als nackter Balken, während der Komponenten-Hub dieselben
  // drei Größen mit Erklärung und Abdeckungs-Zeile zeigt. Beide Melder haben am
  // selben Tag dasselbe gefragt — der Grund fehlte neben der Zahl.
  it('Modus-Aufteilung: nennt Abdeckung und erklärt „Nicht aufgeteilt"', () => {
    const bloecke = baueKomponentenBloecke(d({
      wp_strom_kwh: 1,
      // Klausnns Bild: alles nicht aufgeteilt, Modus-Signal war trotzdem da.
      wp_modus_strom_heizen_kwh: 0, wp_modus_strom_kuehlen_kwh: 0,
      wp_modus_nicht_aufgeteilt_kwh: 1, wp_modus_abdeckung_h: 17,
    }))
    renderBlock(bloecke, 'k-waermepumpe')
    expect(screen.getByText('Modus erfasst')).toBeInTheDocument()
    expect(screen.getByText('17 Stunden')).toBeInTheDocument()
    // ⚠ **Auf die Aussage geprüft, nicht auf den Satzbau** (E4, 26.08.): Der
    // Wortlaut hat sich geändert, weil Lüften und Entfeuchten seither eigene
    // Segmente bekommen können und nicht mehr pauschal als Inhalt der
    // Restmenge genannt werden dürfen. Was N-327 verlangt, ist unverändert —
    // dass neben der Zahl ein Grund steht. Ein Matcher auf den ganzen Satz
    // hätte den Bau blockiert, ohne dass die Regel verletzt war
    // ([[feedback_wortlaut_filter_macht_tests_stumm]]).
    expect(screen.getByText(/ist Standby und alles/)).toBeInTheDocument()
    expect(screen.getByText(/rückwirkend gibt es sie nicht/)).toBeInTheDocument()
  })

  it('Modus-Aufteilung gemessen: Herkunft statt Stundenzahl', () => {
    // Ein Betriebsart-Zähler hat keine „Stunden mit Signal" — „0 Stunden" sähe
    // dort aus wie ein Sensor-Ausfall (dieselbe Unterscheidung wie im Hub).
    const bloecke = baueKomponentenBloecke(d({
      wp_strom_kwh: 300, wp_modus_gemessen: true,
      wp_modus_strom_heizen_kwh: 200, wp_modus_strom_kuehlen_kwh: 100,
      wp_modus_nicht_aufgeteilt_kwh: 0,
    }))
    renderBlock(bloecke, 'k-waermepumpe')
    expect(screen.getByText('Herkunft')).toBeInTheDocument()
    expect(screen.getByText('gemessen')).toBeInTheDocument()
    expect(screen.queryByText('Modus erfasst')).not.toBeInTheDocument()
  })

  it('WP ohne Counter-Daten: keine #238-Kacheln', () => {
    const bloecke = baueKomponentenBloecke(d({ wp_strom_kwh: 330, wp_waerme_kwh: 1254 }))
    renderBlock(bloecke, 'k-waermepumpe')
    expect(screen.queryByText('Kompressor-Starts')).not.toBeInTheDocument()
    expect(screen.queryByText('Betriebsstunden')).not.toBeInTheDocument()
  })

  it('E-Mobilität: Netz-Anteil + extern + V2H-Rückspeisung', () => {
    const bloecke = baueKomponentenBloecke(d({
      emob_ladung_kwh: 62, emob_ladung_netz_kwh: 20, emob_ladung_extern_kwh: 5, emob_v2h_kwh: 3,
    }))
    renderBlock(bloecke, 'k-emob')
    expect(screen.getByText('Ladung · Netz-Anteil')).toBeInTheDocument()
    expect(screen.getByText('Ladung · extern')).toBeInTheDocument()
    expect(screen.getByText('V2H-Rückspeisung')).toBeInTheDocument()
  })
})

describe('Geräte-Hinweis (Aggregation kenntlich machen)', () => {
  it('mehrere Geräte im Block → „Aggregiert aus …" mit Namen (E-Mob: Auto + Wallbox)', () => {
    const bloecke = baueKomponentenBloecke(d({
      emob_ladung_kwh: 62,
      komponenten_geraete: { 'e-auto': ['Tesla Model 3'], 'wallbox': ['go-eCharger'] },
    }))
    renderBlock(bloecke, 'k-emob')
    expect(screen.getByText(/Aggregiert aus:/)).toBeInTheDocument()
    expect(screen.getByText(/Tesla Model 3 · go-eCharger/)).toBeInTheDocument()
  })

  it('nur ein Gerät → kein Hinweis', () => {
    const bloecke = baueKomponentenBloecke(d({
      speicher_ladung_kwh: 99,
      komponenten_geraete: { 'speicher': ['BYD HVS'] },
    }))
    renderBlock(bloecke, 'k-speicher')
    expect(screen.queryByText(/Aggregiert aus/)).not.toBeInTheDocument()
  })
})

// ── Ladezustand am Tag (dietmar1968, Forum T89667 #97) ──────────────────────
// Sein Satz nannte zwei Dinge: „Lade- bzw. Entladeenergie kWh und SOC". Das
// Erste stand längst im Speicher-Block, das Zweite nirgends in der Tagessicht
// (nur als abgewählte Spalte der Stundentabelle). Der SoC ist ein BESTAND: er
// summiert sich nicht und lässt sich über einen Monat nicht mitteln — deshalb
// gibt es ihn ausschließlich auf Tagesebene.
describe('Speicher: Ladezustand (nur Tagesebene)', () => {
  const soc = { min: 12, max: 98, ende: 64 }

  it('Tag mit SoC → Kachel „Ladezustand" mit Stand am Tagesende und Spanne', () => {
    const bloecke = baueKomponentenBloecke(
      d({ speicher_ladung_kwh: 6.1, speicher_entladung_kwh: 5.4 }), NOOP_PARK_STUB, 'tag', soc,
    )
    renderBlock(bloecke, 'k-speicher')
    expect(screen.getByText('Ladezustand')).toBeInTheDocument()
    expect(screen.getByText('64')).toBeInTheDocument()
    expect(screen.getByText(/Spanne 12–98 % · Stand am Tagesende/)).toBeInTheDocument()
  })

  it('Tag ohne Lade-/Entladebewegung, aber mit SoC → der Block erscheint trotzdem', () => {
    const bloecke = baueKomponentenBloecke(d(), NOOP_PARK_STUB, 'tag', soc)
    expect(bloecke.map((b) => b.id)).toContain('k-speicher')
    renderBlock(bloecke, 'k-speicher')
    expect(screen.getByText('Ladezustand')).toBeInTheDocument()
  })

  it('Monat: derselbe Wert wird NICHT gezeigt — ein SoC-Mittel über 30 Tage sagt nichts', () => {
    const bloecke = baueKomponentenBloecke(
      d({ speicher_ladung_kwh: 207, speicher_entladung_kwh: 153 }), NOOP_PARK_STUB, 'monat', soc,
    )
    renderBlock(bloecke, 'k-speicher')
    expect(screen.queryByText('Ladezustand')).not.toBeInTheDocument()
  })

  it('Tag ohne SoC-Messung → keine Kachel (kein „—"-Platzhalter)', () => {
    const bloecke = baueKomponentenBloecke(
      d({ speicher_ladung_kwh: 6.1, speicher_entladung_kwh: 5.4 }), NOOP_PARK_STUB, 'tag', null,
    )
    renderBlock(bloecke, 'k-speicher')
    expect(screen.queryByText('Ladezustand')).not.toBeInTheDocument()
  })
})

describe('Speicher-η: der Wert trägt seine Herkunft (T89667 #163)', () => {
  // Knallfrosch meldete 100,5 % η in der Tagessicht — ohne ein Wort dazu.
  // Der Satz existierte längst (`wirkungsgradHinweis`), nur erreichte ihn die
  // Quelle nicht: `TagKomponenten` setzte das Feld nicht, also fiel die
  // Funktion in ihren Bestands-Zweig und schwieg.
  const mitQuelle = (quelle: string) => baueKomponentenBloecke(
    d({ speicher_ladung_kwh: 6.1, speicher_entladung_kwh: 5.4, speicher_wirkungsgrad_prozent: 88.5, speicher_wirkungsgrad_quelle: quelle }),
    NOOP_PARK_STUB, 'tag',
  )

  it('ΔSoC herausgerechnet → der Tageswert sagt es', () => {
    renderBlock(mitQuelle('soc_korrigiert'), 'k-speicher')
    expect(screen.getByText('Ladestand am Rand herausgerechnet')).toBeInTheDocument()
  })

  it('ohne Ladestand → „ungenau" statt kommentarlos', () => {
    renderBlock(mitQuelle('roh-unkorrigiert'), 'k-speicher')
    expect(screen.getByText(/ohne Ladestand gerechnet — ungenau/)).toBeInTheDocument()
  })

  it('kein belastbarer Wert → „—" MIT Begründung, und der Zeitraum heißt Tag', () => {
    const bloecke = baueKomponentenBloecke(
      d({ speicher_ladung_kwh: 6.1, speicher_entladung_kwh: 6.4, speicher_wirkungsgrad_prozent: null, speicher_wirkungsgrad_quelle: 'nicht-ermittelbar' }),
      NOOP_PARK_STUB, 'tag',
    )
    renderBlock(bloecke, 'k-speicher')
    expect(screen.getByText(/kein Ladestand erfasst — Tageswert nicht belastbar/)).toBeInTheDocument()
  })

  it('und der Tag reicht die Quelle auch wirklich durch — hier saß der Befund', () => {
    const werte = tagWerte('2026-08-14', {
      speicher_ladung: 6.1, speicher_entladung: 5.4,
      speicher_effizienz: 88.5, speicher_effizienz_quelle: 'roh-unkorrigiert',
    })
    const bloecke = baueTagKomponentenUndFinanz(werte, [], [], NOOP_PARK_STUB)
    renderBlock(bloecke, 'k-speicher')
    expect(screen.getByText(/ohne Ladestand gerechnet — ungenau/)).toBeInTheDocument()
  })
})

describe('socTagWerte — Spanne und Tagesende aus den Stundenwerten', () => {
  const std = (soc: number | null) => ({ soc_prozent: soc }) as StundenWert

  it('Spanne = min/max, Ende = letzter GEMESSENER Wert', () => {
    expect(socTagWerte([std(30), std(85), std(64)])).toEqual({ min: 30, max: 85, ende: 64 })
  })

  it('Lücke am Tagesende täuscht keine 0 % vor', () => {
    // Die letzten Stunden des laufenden Tages sind noch nicht aggregiert.
    expect(socTagWerte([std(30), std(64), std(null), std(null)])).toEqual({ min: 30, max: 64, ende: 64 })
  })

  it('kein einziger Messwert → null (statt 0/0/0)', () => {
    expect(socTagWerte([std(null), std(null)])).toBeNull()
    expect(socTagWerte([])).toBeNull()
  })
})
