import { describe, it, expect } from 'vitest'
import { baueMonatKpis } from './MonatBilanz'
import { baueJahrKpis } from './JahrBilanz'
import { aktuellerMonat, ergebnisHerleitung } from '../test/factories'
import type { KpiStripItem } from '../components/blocks'

/**
 * A6 — *Netto-Ertrag*, *Monats-/Jahresergebnis* und *Performance Ratio* nennen
 * ihre eingesetzten Werte (Fund N-365).
 *
 * ## Die Regel
 *
 * Style-Guide **A6**: *„Formel + eingesetzte Werte + Datenquelle/Zeitraum."*
 * Die fünf Kacheln hier trugen bis zum 13.09.2026 **nur** die Formel — „Einspeise-
 * Erlös + Eigenverbrauchs-Ersparnis" ohne die beiden Beträge, aus denen die Summe
 * entstanden ist, und einen Monats-Ø ohne seine Grundgesamtheit.
 *
 * ## Warum die Zahlen aus der Response kommen und nicht hier gerechnet werden
 *
 * Bauform aus `fa270c6f`: die Herleitung nennt die Zahlen, mit denen der Layer
 * gerechnet hat. Für die PR ist das entscheidend — `performance_ratio_tage` ist
 * `len(pr_werte)`, NICHT `tage_mit_daten`; mit dem falschen Nenner stünde neben
 * dem Ø eine Grundgesamtheit, die er nie benutzt hat. Die letzte Probe hält
 * genau das fest.
 */
const finde = (ks: KpiStripItem[], titel: string) => {
  const k = ks.find((x) => x.title === titel)
  expect(k, `Kachel „${titel}" muss es geben`).toBeDefined()
  return k!
}

/** Liest eine Rechenzeile und summiert ihre Summanden mit Vorzeichen — der Zwischenstand
 *  (`= x € vor Betriebskosten`) ist ein Zwischenergebnis und zählt nicht mit. */
const summeDerZeile = (zeile: string): number => {
  const ohneZwischen = zeile.replace(/ = -?[\d.]+,\d{2} € vor Betriebskosten/g, '')
  let summe = 0
  for (const m of ohneZwischen.matchAll(/(^|[+−] )([\d.]+,\d{2}) €/g)) {
    const zahl = Number(m[2].replace(/\./g, '').replace(',', '.'))
    summe += m[1].startsWith('−') ? -zahl : zahl
  }
  return Math.round(summe * 100) / 100
}
const alsZahl = (v: string | number) => Number(String(v).replace(/\./g, '').replace(',', '.'))

// Die Antwort, wie das Backend sie seit 03.10.2026 liefert: Wert UND Herleitung aus der Ergebnis-Leiter.
// (Zahlen bewusst „krumm" und mit Sonstigem, damit die Probe nicht zufällig grün ist.)
const POSTEN = [
  { name: 'Einspeise-Erlös', betrag: 148.2, feld: 'einspeise_erloes_euro', stufe: 1 as const },
  { name: 'Eigenverbrauchs-Ersparnis', betrag: 96.4, feld: 'ev_ersparnis_euro', stufe: 1 as const },
  { name: 'Sonstige Positionen', betrag: 12.3, feld: 'sonstige_netto_euro', stufe: 1 as const },
  { name: 'WP-Ersparnis', betrag: 40.0, feld: 'wp_ersparnis_euro', stufe: 2 as const },
  { name: 'Stromrechnung', betrag: -53.48, feld: 'netzbezug_kosten_euro', stufe: 2 as const },
  { name: 'Betriebskosten', betrag: -41.67, feld: 'betriebskosten_anteilig_euro', stufe: 3 as const },
]
const HERL = ergebnisHerleitung(POSTEN)
const GELD = {
  einspeise_erloes_euro: 148.2,
  ev_ersparnis_euro: 96.4,
  sonstige_netto_euro: 12.3,
  wp_ersparnis_euro: 40.0,
  netzbezug_kosten_euro: 53.48,
  betriebskosten_anteilig_euro: 41.67,
  netto_ertrag_euro: HERL.netto_ertrag.ergebnis_euro,
  ergebnis_vor_betriebskosten_euro: HERL.vor_betriebskosten.ergebnis_euro,
  ergebnis_euro: HERL.ergebnis.ergebnis_euro,
  ergebnis_herleitung: HERL,
}

