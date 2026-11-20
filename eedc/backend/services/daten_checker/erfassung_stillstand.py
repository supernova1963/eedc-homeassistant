"""Daten-Checker — Befund «Stunden ohne Stundenwerte» (``erfassung_stillstand``; N-799 Sitzung 3, Bauplan Fassung 3 E-10).

**Was der Befund nennt.** Die Tage der letzten ``FENSTER_TAGE`` (90), an denen eine Zeile die Mengen mehrerer Stunden trägt:

* **Erfassungs-Stillstand** — eine Quelle: die Fensterliste der Lesestelle ``services/kanal/stillstand.py``
  (``fenster_im_bereich``, Regel ``core/berechnungen/spannen.py::stillstand_fenster``); keine zweite Erkennung. Ein Tag
  steht hier, wenn die Nachtragsstunde eines markierbaren Fensters in ihm liegt.
* **Echte Lücke** (Zeilen fehlten, die nächste trägt die Menge, ``spannen`` n > 1 ohne Stillstand) — wenn die Tagesbilanz sie
  aus den Zählerständen rechnet oder nicht rechnen kann.

**Der Tages-Satz hängt am Kennzeichen der Tagesbilanz** (Bauplan §7), nicht an der Fensterliste: dieselbe Layer-Funktion
wie *Cockpit → Tag* und die Tagestabelle (``tagesbilanz.bilanz_aus_stundenrows`` über ``kanal_stunden.stunden_der_tage``,
dieselben Mischzeilen) — ``fenster`` ⇒ «aus den Zählerständen gerechnet» (dazu die Mindest-Netzladung, wenn die Begrenzung
griff), ``nicht_rechenbar`` ⇒ warum, und dass die drei Spalten leer bleiben, ``voll`` (ein Stillstand, dessen Nachtrag unter
der Schwelle liegt, etwa 15.7.2026 auf Produktiv) ⇒ «wie an jedem Tag gerechnet».

**Zwei Lagen in einem Code:** die Tagesliste (höchstens ``MAX_TAGE``, neueste zuerst, wie N-567) und «regelmäßig» — ein Satz,
wenn die Häufigkeits- oder die Grob-Sperre der Lesestelle griff (``mit_gesperrten``). **Ohne Fund eine OK-Zeile** desselben
Codes: die Tagestabelle verlinkt jeden gekennzeichneten Tag mit ``befund=erfassung_stillstand``, auch einen älteren als 90 Tage
— der Link öffnet den Lösungsweg dieser Zeile (``docs/daten-checker/erfassung_stillstand.md``).

**Bestandstage (E-9, festgestellt in Sitzung 3, angenommen vom Master):** eine Stillstands-Erkennung über die
Tabellenspalten trägt nicht — an Anlagen mit Speicher speichert die Zeile ihn nur saldiert (``tages_tabelle._stundenwerte``:
``batterie_netto``), die Vorbedingung «Ladung und Entladung erfasst» ist dort nicht erfüllbar; der Deckel (R3) verwirft eine
Nachtragsmenge über der mit dem Fenster skalierten Schwelle (``_verwerfe``, die Spalte bleibt ``None``), und ohne Marke trägt
die Tagesbilanz kein Kennzeichen, an dem ein Satz hängen könnte. Für Bestandstage bleibt deshalb N-567 (``nachtrag_nach_eingefrorenem_zaehler``) der Befund; dieser hier nennt dort
nur Lücken-Bündel mit Kennzeichen. Nennt er einen Tag, lässt N-567 ihn aus (``_erfassung_stillstand_tage``).

**Verworfene Zeit (Sensorwechsel U3 a, Rechenweg G1):** eine Stelle, die allein eine bei einer Korrektur verworfene, nicht
gefüllte Zeit eines Bilanz-Zählers erklärt, nennt ``zaehler_zeit_verworfen`` (``_ohne_verworfene_zeit``) — hier fällt sie aus,
die Kennzeichen der Tagesbilanz bleiben.

Schwesterdateien: ``energieprofil.py`` (N-567), ``services/kanal/stillstand.py`` (die Fenster),
``services/energie_profil/stundenpaarung.py`` (die Zeiträume in Worten, der Grund der Tagestabelle).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Optional

from backend.core.zahlenformat import fmt_zahl
from backend.models.anlage import Anlage
from backend.services.daten_checker.kategorien import CheckErgebnis, CheckKategorie, CheckSeverity

CODE = "erfassung_stillstand"
#: Wie weit der Befund zurückblickt (Tage, heute eingeschlossen).
FENSTER_TAGE = 90
#: Höchstens so viele Tage nennt die Liste (wie N-567); der Rest als Zahl.
MAX_TAGE = 10
_STUNDE_S = 3600
#: Die Zähler einer Zeile → Anzeigename (Mengen der Nachtragszeile).
_MENGEN = (("pv_kw", "PV"), ("einspeisung_kw", "Einspeisung"), ("netzbezug_kw", "Netzbezug"),
           ("speicher_ladung_kw", "Speicher-Ladung"), ("speicher_entladung_kw", "Speicher-Entladung"))
#: Feld der Zeile → Achse der Spannen.
_ACHSE_JE_FELD = {"pv_kw": "pv", "einspeisung_kw": "einspeisung", "netzbezug_kw": "netzbezug",
                  "speicher_ladung_kw": "batterie", "speicher_entladung_kw": "batterie"}

SATZ_FENSTER = ("Überschuss, Defizit und Direktverbrauch dieses Tages sind für diese Stunden aus den Zählerständen "
                "gerechnet, nicht aus Stundenwerten.")
SATZ_UNGLEICH = ("Die Zähler haben ihre Mengen nicht für dieselben Stunden nachgetragen — Überschuss, Defizit und "
                 "Direktverbrauch dieses Tages lassen sich nicht bestimmen, die drei Spalten bleiben leer.")
SATZ_SALDIERT = ("Der Speicher ist für diesen Tag nur als Saldo von Ladung und Entladung gespeichert — Überschuss, Defizit "
                 "und Direktverbrauch dieses Tages lassen sich nicht bestimmen, die drei Spalten bleiben leer.")
SATZ_VOLL = ("Die nachgetragene Menge enthält höchstens 0,1 kWh {was} — Überschuss, Defizit und Direktverbrauch dieses Tages "
             "sind wie an jedem anderen Tag gerechnet.")
SATZ_MEHRTAEGIG = ("Der Ausfall beginnt schon am {von}: die ganze Menge steht am {tag}, die Tage davor zeigen für diese "
                   "Stunden nichts.")
SATZ_MEHRERE_TAGE = ("Weil der Ausfall mehr als einen Tag umfasst, liegen Überschuss und Defizit dabei deutlich über dem, was "
                     "Stundenwerte ergeben hätten, und der Direktverbrauch darunter.")
SATZ_HAEUFIG = ("Dazu stand die Erfassung in den letzten 90 Tagen {n}-mal mehrere Stunden still — so oft, dass eedc darin "
                "eine Eigenart der Erfassung sieht und diese Stunden nicht kennzeichnet: dort steht die Menge in der Stunde, "
                "in der die Zähler sie gemeldet haben, und zählt in Überschuss, Defizit und Direktverbrauch als diese eine "
                "Stunde.")
SATZ_GROB = ("Ein Zähler meldet nur in ganzen Zehntel-Kilowattstunden oder gröber; Stunden ohne Änderung sind bei ihm normal, und "
             "eedc kennzeichnet sie nicht ({n}-mal in den letzten 90 Tagen).")
EINLEITUNG = ("An diesen Tagen hat die Erfassung für einige Stunden keine Stundenwerte geliefert — sie stand still oder "
              "hatte eine Lücke — und die Zähler haben die Menge danach auf einmal nachgetragen. Tag und Monat zählen die "
              "Menge vollständig.")
SCHLUSS = "Was für diese Tage gilt und welche Vorbehalte die Rechnung hat, steht unter «Was gilt»."
OK_MELDUNG = "Keine Stunden ohne Stundenwerte in den letzten 90 Tagen"
OK_DETAILS = ("Steht die Erfassung mehrere Stunden still oder fehlen Stundenwerte, nennt eedc hier die Tage der letzten 90 "
              "Tage. Ein älterer Tag mit dem Zeichen «geschätzt» an Überschuss, Defizit und Direktverbrauch öffnet über "
              "«Im Daten-Checker nachlesen» die Erklärung zu diesem Befund.")


@dataclass
class _Stelle:
    """Eine gebündelte Zeile eines Tages: ihr Zeitraum (Ortszeit, ``bis`` = Ende der Nachtragsstunde), ob ein Stillstand
    sie gebildet hat, und die Zeile selbst (Mengen)."""
    von: datetime
    bis: datetime
    stillstand: bool
    zeile: Any


@dataclass
class _Tag:
    datum: date
    bilanz: Any
    stellen: list[_Stelle] = field(default_factory=list)


def _kwh(wert: float) -> str:
    """Eine Menge in Worten, einheitlich mit einer Nachkommastelle (K1): unter 0,005 kWh «0,0 kWh» (auch ein Rundungsrest
    unter null), bis 0,05 kWh «unter 0,1 kWh»."""
    if abs(wert) < 0.005:
        return f"{fmt_zahl(0.0, 1)} kWh"
    if abs(wert) < 0.05:
        return f"unter {fmt_zahl(0.1, 1)} kWh"
    return f"{fmt_zahl(wert, 1)} kWh"


def _mengen(zeile: Any) -> str:
    """Die nachgetragenen Mengen der Zeile (K1, Nachmessung F1): tragen die Bilanz-Achsen mit Wert **dasselbe** n, alle; sonst
    nur die Achsen mit n > 1 — eine Achse mit n = 1 hatte ihre Stundenwerte (6.11.2025: Einspeisung und Netzbezug n = 9,
    PV und Speicher jede Stunde eine Zeile ⇒ nur Einspeisung und Netzbezug)."""
    from backend.core.berechnungen.spannen import spanne_roh

    spannen = getattr(zeile, "spannen", None)
    werte = [(attr, name, w) for attr, name in _MENGEN if (w := getattr(zeile, attr, None)) is not None]
    n_je = {_ACHSE_JE_FELD[attr]: spanne_roh(spannen, _ACHSE_JE_FELD[attr]) for attr, _n, _w in werte}
    alle = len(set(n_je.values())) <= 1
    return ", ".join(f"{name} {_kwh(float(w))}" for attr, name, w in werte
                     if alle or n_je[_ACHSE_JE_FELD[attr]] > 1)


def _stellen_des_tages(tag: date, zeilen: list, fenster: list, bilanz: Any) -> list[_Stelle]:
    """Die Stillstands-Fenster mit Nachtrag an ``tag`` und die übrigen gekennzeichneten Zeilen der Bilanz (Lücken)."""
    from backend.services.energie_profil.stillstand_marke import stunden_der_zeile
    from backend.services.energie_profil.stundenpaarung import zeitraeume

    out: list[_Stelle] = []
    belegt: set[int] = set()
    for f in sorted(fenster, key=lambda f: f.nachtrag_ts):
        zeile = next((z for z in zeilen if f.nachtrag_ts in stunden_der_zeile(tag, z.stunde)
                      and getattr(z, "raster", None) is not None), None)
        if zeile is not None:
            belegt.add(id(zeile))
        out.append(_Stelle(datetime.fromtimestamp(f.von_ts), datetime.fromtimestamp(f.nachtrag_ts + _STUNDE_S),
                           True, zeile))
    for pz in getattr(bilanz, "paarung_zeilen", ()):
        zeile = next((z for z in zeilen if z.stunde == pz[0] and getattr(z, "raster", None) == pz[2]), None)
        if zeile is None or id(zeile) in belegt:
            continue
        belegt.add(id(zeile))
        for von, bis in zeitraeume(tag, [pz]):
            out.append(_Stelle(von, bis, False, zeile))
    return sorted(out, key=lambda s: s.bis)


def _satz_der_stelle(tag: date, s: _Stelle) -> str:
    from backend.services.energie_profil.stundenpaarung import zeitraum_text

    zeitraum = zeitraum_text(tag, s.von, s.bis)
    was = "stand die Erfassung" if s.stillstand else "fehlten Stundenwerte"
    satz = f"Für die Stunden {zeitraum} {was}"
    mengen = _mengen(s.zeile) if s.zeile is not None else ""
    satz += f"; nachgetragen: {mengen}." if mengen else "."
    if s.von.date() < tag:
        satz += " " + SATZ_MEHRTAEGIG.format(von=s.von.strftime("%d.%m.%Y"), tag=tag.strftime("%d.%m.%Y"))
    return satz


def _kennzeichen_satz(t: _Tag) -> str:
    """Der Satz zum Kennzeichen der Tagesbilanz (Bauplan §7: am Kennzeichen, nicht an der Fensterliste)."""
    from backend.core.berechnungen.tagesbilanz import (
        FENSTER_SCHWELLE_KWH, PAARUNG_FENSTER, PAARUNG_NICHT_RECHENBAR, URSACHE_SALDIERT, URSACHE_UNGLEICH,
    )

    paarung = getattr(t.bilanz, "stundenpaarung", None)
    if paarung == PAARUNG_FENSTER:
        from backend.services.energie_profil.stundenpaarung import mindest_satz

        mindest = mindest_satz(t.bilanz)
        lang = any((s.bis - s.von).total_seconds() > 24 * _STUNDE_S for s in t.stellen)
        return " ".join([SATZ_FENSTER] + ([mindest] if mindest else []) + ([SATZ_MEHRERE_TAGE] if lang else []))
    if paarung == PAARUNG_NICHT_RECHENBAR:
        arten = {z[3] for z in getattr(t.bilanz, "paarung_zeilen", ()) if len(z) > 3}
        return SATZ_SALDIERT if URSACHE_SALDIERT in arten and URSACHE_UNGLEICH not in arten else SATZ_UNGLEICH
    pv = [getattr(s.zeile, "pv_kw", None) for s in t.stellen if s.zeile is not None]
    unter = any(p is None or p <= FENSTER_SCHWELLE_KWH for p in pv) if pv else True
    return SATZ_VOLL.format(was="PV" if unter else "Verbrauch")


def _tag_text(t: _Tag) -> str:
    teile = [_satz_der_stelle(t.datum, s) for s in t.stellen]
    return f"{t.datum.strftime('%d.%m.%Y')}: " + " ".join(teile + [_kennzeichen_satz(t)])


def _gesperrt_saetze(gesperrt: list) -> list[str]:
    from backend.core.berechnungen.spannen import SPERRE_GROB, SPERRE_HAEUFIG

    haeufig = sum(1 for f in gesperrt if f.sperre == SPERRE_HAEUFIG)
    grob = sum(1 for f in gesperrt if f.sperre == SPERRE_GROB)
    return ([SATZ_HAEUFIG.format(n=haeufig)] if haeufig else []) + ([SATZ_GROB.format(n=grob)] if grob else [])


def _ergebnis(tage: list[_Tag], gesperrt: list) -> CheckErgebnis:
    from backend.core.berechnungen.spannen import SPERRE_GROB, SPERRE_HAEUFIG
    from backend.core.berechnungen.tagesbilanz import PAARUNG_FENSTER, PAARUNG_NICHT_RECHENBAR

    tage = sorted(tage, key=lambda t: t.datum, reverse=True)
    regel = _gesperrt_saetze(gesperrt)
    if tage:
        meldung = (f"{len(tage)} Tag(e) mit Stunden ohne Stundenwerte "
                   f"({tage[-1].datum.strftime('%d.%m.%Y')} … {tage[0].datum.strftime('%d.%m.%Y')})")
        if regel:
            meldung += " — dazu steht die Erfassung regelmäßig still"
    else:
        meldung = "Die Erfassung steht regelmäßig mehrere Stunden still"
    liste = [_tag_text(t) for t in tage[:MAX_TAGE]]
    if len(tage) > MAX_TAGE:
        liste.append(f"… und {len(tage) - MAX_TAGE} weitere Tage.")
    details = " ".join(([EINLEITUNG] if tage else []) + liste + regel + [SCHLUSS])
    return _zeile(
        True, meldung, details,
        {
            "tage": len(tage),
            "von": tage[-1].datum.isoformat() if tage else None,
            "bis": tage[0].datum.isoformat() if tage else None,
            "stillstand_tage": sum(1 for t in tage if any(s.stillstand for s in t.stellen)),
            "luecken_tage": sum(1 for t in tage if any(not s.stillstand for s in t.stellen)),
            "fenster_gerechnet": sum(1 for t in tage if getattr(t.bilanz, "stundenpaarung", None) == PAARUNG_FENSTER),
            "nicht_rechenbar": sum(1 for t in tage
                                   if getattr(t.bilanz, "stundenpaarung", None) == PAARUNG_NICHT_RECHENBAR),
            "regelmaessig_haeufig": sum(1 for f in gesperrt if f.sperre == SPERRE_HAEUFIG),
            "regelmaessig_grob": sum(1 for f in gesperrt if f.sperre == SPERRE_GROB),
        },
    )


def _zeile(fund: bool, meldung: str, details: str, werte: dict) -> CheckErgebnis:
    """Die eine Erzeuger-Stelle des Codes (W-1: ein Code an genau einer Stelle; W-6: eine Auskunft ist INFO) — Fund (INFO)
    oder OK-Zeile."""
    return CheckErgebnis(kategorie=CheckKategorie.ENERGIEPROFIL_PLAUSIBILITAET,
                         schwere=CheckSeverity.INFO if fund else CheckSeverity.OK, meldung=meldung,
                         details=details, code="erfassung_stillstand", werte=werte)


async def tage_ohne_stundenwerte(db, anlage_id: int, von: date, bis: date) -> tuple[list[_Tag], list]:
    """Die genannten Tage ``von`` … ``bis`` und die gesperrten Fenster (Lage «regelmäßig») — ohne Text."""
    from backend.core.berechnungen.tagesbilanz import PAARUNG_FENSTER, PAARUNG_NICHT_RECHENBAR, bilanz_aus_stundenrows
    from backend.services.energie_profil.kanal_stunden import UEBERSCHUSS_FELDER, stunden_der_tage
    from backend.services.kanal.stillstand import fenster_im_bereich

    fenster = await fenster_im_bereich(db, anlage_id, von, bis, mit_gesperrten=True)
    nachtrag_je_tag: dict[date, list] = defaultdict(list)
    gesperrt = []
    for f in fenster:
        tag = datetime.fromtimestamp(f.nachtrag_ts).date()
        if not von <= tag <= bis:
            continue
        (nachtrag_je_tag[tag] if f.sperre is None else gesperrt).append(f)
    zeilen_je_tag: dict[date, list] = defaultdict(list)
    for z in await stunden_der_tage(db, anlage_id, von, bis, felder=UEBERSCHUSS_FELDER):
        zeilen_je_tag[z.datum].append(z)
    tage: list[_Tag] = []
    for tag in sorted(set(zeilen_je_tag) | set(nachtrag_je_tag)):
        zeilen = zeilen_je_tag.get(tag, [])
        bilanz = bilanz_aus_stundenrows(zeilen)
        gekennzeichnet = bilanz.stundenpaarung in (PAARUNG_FENSTER, PAARUNG_NICHT_RECHENBAR)
        if not gekennzeichnet and tag not in nachtrag_je_tag:
            continue
        t = _Tag(tag, bilanz, _stellen_des_tages(tag, zeilen, nachtrag_je_tag.get(tag, []), bilanz))
        if t.stellen:
            tage.append(t)
    return tage, gesperrt


def _achsen_mit_nachtrag(zeile: Any) -> set[str]:
    """Die Achsen, deren Menge die Zeile über mehr als eine Stunde trägt (``spannen`` n > 1, wie ``_mengen``)."""
    from backend.core.berechnungen.spannen import spanne_roh

    spannen = getattr(zeile, "spannen", None)
    return {_ACHSE_JE_FELD[attr] for attr, _n in _MENGEN
            if getattr(zeile, attr, None) is not None and spanne_roh(spannen, _ACHSE_JE_FELD[attr]) > 1}


async def _ohne_verworfene_zeit(db, anlage: Anlage, tage: list[_Tag]) -> list[_Tag]:
    """**Ein Befund je Ursache** (Sensorwechsel U3 a, Rechenweg G1, Messfrage M5): eine Stelle, die allein eine bei einer
    Korrektur verworfene, nicht gefüllte Zeit eines Bilanz-Zählers erklärt (``datenquelle/verworfen.stelle_erklaert``), nennt
    der Befund ``zaehler_zeit_verworfen`` — hier fällt sie aus; ein Tag ohne übrige Stelle fällt ganz aus. Die Zahlen und
    Kennzeichen der Tagesbilanz (N-799) bleiben, wie sie sind: ausgelassen wird nur im Text, nicht in der Lesestelle der
    Fenster (``kanal/stillstand.fenster_im_bereich`` trägt die Marken der Tagesbilanz). Ohne Lücke keine Abfrage."""
    from backend.services.daten_checker.datenquelle.verworfen import achsen_der_verworfenen_zeiten, stelle_erklaert

    verworfen = await achsen_der_verworfenen_zeiten(db, anlage) if tage else []
    if not verworfen:
        return tage
    aus = []
    for t in tage:
        t.stellen = [s for s in t.stellen if s.zeile is None
                     or not stelle_erklaert(s.von, s.bis, _achsen_mit_nachtrag(s.zeile), verworfen)]
        if t.stellen:
            aus.append(t)
    return aus


class ErfassungStillstandChecks:
    """Mixin des ``DatenChecker`` — der Befund ``erfassung_stillstand``."""

    async def _check_erfassung_stillstand(self, anlage: Anlage, heute: Optional[date] = None) -> list[CheckErgebnis]:
        heute = heute or date.today()
        von = heute - timedelta(days=FENSTER_TAGE - 1)
        tage, gesperrt = await tage_ohne_stundenwerte(self.db, anlage.id, von, heute)
        self._erfassung_stillstand_tage = {t.datum for t in tage}       # auch die ausgelassenen: N-567 nennt sie nicht
        tage = await _ohne_verworfene_zeit(self.db, anlage, tage)
        if not tage and not gesperrt:
            return [_zeile(False, OK_MELDUNG, OK_DETAILS, {"tage": 0})]
        return [_ergebnis(tage, gesperrt)]


__all__ = ["CODE", "FENSTER_TAGE", "MAX_TAGE", "ErfassungStillstandChecks", "tage_ohne_stundenwerte"]
