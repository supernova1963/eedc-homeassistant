"""N-234: EIN Ort für die deutsche Zahlenschreibweise in allen PDF-Berichten.

**Der Befund:** Der Jahresbericht schrieb Zahlen deutsch, die drei anderen
Berichte englisch — sichtbar als „7.9 Jahre", „12.32 kWp" und „48.1372°" in
einem ausgelieferten Dokument. Der Grund war nicht Nachlässigkeit, sondern
**Erreichbarkeit**: Die vier Formatierer lebten als Jinja-Makros **innerhalb**
von ``jahresbericht.html``, und Jinja vererbt Makros nicht über
``{% extends %}`` — für ``finanzbericht.html`` und ``anlagendokumentation.html``
waren sie schlicht nicht da. Die Python-Builder wiederum formatieren im Code,
wo ein Template-Makro ohnehin nicht greift.

**Warum es ein Python-Modul ist und nicht ein zweites Makro-Template:** Zwei
Implementierungen derselben Regel — eine für Jinja, eine für Python — wären
genau die Klasse, die im selben Paket als N-136 behoben wurde. Die Funktionen
hier sind der SoT; ``engine.py`` reicht sie als Jinja-Filter **und** als
Globals in die Templates, damit dort dieselbe Rechnung läuft.

**Die ``–``-Konvention ist übernommen, nicht erfunden:** ``None`` wird zum
Gedankenstrich, weil die Makros das schon so hielten und das PDF diese Lücke
vom Wert „0" unterscheidet (F-43 hängt daran).
"""

from __future__ import annotations

from typing import Optional

#: Was ein fehlender Wert im PDF anzeigt. Bewusst der Gedankenstrich der
#: bisherigen Makros — nicht der Display-Token „—" des Frontends, sonst
#: änderte sich das Schriftbild jedes bestehenden Berichts.
LEER = "–"


def fmt_zahl(wert: Optional[float], decimals: int = 0) -> str:
    """Deutsche Schreibweise mit Tausenderpunkt: ``12.345,67``.

    Der Dreischritt über ``X`` ist nötig, weil Python beide Trennzeichen
    vertauscht setzt; ein einfaches ``replace`` würde sich selbst überschreiben.
    """
    if wert is None:
        return LEER
    return f"{wert:,.{decimals}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def fmt_euro(wert: Optional[float]) -> str:
    """``12.345,67 €`` — zwei Nachkommastellen, wie bisher im Jahresbericht."""
    if wert is None:
        return LEER
    return f"{fmt_zahl(wert, 2)} €"


def fmt_kwh(wert: Optional[float], decimals: int = 0) -> str:
    """``12.345 kWh``."""
    if wert is None:
        return LEER
    return f"{fmt_zahl(wert, decimals)} kWh"


def fmt_pct(wert: Optional[float], decimals: int = 1) -> str:
    """``12,3 %`` — **ohne** Tausenderpunkt und mit Leerzeichen vor dem Zeichen.

    Das Leerzeichen ist Regel 0a des Style-Guides („% mit Leerzeichen"), der
    fehlende Tausenderpunkt die Übernahme des bisherigen ``fmt_pct``-Makros:
    Prozentwerte über 1000 gibt es in diesen Berichten nicht.
    """
    if wert is None:
        return LEER
    return f"{wert:.{decimals}f}".replace(".", ",") + " %"


def fmt_einheit(wert: Optional[float], einheit: str, decimals: int = 2) -> str:
    """``12,32 kWp`` — für die Einheiten, die keinen eigenen Helfer verdienen.

    Genau die Form, die in ``anlagendokumentation.py`` fünfmal als f-String
    ausgeschrieben stand (kWp · kWh · kW (AC)).
    """
    if wert is None:
        return LEER
    return f"{fmt_zahl(wert, decimals)} {einheit}"


#: Was ``engine.py`` in die Jinja-Umgebung hängt. Als **Filter** benutzbar
#: (``{{ v|fmt_eur }}``) und als **Funktion** (``{{ fmt_eur(v) }}``), damit die
#: bestehenden Makro-Aufrufe in `jahresbericht.html` unverändert weiterlaufen.
#: ``fmt_eur``/``fmt_num`` sind die Namen, unter denen das Template sie kennt.
JINJA_FORMATIERER = {
    "fmt_zahl": fmt_zahl,
    "fmt_num": fmt_zahl,
    "fmt_euro": fmt_euro,
    "fmt_eur": fmt_euro,
    "fmt_kwh": fmt_kwh,
    "fmt_pct": fmt_pct,
    "fmt_einheit": fmt_einheit,
}
