"""Datenquellen-Priorisierung — reine Merge-Präzedenz für aktueller_monat.

`get_aktueller_monat` sammelt Monatswerte aus fünf Quellen (gespeichert,
Connector, MQTT-Inbound, HA-Statistics, lokale Tagesebene) und führt sie nach
fester Präzedenz zusammen. Das Sammeln ist I/O (DB/HA) und bleibt in der Route;
die Zusammenführungs-Regel ist reine Logik und lebt hier (ADR-001) — eine
Stelle, testbar, ohne Drift zwischen den `update`/`setdefault`-Zweigen.

Präzedenz (höchste überschreibt niedrigere):
  1. gespeicherte Monatsdaten (Basis)
  2. Connector (Geräte-Snapshot-Delta)
  3. MQTT-Inbound (Energy-Topics, nur laufender Monat — vom Aufrufer gegated)
  4. HA-Statistics (Recorder-DB)
  5. lokale Tagesebene (nur laufender Monat — füllt, was sonst fehlt)

**Die Tagesebene ist die schwächste Quelle, und das ist keine Wertung ihrer
Genauigkeit** (sie entsteht aus denselben Snapshots wie 3 und 4). Sie ist die
**abgeleitete** Quelle: Σ über die Tage, für die eine Aggregation gelaufen ist.
Wo eine der vier direkten Quellen antwortet, ist deren Antwort die über den
ganzen Monat — die Tagesebene füllt deshalb ausschließlich Lücken
(`setdefault`, in jedem Monat, auch im laufenden) und überschreibt nie. Der
Anlass steht in `mqtt_teilzeitraum_felder` weiter unten (N-472).

Laufender Monat: jede frischere Quelle DARF gespeicherte Werte überschreiben
(Live-Vorschau) → `update`. Abgeschlossener Monat: gespeicherte/manuell
gepflegte Werte sind authoritativ — Connector und HA-Statistics füllen nur
fehlende Felder (`setdefault`), überschreiben NICHT rückwirkend (#325 Connector,
#118 HA-Statistics). MQTT wird für vergangene Monate vom Aufrufer gar nicht
erst gesammelt (leeres Dict).

**Connector im laufenden Monat — Abdeckung entscheidet.** Der Connector-Wert
ist die Differenz zweier Zähler-Snapshots und misst damit nur den Zeitraum
zwischen ihnen. Beginnt der erste Snapshot mitten im Monat (frisch
eingerichteter Connector), ist das Delta kein Monatswert, sondern ein
Teilzeitraum — es darf einen gespeicherten Monatswert dann NICHT überschreiben,
sondern nur füllen, was sonst fehlt. Der Wert für den nicht abgedeckten Teil
kommt aus dem Monatsdaten-Import (CSV/Statistik), der einzigen Quelle, die die
Zeit vor dem ersten Snapshot kennt. Bewusst NICHT: Import und Delta addieren
(die Abdeckung des Imports ist unbekannt — aneinandergestückelt wäre es Raten).

Ein Connector-Wert ohne Monatsabdeckung bleibt auch dort ein Bruchstück, wo er
eine Lücke füllen darf. `teilzeitraum_felder` weist genau diese Felder aus —
der Aufrufer unterdrückt damit **nicht** die Aggregation der Komponenten-Werte,
die den Monat vollständig kennen (#361).

**Eine Präzedenz, zwei Antworten (N-624, 04.10.2026).** `gewinner_je_feld` sagt
je Feld, welche Quelle gewinnt; `merge_datenquellen` (welcher Wert) und
`teilzeitraum_felder` (misst er nur einen Teil des Monats?) entstehen beide
daraus. Bis dahin markierte die Teilzeitraum-Regel JEDES Feld, das die
Tagesebene kannte — auch dort, wo die HA-Statistik das Feld gewonnen hatte. Im
Betrieb gibt es im laufenden Monat immer Tageszeilen; der Anlagen-PV-Zähler aus
der HA-Monatsstatistik wurde so wie ein Bruchstück behandelt und durch den
ersten Einzelzähler ersetzt (PV 9 statt 63, Eigenverbrauch 0).

Werte sind `(float, DatenquelleInfo)`-Tupel; diese Funktion bewegt sie nur und
ist daher bewusst typ-agnostisch über das zweite Tupel-Element (kein Import aus
api/routes → keine Layer-Inversion). Die Abdeckung kommt deshalb als eigenes
Argument herein, nicht aus dem Wert-Tupel.
"""

from __future__ import annotations

from datetime import datetime
from typing import TypeVar

_V = TypeVar("_V")


def connector_deckt_monatsanfang(
    abdeckung_von: datetime | None,
    monat_start: datetime | None,
) -> bool:
    """Deckt das Connector-Delta den Monat ab seinem ersten Tag ab?

    Nur dann ist es ein vollwertiger Monatswert. Unbekannte Abdeckung zählt
    als „deckt nicht" — ohne Beleg über den gemessenen Zeitraum wird kein
    gespeicherter Wert überschrieben.
    """
    if abdeckung_von is None or monat_start is None:
        return False
    return abdeckung_von <= monat_start


