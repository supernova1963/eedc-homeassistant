#!/usr/bin/env python3
"""Prüfstand Wärme/Klima seeden — in eine SQLite-Datei ODER über die echten Routen.

```bash
# Demo-DB (r28): direkt in die Datei
scripts/seed-pruefstand-waerme-klima.py --db eedc/data/devbox-r28-demo.db

# HAOS-Lab: über die API (läuft auch auf dem Lab selbst — nur Stdlib)
scripts/seed-pruefstand-waerme-klima.py --api http://local-eedc:8099
```

## Was entsteht

1. **In der bestehenden Demo-Anlage** eine Split-Klimaanlage neben der Daikin
   (Handbuch-Lage **A/E**): Ihr Strom steht neben dem der Wärmepumpe, ihre
   Wärme gibt es bauartbedingt nicht ⇒ die anlagenweite Arbeitszahl fällt weg
   und nennt ihren Grund, die Daikin behält ihre Zahl im Komponenten-Hub.
2. **Eine zweite Anlage „Prüfstand Wärme/Klima“** mit drei Wärmepumpen für die
   Lagen **G** (ein Wärmemengenzähler über Heizung und Warmwasser), **D**
   (Kältemengenzähler) und **F** (Brauchwasser).

Die Zahlen stehen in `pruefstand_waerme_klima/daten.py` und sind so normiert,
dass ein volles Kalenderjahr (2025) die Handbuch-Zahlen **exakt** trifft.

## Idempotenz

Jedes erzeugte Gerät trägt `parameter.pruefstand = "wk15"`. Ein zweiter Lauf
findet seine eigenen Zeilen daran wieder und **aktualisiert** sie; er legt
nichts doppelt an und verschiebt keine ID. Alle Zeitstempel sind Konstanten —
zwei Läufe erzeugen bitgleiche Zeilen.

## Grenzen des API-Wegs (gemessen 14.09.2026)

* **Investitions-Monatsdaten trägt nur der Monatsabschluss**
  (`POST /api/monatsabschluss/{aid}/{jahr}/{monat}`); `POST /api/monatsdaten/`
  schreibt ausschließlich die Anlagenzeile, und für `InvestitionMonatsdaten`
  gibt es keinen eigenen Schreib-Endpunkt.
* **Tages-Snapshots kann die API nicht setzen.** `sensor_snapshots`,
  `tages_energie_profil` und `tages_zusammenfassung` haben keinen
  Schreib-Endpunkt — im Lab entstehen die Tageszeilen aus dem laufenden
  MQTT-Feeder (`scripts/pruefstand-mqtt-feeder.py`), nicht aus diesem Skript.
* **Eine MQTT-Zuordnung ist nicht nötig.** MQTT-Inbound ist die
  Grundeinstellung der Datenquellen-Fläche (`datenquellen.py`:
  `QUELLE_STANDARD` ⇒ *„kein Eintrag nötig“*), und `mqtt_zaehler_keys` belegt
  einen Zähler daran, dass **Werte angekommen sind**. Der Seeder setzt deshalb
  keine Quelle; er würde die Grundeinstellung nur bestätigen.
"""

from __future__ import annotations

import argparse
import calendar
import json
import os
import sqlite3
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pruefstand_waerme_klima import daten as D  # noqa: E402

#: Fester Zeitstempel für alle geschriebenen Zeilen. **Keine echte Uhr** — sonst
#: unterschieden sich zwei Läufe in jeder Zeile, und „der zweite Lauf ändert
#: nichts“ wäre nicht mehr prüfbar.
SEED_ZEIT = "2026-09-14 00:00:00"
SEED_ZEIT_ISO = "2026-09-14T00:00:00Z"
SEED_QUELLE = "auto:demo_data"
SEED_WRITER = "pruefstand_wk15"

DEMO_ANLAGE_NAME = "Demo-Anlage"

#: Die Monate, für die eine Zeile **geschrieben** wird. Der Generator kennt
#: einen Monat mehr (September 2026) — er ist der **laufende** und bleibt
#: bewusst ohne gespeicherte Zeile: im Lab kommt er über MQTT, in der Demo-DB
#: aus den Tages-Snapshots. Ohne diese Trennung wäre „laufender Monat" auf
#: keiner der beiden Boxen klickbar.
GESPEICHERTE_MONATE = frozenset(
    D.monatsachse(D.MONAT_VON, D.MONAT_BIS_GESPEICHERT)
)


def _provenance(felder, praefix: str = "") -> str:
    return json.dumps({
        f"{praefix}{f}": {"source": SEED_QUELLE, "writer": SEED_WRITER,
                          "at": SEED_ZEIT_ISO}
        for f in felder
    }, ensure_ascii=False)


# ═══ Anlagenzeile der Prüfstand-Anlage ══════════════════════════════════════

