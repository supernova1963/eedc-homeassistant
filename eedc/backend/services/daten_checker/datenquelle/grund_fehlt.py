"""Daten-Checker — Zuordnung geändert, Grund fehlt (Sensorwechsel mit Grund, Bauplan B-7, Konzept S-10 c; Sitzung 4).

**Warum es das gibt.** Seit Sitzung 3b fragt eedc beim Wechsel der Quelle eines Zählers mit eigenen Werten, warum er
wechselt (Fortsetzung oder Korrektur), und rechnet danach: über eine Fortsetzung bilden die Leser der Zählerstände keine
Differenz (die Naht zählt nicht als Menge), eine Korrektur verwirft und baut neu auf. Wechsel aus der Zeit davor
(überführt aus dem Aktivitäts-Protokoll und den Alt-Hinweisen, ``zuordnung_wechsel/ueberfuehrung.py``) und Wechsel, die eine
Route ohne Grund verzeichnet hat, stehen in ``zuordnung_wechsel`` ohne Grund — über sie rechnet eedc wie vor diesem Vorhaben.
Der Befund nennt jeden solchen Wechsel, **nach dem die Abfrage gefragt hätte** (``zuordnung_wechsel/abfrage.haette_gefragt``,
die eine Prüf-Funktion — nicht nachgebaut), mit dem Handgriff «Grund nachtragen»: ein Sprung in die Datenquellen an das
Feld, der dort den Dialog öffnet (``ziel_datenquelle_schluessel(…, nachtrag=<id>)``, ``zuordnung_wechsel/nachtrag.py``).

**Nicht gemeldet:** ein Wechsel nach «Keine», die Rückkehr zur letzten Quelle mit Werten, ein Wechsel an einem Feld ohne eigene
Werte davor, ein «Zähler getauscht» (gleiche Quelle) und jede aufgehobene Zeile. Kein Fund ⇒ keine Zeile.

Schwesterdateien: ``versatz.py`` (der versetzte Abschnitt in der Standreihe), ``ruecksprung.py``.
"""

from __future__ import annotations

from sqlalchemy import select

from backend.models.anlage import Anlage
from backend.services.daten_checker.kategorien import CheckErgebnis, CheckKategorie, CheckSeverity


def feld_name(invs: dict, key: str) -> str:
    """``inv:2:ladung_kwh`` → «<Gerät> – Ladung gesamt»; ``basis:netzbezug`` → «Netzbezug» (Namen der Oberfläche)."""
    from backend.core.field_definitions import FELD_LABELS, feld_label_fuer_investition

    if key.startswith("inv:"):
        _, inv_id, feld = key.split(":", 2)
        inv = invs.get(inv_id)
        label = feld_label_fuer_investition(inv, feld)
        return f"{inv.bezeichnung} – {label}" if inv is not None else label
    feld = key.split(":", 1)[-1]
    return FELD_LABELS.get(feld, FELD_LABELS.get(f"{feld}_kwh", feld))


def texte(name: str, row) -> tuple[str, str]:
    """Meldung und Details in Anwender-Sprache (kein Menüweg — der Knopf ist der Weg)."""
    from backend.services.zuordnung_wechsel.nachtrag import quelle_text

    datum = row.erklaert_ts.strftime("%d.%m.%Y")
    zeit = row.erklaert_ts.strftime("%d.%m.%Y %H:%M")
    meldung = f"{name}: Zuordnung am {datum} geändert — Grund fehlt"
    details = (
        f"Am {zeit} Uhr wechselte die Quelle dieses Felds von {quelle_text(row.vorher)} zu {quelle_text(row.nachher)}; das "
        "Feld hatte da schon eigene Werte. Ob der neue Sensor dasselbe weiter misst (etwa nach einem Zählertausch) oder "
        "bisher der falsche Sensor zugeordnet war, ist nicht verzeichnet. Bis du es nachträgst, rechnet eedc über den Wechsel "
        "hinweg wie bisher: wo eedc einen Wert aus den gespeicherten Zählerständen bildet, kann der Unterschied zwischen "
        "altem und neuem Zählerstand als Menge zählen. „Grund nachtragen“ stellt dieselbe Frage wie beim Wechsel der Quelle."
    )
    return meldung, details


class GrundFehltChecks:
    """Prüfung: verzeichneter Wechsel der Quelle eines Zählers ohne Grund, nach dem die Abfrage gefragt hätte."""

    async def _check_zuordnung_grund_fehlt(self, anlage: Anlage) -> list[CheckErgebnis]:
        from backend.models.investition import Investition
        from backend.models.zuordnung_wechsel import ZuordnungWechsel
        from backend.services.zuordnung_wechsel.nachtrag import offen

        rows = (await self.db.execute(select(ZuordnungWechsel).where(ZuordnungWechsel.anlage_id == anlage.id)
                                      .order_by(ZuordnungWechsel.ab_ts, ZuordnungWechsel.id))).scalars().all()
        offene = [r for r in rows if await offen(self.db, anlage.id, r)]
        if not offene:
            return []
        invs = {str(i.id): i for i in (await self.db.execute(
            select(Investition).where(Investition.anlage_id == anlage.id))).scalars().all()}
        return [_befund(feld_name(invs, r.sensor_key), r) for r in offene]


def _befund(name: str, row) -> CheckErgebnis:
    """Die eine Erzeuger-Stelle des Codes (W-1)."""
    from backend.services.daten_checker.ziele import ziel_datenquelle_schluessel

    meldung, details = texte(name, row)
    teile = row.sensor_key.split(":")
    inv_id = int(teile[1]) if len(teile) == 3 and teile[0] == "inv" and teile[1].isdigit() else None
    return CheckErgebnis(
        kategorie=CheckKategorie.ZUORDNUNG_GRUND_FEHLT.value,
        schwere=CheckSeverity.WARNING,
        meldung=meldung,
        details=details,
        investition_id=inv_id,
        code="zuordnung_grund_fehlt",
        ziel=ziel_datenquelle_schluessel(row.sensor_key, nachtrag=row.id),
        werte={"schluessel": row.sensor_key, "wechsel_id": row.id, "herkunft": row.herkunft,
               "wechsel": row.erklaert_ts.isoformat(timespec="minutes")},
    )


__all__ = ["GrundFehltChecks", "feld_name", "texte"]