def mqtt_teilzeitraum_felder(
    *,
    mqtt_energy: dict[str, _V],
    mqtt_ab_monatsbeginn: set[str] | None = None,
    tagesebene: dict[str, _V] | None = None,
) -> set[str]:
    """Felder, deren Endwert **nicht** den ganzen Monat misst (N-472).

    ⚠ **Fragt die Herkunft, nicht den Gewinner** — `teilzeitraum_felder` ruft sie
    deshalb seit N-624 nicht mehr, sondern fragt `gewinner_je_feld`: dass die
    Tagesebene ein Feld KENNT, heißt nicht, dass ihr Wert gewinnt.

    Zwei Herkünfte, dieselbe Eigenschaft:

    * **MQTT mit Rückfall** — der Stand am Monatsersten fehlte, gemessen ist
      erst ab dem ersten Stand des Monats (`mqtt_ab_monatsbeginn` nennt die
      Gegenmenge: die Felder, deren linker Rand *der* Monatserste war).
    * **lokale Tagesebene** — Σ über die Tage mit Spur; im laufenden Monat sind
      das naturgemäß nicht alle.

    ⛔ **Warum das nicht bloß Kosmetik ist.** Der Aufrufer sperrt mit einem
    Top-Level-Wert die Aggregation der Komponenten-Werte (sonst Doppelzählung).
    Vor dem Rückfall *fehlte* ein solcher Wert und sperrte nichts; mit dem
    Rückfall steht er da und würde eine **vollständige** Komponentensumme durch
    eine beschnittene Anlagenzahl verdrängen. Genau dieselbe Klasse wie #361
    (coolxmad #353) beim Connector — dort mit demselben Ergebnis behandelt: ein
    Bruchstück sperrt nicht, es wird vom ersten aggregierten Beitrag ersetzt.
    """
    felder = {
        k for k in mqtt_energy
        if mqtt_ab_monatsbeginn is None or k not in mqtt_ab_monatsbeginn
    }
    if tagesebene:
        felder |= set(tagesebene)
    return felder


#: Namen der Quellen in `gewinner_je_feld`.
QUELLE_GESPEICHERT = "saved"
QUELLE_CONNECTOR = "connector"
QUELLE_MQTT = "mqtt"
QUELLE_HA_STATISTIK = "ha_stats"
QUELLE_TAGESEBENE = "tagesebene"


def gewinner_je_feld(
    *,
    saved: dict[str, _V],
    connector: dict[str, _V],
    mqtt_energy: dict[str, _V],
    ha_stats: dict[str, _V],
    ist_aktueller_monat: bool,
    connector_abdeckung_von: datetime | None = None,
    monat_start: datetime | None = None,
    tagesebene: dict[str, _V] | None = None,
) -> dict[str, str]:
    """Feld → Name der Quelle, deren Wert gewinnt — DIE Präzedenz (Modul-Docstring).

    Reine Funktion. `merge_datenquellen` nimmt je Feld den Wert dieser Quelle,
    `teilzeitraum_felder` fragt, ob dieser Gewinner nur einen Teil des Monats misst.
    Die Reihenfolge der Felder ist die des Merge (zuerst eingefügt, zuerst genannt).
    """
    g: dict[str, str] = {k: QUELLE_GESPEICHERT for k in saved}
    if ist_aktueller_monat and connector_deckt_monatsanfang(connector_abdeckung_von, monat_start):
        g.update({k: QUELLE_CONNECTOR for k in connector})
    else:
        for k in connector:
            g.setdefault(k, QUELLE_CONNECTOR)
    g.update({k: QUELLE_MQTT for k in mqtt_energy})
    if ist_aktueller_monat:
        g.update({k: QUELLE_HA_STATISTIK for k in ha_stats})
    else:
        for k in ha_stats:
            g.setdefault(k, QUELLE_HA_STATISTIK)
    for k in (tagesebene or {}):
        g.setdefault(k, QUELLE_TAGESEBENE)
    return g


