"""N-79 — `bedingung_anlage` hat einen SoT, und beide Auswerter lesen ihn.

**Der Befund.** Die Zuordnung *Bedingungswert → verdrängender Investitionstyp*
stand bis 2026-08-29 **zweimal wertgleich** im Baum: als `if`-Kette in
``field_definitions.get_felder_fuer_investition`` (Monatsabschluss-/Import-Weg)
und als Dict ``_VERDRAENGT_TYP`` in ``services/datenquellen_validierung.py``
(Datenquellen-Fläche). Ein dritter Wert, nur an einer der beiden Stellen
eingetragen, hätte an genau einer der beiden Flächen gewirkt — **still**, weil
beide Wege fail-open sind: ein unbekannter Wert verdrängt einfach nicht.

⚠ **Warum es diese Datei überhaupt gibt und nicht nur eine Vokabel-Probe:**
Eine Probe, die nur prüft, ob jeder benutzte Wert im SoT steht, bliebe **grün**,
wenn ein Auswerter wieder seine eigene Kopie bekäme — der SoT wäre dann korrekt
und trotzdem wirkungslos. Deshalb steht hier **je Auswerter eine eigene
Verhaltens-Gegenprobe**: beide biegen den SoT auf einen anderen Typ um und
verlangen, dass sich das Verhalten mitbewegt. Wer die Einhängung an *einer* der
beiden Stellen zurückbaut, macht *eine* davon rot.
(Bauform aus N-274/W-Z1: dort blieb ein Wächter grün, als die Einhängung
zurückgebaut wurde — die Größe wurde an mehr Stellen gebildet als geprüft.)
"""
import pytest

from backend.core.field_definitions import (
    BEDINGUNG_ANLAGE_VERDRAENGT,
    INVESTITION_FELDER,
    get_felder_fuer_investition,
    verdraengender_typ,
)
from backend.services.datenquellen_validierung import (
    _VERDRAENGT_TEXT,
    stufe_bedarf_ein,
)


def _alle_felder(felder):
    """Beide Formen der Registry — Liste ODER Dict von Listen (`sonstiges`)."""
    listen = felder.values() if isinstance(felder, dict) else [felder]
    return [f for liste in listen for f in liste]


def _benutzte_werte() -> set[str]:
    return {
        f["bedingung_anlage"]
        for felder in INVESTITION_FELDER.values()
        for f in _alle_felder(felder)
        if f.get("bedingung_anlage")
    }


# ─── Vokabel-Wächter — trägt das Fail-open ──────────────────────────────────

def test_jeder_bedingung_anlage_wert_ist_bekannt():
    """Ein Tippfehler fällt zur Laufzeit NICHT auf — hier muss er auffallen.

    Fail-open heißt: ein unbekannter Wert verdrängt nichts, das Feld erscheint
    einfach. Ohne diesen Wächter wäre das die Einladung, eine Bedingung still
    wirkungslos zu machen.
    """
    unbekannt = sorted(_benutzte_werte() - set(BEDINGUNG_ANLAGE_VERDRAENGT))
    assert not unbekannt, f"bedingung_anlage ohne Eintrag im SoT: {unbekannt}"


def test_jeder_wert_hat_auch_einen_anwendertext():
    """Zweite Hälfte desselben Vokabulars.

    `_VERDRAENGT_TEXT` bleibt bewusst in der Datenquellen-Fläche — er ist
    Anwendertext, keine Semantik. Aber er wird nach denselben Werten
    geschlüsselt: Wer einen dritten Wert einführt und den Text vergisst, bekommt
    ein Feld, das ohne Begründung inaktiv steht.
    """
    ohne_text = sorted(_benutzte_werte() - set(_VERDRAENGT_TEXT))
    assert not ohne_text, f"bedingung_anlage ohne Anwendertext: {ohne_text}"


