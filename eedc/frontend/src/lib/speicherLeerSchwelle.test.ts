/**
 * Der Client-Spiegel der Leer-Schwelle darf nicht vom Backend abdriften (#379).
 *
 * `leerSchwelleProzent` in `investitionParameter.ts` bildet
 * `core/berechnungen/speicher_potential.py::leer_schwelle_prozent` nach, damit
 * das Speicher-Formular die abgeleitete Entladegrenze **beim Eintippen** zeigen
 * kann — cbrosius' Punkt vom 30.08.2026: unter *Wirtschaftlichkeit* stand sie
 * schon, am Eingabefeld nicht.
 *
 * ⚠ **Ein Spiegel ohne Probe ist eine Drift-Wette.** Diese Datei fährt deshalb
 * genau die Stützstellen, die das Backend in
 * `backend/tests/test_speicher_zusatzpotential.py` festhält (30/24 ⇒ 23 %,
 * Rückfall-Fälle, Deckel bei 1 von 30) — wer eine Seite ändert, sieht die
 * andere rot. Die Zahlen stehen hier bewusst als Literale und nicht als
 * Wiederholung der Formel: eine Probe, die die Formel nachrechnet, prüft nur
 * sich selbst.
 */
import { describe, it, expect } from 'vitest'

import {
  SOC_LEER_PROZENT,
  SOC_LEER_MAX_PROZENT,
  leerSchwelleProzent,
} from './investitionParameter'

describe('leerSchwelleProzent — Spiegel von speicher_potential.leer_schwelle_prozent', () => {
  it('leitet Glens Grenze aus 24 von 30 kWh ab (Backend: 23 %)', () => {
    expect(leerSchwelleProzent(30, 24)).toBeCloseTo(23, 6)
  })

  it('rechnet die 10/90-Fahrweise auf 23 %, obwohl die Untergrenze 10 % ist', () => {
    // Das ist die Annahme „die Reserve sitzt unten", und sie trifft hier nicht
    // zu — deshalb nennt das Formular sie ausdruecklich, statt die Zahl allein
    // hinzuschreiben. Belegt die Abweichung, gegen die der Hinweis gebaut ist.
    expect(leerSchwelleProzent(10, 8)).toBeCloseTo(23, 6)
  })

  it.each([
    ['keine Kapazitaet gepflegt', null, null],
    ['nur brutto gepflegt', 30, null],
    ['nur netto gepflegt', null, 24],
    ['unplausibel (0)', 30, 0],
    ['nutzbar >= brutto — keine Reserve', 30, 30],
    ['nutzbar groesser als brutto', 30, 33],
  ])('faellt bei „%s" auf den Standard zurueck', (_warum, brutto, nutzbar) => {
    expect(leerSchwelleProzent(brutto, nutzbar)).toBe(SOC_LEER_PROZENT)
  })

  it('deckelt bei 50 %, damit „1 von 30 nutzbar" nicht fast alles leer nennt', () => {
    expect(leerSchwelleProzent(30, 1)).toBe(SOC_LEER_MAX_PROZENT)
  })

  it('bleibt beim Standard, wo die Ableitung darunter laege', () => {
    // 29,5 von 30 ⇒ 1,7 % abgeleitet, unter dem Rueckfall von 5 %.
    expect(leerSchwelleProzent(30, 29.5)).toBe(SOC_LEER_PROZENT)
  })
})
