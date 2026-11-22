"""Daten-Checker — Auskunft «Daten vor der Änderung gelöscht» (``daten_vor_aenderung_geloescht``; Sensorwechsel Weg B, Entscheid
Gernot 21.11.2026, Bauplan Nr. 179/180).

**Warum es das gibt.** Beim Wechsel der Quelle eines Felds mit eigenen Werten kann der Anwender «Daten vor der Änderung
löschen» wählen (``services/feld_loeschen.py``): die Daten dieses Felds vor der Änderung gehen weg, das Feld verhält sich danach,
als wäre der neue Sensor von Anfang an zugeordnet — was Home Assistant für ihn führt, übernimmt eedc, davor zeigt das Feld «—».
Der Dialog hat das beim Wechsel gesagt; diese Auskunft sagt es danach, je Feld eine Zeile (INFO, Knopf «Was gilt»).

**Was sie liest** — nur den Platzhalter des Kanals (``kanal/verwerfen.platzhalter_bedingung``: ``verworfen_ts`` = Zeitpunkt des
Löschens, ``gueltig_ab`` = Beginn der gelöschten Zeit) und die erste Zeile des Kanals danach; ob diese die erste einer
HA-Statistik ist, fragt dieselbe Bedingung wie die Lese-Regel «Anfangsstand 0» (``kanal/bilanz_leser.ha_statistik_beginn``).
Beginnt sie nicht zur vollen Tagesgrenze, ist der Tag für dieses Feld nicht vollständig — Home Assistant führt den Sensor erst
ab dieser Stunde, und eedc zeigt für den Tag, was Home Assistant liefert. Dazu die Monate mit gespeichertem Monatswert
(``feld_loeschen.gespeicherte_monate``) — er bleibt. Keine Lücken-Maschinerie, kein Vergleich, kein Schätzen.

Schwesterdateien: ``monatswert.py``, ``services/feld_loeschen.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional

from sqlalchemy import select

from backend.models.anlage import Anlage
from backend.services.daten_checker.kategorien import CheckErgebnis, CheckKategorie, CheckSeverity

CODE = "daten_vor_aenderung_geloescht"

#: Wortlaute (Weg B, Bau-Sitzung B1 — Liste im Bericht).
SATZ_MELDUNG = "{name}: Daten vor dem {zeit} Uhr gelöscht"
SATZ_GELOESCHT = ("Die Daten dieses Felds vor dem {zeit} Uhr sind gelöscht («Daten vor der Änderung löschen»). Seitdem verhält "
                  "sich das Feld, als wäre der neue Sensor von Anfang an zugeordnet.")
#: Ohne Beginn einer HA-Statistik (MQTT, eigene Zählerstände; Korrekturrunde WEGB-K, Nachmessung B3): «Quelle», nicht «Sensor».
SATZ_GELOESCHT_QUELLE = ("Die Daten dieses Felds vor dem {zeit} Uhr sind gelöscht («Daten vor der Änderung löschen»). Seitdem "
                         "verhält sich das Feld, als wäre die neue Quelle von Anfang an zugeordnet.")
SATZ_HA_SEIT = "Home Assistant führt den neuen Sensor seit dem {zeit} Uhr; davor zeigt das Feld «—»."
SATZ_TAG_TEIL = ("Der {tag} ist für dieses Feld deshalb nicht vollständig: eedc zählt ihn, wie Home Assistant, erst ab "
                 "{uhr} Uhr.")
#: Die Zeit ist die des ersten gespeicherten Zählerstands (Ende der ersten Kanal-Stunde): die erste Zeile ist der Nullpunkt,
#: gezählt wird ab ihr (WEGB-K, Nachmessung B3 — vorher die volle Stunde davor).
SATZ_QUELLE_SEIT = "eedc zählt die neue Quelle ab ihrem ersten gespeicherten Zählerstand am {zeit} Uhr; davor zeigt das Feld «—»."
SATZ_NOCH_KEIN_WERT = "Die neue Quelle hat noch keinen Wert geliefert; bis dahin zeigt das Feld «—»."
SATZ_MONAT = "Für {monate} ist ein Monatswert gespeichert. Er bleibt, wie er ist."
SATZ_MONATE = "Für {monate} sind Monatswerte gespeichert. Sie bleiben, wie sie sind."


@dataclass
class Geloescht:
    """Ein Feld mit Platzhalter: wann gelöscht, ab wann die gelöschte Zeit, die erste Zeile danach."""
    sensor_key: str
    geloescht_am: datetime
    beginn: datetime
    erste: Optional[datetime] = None
    ha_beginn: bool = False
    monate: list[tuple[int, int]] = field(default_factory=list)

    @property
    def teil_tag(self) -> Optional[date]:
        """Der Kalendertag der ersten Zeile, wenn Home Assistant den Sensor dort mitten im Tag zu führen beginnt."""
        if self.erste is None or not self.ha_beginn or (self.erste.hour, self.erste.minute) == (0, 0):
            return None
        return self.erste.date()


async def geloeschte_felder(db, anlage_id: int) -> list[Geloescht]:
    """Je Kanal mit Platzhalter eine Angabe, nach Schlüssel — zwei kleine Abfragen (meist keine Zeile)."""
    from sqlalchemy import and_, func

    from backend.models.kanal import Kanal, KanalQuelle, KanalStatistik
    from backend.services.feld_loeschen import gespeicherte_monate
    from backend.services.kanal.bilanz_leser import ha_statistik_beginn
    from backend.services.kanal.verwerfen import platzhalter_bedingung

    zeilen = (await db.execute(select(Kanal.id, Kanal.key, KanalQuelle.gueltig_ab, KanalQuelle.verworfen_ts)
                               .join(KanalQuelle, KanalQuelle.kanal_id == Kanal.id)
                               .where(and_(Kanal.anlage_id == anlage_id, platzhalter_bedingung()))
                               .order_by(Kanal.key))).all()
    if not zeilen:
        return []
    beginn_ha = await ha_statistik_beginn(db, anlage_id)
    aus = []
    for kid, key, ab, am in zeilen:
        erste = (await db.execute(select(func.min(KanalStatistik.start_ts)).where(KanalStatistik.kanal_id == kid))).scalar()
        g = Geloescht(key, datetime.fromtimestamp(am), datetime.fromtimestamp(ab),
                      None if erste is None else datetime.fromtimestamp(erste), beginn_ha.get(key) == erste)
        g.monate = await gespeicherte_monate(db, anlage_id, g.beginn, g.geloescht_am)
        aus.append(g)
    return aus


async def tag_vor_erster_zeile(db, anlage_id: int, tag: date, praefixe: tuple[str, ...]) -> bool:
    """Fund-Päckchen B (H4): liegt ``tag`` ganz vor der ersten Zeile eines gelöschten Felds, dessen Schlüssel mit einem der
    ``praefixe`` beginnt (oder hat es noch keine)? Dort hat «Den Tag in der Reparatur-Werkbank nachrechnen» nichts, woraus es
    rechnen könnte — die Daten vor der Änderung sind gelöscht. Ohne Platzhalter eine Abfrage ohne Zeile."""
    for g in await geloeschte_felder(db, anlage_id):
        if g.sensor_key.startswith(praefixe) and g.beginn.date() <= tag and (g.erste is None or tag < g.erste.date()):
            return True
    return False


def _uhr(t: datetime) -> str:
    return t.strftime("%d.%m.%Y %H:%M")


def texte(name: str, g: Geloescht) -> tuple[str, str]:
    """Meldung und Details in Anwender-Sprache (kein Menüweg — «Was gilt» öffnet den Lösungsweg)."""
    from backend.services.verwerfen_vor_quellbeginn import _monate_text

    teile = [(SATZ_GELOESCHT if g.ha_beginn else SATZ_GELOESCHT_QUELLE).format(zeit=_uhr(g.geloescht_am))]
    if g.erste is None:
        teile.append(SATZ_NOCH_KEIN_WERT)
    elif g.ha_beginn:
        teile.append(SATZ_HA_SEIT.format(zeit=_uhr(g.erste)))
        if g.teil_tag is not None:
            teile.append(SATZ_TAG_TEIL.format(tag=g.teil_tag.strftime("%d.%m.%Y"), uhr=g.erste.strftime("%H:%M")))
    else:
        teile.append(SATZ_QUELLE_SEIT.format(zeit=_uhr(datetime.fromtimestamp(g.erste.timestamp() + 3600))))
    if g.monate:
        teile.append((SATZ_MONAT if len(g.monate) == 1 else SATZ_MONATE).format(monate=_monate_text(g.monate)))
    return SATZ_MELDUNG.format(name=name, zeit=_uhr(g.geloescht_am)), " ".join(teile)


def feld_name(invs: dict, key: str) -> str:
    """``inv:2:ladung_kwh`` → «<Gerät> – Ladung gesamt»; ``basis:netzbezug`` → «Netzbezug» (Namen der Oberfläche). Seit Weg B
    (Sitzung B2) hier — vorher in ``grund_fehlt.py`` (entfernt); auch für ``monatswert.py``."""
    from backend.core.field_definitions import FELD_LABELS, feld_label_fuer_investition

    if key.startswith("inv:"):
        _, inv_id, feld = key.split(":", 2)
        inv = invs.get(inv_id)
        label = feld_label_fuer_investition(inv, feld)
        return f"{inv.bezeichnung} – {label}" if inv is not None else label
    feld = key.split(":", 1)[-1]
    return FELD_LABELS.get(feld, FELD_LABELS.get(f"{feld}_kwh", feld))


class DatenGeloeschtChecks:
    """Auskunft je Feld, dessen Daten vor einer Änderung der Quelle gelöscht wurden."""

    async def _check_daten_vor_aenderung_geloescht(self, anlage: Anlage) -> list[CheckErgebnis]:
        from backend.models.investition import Investition

        felder = await geloeschte_felder(self.db, anlage.id)
        if not felder:
            return []
        invs = {str(i.id): i for i in (await self.db.execute(
            select(Investition).where(Investition.anlage_id == anlage.id))).scalars().all()}
        return [_befund(feld_name(invs, g.sensor_key), g) for g in felder]


def _befund(name: str, g: Geloescht) -> CheckErgebnis:
    """Die eine Erzeuger-Stelle des Codes (W-1; W-6: eine Auskunft ist INFO)."""
    meldung, details = texte(name, g)
    teile = g.sensor_key.split(":")
    return CheckErgebnis(
        kategorie=CheckKategorie.DATEN_VOR_AENDERUNG_GELOESCHT.value,
        schwere=CheckSeverity.INFO,
        meldung=meldung,
        details=details,
        investition_id=int(teile[1]) if len(teile) == 3 and teile[0] == "inv" and teile[1].isdigit() else None,
        code="daten_vor_aenderung_geloescht",
        werte={"schluessel": g.sensor_key, "geloescht_am": g.geloescht_am.isoformat(timespec="minutes"),
               "beginn": g.beginn.isoformat(timespec="minutes"),
               "erste": None if g.erste is None else g.erste.isoformat(timespec="minutes"), "ha_beginn": g.ha_beginn,
               "tag_nicht_vollstaendig": None if g.teil_tag is None else g.teil_tag.isoformat(),
               "monate_gespeichert": [f"{j}-{m:02d}" for j, m in g.monate]},
    )


__all__ = ["CODE", "DatenGeloeschtChecks", "Geloescht", "feld_name", "geloeschte_felder", "texte"]