def anlagen_monatswerte() -> dict[tuple[int, int], dict[str, float]]:
    """Netzbezug und Einspeisung der Prüfstand-Anlage je Monat.

    **Aus denselben Gerätezahlen gebildet, nicht daneben erfunden.** Der
    Netzbezug trägt Haushalt + Wärmepumpenstrom abzüglich des PV-Anteils, der
    zeitgleich anfällt; die Einspeisung ist der Rest der Erzeugung. Beide
    Größen sind hier **Kontext** — geprüft wird Wärme/Klima.
    """
    monate = D.monatsachse()
    pv = D.monatswerte(D.PRUEFSTAND_PV)
    wp_strom: dict[tuple[int, int], float] = {}
    for geraet in (D.VAILLANT, D.NIBE, D.STIEBEL):
        for schluessel, zeile in D.monatswerte(geraet).items():
            summe = sum(
                wert for feld, wert in zeile.items()
                if feld in ("stromverbrauch_kwh", "strom_heizen_kwh",
                            "strom_warmwasser_kwh", "betriebsart_strom_kuehlen_kwh")
            )
            wp_strom[schluessel] = wp_strom.get(schluessel, 0.0) + summe

    aus: dict[tuple[int, int], dict[str, float]] = {}
    for schluessel in monate:
        pv_kwh = pv.get(schluessel, {}).get("pv_erzeugung_kwh", 0.0)
        verbrauch = D.HAUSHALT_KWH_MONAT + wp_strom.get(schluessel, 0.0)
        # Eigenverbrauchsquote saisonal: im Sommer deckt die PV mehr.
        quote = 0.55 if schluessel[1] in (4, 5, 6, 7, 8, 9) else 0.30
        eigen = min(pv_kwh * quote, verbrauch)
        aus[schluessel] = {
            "netzbezug_kwh": round(max(0.0, verbrauch - eigen), 1),
            "einspeisung_kwh": round(max(0.0, pv_kwh - eigen), 1),
            # ⚠ Monatsmittel, **kein** Ersatz für die Tagesreihe: die
            # Heizgradtage lesen ausdrücklich Tageswerte. Der Wert steht hier,
            # weil der Daten-Checker ihn sonst in allen 24 Monaten vermisst.
            "durchschnittstemperatur": MONATSTEMPERATUR[schluessel[1]],
        }
    return aus


#: Monatsmittel der Außentemperatur (°C) — Kassel, langjähriges Mittel.
MONATSTEMPERATUR = {1: 1.5, 2: 2.4, 3: 5.6, 4: 9.8, 5: 14.1, 6: 17.3,
                    7: 19.1, 8: 18.6, 9: 14.6, 10: 10.1, 11: 5.4, 12: 2.4}


# ═══ SQLite-Schreiber ════════════════════════════════════════════════════════

