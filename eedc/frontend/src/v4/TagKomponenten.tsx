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
 * ⛔ **Hier stand bis 29.08.2026: „Echt MONATLICHE KPIs (WP-Wärme/JAZ/€
 * thermisch, E-Auto-km/Verbrauch/€/V2H kein Tages-Sensor) existieren pro Tag
 * NICHT → auf Tag bewusst weggelassen (kein ‚—'-Clutter)."** Der Satz war
 * zweifach überholt und hat die Auslassung überlebt, die er begründete:
 *
 *  - **WP-Wärme und JAZ gibt es pro Tag** — seit dem 26.08. liefert der
 *    Tages-Endpunkt beides fertig aus dem Layer (W-9/W-3).
 *  - **„Weglassen statt ‚—'" ist die abgelöste Linie.** Gültig ist seit dem
 *    24.06.2026 die Gegenregel: was sensor-ableitbar, aber nicht vorhanden ist,
 *    steht als „—" **mit Grund** da; ein „—" ist Information, kein Clutter
 *    ([[feedback_sensor_ableitbar_nicht_weglassen]]). Genau danach verfahren
 *    die km- und Verbrauchs-Kacheln unten seit Langem.
 *
 * ⭐ Der Satz ist nicht nur veraltet, er war **wirksam**: Die drei Arbeitszahlen
 * je Funktion fielen im Tag ersatzlos weg, weil ihre Durchreichung fehlte — und
 * dieser Absatz las sich wie die Begründung dafür (**N-348**, 29.08.2026).
 * Was der Tag wirklich nicht kann, steht jetzt beim jeweiligen Feld.
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
    // Die Quelle gehört zum Wert: `wirkungsgradHinweis` fällt ohne sie in den
    // Bestands-Zweig und schweigt — dann stand ein η von 100,5 % ohne ein Wort
    // in der Tageskachel (T89667 #163). Seit 15.08.2026 liefert der Tag sie
    // wie der Monat.
    speicher_wirkungsgrad_quelle: tag.speicher_effizienz_quelle,
    // Kanon seit 2026-07-28: Entladung ÷ Kapazität, im Backend gerechnet.
    // `batterie_vollzyklen` (ΔSoC ÷ 200) ist eine ANDERE Größe — sie heißt
    // jetzt „SoC-Hübe" und steht in der Energieprofil-Tabelle.
    speicher_vollzyklen: tag.speicher_vollzyklen,
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
    // ⛔ **Hier stand bis 26.08.2026 `(wp_heizung ?? 0) + (wp_warmwasser ?? 0)`**
    // — seit der ersten Fassung dieser Datei, und damit die zweite Stelle für
    // den Wärme-Kanon des Layers (Befund W-9, ADR-001/S1). Die Summe war
    // *richtig*; falsch war, dass sie hier stand: Der Client kannte damit die
    // eine Hälfte der Regel („sonst Heizung + Warmwasser") und nicht die
    // andere („Gesamtwert hat Vorrang"), und die Belastbarkeits-Sperre der
    // Arbeitszahl konnte er gar nicht kennen.
    wp_waerme_kwh: tagDetail?.wp_waerme_kwh ?? null,
    wp_jaz: tagDetail?.wp_jaz ?? null,
    wp_jaz_grund: tagDetail?.wp_jaz_grund ?? null,
    wp_jaz_hinweis: tagDetail?.wp_jaz_hinweis ?? null,
    wp_jaz_zaehler_kwh: tagDetail?.wp_jaz_zaehler_kwh ?? null,
    wp_jaz_nenner_kwh: tagDetail?.wp_jaz_nenner_kwh ?? null,
    // N-348: Bis 29.08.2026 endete die Durchreichung hier, und die drei
    // je-Funktion-Zeilen fielen im Tag ERSATZLOS weg — nicht als „—", sondern
    // gar nicht, weil `jazZeile` in der geteilten Blockfabrik ohne Wert UND
    // ohne Grund nichts rendert. Der Monat lieferte beides immer. Die Zeilen
    // kommen jetzt fertig aus dem Backend, wie die Gesamtzahl darüber.
    wp_jaz_heizen: tagDetail?.wp_jaz_heizen ?? null,
    wp_jaz_heizen_grund: tagDetail?.wp_jaz_heizen_grund ?? null,
    wp_jaz_warmwasser: tagDetail?.wp_jaz_warmwasser ?? null,
    wp_jaz_warmwasser_grund: tagDetail?.wp_jaz_warmwasser_grund ?? null,
    wp_jaz_kuehlen: tagDetail?.wp_jaz_kuehlen ?? null,
    wp_jaz_kuehlen_grund: tagDetail?.wp_jaz_kuehlen_grund ?? null,
    // W-18: Der Grund kommt fertig formuliert aus dem Backend — er weiss als
    // einziger, ob der Zaehler fehlt, ob er zugeordnet aber fuer diesen Tag
    // leer ist, oder ob er zurueckgesprungen ist.
    wp_waerme_grund: tagDetail?.wp_waerme_grund ?? null,
    emob_ladung_pv_grund: tagDetail?.emob_ladung_pv_grund ?? null,
    // #263/T2 — Aufteilung Heizen/Kühlen des Tages (gemeldet von OB73-gif).
    // Die Blockfabrik zeigt den Balken bereits, sobald `wp_modus_abdeckung_h`
    // gesetzt ist — sie ist für Monat UND Tag dieselbe. Hier ist deshalb nur
    // durchzureichen, was der Tag-Endpoint liefert: **kein neuer Block, keine
    // zweite Komponente**, und der Rest kommt fertig aus dem Backend statt aus
    // einer Client-Subtraktion.
    wp_modus_strom_heizen_kwh: tagDetail?.wp_modus_strom_heizen_kwh ?? null,
    wp_modus_strom_kuehlen_kwh: tagDetail?.wp_modus_strom_kuehlen_kwh ?? null,
    wp_modus_strom_warmwasser_kwh: tagDetail?.wp_modus_strom_warmwasser_kwh ?? null,
    // E4: dieselben Segmente wie im Monat — die Blockfabrik ist geteilt.
    wp_modus_strom_lueften_kwh: tagDetail?.wp_modus_strom_lueften_kwh ?? null,
    wp_modus_strom_entfeuchten_kwh: tagDetail?.wp_modus_strom_entfeuchten_kwh ?? null,
    wp_modus_nicht_aufgeteilt_kwh: tagDetail?.wp_modus_nicht_aufgeteilt_kwh ?? null,
    wp_modus_abdeckung_h: tagDetail?.wp_modus_abdeckung_h ?? null,
    // W-17b: die Grundmenge des Balkens.
    wp_modus_strom_bezug_kwh: tagDetail?.wp_modus_strom_bezug_kwh ?? null,
    // Ohne dieses Feld zeigte der Tag die Aufteilung nur für ABGELEITETE
    // Geräte: die Blockfabrik gattert auf `wp_modus_gemessen ||
    // wp_modus_abdeckung_h > 0`, und ein Betriebsart-Zähler hat keine
    // Abdeckungs-Stunden. Monat und Jahr zeigten den Block, der Tag nie.
    wp_modus_gemessen: tagDetail?.wp_modus_gemessen ?? null,
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
    // ⭐ Die Geräte hinter den Tagessummen — Futter für den `GeraeteHinweis`
    // („Aggregiert aus: …"), den die geteilte Blockfabrik ab zwei Geräten
    // zeigt. **Kein neues Element und keine zweite Komponente:** das Element
    // gibt es für Wärmepumpe, Speicher und E-Mobilität längst, es bekam im Tag
    // nur nie etwas zu lesen.
    //
    // ⛔ **Warum das kein Schönheitsfehler war.** Monat und Jahr füllten das
    // Feld, der Tag als einzige Sicht nicht — und ein fehlender Hinweis sieht
    // nicht aus wie eine Lücke, sondern wie „hier steckt ein Gerät drin".
    // dietmar1968 betreibt eine Luft-Wasser-Wärmepumpe und eine Split-
    // Klimaanlage; beide sind `typ="waermepumpe"` und stehen deshalb in
    // denselben Balken. Er verglich diesen Balken (11 kWh) mit dem Zähler
    // seiner Klimaanlage (8,71 kWh) und schrieb: *„er vermengt die Anlagen"*
    // (T89667 #221/#226/#237). Er hatte recht — nur war die Vermengung
    // gewollt (SOLL §5: Mengen dürfen nebeneinander stehen) und nirgends
    // gesagt. Genau das sagt der Hinweis jetzt auch im Tag.
    komponenten_geraete: tagDetail?.komponenten_geraete ?? {},
  } as unknown as AktuellerMonatResponse
}