describe('A6 — Cockpit/Monat nennt die eingesetzten Werte', () => {
  // Bis 03.10.2026 lautete die Erwartung hier „310,50 € − 41,67 € + 12,30 €" — Gesamt-Nettoertrag − BK + Sonstiges.
  // Sie war nur wahr, weil der Client das Sammelfeld einsetzte, in dem die Stromrechnung unsichtbar steckte (N-600,
  // #398). Die SUBSTANZ der Regel bleibt und ist jetzt die Probe: jeder Summand einzeln, und die Rechnung führt auf
  // die Zahl daneben (Gernot 02.10., [[feedback_regel_war_nur_wahr_wegen_des_defekts]]).
  it('Netto-Ertrag nennt jeden Summanden der Leiter und führt auf die Zahl daneben', () => {
    const k = finde(baueMonatKpis(aktuellerMonat(2026, 8, GELD), null), 'Netto-Ertrag')
    expect(k.formel).toBe('Einspeise-Erlös + Eigenverbrauchs-Ersparnis + Sonstige Positionen')
    expect(k.berechnung).toBe('148,20 € Einspeise-Erlös + 96,40 € Eigenverbrauchs-Ersparnis + 12,30 € Sonstige Positionen')
    expect(summeDerZeile(k.berechnung!)).toBe(alsZahl(k.value))
    expect(k.ergebnis).toBe(`= ${k.value} €`)
  })

  it('ohne Netto-Ertrag steht KEINE Rechnung da (kein „0,00 €")', () => {
    // Zweite Regelhälfte: fehlt ein Pflichtposten, liefert die Leiter keinen Wert — und neben „—" steht nichts.
    const leer = { ...HERL, netto_ertrag: { ...HERL.netto_ertrag, ergebnis_euro: null } }
    const k = finde(
      baueMonatKpis(aktuellerMonat(2026, 8, { ...GELD, ev_ersparnis_euro: null, netto_ertrag_euro: null, ergebnis_herleitung: leer }), null),
      'Netto-Ertrag',
    )
    expect(k.berechnung).toBeUndefined()
    expect(k.ergebnis).toBeUndefined()
  })

  it('Monatsergebnis nennt Einspeise-Erlös, EV-Ersparnis, Stromrechnung und Betriebskosten einzeln (N-600)', () => {
    const k = finde(baueMonatKpis(aktuellerMonat(2026, 8, GELD), null), 'Monatsergebnis')
    for (const name of ['Einspeise-Erlös', 'Eigenverbrauchs-Ersparnis', 'Stromrechnung', 'Betriebskosten', 'WP-Ersparnis']) {
      expect(k.berechnung).toContain(name)
    }
    expect(k.berechnung).not.toContain('Gesamt-Nettoertrag')
    // Der Zwischenstand vor den Betriebskosten steht in der Zeile (Stufe 2 hat im UI keinen eigenen Namen, G4).
    expect(k.berechnung).toContain(`= ${HERL.vor_betriebskosten.ergebnis_euro!.toLocaleString('de-DE', { minimumFractionDigits: 2 })} € vor Betriebskosten`)
    // Die Rechnung führt auf die Zahl daneben: 148,20 + 96,40 + 12,30 + 40,00 − 53,48 − 41,67 = 201,75.
    expect(k.value).toBe('201,75')
    expect(summeDerZeile(k.berechnung!)).toBe(alsZahl(k.value))
    expect(k.ergebnis).toBe('= 201,75 €')
  })

  it('ohne Ergebnis bleibt die Rechnung leer und der Grund steht da', () => {
    const k = finde(
      baueMonatKpis(aktuellerMonat(2026, 8, { ...GELD, ergebnis_euro: null, fehlende_posten: ['Stromrechnung'] }), null),
      'Monatsergebnis',
    )
    expect(k.value).toBe('—')
    expect(k.berechnung).toBeUndefined()
    expect(k.ergebnis).toBeUndefined()
    expect(k.hinweis).toBe('fehlt: Stromrechnung')
  })

  it('Performance Ratio nennt die Zahl der Tage, über die gemittelt wurde', () => {
    const k = finde(baueMonatKpis(aktuellerMonat(2026, 8, GELD), null, 0.82, 17), 'Performance Ratio')
    expect(k.value).toBe('0,82')
    expect(k.berechnung).toBe('Ø aus 17 Tagen mit Einstrahlungsdaten')
  })

  it('EIN Tag heißt „Tag", nicht „Tagen"', () => {
    const k = finde(baueMonatKpis(aktuellerMonat(2026, 8, GELD), null, 0.9, 1), 'Performance Ratio')
    expect(k.berechnung).toBe('Ø aus 1 Tag mit Einstrahlungsdaten')
  })

  it('ohne gelieferte Tageszahl steht der Ø ohne Grundgesamtheit da, statt einer erfundenen', () => {
    // ⭐ Der eigentliche Gegenstand: `tage_mit_daten` ist ein ANDERER Nenner
    // (Tage mit irgendwelchen Daten). Wer ihn hier einsetzte, schriebe eine
    // Grundgesamtheit hin, die der Ø nie benutzt hat. Fehlt die Zahl, bleibt
    // die Herleitung leer — die Kachel selbst bleibt sichtbar.
    const k = finde(baueMonatKpis(aktuellerMonat(2026, 8, GELD), null, 0.82, null), 'Performance Ratio')
    expect(k.value).toBe('0,82')
    expect(k.berechnung).toBeUndefined()
  })
})