class DbSeeder:
    """Schreibt direkt in eine eedc-SQLite-Datei (Demo-DB-Pipeline)."""

    def __init__(self, pfad: str, demo_anlage: Optional[str] = None,
                 verbose: bool = True):
        self.con = sqlite3.connect(pfad)
        self.con.row_factory = sqlite3.Row
        self.cur = self.con.cursor()
        self.demo_anlage_bez = demo_anlage or DEMO_ANLAGE_NAME
        self.verbose = verbose
        self.bericht: list[str] = []

    def log(self, text: str) -> None:
        self.bericht.append(text)
        if self.verbose:
            print(text)

    # — Stammdaten ————————————————————————————————————————————————————

    def demo_anlage_id(self) -> int:
        row = self.cur.execute(
            "SELECT id FROM anlagen WHERE anlagenname = ?", (self.demo_anlage_bez,)
        ).fetchone()
        if row:
            return int(row["id"])
        row = self.cur.execute(
            "SELECT a.id FROM anlagen a JOIN investitionen i ON i.anlage_id = a.id "
            "GROUP BY a.id ORDER BY COUNT(i.id) DESC LIMIT 1"
        ).fetchone()
        if not row:
            raise SystemExit("Keine Anlage in der DB — nichts zum Anhängen.")
        return int(row["id"])

    def pruefstand_anlage_id(self) -> int:
        row = self.cur.execute(
            "SELECT id FROM anlagen WHERE anlagenname = ?", (D.PRUEFSTAND_ANLAGE,)
        ).fetchone()
        if row:
            aid = int(row["id"])
            self.cur.execute(
                "UPDATE anlagen SET leistung_kwp=?, installationsdatum=?, updated_at=? "
                "WHERE id=?",
                (D.PRUEFSTAND_PV_KWP, D.VAILLANT.anschaffungsdatum.isoformat(),
                 SEED_ZEIT, aid),
            )
            self.log(f"Anlage „{D.PRUEFSTAND_ANLAGE}“ vorhanden (id {aid}) — aktualisiert")
            return aid
        self.cur.execute(
            "INSERT INTO anlagen (anlagenname, leistung_kwp, installationsdatum, "
            " standort_land, standort_plz, standort_ort, standort_strasse, "
            " latitude, longitude, ausrichtung, neigung_grad, sensor_mapping, "
            " wetter_provider, wetter_modell, prognose_quelle, "
            " steuerliche_behandlung, ust_satz_prozent, community_auto_share, "
            " vollbackfill_durchgefuehrt, netz_puffer_w, unterliegt_eeg_51, "
            " guenstig_schwelle_prozent, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (D.PRUEFSTAND_ANLAGE, D.PRUEFSTAND_PV_KWP,
             D.VAILLANT.anschaffungsdatum.isoformat(),
             "DE", "34117", "Kassel", "Prüfstandweg 1", 51.3127, 9.4797,
             "Süd", 30.0, "{}", "auto", "auto", "eedc", "keine_ust", 19.0,
             0, 0, 100, 0, 10.0, SEED_ZEIT, SEED_ZEIT),
        )
        aid = int(self.cur.lastrowid)
        self.log(f"Anlage „{D.PRUEFSTAND_ANLAGE}“ neu angelegt (id {aid})")
        return aid

    def geraet_id(self, anlage_id: int, geraet: D.Geraet) -> int:
        row = self.cur.execute(
            "SELECT id, parameter FROM investitionen WHERE anlage_id = ? "
            "AND json_extract(parameter, '$.pruefstand') = ? "
            "AND bezeichnung = ?",
            (anlage_id, D.PRUEFSTAND_MARKE, geraet.bezeichnung),
        ).fetchone()
        parameter = json.dumps(geraet.parameter, ensure_ascii=False)
        if row:
            iid = int(row["id"])
            self.cur.execute(
                "UPDATE investitionen SET typ=?, bezeichnung=?, anschaffungsdatum=?, "
                " anschaffungskosten_gesamt=?, anschaffungskosten_alternativ=?, "
                " parameter=?, aktiv=1, leistung_kwp=?, "
                " updated_at=? WHERE id=?",
                (geraet.typ, geraet.bezeichnung, geraet.anschaffungsdatum.isoformat(),
                 geraet.anschaffungskosten_gesamt,
                 geraet.anschaffungskosten_alternativ, parameter,
                 D.PRUEFSTAND_PV_KWP if geraet.typ == "pv-module" else None,
                 SEED_ZEIT, iid),
            )
            self.log(f"  Gerät „{geraet.bezeichnung}“ vorhanden (id {iid}) — aktualisiert")
            return iid
        self.cur.execute(
            "INSERT INTO investitionen (anlage_id, typ, bezeichnung, anschaffungsdatum, "
            " anschaffungskosten_gesamt, anschaffungskosten_alternativ, parameter, "
            " aktiv, leistung_kwp, ausrichtung, "
            " neigung_grad, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (anlage_id, geraet.typ, geraet.bezeichnung,
             geraet.anschaffungsdatum.isoformat(), geraet.anschaffungskosten_gesamt,
             geraet.anschaffungskosten_alternativ,
             parameter, 1,
             D.PRUEFSTAND_PV_KWP if geraet.typ == "pv-module" else None,
             "Süd" if geraet.typ == "pv-module" else None,
             30.0 if geraet.typ == "pv-module" else None,
             SEED_ZEIT, SEED_ZEIT),
        )
        iid = int(self.cur.lastrowid)
        self.log(f"  Gerät „{geraet.bezeichnung}“ neu angelegt (id {iid})")
        return iid

    # — Monatszeilen ———————————————————————————————————————————————————

    def vorhandene_monate(self, anlage_id: int) -> set[tuple[int, int]]:
        return {
            (int(r["jahr"]), int(r["monat"]))
            for r in self.cur.execute(
                "SELECT jahr, monat FROM monatsdaten WHERE anlage_id = ?", (anlage_id,)
            )
        }

    def schreibe_anlagen_monate(self, anlage_id: int) -> int:
        werte = anlagen_monatswerte()
        n = 0
        for (jahr, monat), zeile in sorted(werte.items()):
            if (jahr, monat) not in GESPEICHERTE_MONATE:
                continue
            prov = _provenance(zeile.keys())
            vorhanden = self.cur.execute(
                "SELECT id FROM monatsdaten WHERE anlage_id=? AND jahr=? AND monat=?",
                (anlage_id, jahr, monat),
            ).fetchone()
            if vorhanden:
                self.cur.execute(
                    "UPDATE monatsdaten SET einspeisung_kwh=?, netzbezug_kwh=?, "
                    " durchschnittstemperatur=?, datenquelle='demo', "
                    " source_provenance=?, updated_at=? WHERE id=?",
                    (zeile["einspeisung_kwh"], zeile["netzbezug_kwh"],
                     zeile["durchschnittstemperatur"], prov,
                     SEED_ZEIT, vorhanden["id"]),
                )
            else:
                self.cur.execute(
                    "INSERT INTO monatsdaten (anlage_id, jahr, monat, einspeisung_kwh, "
                    " netzbezug_kwh, durchschnittstemperatur, datenquelle, "
                    " source_provenance, geprueft_gegen, "
                    " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (anlage_id, jahr, monat, zeile["einspeisung_kwh"],
                     zeile["netzbezug_kwh"], zeile["durchschnittstemperatur"],
                     "demo", prov, "{}", SEED_ZEIT, SEED_ZEIT),
                )
            n += 1
        self.log(f"  Anlagen-Monatszeilen: {n}")
        return n

    def schreibe_geraete_monate(self, inv_id: int, geraet: D.Geraet,
                                nur_monate: Optional[set[tuple[int, int]]] = None) -> int:
        werte = D.monatswerte(geraet)
        n = 0
        for schluessel, zeile in sorted(werte.items()):
            if schluessel not in GESPEICHERTE_MONATE:
                continue
            if nur_monate is not None and schluessel not in nur_monate:
                continue
            if not zeile:
                continue
            jahr, monat = schluessel
            daten = json.dumps(zeile, ensure_ascii=False)
            prov = _provenance(zeile.keys(), praefix="verbrauch_daten.")
            vorhanden = self.cur.execute(
                "SELECT id FROM investition_monatsdaten "
                "WHERE investition_id=? AND jahr=? AND monat=?",
                (inv_id, jahr, monat),
            ).fetchone()
            if vorhanden:
                self.cur.execute(
                    "UPDATE investition_monatsdaten SET verbrauch_daten=?, "
                    " source_provenance=?, updated_at=? WHERE id=?",
                    (daten, prov, SEED_ZEIT, vorhanden["id"]),
                )
            else:
                self.cur.execute(
                    "INSERT INTO investition_monatsdaten (investition_id, jahr, monat, "
                    " verbrauch_daten, source_provenance, geprueft_gegen, created_at, "
                    " updated_at) VALUES (?,?,?,?,?,?,?,?)",
                    (inv_id, jahr, monat, daten, prov, "{}", SEED_ZEIT, SEED_ZEIT),
                )
            n += 1
        self.log(f"    Monatszeilen: {n}")
        return n

    # — Tarife ————————————————————————————————————————————————————————

    def schreibe_tarife(self, anlage_id: int) -> int:
        n = 0
        for tarif in D.TARIFE:
            vorhanden = self.cur.execute(
                "SELECT id FROM strompreise WHERE anlage_id=? AND gueltig_ab=?",
                (anlage_id, tarif["gueltig_ab"].isoformat()),
            ).fetchone()
            felder = (
                tarif["netzbezug_arbeitspreis_cent_kwh"],
                tarif["einspeiseverguetung_cent_kwh"],
                tarif["grundpreis_euro_monat"],
                tarif["gueltig_bis"].isoformat() if tarif["gueltig_bis"] else None,
                tarif["tarifname"], tarif["anbieter"],
            )
            if vorhanden:
                self.cur.execute(
                    "UPDATE strompreise SET netzbezug_arbeitspreis_cent_kwh=?, "
                    " einspeiseverguetung_cent_kwh=?, grundpreis_euro_monat=?, "
                    " gueltig_bis=?, tarifname=?, anbieter=?, updated_at=? WHERE id=?",
                    (*felder, SEED_ZEIT, vorhanden["id"]),
                )
            else:
                self.cur.execute(
                    "INSERT INTO strompreise (anlage_id, netzbezug_arbeitspreis_cent_kwh, "
                    " einspeiseverguetung_cent_kwh, grundpreis_euro_monat, gueltig_ab, "
                    " gueltig_bis, tarifname, anbieter, verwendung, einspeisung_variabel, "
                    " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (anlage_id, tarif["netzbezug_arbeitspreis_cent_kwh"],
                     tarif["einspeiseverguetung_cent_kwh"],
                     tarif["grundpreis_euro_monat"], tarif["gueltig_ab"].isoformat(),
                     tarif["gueltig_bis"].isoformat() if tarif["gueltig_bis"] else None,
                     tarif["tarifname"], tarif["anbieter"], "allgemein", 0,
                     SEED_ZEIT, SEED_ZEIT),
                )
            n += 1
        self.log(f"  Tarife: {n}")
        return n

    # — Zuordnung ——————————————————————————————————————————————————————

    def schreibe_sensor_mapping(self, anlage_id: int,
                                zuordnungen: dict[int, D.Geraet]) -> int:
        row = self.cur.execute(
            "SELECT sensor_mapping FROM anlagen WHERE id=?", (anlage_id,)
        ).fetchone()
        mapping = json.loads(row["sensor_mapping"] or "{}") or {}
        invs = mapping.setdefault("investitionen", {})
        n = 0
        for inv_id, geraet in zuordnungen.items():
            eintrag = invs.setdefault(str(inv_id), {})
            felder = eintrag.setdefault("felder", {})
            for feld in geraet.zaehler:
                felder[feld] = {"strategie": "sensor",
                                "sensor_id": D.demo_sensor(geraet, feld)}
                n += 1
            if geraet.modus_signal:
                # Der Betriebsmodus ist ein ZUSTAND, kein Zähler — er bekommt
                # keinen Snapshot und keine Einheit (`ist_zustand_feld`).
                felder["betriebsmodus"] = {
                    "strategie": "sensor",
                    "sensor_id": f"climate.demo_{geraet.schluessel}",
                }
                n += 1
        self.cur.execute(
            "UPDATE anlagen SET sensor_mapping=?, updated_at=? WHERE id=?",
            (json.dumps(mapping, ensure_ascii=False), SEED_ZEIT, anlage_id),
        )
        self.log(f"  sensor_mapping: {n} Felder")
        return n

    # — Tagesebene ————————————————————————————————————————————————————

    def demo_tage(self, anlage_id: int) -> list[date]:
        """Die Tage, an denen die Demo-Anlage **schon** Stundenzeilen hat.

        Der Seed erfindet für sie keine neuen Tage: ein Tag ohne PV-Zeile sähe
        im Cockpit → Tag aus wie ein Ausfall.
        """
        return [
            date.fromisoformat(r["datum"])
            for r in self.cur.execute(
                "SELECT DISTINCT datum FROM tages_energie_profil WHERE anlage_id=? "
                "ORDER BY datum", (anlage_id,)
            )
        ]

    def schreibe_snapshots(self, anlage_id: int, inv_id: int, geraet: D.Geraet,
                           tage: list[date]) -> int:
        """Kumulative Zählerstände an den Tagesrändern (00:00 **und** 23:00).

        Zwei Ränder je Tag, weil die Tageszeile je nach Herkunft vorwärts
        ([00:00, 24:00)) oder rückwärts ([Vortag 23:00, 23:00)) gelesen wird
        (N-444). Das Modell ist **ein Zuwachs je Tag**: in [23:00, 24:00) fällt
        nichts an, deshalb liefern beide Fenster dieselbe Menge.
        """
        if not tage or not geraet.zaehler:
            return 0
        monate = D.monatswerte(geraet)
        stand = {feld: D.ZAEHLER_STARTSTAND.get(feld, 0.0) for feld in geraet.zaehler}
        keys = [D.snapshot_key(inv_id, f) for f in geraet.zaehler]
        zeilen: list[tuple] = []
        vortag = tage[0] - timedelta(days=1)
        for feld in geraet.zaehler:
            zeilen.append((anlage_id, D.snapshot_key(inv_id, feld),
                           f"{vortag.isoformat()} 23:00:00", round(stand[feld], 3),
                           "ha_statistics"))
        vorheriger: Optional[date] = None
        for tag in tage:
            if vorheriger is not None and (tag - vorheriger).days > 1:
                # ⚠ **Lücke im Fenster** (die Demo hat zwei Blöcke: Herbst 2025
                # und Frühjahr/Sommer 2026). Der erste Tag nach der Lücke
                # braucht einen Rand um **Vortag 23:00** — sonst findet das
                # Rückwärts-Fenster [Vortag 23:00, heute 23:00) seinen linken
                # Rand nicht und der Tag bleibt ohne Wert (N-444). Der Stand
                # ist derselbe wie am letzten Tag davor: An Tagen, die der Seed
                # nicht kennt, ist auch nichts gelaufen.
                for feld in geraet.zaehler:
                    zeilen.append((
                        anlage_id, D.snapshot_key(inv_id, feld),
                        f"{(tag - timedelta(days=1)).isoformat()} 23:00:00",
                        round(stand[feld], 3), "ha_statistics"))
            bild = D.tagesbild(geraet, tag, monate)
            for feld in geraet.zaehler:
                key = D.snapshot_key(inv_id, feld)
                zeilen.append((anlage_id, key, f"{tag.isoformat()} 00:00:00",
                               round(stand[feld], 3), "ha_statistics"))
                stand[feld] += bild.tag.get(feld, 0.0)
                zeilen.append((anlage_id, key, f"{tag.isoformat()} 23:00:00",
                               round(stand[feld], 3), "ha_statistics"))
            vorheriger = tag
        letzter = tage[-1] + timedelta(days=1)
        for feld in geraet.zaehler:
            zeilen.append((anlage_id, D.snapshot_key(inv_id, feld),
                           f"{letzter.isoformat()} 00:00:00", round(stand[feld], 3),
                           "ha_statistics"))
        # ⛔ **Upsert statt `INSERT OR REPLACE`.** REPLACE löscht die
        # kollidierende Zeile und legt eine neue an — mit **neuer** `id`. Beim
        # zweiten Lauf wäre die Datei damit nicht mehr bitgleich, obwohl sich
        # kein einziger Wert geändert hat, und der Idempotenz-Beleg wäre
        # wertlos. `ON CONFLICT … DO UPDATE` behält die Zeile.
        self.cur.executemany(
            "INSERT INTO sensor_snapshots "
            "(anlage_id, sensor_key, zeitpunkt, wert_kwh, quelle) VALUES (?,?,?,?,?) "
            "ON CONFLICT(anlage_id, sensor_key, zeitpunkt) "
            "DO UPDATE SET wert_kwh=excluded.wert_kwh, quelle=excluded.quelle",
            zeilen,
        )
        # Ränder aus einem früheren Lauf mit anderem Fenster fallen weg.
        zeitpunkte = sorted({z[2] for z in zeilen})
        self.cur.execute(
            "DELETE FROM sensor_snapshots WHERE anlage_id=? AND sensor_key IN (%s) "
            "AND zeitpunkt NOT IN (%s)"
            % (",".join("?" * len(keys)), ",".join("?" * len(zeitpunkte))),
            (anlage_id, *keys, *zeitpunkte),
        )
        self.log(f"    Snapshots: {len(zeilen)}")
        return len(zeilen)

    def ergaenze_demo_stunden(self, anlage_id: int, inv_id: int, geraet: D.Geraet,
                              tage: list[date]) -> int:
        """Stundenzeilen der Demo-Anlage um das neue Gerät ergänzen.

        Angefasst werden genau drei Dinge: ``komponenten`` bekommt den Schlüssel
        ``waermepumpe_<id>`` (negativ — der Leistungspfad führt Senken so),
        ``betriebsmodus_je_wp`` die Modus-Spur, und ``waermepumpe_kw`` wird um
        den Beitrag erhöht. Alles andere bleibt, wie es war.
        """
        monate = D.monatswerte(geraet)
        n = 0
        for tag in tage:
            bild = D.tagesbild(geraet, tag, monate)
            # `strom_je_stunde` löst die drei Kanon-Familien schon auf: ein
            # Gesamtzähler gilt allein, Teilmengen werden nie addiert.
            strom = bild.strom_je_stunde
            modi = D.modus_je_stunde(geraet, bild)
            for row in self.cur.execute(
                "SELECT id, stunde, komponenten, betriebsmodus_je_wp, waermepumpe_kw "
                "FROM tages_energie_profil WHERE anlage_id=? AND datum=?",
                (anlage_id, tag.isoformat()),
            ).fetchall():
                stunde = int(row["stunde"])
                komponenten = json.loads(row["komponenten"] or "{}") or {}
                modus_map = json.loads(row["betriebsmodus_je_wp"] or "{}") or {}
                kwh = round(strom[stunde], 4) if stunde < len(strom) else 0.0
                komponenten[f"waermepumpe_{inv_id}"] = -kwh
                if modi:
                    modus_map[str(inv_id)] = modi.get(stunde, "aus")
                basis = float(row["waermepumpe_kw"] or 0.0)
                # Der Beitrag DIESES Geräts wird ersetzt, nicht addiert —
                # sonst wüchse die Spalte mit jedem Lauf.
                alt = abs(float((json.loads(row["komponenten"] or "{}") or {})
                                .get(f"waermepumpe_{inv_id}", 0.0)))
                # `created_at` mitstempeln (N-595): die Zeile trägt die Modus-Spur
                # jetzt backward, gepaart mit `komponenten` derselben Zeile. Bliebe
                # die Schreibzeit des Demo-Seeds (vor N-382, 04.09.) stehen, hielte
                # `slot_konvention.betriebsmodus_ziel_slot` die Spur für forward und
                # schöbe sie beim Neu-Aggregieren eine Stunde weiter. Für die `*_kw`
                # ändert sich nichts — die Demo-Zeilen liegen schon nach
                # `SLOT_PAARUNG_VORZEILE_AB`.
                self.cur.execute(
                    "UPDATE tages_energie_profil SET komponenten=?, "
                    " betriebsmodus_je_wp=?, waermepumpe_kw=?, created_at=? WHERE id=?",
                    (json.dumps(komponenten, ensure_ascii=False),
                     json.dumps(modus_map, ensure_ascii=False) if modus_map else None,
                     round(basis - alt + kwh, 4), SEED_ZEIT, row["id"]),
                )
                n += 1
            # Tages-Zählersumme: der Bezug, auf den der Modus-Split normiert.
            tz = self.cur.execute(
                "SELECT id, komponenten_kwh FROM tages_zusammenfassung "
                "WHERE anlage_id=? AND datum=?", (anlage_id, tag.isoformat()),
            ).fetchone()
            if tz:
                komp = json.loads(tz["komponenten_kwh"] or "{}") or {}
                komp[f"waermepumpe_{inv_id}"] = round(sum(strom), 3)
                self.cur.execute(
                    "UPDATE tages_zusammenfassung SET komponenten_kwh=?, updated_at=? "
                    "WHERE id=?",
                    (json.dumps(komp, ensure_ascii=False), SEED_ZEIT, tz["id"]),
                )
        self.log(f"    Stundenzeilen ergänzt: {n}")
        return n

    def schreibe_pruefstand_stunden(self, anlage_id: int,
                                    inv_ids: dict[str, int]) -> int:
        """Stunden- und Tageszeilen der Prüfstand-Anlage — sie bringt keine mit."""
        tage = D.tagesachse()
        pv_monate = D.monatswerte(D.PRUEFSTAND_PV)
        geraete = [(D.VAILLANT, inv_ids["vaillant"]), (D.NIBE, inv_ids["nibe"]),
                   (D.STIEBEL, inv_ids["stiebel"])]
        monate_je_geraet = {g.schluessel: D.monatswerte(g) for g, _ in geraete}
        self.cur.execute(
            "DELETE FROM tages_energie_profil WHERE anlage_id=?", (anlage_id,))
        self.cur.execute(
            "DELETE FROM tages_zusammenfassung WHERE anlage_id=?", (anlage_id,))
        tep_zeilen: list[tuple] = []
        tz_zeilen: list[tuple] = []
        for tag in tage:
            pv_bild = D.tagesbild(D.PRUEFSTAND_PV, tag, pv_monate)
            pv_stunden = pv_bild.stunden.get("pv_erzeugung_kwh", [0.0] * 24)
            haushalt_tag = D.HAUSHALT_KWH_MONAT / calendar.monthrange(
                tag.year, tag.month)[1]
            haushalt = D.verteile_auf_stunden(haushalt_tag, D.STUNDENFORM["haushalt"])
            wp_stunden: dict[int, list[float]] = {}
            modi_je_inv: dict[int, dict[int, str]] = {}
            for geraet, inv_id in geraete:
                bild = D.tagesbild(geraet, tag, monate_je_geraet[geraet.schluessel])
                wp_stunden[inv_id] = bild.strom_je_stunde
                modi = D.modus_je_stunde(geraet, bild)
                if modi:
                    modi_je_inv[inv_id] = modi
            tages_pv = round(sum(pv_stunden), 3)
            tages_wp = {iid: round(sum(w), 3) for iid, w in wp_stunden.items()}
            for stunde in range(24):
                pv_kw = round(pv_stunden[stunde], 4)
                verbrauch_kw = round(
                    haushalt[stunde] + sum(w[stunde] for w in wp_stunden.values()), 4)
                ueberschuss = max(0.0, pv_kw - verbrauch_kw)
                defizit = max(0.0, verbrauch_kw - pv_kw)
                komponenten: dict[str, float] = {
                    f"pv_{inv_ids['pv_pruefstand']}": pv_kw,
                }
                for iid, werte in wp_stunden.items():
                    komponenten[f"waermepumpe_{iid}"] = -round(werte[stunde], 4)
                if defizit > 0:
                    komponenten["netz"] = round(defizit, 4)
                modus_map = {
                    str(iid): modi.get(stunde, "aus")
                    for iid, modi in modi_je_inv.items()
                }
                tep_zeilen.append((
                    anlage_id, tag.isoformat(), stunde, pv_kw, verbrauch_kw,
                    round(ueberschuss, 4), round(defizit, 4), 0.0,
                    round(sum(w[stunde] for w in wp_stunden.values()), 4),
                    round(ueberschuss, 4), round(defizit, 4),
                    json.dumps(komponenten, ensure_ascii=False),
                    json.dumps(modus_map, ensure_ascii=False) if modus_map else None,
                    "{}", SEED_ZEIT,
                ))
            komp_kwh = {f"pv_{inv_ids['pv_pruefstand']}": tages_pv}
            komp_kwh.update({f"waermepumpe_{iid}": w for iid, w in tages_wp.items()})
            tz_zeilen.append((
                anlage_id, tag.isoformat(), 24, "demo",
                json.dumps(komp_kwh, ensure_ascii=False),
                round(tages_pv / 0.95, 1), "{}", SEED_ZEIT, SEED_ZEIT,
            ))
        self.cur.executemany(
            "INSERT INTO tages_energie_profil (anlage_id, datum, stunde, pv_kw, "
            " verbrauch_kw, einspeisung_kw, netzbezug_kw, batterie_kw, waermepumpe_kw, "
            " ueberschuss_kw, defizit_kw, komponenten, betriebsmodus_je_wp, "
            " source_provenance, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            tep_zeilen,
        )
        self.cur.executemany(
            "INSERT INTO tages_zusammenfassung (anlage_id, datum, stunden_verfuegbar, "
            " datenquelle, komponenten_kwh, pv_prognose_kwh, source_provenance, "
            " created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            tz_zeilen,
        )
        self.log(f"  Prüfstand-Tagesebene: {len(tep_zeilen)} Stunden-, "
                 f"{len(tz_zeilen)} Tageszeilen ({D.TAG_VON} .. {D.TAG_BIS})")
        return len(tep_zeilen)

    # — Ablauf ————————————————————————————————————————————————————————

    def lauf(self) -> dict[str, Any]:
        ergebnis: dict[str, Any] = {}

        demo_id = self.demo_anlage_id()
        self.log(f"Demo-Anlage: id {demo_id}")
        multisplit_id = self.geraet_id(demo_id, D.MULTISPLIT)
        ergebnis["multisplit_id"] = multisplit_id
        # ⚠ NUR Monate, die die Demo-Anlage schon hat. Ein Investitions-Monat
        # ohne Anlagenzeile erzeugt eine leere Anlagenzeile — und Cockpit →
        # Monat springt auf einen Monat mit 0 kWh PV.
        ergebnis["multisplit_monate"] = self.schreibe_geraete_monate(
            multisplit_id, D.MULTISPLIT, nur_monate=self.vorhandene_monate(demo_id))
        self.schreibe_sensor_mapping(demo_id, {multisplit_id: D.MULTISPLIT})
        demo_tage = self.demo_tage(demo_id)
        self.schreibe_snapshots(demo_id, multisplit_id, D.MULTISPLIT, demo_tage)
        self.ergaenze_demo_stunden(demo_id, multisplit_id, D.MULTISPLIT, demo_tage)

        pruef_id = self.pruefstand_anlage_id()
        ergebnis["pruefstand_anlage_id"] = pruef_id
        inv_ids: dict[str, int] = {}
        for geraet in (D.PRUEFSTAND_PV, D.VAILLANT, D.NIBE, D.STIEBEL):
            inv_ids[geraet.schluessel] = self.geraet_id(pruef_id, geraet)
            self.schreibe_geraete_monate(inv_ids[geraet.schluessel], geraet)
        ergebnis["pruefstand_inv_ids"] = inv_ids
        self.schreibe_anlagen_monate(pruef_id)
        self.schreibe_tarife(pruef_id)
        self.schreibe_sensor_mapping(pruef_id, {
            inv_ids[g.schluessel]: g
            for g in (D.PRUEFSTAND_PV, D.VAILLANT, D.NIBE, D.STIEBEL)
        })
        self.schreibe_pruefstand_stunden(pruef_id, inv_ids)
        tage = D.tagesachse()
        for geraet in (D.PRUEFSTAND_PV, D.VAILLANT, D.NIBE, D.STIEBEL):
            self.schreibe_snapshots(pruef_id, inv_ids[geraet.schluessel], geraet, tage)

        self.con.commit()
        return ergebnis

    def close(self) -> None:
        self.con.close()