/**
 * Ladezustand des Tages aus den Stundenwerten — Spanne und Stand am Tagesende.
 *
 * Der SoC ist die einzige Speicher-Größe, die **nicht** als Tagessumme existiert:
 * Er ist ein Bestand, kein Fluss, und steht deshalb weder in `TagWerte` noch im
 * Tagesdetail. Die Stunden tragen ihn (`soc_prozent`), sichtbar war er bisher nur
 * als abgewählte Spalte der Stundentabelle.
 *
 * „Tagesende" ist der **letzte gemessene** Stundenwert, nicht zwingend 23 Uhr —
 * am laufenden Tag ist das die zuletzt aggregierte Stunde. Das ist gewollt: eine
 * Lücke am Tagesrand darf keinen SoC von 0 % vortäuschen.
 *
 * Gemeldet von dietmar1968 (Forum T89667 #97, 05.08.2026): „In dieser Aufstellung
 * fehlt mir eigentlich der Batteriespeicher mit Lade- bzw. Entladeenergie kWh und
 * SOC." Ladung/Entladung standen bereits im Speicher-Block, der SoC nicht.
 */
export function socTagWerte(stunden: StundenWert[]): { min: number; max: number; ende: number } | null {
  const werte = stunden.map((s) => s.soc_prozent).filter((v): v is number => v != null)
  if (werte.length === 0) return null
  return { min: Math.min(...werte), max: Math.max(...werte), ende: werte[werte.length - 1] }
}

/** Komponenten-Detailblöcke (aktiv-gegated) + Finanz-Teaser für einen Tag — gleiche
 *  Bauer wie Cockpit/Monat. Reihenfolge: Komponenten …, dann Finanzen (ganz unten). */
export function baueTagKomponentenUndFinanz(
  tag: TagWerte, stunden: StundenWert[], serien: SerieInfo[], park: ParkApi, tagDetail?: TagDetail | null,
): Block[] {
  const d = baueTagAlsMonat(tag, stunden, serien, tagDetail)
  const finanz = finanzTeaserBlock(d, park)
  return [...baueKomponentenBloecke(d, park, 'tag', socTagWerte(stunden)), ...(finanz ? [finanz] : [])]
}
