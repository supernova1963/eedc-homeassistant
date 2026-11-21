"""Daten-Checker — «Gespeicherter Monatswert passt nicht mehr» (``monatswert_ueberholt``; Sensorwechsel U3 a, Rechenweg G2,
Bauplan Nr. 150, Schwere nach E6: Warnung).

**Warum es das gibt.** Ein Wechsel der Quelle mit «Bisherige Werte bleiben» oder eine Korrektur ändert, was eedc für einen
Monat aus der Quelle bildet; ein schon gespeicherter Monatswert (Monatsabschluss, «Aus HA laden», Import) bleibt, wie er ist —
und alles, was eedc für diesen Monat zeigt, rechnet mit ihm (``verwerfen_vor_quellbeginn.abschluss_monate``: ein Monat mit
Monatsdaten-Zeile ist abgeschlossen). Ohne Vergleich wäre eine Auskunft je gespeichertem Monat ein Dauer-Alarm (an der
Produktiv-Kopie 41 Monate am Schlüssel mit Wechsel, im Monat des Wechsels 242,9 gegen 242,871 — kein Unterschied).

**Regel.** Nur Monate, die ein verzeichneter Wechsel berührt — das Intervall ``[falsch_seit, ab)`` einer Korrektur und die
Monate ab einem Wechsel «bleiben» (Grund «Fortsetzung», auch «Zähler getauscht») **bis zum Monat, in dem eedc die Zeile
eingetragen hat** (``eingetragen_ts``, Sensorwechsel U3-K, Nachmessung B5: einen später gespeicherten Monat hat der Anwender
schon mit dem Wechsel gesehen — ohne die Grenze kam jeden Monat ein neuer Befund; ``NULL`` an einer Bestandszeile: bis zum
letzten abgeschlossenen Monat) —, nur abgeschlossene Monate vor dem laufenden, und nur, wenn

* ein Wert gespeichert ist (Anlage: ``Monatsdaten.einspeisung_kwh``/``netzbezug_kwh`` nach der Regel N-739 «erfasst»;
  Gerät: ``InvestitionMonatsdaten.verbrauch_daten[feld]``),
* eedc heute einen **vollen** Wert aus der Quelle hat — der Kanal des Felds deckt den ganzen Monat
  (``kanal/feld_leser.kanal_feldwerte_je_fenster``, «echte Deckung»; ein Monat über eine verworfene Zeit ist nicht voll, ihn
  nennt ``zaehler_zeit_verworfen``),
* beide um mindestens 1 kWh abweichen (``core/berechnungen/monatswert_vergleich.monatswert_weicht_ab``),
* und der Anwender den gespeicherten Wert nicht im Monatsabschluss bewusst behalten hat (``geprueft_gegen[feld]`` mit genau
  diesem Wert, PN 90128).

Handgriff «Monat öffnen» (Sprung ins Formular des Monats beim Feld). **Benannt:** der Anlagen-PV-Zähler (``basis:pv_gesamt``,
ADR-002/P7 — der gespeicherte Wert ist die Summe je Modul) und Felder ohne Kanal werden nicht geprüft.

Schwesterdateien: ``verworfen.py`` (``zaehler_zeit_verworfen``), ``versatz.py``, ``geloescht.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import select

from backend.models.anlage import Anlage
from backend.services.daten_checker.kategorien import CheckErgebnis, CheckKategorie, CheckSeverity

CODE = "monatswert_ueberholt"
#: Basis-Zähler mit gespeichertem Monatswert in einer eigenen Spalte (``Monatsdaten``).
_BASIS_SPALTE = {"einspeisung": "einspeisung_kwh", "netzbezug": "netzbezug_kwh"}

SATZ_MELDUNG = "{name}: gespeicherter Monatswert {monat} passt nicht mehr zur Quelle"
SATZ_DETAILS = ("Gespeichert sind {gespeichert} kWh. Seit {anlass} ergibt die Quelle für diesen Monat {quelle} kWh. Alles, was "
                "eedc für diesen Monat zeigt, rechnet mit dem gespeicherten Wert; er bleibt, bis du ihn änderst.")
ANLASS_KORREKTUR = "der Korrektur vom {datum}"
ANLASS_TAUSCH = "dem Zählertausch am {datum}"
ANLASS_WECHSEL = "dem Wechsel der Quelle am {datum}"


@dataclass(frozen=True)
class Anlass:
    """Was den Monat berührt: die Art und der Zeitpunkt der Erklärung."""
    art: str
    zeit: datetime


def _monat_davor(m: tuple[int, int]) -> tuple[int, int]:
    return (m[0] - 1, 12) if m[1] == 1 else (m[0], m[1] - 1)


def _naechster(m: tuple[int, int]) -> tuple[int, int]:
    return (m[0] + 1, 1) if m[1] == 12 else (m[0], m[1] + 1)


def _monate(von: tuple[int, int], bis: tuple[int, int]) -> list[tuple[int, int]]:
    out, m = [], von
    while m <= bis:
        out.append(m)
        m = _naechster(m)
    return out


def beruehrte_monate(wechsel, heute: date) -> dict[tuple[int, int], Anlass]:
    """Die abgeschlossenen Monate (vor dem laufenden), die die nicht aufgehobenen Zeilen eines Schlüssels berühren, je mit dem
    jüngsten Anlass: das Intervall einer Korrektur; ab einem Wechsel «bleiben» jeder Monat bis zum Monat des Eintrags (U3-K,
    ``eingetragen_ts``; ohne ihn bis zum letzten abgeschlossenen). Lücken-Zeilen gehören zu ihrer Korrektur; ein Wechsel ohne
    Grund berührt nichts (dort rechnet eedc wie vorher)."""
    from backend.models.zuordnung_wechsel import GRUND_FORTSETZUNG, GRUND_KORREKTUR
    from backend.services.zuordnung_wechsel.zeitpunkt import gleiche_quelle, ist_luecken_zeile

    letzter = _monat_davor((heute.year, heute.month))
    aus: dict[tuple[int, int], Anlass] = {}
    for w in wechsel or ():
        if w.aufgehoben_durch is not None or ist_luecken_zeile(w):
            continue
        zeit = w.erklaert_ts or w.ab_ts
        eingetragen = getattr(w, "eingetragen_ts", None)
        bis = letzter if eingetragen is None else min(letzter, (eingetragen.year, eingetragen.month))
        if w.grund == GRUND_KORREKTUR and w.falsch_seit_ts is not None:
            letzte = w.ab_ts - timedelta(seconds=1)
            monate, anlass = _monate((w.falsch_seit_ts.year, w.falsch_seit_ts.month),
                                     min((letzte.year, letzte.month), bis)), Anlass(GRUND_KORREKTUR, zeit)
        elif w.grund == GRUND_FORTSETZUNG:
            art = "tausch" if gleiche_quelle(w.vorher, w.nachher) else GRUND_FORTSETZUNG
            monate, anlass = _monate((w.ab_ts.year, w.ab_ts.month), bis), Anlass(art, zeit)
        else:
            continue
        for m in monate:
            if m not in aus or aus[m].zeit < anlass.zeit:
                aus[m] = anlass
    return aus


async def _gespeichert(db, anlage_id: int, key: str, monate: list[tuple[int, int]]) -> dict[tuple[int, int], tuple[float, dict]]:
    """Je Monat der gespeicherte Wert des Felds und der Eintrag «bewusst behalten» (``geprueft_gegen``) — nur Monate mit Wert."""
    from backend.models.investition import InvestitionMonatsdaten
    from backend.models.monatsdaten import Monatsdaten
    from backend.services.monats_fakten.roh import netzfeld_ist_erfasst

    teile = key.split(":")
    aus: dict[tuple[int, int], tuple[float, dict]] = {}
    if len(teile) == 2 and teile[0] == "basis" and teile[1] in _BASIS_SPALTE:
        spalte = _BASIS_SPALTE[teile[1]]
        for md in (await db.execute(select(Monatsdaten).where(Monatsdaten.anlage_id == anlage_id))).scalars():
            wert = getattr(md, spalte, None)
            if (md.jahr, md.monat) in monate and wert is not None and netzfeld_ist_erfasst(md, spalte):
                aus[(md.jahr, md.monat)] = (float(wert), (md.geprueft_gegen or {}).get(spalte) or {})
    elif len(teile) == 3 and teile[0] == "inv" and teile[1].isdigit():
        for imd in (await db.execute(select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id == int(teile[1])))).scalars():
            wert = (imd.verbrauch_daten or {}).get(teile[2])
            if (imd.jahr, imd.monat) in monate and isinstance(wert, (int, float)):
                aus[(imd.jahr, imd.monat)] = (float(wert), (imd.geprueft_gegen or {}).get(teile[2]) or {})
    return aus


async def _quelle_je_monat(db, anlage_id: int, key: str, monate: list[tuple[int, int]]) -> dict[tuple[int, int], float]:
    """Was der Kanal des Felds heute für jeden Monat ergibt — nur Monate, die er ganz deckt."""
    from backend.services.kanal.feld_leser import kanal_feldwerte_je_fenster

    fenster = {date(j, m, 1): (datetime(j, m, 1), datetime(*_naechster((j, m)), 1)) for j, m in monate}
    werte = (await kanal_feldwerte_je_fenster(db, anlage_id, [key], fenster)).get(key, {})
    return {(d.year, d.month): w for d, w in werte.items()}


def _behalten(eintrag: dict, gespeichert: float) -> bool:
    """Hat der Anwender genau diesen gespeicherten Wert im Monatsabschluss bewusst behalten (``geprueft_gegen``)?"""
    from backend.core.berechnungen.monatswert_vergleich import monatswert_weicht_ab

    wert = eintrag.get("wert") if isinstance(eintrag, dict) else None
    return isinstance(wert, (int, float)) and not monatswert_weicht_ab(gespeichert, wert, 0.001)


async def ueberholte_monate(db, anlage_id: int, key: str, wechsel, heute: date) -> list[tuple[tuple[int, int], float, float, Anlass]]:
    """``[(Monat, gespeichert, Quelle, Anlass)]`` der Monate, deren gespeicherter Wert nicht mehr zur Quelle passt."""
    from backend.core.berechnungen.monatswert_vergleich import monatswert_weicht_ab

    beruehrt = beruehrte_monate(wechsel, heute)
    if not beruehrt:
        return []
    monate = sorted(beruehrt)
    gespeichert = await _gespeichert(db, anlage_id, key, monate)
    if not gespeichert:
        return []
    quelle = await _quelle_je_monat(db, anlage_id, key, sorted(gespeichert))
    return [(m, g, quelle[m], beruehrt[m]) for m, (g, eintrag) in sorted(gespeichert.items())
            if m in quelle and monatswert_weicht_ab(g, quelle[m]) and not _behalten(eintrag, g)]


class MonatswertUeberholtChecks:
    """Prüfung: gespeicherter Monatswert eines vom Wechsel berührten Monats weicht von der Quelle ab."""

    async def _check_monatswert_ueberholt(self, anlage: Anlage, heute: Optional[date] = None) -> list[CheckErgebnis]:
        from backend.models.investition import Investition
        from backend.services.daten_checker.datenquelle.geloescht import feld_name
        from backend.services.zuordnung_wechsel.zeitpunkt import lade_wechsel

        je_key = await lade_wechsel(self.db, anlage.id)
        if not je_key:
            return []
        heute = heute or date.today()
        funde = [(key, *f) for key in sorted(je_key)
                 for f in await ueberholte_monate(self.db, anlage.id, key, je_key[key], heute)]
        if not funde:
            return []
        invs = {str(i.id): i for i in (await self.db.execute(
            select(Investition).where(Investition.anlage_id == anlage.id))).scalars().all()}
        return [_befund(feld_name(invs, key), key, m, g, q, anlass) for key, m, g, q, anlass in funde]


def _anlass_text(anlass: Anlass) -> str:
    from backend.models.zuordnung_wechsel import GRUND_KORREKTUR

    vorlage = {GRUND_KORREKTUR: ANLASS_KORREKTUR, "tausch": ANLASS_TAUSCH}.get(anlass.art, ANLASS_WECHSEL)
    return vorlage.format(datum=anlass.zeit.strftime("%d.%m.%Y"))


def _befund(name: str, key: str, m: tuple[int, int], gespeichert: float, quelle: float, anlass: Anlass) -> CheckErgebnis:
    """Die eine Erzeuger-Stelle des Codes (W-1)."""
    from backend.core.berechnungen.monatswert_vergleich import abweichung_kwh
    from backend.core.zahlenformat import fmt_zahl
    from backend.services.daten_checker.ziele import ziel_monat

    jahr, monat = m
    teile = key.split(":")
    inv = teile[0] == "inv"
    return CheckErgebnis(
        kategorie=CheckKategorie.MONATSWERT_UEBERHOLT.value,
        schwere=CheckSeverity.WARNING,
        meldung=SATZ_MELDUNG.format(name=name, monat=f"{monat:02d}/{jahr}"),
        details=SATZ_DETAILS.format(gespeichert=fmt_zahl(gespeichert, 1), anlass=_anlass_text(anlass),
                                    quelle=fmt_zahl(quelle, 1)),
        investition_id=int(teile[1]) if inv else None,
        code="monatswert_ueberholt",
        # Am Gerät springt das Formular zum Gerät (``geraet`` allein); ein Feld eines Geräts ist statisch nicht prüfbar (W-2).
        ziel=ziel_monat(jahr, monat, geraet=int(teile[1])) if inv else ziel_monat(jahr, monat, feld=_BASIS_SPALTE[teile[1]]),
        werte={"schluessel": key, "jahr": jahr, "monat": monat, "gespeichert_kwh": round(gespeichert, 3),
               "quelle_kwh": round(quelle, 3), "abweichung_kwh": round(abweichung_kwh(gespeichert, quelle), 3),
               "anlass": anlass.art, "anlass_zeit": anlass.zeit.isoformat(timespec="minutes")},
    )


__all__ = ["CODE", "MonatswertUeberholtChecks", "beruehrte_monate", "ueberholte_monate"]
