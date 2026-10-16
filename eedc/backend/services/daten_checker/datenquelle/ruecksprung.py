"""Daten-Checker — Zählerstände: rückspringende Zähler (N-47), Fenster und Beispiele.
"""
# Reiner Umzug aus `services/daten_checker/datenquelle.py` (18.09.2026, Vorlage 9 des Refactorings grosser
# Dateien): Methoden, Attribute und Helfer 1:1 uebernommen, kein Verhaltenswechsel. Die Fassade `__init__.py`
# traegt `DatenquelleChecks` als Verbund dieser Mixins weiter; `DatenChecker` komponiert wie bisher.

from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import select
from backend.models.anlage import Anlage
from backend.services.daten_checker.kategorien import (
    CheckErgebnis,
    CheckKategorie,
    CheckSeverity,
    LINK_DATENQUELLEN,
)
from backend.core.zahlenformat import fmt_zahl


#: Fenster, über das der Rücksprung-Check die Standreihen liest (N-341).
#:
#: **30 Tage, weil ein Monat die Frage ist, um die es geht** — kürzer würde ein
#: monatlich zurückgesetzter Zähler nie auffallen. Die MQTT-Rohreihe hält
#: ohnehin 31 Tage vor (`cleanup_old_snapshots`).
RUECKSPRUNG_FENSTER_TAGE = 30

#: Wie viele betroffene Felder die Meldung beim Namen nennt.
RUECKSPRUNG_BEISPIELE = 5

#: Folge für Felder OHNE Kanal (N-341, Wortlaut bis S4 unverändert).
_FOLGE_OHNE_KANAL = (
    "Folge: eedc kann für diese Felder keine Tages- oder "
    "Monatsmenge bilden, denn die Differenz zweier Stände aus "
    "verschiedenen Zählerläufen ist keine Menge. Sie bleiben im "
    "Monatsabschluss ohne Vorschlag. "
)
#: Folge für Felder MIT Kanal «Eigene Summe» (HA-Bauform S4-R-7, gemessen E-S4-2 Punkt 3): Tag, Monat und Jahr über die
#: Kanäle wie HA; Live (Mitternachts-Snapshot), der Monatsabschluss-Vorschlag (MQTT-Felder haben keinen Kanal-Weg) und
#: Geräte-Tageswerte vor dem Kanal (Bestandstag) nicht.
_FOLGE_MIT_KANAL = (
    "eedc führt für {wen} einen Kanal mit eigener Summe aus den MQTT-Ständen: "
    "Tag, Monat und Jahr rechnen darüber wie Home Assistant — ein Zurücksetzen "
    "gilt als Neubeginn, die Summe läuft weiter. Nicht verlässlich bleiben "
    "Live „heute“ und „gestern“ sowie Geräte-Tageswerte aus der Zeit vor dem "
    "Kanal; einen Vorschlag im Monatsabschluss gibt es für diese Felder nicht. "
)


def _texte(betroffen: list, mit_kanal: set[str]) -> tuple[str, str]:
    """Meldung und Folge-Satz (HA-Bauform S4-R-7): ohne Kanal der Wortlaut von N-341; mit Kanal «Eigene Summe» sagt der
    Text, was über die Kanäle geht und was nicht; gemischt beides mit Namen. ``betroffen``: ``(name, anzahl, …, key)``."""
    n = len(betroffen)
    mit = [b for b in betroffen if b[-1] in mit_kanal]
    ohne = [b for b in betroffen if b[-1] not in mit_kanal]
    kopf = f"{n} Zähler-Feld(er) werden zwischendurch zurückgesetzt — "
    if not mit:
        return kopf + "daraus entsteht keine Monatsmenge", _FOLGE_OHNE_KANAL
    if not ohne:
        return (kopf + "Tag und Monat rechnet eedc über die Kanäle, Live und Monatsabschluss nicht",
                "Folge: " + _FOLGE_MIT_KANAL.format(wen="diese Felder"))
    namen_mit = ", ".join(b[0] for b in mit[:RUECKSPRUNG_BEISPIELE])
    namen_ohne = ", ".join(b[0] for b in ohne[:RUECKSPRUNG_BEISPIELE])
    return (kopf + f"{len(mit)} davon rechnet eedc über die Kanäle, für {len(ohne)} entsteht keine Monatsmenge",
            "Folge: " + _FOLGE_MIT_KANAL.format(wen=namen_mit) + "Für " + namen_ohne + " gilt: "
            + _FOLGE_OHNE_KANAL.removeprefix("Folge: "))


