/**
 * TagKomponenten — Komponenten- + Finanz-Blöcke der Cockpit/Tag-Sicht.
 *
 * Konvergenz statt zweiter Code-Pfad: baut aus den Tagesdaten ein
 * `AktuellerMonatResponse`-förmiges Objekt und füttert damit die BESTEHENDEN
 * Monat-Block-Bauer {@link baueKomponentenBloecke} + {@link finanzTeaserBlock}.
 * So hat Cockpit/Tag exakt dieselbe Block-Reihe/Optik wie Cockpit/Monat
 * (Vorgabe: „Monat ist die Vorlage für Tag und Jahr").
 *
 * Datenherkunft (kein neuer Endpoint):
 *  - Speicher (Ladung/Entladung/η/Zyklen), WP-Strom, Finanzen → direkt aus
 *    `TagWerte` (backend-aggregiert, kein Drift).
 *  - BKW / E-Mobilität / Sonstiges-Energie → Tagessumme der Stunden-`komponenten`
 *    je Serie, klassifiziert über die backend-gelieferte `SerieInfo`
 *    (`komponenten_kwh`-Tagesrollup ist für manche Tage leer → Stunden sind die
 *    robuste Quelle, wie schon die IST-„Tagesdetail"-KPIs).
 *
 * Tagesgenau erhebbar (D1 „maximal erheben", SPEC-COCKPIT-TAG-JAHR Abschnitt F)
 * und über `tagDetail` (Endpoint `tag-detail`) zugespielt: WP-Strom-Split
 * Heizung/Warmwasser, Speicher-Netzladung (Arbitrage), Speicher effektiver
 * Ladepreis.
 *
 * Echt MONATLICHE KPIs (WP-Wärme/JAZ/€ thermisch, E-Auto-km/Verbrauch/€/V2H
 * kein Tages-Sensor) existieren pro Tag NICHT → auf Tag bewusst weggelassen
 * (kein „—"-Clutter) + Cross-Link „→ Monat" (period='tag' in den Bauern).
 */
import { baueKomponentenBloecke } from './KomponentenSektionen'
import { finanzTeaserBlock } from './MonatRahmen'
import type { Block } from '../components/blocks'
import type { ParkApi } from '../components/park'
import type { TagWerte, StundenWert, SerieInfo, TagDetail } from '../api/energie_profil'
import type { AktuellerMonatResponse, SonstigesGeraet } from '../api/aktuellerMonat'

/** Tages-Daten → `AktuellerMonatResponse`-Shape (nur die von den Bauern gelesenen
 *  Felder; Rest bleibt undefined/null → „—"). `tagDetail` (optional) liefert die
 *  snapshot-teuren, tagesgenau erhebbaren Zusatzwerte. */