describe('A6 — Cockpit/Jahr nennt dieselben Werte', () => {
  // Andere Zahlen als im Monat, damit die Probe nicht zufällig grün ist, wenn jemand den Monats-Strip zurückgibt.
  // Bis 03.10.2026: „3.722,00 € − 500,04 € + 148,50 €" (Σ Gesamt-Nettoertrag − BK + Sonstiges, im Client) — die
  // Stromrechnung steckte unsichtbar im ersten Summanden (N-600). Jetzt die Jahressummen der Posten aus der Leiter.
  const JAHR_POSTEN = [
    { name: 'Einspeise-Erlös', betrag: 1780.4, feld: 'einspeise_erloes_euro', stufe: 1 as const },
    { name: 'Eigenverbrauchs-Ersparnis', betrag: 1160.9, feld: 'ev_ersparnis_euro', stufe: 1 as const },
    { name: 'Sonstige Positionen', betrag: 148.5, feld: 'sonstige_netto_euro', stufe: 1 as const },
    { name: 'WP-Ersparnis', betrag: 1240.6, feld: 'wp_ersparnis_euro', stufe: 2 as const },
    { name: 'Stromrechnung', betrag: -459.9, feld: 'netzbezug_kosten_euro', stufe: 2 as const },
    { name: 'Betriebskosten', betrag: -500.04, feld: 'betriebskosten_anteilig_euro', stufe: 3 as const },
  ]
  const H = ergebnisHerleitung(JAHR_POSTEN)
  const jahr = {
    einspeise_erloes_euro: 1780.4, ev_ersparnis_euro: 1160.9, sonstige_netto_euro: 148.5,
    netto_ertrag_euro: H.netto_ertrag.ergebnis_euro,
    ergebnis_vor_betriebskosten_euro: H.vor_betriebskosten.ergebnis_euro,
    ergebnis_euro: H.ergebnis.ergebnis_euro,
    ergebnis_herleitung: H,
  }

  it('Netto-Ertrag und Jahresergebnis tragen ihre Summanden und führen auf die Zahl daneben', () => {
    const ks = baueJahrKpis(aktuellerMonat(2026, 0, jahr), null)
    const ne = finde(ks, 'Netto-Ertrag')
    expect(ne.berechnung).toBe('1.780,40 € Einspeise-Erlös + 1.160,90 € Eigenverbrauchs-Ersparnis + 148,50 € Sonstige Positionen')
    expect(summeDerZeile(ne.berechnung!)).toBe(alsZahl(ne.value))
    expect(ne.ergebnis).toBe('= 3.089,80 €')
    const erg = finde(ks, 'Jahresergebnis')
    for (const name of ['Einspeise-Erlös', 'Eigenverbrauchs-Ersparnis', 'Stromrechnung', 'Betriebskosten']) {
      expect(erg.berechnung).toContain(name)
    }
    expect(erg.value).toBe('3.370,46')
    expect(summeDerZeile(erg.berechnung!)).toBe(alsZahl(erg.value))
    expect(erg.ergebnis).toBe('= 3.370,46 €')
  })

  it('ohne Jahresergebnis (eine Stromrechnung fehlt) der Grund statt einer Zahl (G2/E10)', () => {
    const ks = baueJahrKpis(aktuellerMonat(2026, 0, {
      ...jahr, ergebnis_euro: null, fehlende_posten: ['Stromrechnung (Sep 2026)'],
    }), null)
    const erg = finde(ks, 'Jahresergebnis')
    expect(erg.value).toBe('—')
    expect(erg.berechnung).toBeUndefined()
    expect(erg.hinweis).toBe('fehlt: Stromrechnung (Sep 2026)')
  })
})