class RuecksprungChecks:
    """Prüfung rückspringender Zählerstände."""

    async def _check_zaehler_ruecksprung(
        self, anlage: Anlage, jetzt: Optional[datetime] = None,
    ) -> list[CheckErgebnis]:
        """Ein zugeordneter Zähler springt zurück — und liefert deshalb nichts.

        **Der Anlass (N-341).** eedc lehnt einen Zähler mit Tages- oder
        Monats-Reset als Mengenquelle ab: Die Differenz zweier Stände, zwischen
        denen der Zähler neu begonnen hat, ist keine Menge (`reader.delta`).
        Bis zum 28.08.2026 entstand daraus im Monatsfenster sogar eine
        *falsche* Zahl; seither entsteht **keine**. Beides sah für den Anwender
        gleich aus — er sieht ein leeres Feld und erfährt nicht, warum.

        ⭐ **Der Hinweis existiert längst, nur an der falschen Stelle im
        Lebenslauf.** Der Daten-Checker rät beim **Anlegen** eines Helfers
        ausdrücklich zu *Zurücksetzen „nie" (ohne Zyklus)* (`sensoren.py`). Wer
        den Sensor bereits zugeordnet hat, liest diesen Rat nie — dieselbe
        Klasse wie W-18: ein erkannter Zustand, der nur als Logzeile existierte.

        ⚠ **Geprüft werden die MQTT-Reihen**, nicht alles. Über Home Assistant
        kommt der reset-bereinigte ``sum``-Wert, dort ist ein `utility_meter`
        mit Tageszyklus folgenlos; die rohen Stände aus MQTT trifft es. Gas-,
        Wasser- und Ölzähler haben mit ``zaehlerstand_reihe`` ihren eigenen
        Punkt und eine eigene Tabelle — **kein zweiter Turm daneben.**

        ⛔ **Kein Reparatur-Knopf.** eedc kann den Rücksprung nicht heilen: Die
        Energie zwischen dem letzten Stand und dem Reset steht in keiner Quelle,
        und die Reparatur liegt beim Absender — im Helfer, im Publisher, im
        Skript. Ein Knopf, der hier etwas verspricht, wäre die P-6-Falle in der
        Gegenrichtung.

        **Eine Meldung je Anlage, nicht je Feld.** Wer seinen Publisher auf
        „heute"-Felder gestellt hat, hat das meist für alle getan; zwanzig
        gleichlautende Zeilen wären keine bessere Auskunft
        ([[feedback_daten_checker_kein_akzeptiert]] — melden und erklären,
        nicht nörgeln).

        ⭐ **HA-Bauform S4-R-7 (Bauplan S4 §4, Entscheid S4-E4 A, gemessen E-S4-2 Punkt 3).** Hat der Schlüssel eines
        betroffenen Felds einen Kanal mit **Eigener Summe** (Familie Mitschrift: HAs 90-%-Regel über die MQTT-Rohstände),
        rechnen Tag, Monat und Jahr über die Kanäle wie Home Assistant — ein Zurücksetzen gilt als Neubeginn (Probe
        ``test_s4_r7_tagesreset_zaehler.py``). Der Text sagt dann, was geht und was nicht: Live „heute“/„gestern“
        (Mitternachts-Snapshot), der Monatsabschluss-Vorschlag (MQTT-Felder haben keinen Kanal-Weg; N-341 lehnt die
        Standreihe weiter ab) und Geräte-Tageswerte vor dem Kanal nicht. Die Empfehlung an der Quelle bleibt der erste
        Satz der Lösung, die Schwere WARNING (Live fehlt). Der Kasten in ``snapshot/reader.py`` (Entscheid 28.08.) gilt
        für Live und Bestand unverändert; ohne Kanal bleibt der Wortlaut von N-341.

        Args:
            jetzt: Endzeitpunkt des Prüffensters. Default ist die Uhr; die
                Naht existiert für die Proben (s. Kommentar im Rumpf).
        """
        from backend.core.field_definitions import FELD_LABELS
        from backend.models.investition import Investition as _Inv
        from backend.models.kanal import ART_SUM, FAMILIE_MITSCHRIFT, Kanal, KanalQuelle
        from backend.services.snapshot.reader import (
            MQTT_AKTIV_TAGE, finde_zaehler_ruecksprunge, mqtt_zaehler_keys,
        )

        kat = CheckKategorie.ZAEHLER_RUECKSPRUNG.value

        # ⚠ `jetzt` ist eine NAHT, kein `datetime.now()` mitten im Rumpf: Eine
        # Probe, die die Prozessuhr liest, wettet auf die Stunde ihres Laufs
        # (N-167) — und die Suite fährt in drei Zeitzonen. Der Wächter
        # `test_konformitaet_echte_uhr_in_tests.py` verhindert genau das.
        bis = jetzt or datetime.now()
        von = bis - timedelta(days=RUECKSPRUNG_FENSTER_TAGE)
        # Dasselbe Aktiv-Fenster wie die Abdeckungs-Prüfung: ein Topic, das seit
        # Wochen schweigt, ist eine andere Frage und hat dort seinen Punkt.
        keys = await mqtt_zaehler_keys(
            self.db, anlage.id, seit=bis - timedelta(days=MQTT_AKTIV_TAGE),
        )
        if not keys:
            return []

        # ⚑ **Bewusst OHNE Aktiv-Filter** — anders als in N-64/N-313, wo
        # dieselbe Zeile eine Rechnung speist. Hier dient sie allein dem
        # **Namen** in der Meldung: Sendet das Topic eines stillgelegten Geräts
        # weiter und springt zurück, ist der Befund richtig und der Anwender
        # soll lesen, um welches Gerät es geht. Welche Felder überhaupt geprüft
        # werden, entscheidet `mqtt_zaehler_keys` — nicht diese Liste.
        inv_result = await self.db.execute(
            select(_Inv).where(_Inv.anlage_id == anlage.id)
        )
        invs_by_id = {str(inv.id): inv for inv in inv_result.scalars().all()}

        def _feld_name(sensor_key: str) -> str:
            """`basis:netzbezug` → „Netzbezug"; `inv:7:ladung_kwh` → „ID.3 – Ladung"."""
            if sensor_key.startswith("inv:"):
                _, inv_id, feld = sensor_key.split(":", 2)
                inv = invs_by_id.get(inv_id)
                label = FELD_LABELS.get(feld, feld)
                return f"{inv.bezeichnung} – {label}" if inv else label
            feld = sensor_key.split(":", 1)[-1]
            return FELD_LABELS.get(feld, FELD_LABELS.get(f"{feld}_kwh", feld))

        betroffen: list[tuple[str, int, datetime, float, float, str]] = []
        for sensor_key in sorted(keys):
            spruenge = await finde_zaehler_ruecksprunge(
                self.db, anlage.id, sensor_key, von, bis,
            )
            if spruenge:
                zeitpunkt, vorher, nachher = spruenge[-1]  # der jüngste
                betroffen.append(
                    (_feld_name(sensor_key), len(spruenge), zeitpunkt, vorher, nachher, sensor_key)
                )

        if not betroffen:
            return []

        betroffen.sort(key=lambda b: -b[1])
        namen = "; ".join(f"{name} ({anzahl}×)" for name, anzahl, *_ in
                          betroffen[:RUECKSPRUNG_BEISPIELE])
        if len(betroffen) > RUECKSPRUNG_BEISPIELE:
            namen += f" (+{len(betroffen) - RUECKSPRUNG_BEISPIELE} weitere)"

        _name, _anzahl, zeitpunkt, vorher, nachher, _key = betroffen[0]
        beleg = (
            f"Zuletzt am {zeitpunkt.strftime('%d.%m.%Y um %H:%M')} bei „{_name}“: "
            f"{fmt_zahl(vorher, 1)} → {fmt_zahl(nachher, 1)}."
        )
        # S4-R-7: welche Schlüssel einen Kanal mit Eigener Summe haben (eine Abfrage, kein Lese-Schicht-Import).
        mit_kanal = set((await self.db.execute(
            select(Kanal.key).join(KanalQuelle, KanalQuelle.kanal_id == Kanal.id).where(
                Kanal.anlage_id == anlage.id, Kanal.art == ART_SUM, KanalQuelle.familie == FAMILIE_MITSCHRIFT,
            ).distinct()
        )).scalars().all())
        meldung, folge = _texte(betroffen, mit_kanal)

        return [CheckErgebnis(
            kategorie=kat,
            schwere=CheckSeverity.WARNING,
            meldung=meldung,
            details=(
                f"Ein Zählerstand muss fortlaufend steigen. Bei diesen Feldern "
                f"fällt er in den letzten {RUECKSPRUNG_FENSTER_TAGE} Tagen "
                f"wieder auf einen niedrigeren Wert zurück — typisch für ein "
                f"Feld, das „heute“ oder „diesen Monat“ meint. {beleg} "
                f"{folge}"
                f"Lösung: Schicke den fortlaufenden Stand statt des Tageswerts. "
                f"Kommt der Wert aus einem Home-Assistant-Helfer, steht die "
                f"Einstellung unter Einstellungen → Geräte & Dienste → Helfer: "
                f"Zurücksetzen auf „nie“ (ohne Zyklus). Kommt er aus einer "
                f"eigenen App oder einem Skript, sende den Lebenszählerstand. "
                f"eedc bildet Tag, Monat und Jahr daraus selbst — und exakt. "
                f"Betroffen: {namen}"
            ),
            link=LINK_DATENQUELLEN,
        )]
