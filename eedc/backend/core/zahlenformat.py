"""Deutsche Zahlenschreibweise — EIN Ort für das ganze Backend (N-234 → N-353).

**Warum dieses Modul in ``core/`` liegt und nicht mehr unter ``services/pdf/``.**
Die Regel entstand mit **N-234** für die vier PDF-Berichte und wurde dort korrekt
zentralisiert (``services/pdf/formatierung.py``). Sie ist aber keine PDF-Regel,
sondern die **Darstellungs-Regel des Produkts** — Style-Guide 0a: *„Regel/SoT
existiert → anwenden, keine lokale Formatierung daneben."* Am falschen Ort war
sie für jeden anderen Konsumenten unerreichbar, und genau das ist **N-353**
geworden: der Daten-Checker schrieb „6.0 kWp", während dasselbe Gerät in der
Oberfläche und im PDF „6,0 kWp" heißt.

⚠ **Die PDF-Seite ist damit NICHT umgezogen.** ``services/pdf/formatierung.py``
bleibt bestehen und reicht diese Funktionen weiter — Templates, Jinja-Filter und
die vier Builder rufen unverändert dieselben Namen auf, und ``LEER`` bleibt der
PDF-Gedankenstrich. Ein Umzug, der das Schriftbild eines ausgelieferten Berichts
ändert, wäre ein anderer Vorgang als dieser hier
([[feedback_ist_anzeigen_nur_aendern_wo_noetig]]).

**Die zwei Defekte, die eine deutsche Zahl hat, und warum beide zählen:**

1. **Das Dezimaltrennzeichen** — ``f"{6.0:.1f}"`` ergibt ``6.0`` statt ``6,0``.
   Betrifft jede Formatierung mit Nachkommastelle.
2. **Der Tausenderpunkt** — ``f"{12000:.0f}"`` ergibt ``12000`` statt ``12.000``.
   Betrifft auch ``:.0f``, und das ist der Teil, den ein Blick auf das
   Dezimaltrennzeichen allein übersieht (gemessen 2026-09-16: im Daten-Checker
   stehen Heizwärmebedarfe und Jahresfahrleistungen genau so).

**Kein ``locale``.** Die Prozessumgebung des Add-ons ist nicht gesetzt, und eine
Formatierung, die von einer Umgebungsvariable abhängt, liefert je nach Container
etwas anderes — dieselbe Klasse wie die Zeitzonen-Frage in CLAUDE.md, nur ohne
deren Auslieferungs-Garantien.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

#: Was ein fehlender Wert anzeigt, wenn der Aufrufer nichts anderes sagt.
#: ⚠ **Nicht der Display-Token „—" des Frontends und nicht der PDF-Gedankenstrich
#: „–"**: Die Konsumenten dieses Moduls setzen ihn selbst (``services/pdf``
#: übergibt seinen eigenen). Im Fließtext einer Meldung kommt ``None`` gar nicht
#: vor — dort entsteht der Satz nur, wenn es einen Wert gibt.
LEER = ""


def fmt_zahl(
    wert: Optional[float],
    decimals: int = 0,
    leer: str = LEER,
    vorzeichen: bool = False,
) -> str:
    """Deutsche Schreibweise mit Tausenderpunkt: ``12.345,67``.

    Der Dreischritt über ``X`` ist nötig, weil Python beide Trennzeichen
    vertauscht setzt; ein einfaches ``replace`` würde sich selbst überschreiben.

    ⭐ **``vorzeichen=True`` ist kein Luxus, sondern Bedingung.** Die
    Drift-Meldungen des Daten-Checkers schreiben ``Δ {x:+.1f} kWh`` — dort
    **ist** das Plus die Aussage (eedc liegt über HA oder darunter). Ohne dieses
    Argument hätte der Sweep aus N-353 an genau diesen Stellen entweder das
    Vorzeichen verloren oder sie auslassen müssen; beides wäre schlechter als
    der Ist-Zustand gewesen ([[feedback_umzug_traegt_die_annahmen_mit]]).
    """
    if wert is None:
        return leer
    flagge = "+" if vorzeichen else ""
    return (
        f"{wert:{flagge},.{decimals}f}"
        .replace(",", "X").replace(".", ",").replace("X", ".")
    )


def fmt_euro(wert: Optional[float], decimals: int = 2, leer: str = LEER) -> str:
    """``12.345,67 €``."""
    if wert is None:
        return leer
    return f"{fmt_zahl(wert, decimals)} €"


def fmt_kwh(wert: Optional[float], decimals: int = 0, leer: str = LEER) -> str:
    """``12.345 kWh``."""
    if wert is None:
        return leer
    return f"{fmt_zahl(wert, decimals)} kWh"


def fmt_pct(
    wert: Optional[float],
    decimals: int = 1,
    leer: str = LEER,
    vorzeichen: bool = False,
) -> str:
    """``12,3 %`` — **ohne** Tausenderpunkt, mit Leerzeichen vor dem Zeichen.

    Das Leerzeichen ist Regel 0a des Style-Guides („% mit Leerzeichen"); der
    fehlende Tausenderpunkt stammt aus dem N-234-Makro und gilt weiter:
    Prozentwerte über 1000 gibt es in diesen Texten nicht.
    """
    if wert is None:
        return leer
    flagge = "+" if vorzeichen else ""
    return f"{wert:{flagge}.{decimals}f}".replace(".", ",") + " %"


def fmt_einheit(
    wert: Optional[float], einheit: str, decimals: int = 2, leer: str = LEER
) -> str:
    """``12,32 kWp`` — für die Einheiten, die keinen eigenen Helfer verdienen."""
    if wert is None:
        return leer
    return f"{fmt_zahl(wert, decimals)} {einheit}"


def fmt_datum(wert: Optional[date], leer: str = LEER) -> str:
    """``01.09.2026`` — das Datum in derselben Schreibweise wie Oberfläche und PDF.

    N-560 (25.09.2026): das Aktivitätsprotokoll nennt Anschaffungs- und
    Stilllegungsdatum einer Komponente im Klartext; bisher bildete jeder
    Konsument ``strftime("%d.%m.%Y")`` selbst (PDF-Builder, Daten-Checker).
    """
    if wert is None:
        return leer
    return wert.strftime("%d.%m.%Y")