# ═══ API-Schreiber (nur Stdlib) ══════════════════════════════════════════════

class ApiSeeder:
    """Schreibt über die echten Routen — läuft auch auf dem Lab selbst.

    Bewusst `urllib` statt `requests`: Im SSH-Add-on des HAOS-Labs gibt es kein
    `requests`, und die Lab-API ist von der Dev-Box aus nicht erreichbar.
    """

    def __init__(self, basis: str, demo_anlage: Optional[str] = None,
                 verbose: bool = True, timeout: float = 60.0):
        self.basis = basis.rstrip("/")
        self.demo_anlage_bez = demo_anlage or DEMO_ANLAGE_NAME
        self.verbose = verbose
        self.timeout = timeout
        self.bericht: list[str] = []

    def log(self, text: str) -> None:
        self.bericht.append(text)
        if self.verbose:
            print(text, flush=True)

    def _ruf(self, methode: str, pfad: str, koerper: Optional[dict] = None) -> Any:
        daten = json.dumps(koerper, ensure_ascii=False).encode() if koerper is not None else None
        req = urllib.request.Request(
            f"{self.basis}{pfad}", data=daten, method=methode,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as antwort:
                roh = antwort.read().decode()
                return json.loads(roh) if roh else None
        except urllib.error.HTTPError as fehler:
            text = fehler.read().decode()[:400]
            raise SystemExit(f"{methode} {pfad} → HTTP {fehler.code}: {text}")

    # — Stammdaten ————————————————————————————————————————————————————

    def anlagen(self) -> list[dict]:
        return self._ruf("GET", "/api/anlagen/") or []

    def anlage_id(self, name: str) -> Optional[int]:
        for a in self.anlagen():
            if a.get("anlagenname") == name:
                return int(a["id"])
        return None

    def pruefstand_anlage_id(self) -> int:
        vorhanden = self.anlage_id(D.PRUEFSTAND_ANLAGE)
        if vorhanden:
            self.log(f"Anlage „{D.PRUEFSTAND_ANLAGE}“ vorhanden (id {vorhanden})")
            return vorhanden
        neu = self._ruf("POST", "/api/anlagen/", {
            "anlagenname": D.PRUEFSTAND_ANLAGE,
            "leistung_kwp": D.PRUEFSTAND_PV_KWP,
            "installationsdatum": D.VAILLANT.anschaffungsdatum.isoformat(),
            "standort_land": "DE", "standort_plz": "34117",
            "standort_ort": "Kassel", "standort_strasse": "Prüfstandweg 1",
            "latitude": 51.3127, "longitude": 9.4797,
            "ausrichtung": "Süd", "neigung_grad": 30.0,
        })
        self.log(f"Anlage „{D.PRUEFSTAND_ANLAGE}“ neu angelegt (id {neu['id']})")
        return int(neu["id"])

    def geraet_id(self, anlage_id: int, geraet: D.Geraet) -> int:
        vorhandene = self._ruf("GET", f"/api/investitionen/?anlage_id={anlage_id}") or []
        for inv in vorhandene:
            param = inv.get("parameter") or {}
            if (param.get("pruefstand") == D.PRUEFSTAND_MARKE
                    and inv.get("bezeichnung") == geraet.bezeichnung):
                self._ruf("PUT", f"/api/investitionen/{inv['id']}", {
                    "bezeichnung": geraet.bezeichnung,
                    "anschaffungsdatum": geraet.anschaffungsdatum.isoformat(),
                    "anschaffungskosten_gesamt": geraet.anschaffungskosten_gesamt,
                    "anschaffungskosten_alternativ": geraet.anschaffungskosten_alternativ,
                    "parameter": geraet.parameter,
                    "aktiv": True,
                    **({"leistung_kwp": D.PRUEFSTAND_PV_KWP}
                       if geraet.typ == "pv-module" else {}),
                })
                self.log(f"  Gerät „{geraet.bezeichnung}“ vorhanden (id {inv['id']}) — aktualisiert")
                return int(inv["id"])
        koerper = {
            "anlage_id": anlage_id, "typ": geraet.typ,
            "bezeichnung": geraet.bezeichnung,
            "anschaffungsdatum": geraet.anschaffungsdatum.isoformat(),
            "anschaffungskosten_gesamt": geraet.anschaffungskosten_gesamt,
            "anschaffungskosten_alternativ": geraet.anschaffungskosten_alternativ,
            "parameter": geraet.parameter, "aktiv": True,
        }
        if geraet.typ == "pv-module":
            koerper.update({"leistung_kwp": D.PRUEFSTAND_PV_KWP,
                            "ausrichtung": "Süd", "neigung_grad": 30.0})
        neu = self._ruf("POST", "/api/investitionen/", koerper)
        self.log(f"  Gerät „{geraet.bezeichnung}“ neu angelegt (id {neu['id']})")
        return int(neu["id"])

    # — Monatszeilen ———————————————————————————————————————————————————

    def vorhandene_monate(self, anlage_id: int) -> set[tuple[int, int]]:
        zeilen = self._ruf("GET", f"/api/monatsdaten/?anlage_id={anlage_id}") or []
        return {(int(z["jahr"]), int(z["monat"])) for z in zeilen}

    def schreibe_monate(self, anlage_id: int,
                        geraete: dict[int, D.Geraet],
                        anlagenzeile: bool,
                        nur_monate: Optional[set[tuple[int, int]]] = None) -> int:
        """Ein `POST /api/monatsabschluss/...` je Monat — der einzige API-Weg,
        der Investitions-Monatsdaten trägt (gemessen, s. Modul-Docstring)."""
        werte_je_geraet = {iid: D.monatswerte(g) for iid, g in geraete.items()}
        anlagen_werte = anlagen_monatswerte() if anlagenzeile else {}
        n = 0
        for schluessel in sorted(GESPEICHERTE_MONATE):
            if nur_monate is not None and schluessel not in nur_monate:
                continue
            jahr, monat = schluessel
            investitionen = []
            for iid, werte in werte_je_geraet.items():
                zeile = werte.get(schluessel) or {}
                if not zeile:
                    continue
                investitionen.append({
                    "investition_id": iid,
                    "felder": [{"feld": f, "wert": w} for f, w in sorted(zeile.items())],
                })
            koerper: dict[str, Any] = {"investitionen": investitionen,
                                       "datenquelle": "demo"}
            if anlagenzeile and schluessel in anlagen_werte:
                koerper.update(anlagen_werte[schluessel])
            if not investitionen and not anlagenzeile:
                continue
            antwort = self._ruf(
                "POST", f"/api/monatsabschluss/{anlage_id}/{jahr}/{monat}", koerper)
            for warnung in (antwort or {}).get("warnungen", []):
                self.log(f"    ⚠ {jahr}-{monat:02d}: {warnung.get('meldung')}")
            n += 1
        self.log(f"  Monatsabschlüsse: {n}")
        return n

    def schreibe_tarife(self, anlage_id: int) -> int:
        vorhandene = self._ruf("GET", f"/api/strompreise/?anlage_id={anlage_id}") or []
        bekannt = {t.get("gueltig_ab") for t in vorhandene}
        n = 0
        for tarif in D.TARIFE:
            ab = tarif["gueltig_ab"].isoformat()
            if ab in bekannt:
                continue
            self._ruf("POST", "/api/strompreise/", {
                "anlage_id": anlage_id,
                "netzbezug_arbeitspreis_cent_kwh": tarif["netzbezug_arbeitspreis_cent_kwh"],
                "einspeiseverguetung_cent_kwh": tarif["einspeiseverguetung_cent_kwh"],
                "grundpreis_euro_monat": tarif["grundpreis_euro_monat"],
                "gueltig_ab": ab,
                "gueltig_bis": (tarif["gueltig_bis"].isoformat()
                                if tarif["gueltig_bis"] else None),
                "tarifname": tarif["tarifname"], "anbieter": tarif["anbieter"],
                "verwendung": "allgemein",
            })
            n += 1
        self.log(f"  Tarife: {n} neu ({len(vorhandene)} vorhanden)")
        return n

    # — Ablauf ————————————————————————————————————————————————————————

    def lauf(self) -> dict[str, Any]:
        ergebnis: dict[str, Any] = {}
        demo_id = self.anlage_id(self.demo_anlage_bez)
        if demo_id is None:
            raise SystemExit(f"Anlage „{self.demo_anlage_bez}“ nicht gefunden")
        self.log(f"Demo-Anlage: id {demo_id}")
        multisplit_id = self.geraet_id(demo_id, D.MULTISPLIT)
        ergebnis["multisplit_id"] = multisplit_id
        self.schreibe_monate(demo_id, {multisplit_id: D.MULTISPLIT},
                             anlagenzeile=False,
                             nur_monate=self.vorhandene_monate(demo_id))

        pruef_id = self.pruefstand_anlage_id()
        ergebnis["pruefstand_anlage_id"] = pruef_id
        inv_ids = {g.schluessel: self.geraet_id(pruef_id, g)
                   for g in (D.PRUEFSTAND_PV, D.VAILLANT, D.NIBE, D.STIEBEL)}
        ergebnis["pruefstand_inv_ids"] = inv_ids
        self.schreibe_tarife(pruef_id)
        self.schreibe_monate(
            pruef_id,
            {inv_ids[g.schluessel]: g
             for g in (D.PRUEFSTAND_PV, D.VAILLANT, D.NIBE, D.STIEBEL)},
            anlagenzeile=True,
        )
        self.log("Hinweis: Tageszeilen und Zählerstände setzt die API nicht — "
                 "im Lab entstehen sie aus dem MQTT-Feeder.")
        return ergebnis


# ═══ CLI ═════════════════════════════════════════════════════════════════════

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--db", help="Pfad einer eedc-SQLite-Datei")
    p.add_argument("--api", help="Basis-URL einer laufenden eedc-Instanz")
    p.add_argument("--demo-anlage", default=None,
                   help=f"Name der bestehenden Demo-Anlage (Default: {DEMO_ANLAGE_NAME})")
    p.add_argument("--json", action="store_true", help="Ergebnis als JSON ausgeben")
    args = p.parse_args()

    if bool(args.db) == bool(args.api):
        p.error("genau eines von --db / --api angeben")

    if args.db:
        seeder: Any = DbSeeder(args.db, args.demo_anlage, verbose=not args.json)
        ergebnis = seeder.lauf()
        seeder.close()
    else:
        seeder = ApiSeeder(args.api, args.demo_anlage, verbose=not args.json)
        ergebnis = seeder.lauf()

    if args.json:
        print(json.dumps(ergebnis, ensure_ascii=False, indent=1))
    else:
        print("Fertig.", json.dumps(ergebnis, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
