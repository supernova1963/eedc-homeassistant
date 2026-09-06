import { describe, it, expect } from 'vitest'
import { execFileSync } from 'node:child_process'

// Element-Park-Doktrin, Haelfte 4 — die ID-LISTE (2026-09-06).
//
// Ein Auto-Hide-Gate fragt „sind ALLE Element-IDs geparkt?" und braucht dafuer
// eine Liste. Driftet sie vom Gerenderten ab, wird `alleGeparkt` nie wahr und
// der leere Block bleibt im Bild stehen.
//
// Der Waechter fand bei seinem ersten Lauf ZWEI reale Faelle dieser Klasse, die
// der abgeloeste Laufzeit-Leertest nie gefunden hat: die Zaehlerstaende ohne
// Verlauf (Cockpit Tag/Monat/Jahr — sein Demo-Datensatz TRAEGT einen Verlauf)
// und die Top-10-Liste fuer alle, die nicht in den Top 10 stehen
// (`#/community/statistiken` — eine Sicht, die er nie besucht hat).
const FRONTEND_ROOT = process.cwd()

describe('Element-Park-Doktrin: ID-Liste gegen Erzeugungsstellen', () => {
  it('jede ID einer Auto-Hide-Liste wird auch wirklich gerendert', () => {
    expect(() =>
      execFileSync('node', ['scripts/check-park-idliste.mjs'], {
        cwd: FRONTEND_ROOT,
        stdio: 'pipe',
      }),
    ).not.toThrow()
  })
})