export function baueTagAlsMonat(
  tag: TagWerte, stunden: StundenWert[], serien: SerieInfo[], tagDetail?: TagDetail | null,
): AktuellerMonatResponse {
  const tagessumme = (key: string) => stunden.reduce((a, s) => a + (s.komponenten?.[key] ?? 0), 0)
  // WP-Counter pro Tag (Issue #136/#238): Tagessumme der Stundenwerte (anlagenweit).
  const wpStartsTag = stunden.reduce((a, s) => a + (s.wp_starts_anzahl ?? 0), 0)
  const wpBetriebsstundenTag = stunden.reduce((a, s) => a + (s.wp_betriebsstunden ?? 0), 0)
  let bkw = 0, emob = 0, sonstErz = 0, sonstVerb = 0
  // Pro-Gerät-Liste (Tag): je Serie ein Gerät — Tag kennt nur Erzeugung/Verbrauch
  // (kein Eigenverbrauch-/Bezug-Split auf Stundenebene).
  const sonstigesGeraete: SonstigesGeraet[] = []
  for (const s of serien) {
    const v = tagessumme(s.key)
    if (s.typ === 'balkonkraftwerk') bkw += Math.max(0, v)
    else if (s.kategorie === 'wallbox' || s.kategorie === 'eauto') emob += Math.abs(v)
    else if (s.kategorie === 'sonstige') {
      if (s.seite === 'quelle') {
        const e = Math.max(0, v); sonstErz += e
        if (e > 0) sonstigesGeraete.push({ bezeichnung: s.label, kategorie: 'erzeuger', erzeugung_kwh: e })
      } else if (s.seite === 'senke') {
        const c = Math.abs(v); sonstVerb += c
        if (c > 0) sonstigesGeraete.push({ bezeichnung: s.label, kategorie: 'verbraucher', verbrauch_kwh: c })
      }
    }
  }
  const pos = (v: number) => (v > 0 ? v : null)
  return {
    // Speicher (TagWerte, backend-aggregiert) + tagesgenaue Netzladung/Ladepreis (tagDetail).
    speicher_ladung_kwh: tag.speicher_ladung,
    speicher_entladung_kwh: tag.speicher_entladung,
    speicher_wirkungsgrad_prozent: tag.speicher_effizienz,
    speicher_vollzyklen: tag.batterie_vollzyklen,
    speicher_ladung_netz_kwh: tagDetail?.speicher_ladung_netz_kwh ?? null,
    speicher_effektiver_ladepreis_cent: tagDetail?.speicher_effektiver_ladepreis_cent ?? null,
    speicher_effektiver_ladepreis_quelle: tagDetail?.speicher_effektiver_ladepreis_quelle ?? null,
    // Wärmepumpe — Tages-Strom + Tages-Counter (Starts/Betriebsstunden, period-
    // neutraler Slot `*_summe_monat`) + tagesgenauer Strom-Split Heizung/Warmwasser
    // + thermische Wärme (tagDetail, nur mit Wärmemengenzähler → sonst null/„—").
    // Tages-Wärme ermöglicht Tages-JAZ (= Wärme ÷ Strom, im Bauer berechnet).
    wp_strom_kwh: tag.wp_strom,
    wp_strom_heizen_kwh: tagDetail?.wp_strom_heizen_kwh ?? null,
    wp_strom_warmwasser_kwh: tagDetail?.wp_strom_warmwasser_kwh ?? null,
    wp_heizung_kwh: tagDetail?.wp_heizung_kwh ?? null,
    wp_warmwasser_kwh: tagDetail?.wp_warmwasser_kwh ?? null,
    wp_waerme_kwh: ((tagDetail?.wp_heizung_kwh ?? 0) + (tagDetail?.wp_warmwasser_kwh ?? 0)) || null,
    wp_starts_summe_monat: wpStartsTag > 0 ? wpStartsTag : null,
    wp_betriebsstunden_summe_monat: wpBetriebsstundenTag > 0 ? wpBetriebsstundenTag : null,
    // E-Mobilität / BKW / Sonstiges — Tagessumme aus Stunden; PV-/Netz-Anteil der
    // Ladung tagesgenau aus tagDetail (nur mit Sensor → sonst null/„—"). km/Verbrauch/
    // V2H/€ haben keinen Tages-Sensor → bleiben null/„—".
    emob_ladung_kwh: pos(emob),
    emob_ladung_pv_kwh: tagDetail?.emob_ladung_pv_kwh ?? null,
    emob_ladung_netz_kwh: tagDetail?.emob_ladung_netz_kwh ?? null,
    bkw_erzeugung_kwh: pos(bkw),
    sonstiges_erzeugung_kwh: pos(sonstErz),
    sonstiges_verbrauch_kwh: pos(sonstVerb),
    sonstiges_geraete: sonstigesGeraete,
    investitionen_financials: sonstigesGeraete.map((g) => ({ typ: 'sonstiges', bezeichnung: g.bezeichnung })),
    // PV Tages-SOLL (OM × Lernfaktor) — für SOLL-Annotation am PV-KPI.
    soll_pv_kwh: tagDetail?.soll_pv_kwh ?? null,
    // Finanzen (TagWerte) + Tagestarif (tagDetail) für Wirkungsverluste €/Tarif-Zeile.
    netto_ertrag_euro: tag.netto_ertrag,
    einspeise_erloes_euro: tag.einspeise_erloes,
    ev_ersparnis_euro: tag.ev_ersparnis,
    netzbezug_kosten_euro: tag.netzbezug_kosten,
    einspeise_preis_cent: tagDetail?.einspeise_preis_cent ?? null,
    netzbezug_preis_cent: tagDetail?.netzbezug_preis_cent ?? null,
  } as unknown as AktuellerMonatResponse
}

/** Komponenten-Detailblöcke (aktiv-gegated) + Finanz-Teaser für einen Tag — gleiche
 *  Bauer wie Cockpit/Monat. Reihenfolge: Komponenten …, dann Finanzen (ganz unten). */
export function baueTagKomponentenUndFinanz(
  tag: TagWerte, stunden: StundenWert[], serien: SerieInfo[], park: ParkApi, tagDetail?: TagDetail | null,
): Block[] {
  const d = baueTagAlsMonat(tag, stunden, serien, tagDetail)
  const finanz = finanzTeaserBlock(d, park)
  return [...baueKomponentenBloecke(d, park, 'tag'), ...(finanz ? [finanz] : [])]
}