def teilzeitraum_felder(
    *,
    saved: dict[str, _V],
    connector: dict[str, _V],
    mqtt_energy: dict[str, _V],
    ha_stats: dict[str, _V],
    ist_aktueller_monat: bool,
    connector_abdeckung_von: datetime | None = None,
    monat_start: datetime | None = None,
    tagesebene: dict[str, _V] | None = None,
    mqtt_ab_monatsbeginn: set[str] | None = None,
) -> set[str]:
    """Felder, deren Endwert nur einen **Teilzeitraum** des Monats misst.

    Gegenstück zu `merge_datenquellen` mit denselben Argumenten: Während der
    Merge entscheidet, *welcher* Wert gewinnt, sagt diese Funktion, welche
    Gewinner nur einen Teilzeitraum messen. Der Aufrufer braucht das, weil
    ein Anlagen-Gesamtwert die Aggregation der Komponenten-Werte unterdrückt
    (sonst Doppelzählung) — und ein Bruchstück das nicht darf (#361, coolxmad
    #353: frisch eingerichteter Connector, Delta 0 kWh, verdrängte die
    vollständige HA-Summe der PV-Komponente).

    **Connector:** deckt er den Monat ab, ist sein Wert vollwertig. Sonst
    zählen genau die Felder, die er selbst gesetzt hat: `saved` gewinnt im
    `setdefault`-Zweig, MQTT und (im laufenden Monat) HA-Statistik
    überschreiben ihn danach.

    **MQTT-Rückfall und Tagesebene** (N-472, {@link mqtt_teilzeitraum_felder}):
    ein MQTT-Feld aus dem Rückfall ist ein Teilzeitraum, eines mit dem
    Monatsersten als linkem Rand nicht; ohne `mqtt_ab_monatsbeginn` hat der
    Aufrufer keine Auskunft gegeben, und kein MQTT-Feld zählt.

    **Die Marke folgt dem Gewinner (N-624).** Ein Teilzeitraum ist ein Feld nur,
    wenn sein **Gewinner** einer ist: die Tagesebene, der MQTT-Rückfall, der
    Connector ohne Abdeckung des Monatsanfangs. Im laufenden Monat bleiben für
    Felder, die die Tagesebene ebenfalls kennt, außerdem der gespeicherte Wert
    (er misst bis zum Speichern) und der Connector mit Abdeckung (er misst bis
    zum letzten Abruf) ersetzbar — wie bisher. Die HA-Statistik und MQTT ab dem
    Monatsersten messen den Monat bis jetzt und sperren.

    ⚠ **Benannte Grenze:** entsteht der HA-Sensor des Anlagenzählers erst im
    Monat, misst seine Monatsstatistik nur den Rest — sie trägt keine
    Abdeckungs-Auskunft, die das hier sichtbar machen könnte.
    """
    gewinner = gewinner_je_feld(
        saved=saved, connector=connector, mqtt_energy=mqtt_energy, ha_stats=ha_stats,
        ist_aktueller_monat=ist_aktueller_monat,
        connector_abdeckung_von=connector_abdeckung_von, monat_start=monat_start,
        tagesebene=tagesebene,
    )
    deckt = connector_deckt_monatsanfang(connector_abdeckung_von, monat_start)
    teil: set[str] = set()
    for k, quelle in gewinner.items():
        if quelle == QUELLE_TAGESEBENE:
            teil.add(k)
        elif quelle == QUELLE_MQTT:
            if mqtt_ab_monatsbeginn is not None and k not in mqtt_ab_monatsbeginn:
                teil.add(k)
        elif quelle == QUELLE_CONNECTOR and not deckt:
            teil.add(k)
        elif (quelle in (QUELLE_GESPEICHERT, QUELLE_CONNECTOR)
              and ist_aktueller_monat and k in (tagesebene or {})):
            teil.add(k)
    return teil


def merge_datenquellen(
    *,
    saved: dict[str, _V],
    connector: dict[str, _V],
    mqtt_energy: dict[str, _V],
    ha_stats: dict[str, _V],
    ist_aktueller_monat: bool,
    connector_abdeckung_von: datetime | None = None,
    monat_start: datetime | None = None,
    tagesebene: dict[str, _V] | None = None,
) -> dict[str, _V]:
    """Führt die fünf Datenquellen nach fester Präzedenz zusammen.

    Reine Funktion, kein I/O. Regeln siehe Modul-Docstring. ``mqtt_energy``
    wird unverändert per ``update`` angewendet — der Aufrufer übergibt für
    abgeschlossene Monate ein leeres Dict (MQTT wird dann nicht gesammelt).

    ``connector_abdeckung_von``/``monat_start`` beschreiben den Zeitraum, den
    das Connector-Delta wirklich misst. Fehlen sie, gilt die Abdeckung als
    unbekannt und der Connector überschreibt auch im laufenden Monat nicht.

    ``tagesebene`` ist die fünfte und schwächste Quelle (N-472) und wird
    **immer** per ``setdefault`` angewendet — sie füllt, was keine der vier
    direkten Quellen beantwortet hat, und verdrängt nie. Ohne sie ist das
    Ergebnis bitgleich zu vorher.

    Die Präzedenz selbst steht in `gewinner_je_feld` (N-624): laufender Monat
    mit Connector-Abdeckung ab dem Monatsersten ⇒ der Connector überschreibt
    den gespeicherten Wert (Vorschau), sonst füllt er nur (#325); MQTT
    überschreibt; HA-Statistik überschreibt im laufenden Monat und füllt im
    abgeschlossenen (#118); die Tagesebene füllt zuletzt (N-472).
    """
    quellen: dict[str, dict[str, _V]] = {
        QUELLE_GESPEICHERT: saved, QUELLE_CONNECTOR: connector, QUELLE_MQTT: mqtt_energy,
        QUELLE_HA_STATISTIK: ha_stats, QUELLE_TAGESEBENE: tagesebene or {},
    }
    gewinner = gewinner_je_feld(
        saved=saved, connector=connector, mqtt_energy=mqtt_energy, ha_stats=ha_stats,
        ist_aktueller_monat=ist_aktueller_monat,
        connector_abdeckung_von=connector_abdeckung_von, monat_start=monat_start,
        tagesebene=tagesebene,
    )
    return {k: quellen[quelle][k] for k, quelle in gewinner.items()}