def test_ein_unbekannter_wert_verdraengt_nichts():
    """Fail-open, ausdrücklich festgehalten — die Gegenrichtung wäre schlimmer.

    Ein Auswerter, der bei unbekanntem Wert wirft oder ausblendet, ließe ein
    bereits ZUGEORDNETES Feld unsichtbar verschwinden und unlöschbar
    zurückbleiben.
    """
    assert verdraengender_typ("gibt_es_nicht") is None
    assert verdraengender_typ(None) is None
    assert verdraengender_typ("") is None


# ─── Je Auswerter eine eigene Gegenprobe ────────────────────────────────────
#
# Beide biegen den SoT für `keine_wallbox` von "wallbox" auf "speicher" um.
# Liest der Auswerter den SoT, dreht sich das Verhalten mit. Hat er seine eigene
# Kopie, bleibt er bei "wallbox" — und die Probe wird rot.

_FELD = "ladung_pv_kwh"          # e-auto, trägt `bedingung_anlage: keine_wallbox`
_PARAM = {"laedt_aus_netz": True}


def _felder_der_anlage(typen: list[str]) -> set[str]:
    class _Inv:
        def __init__(self, typ): self.typ = typ
    felder = get_felder_fuer_investition(
        "e-auto", _PARAM, anlage_investitionen=[_Inv(t) for t in typen],
    )
    return {f["feld"] for f in felder}


def test_registry_weg_liest_den_sot(monkeypatch):
    """Gegenprobe 1 — `field_definitions.get_felder_fuer_investition`."""
    # Ausgangslage: die Wallbox verdrängt, der Speicher nicht.
    assert _FELD not in _felder_der_anlage(["wallbox"])
    assert _FELD in _felder_der_anlage(["speicher"])

    monkeypatch.setitem(BEDINGUNG_ANLAGE_VERDRAENGT, "keine_wallbox", "speicher")

    # Jetzt muss es genau andersherum sein — sonst rechnet die Stelle selbst.
    assert _FELD in _felder_der_anlage(["wallbox"]), (
        "get_felder_fuer_investition folgt dem SoT nicht — es verdrängt weiter "
        "bei 'wallbox', obwohl der SoT 'speicher' sagt (N-79)"
    )
    assert _FELD not in _felder_der_anlage(["speicher"])


def _bedarf(typen: set[str]) -> str:
    ergebnis = stufe_bedarf_ein(
        [{"id": "f1", "feld": _FELD, "typ": "e-auto", "belegt": False,
          "bedarf": "pflicht", "bedarf_gruppe": None,
          "bedingung_anlage": "keine_wallbox"}],
        vorhandene_typen=typen,
    )
    return ergebnis["f1"]["bedarf"]


def test_datenquellen_flaeche_liest_den_sot(monkeypatch):
    """Gegenprobe 2 — `datenquellen_validierung.stufe_bedarf_ein`."""
    assert _bedarf({"wallbox"}) == "inaktiv"
    assert _bedarf({"speicher"}) != "inaktiv"

    monkeypatch.setitem(BEDINGUNG_ANLAGE_VERDRAENGT, "keine_wallbox", "speicher")

    assert _bedarf({"wallbox"}) != "inaktiv", (
        "stufe_bedarf_ein folgt dem SoT nicht — es verdrängt weiter bei "
        "'wallbox', obwohl der SoT 'speicher' sagt (N-79)"
    )
    assert _bedarf({"speicher"}) == "inaktiv"


@pytest.mark.parametrize("wert,typ", sorted(BEDINGUNG_ANLAGE_VERDRAENGT.items()))
def test_sot_eintraege_nennen_einen_echten_investitionstyp(wert, typ):
    """Ein Vokabel-Eintrag, der auf einen Typ zeigt, den es nicht gibt,
    verdrängt nie — und sieht dabei aus wie eine gesetzte Regel."""
    assert typ in INVESTITION_FELDER, f"{wert!r} zeigt auf unbekannten Typ {typ!r}"
