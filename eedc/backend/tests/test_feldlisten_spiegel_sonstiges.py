"""Wächter «Feldlisten-Spiegel Sonstiges» (#443/N-785, Päckchen DD 10.11.2026).

**Warum es ihn gibt.** Die Monatsabschluss-Felder eines *Sonstiges*-Geräts stehen zweimal: in der Backend-Registry
(``core/field_definitions/registry.py::INVESTITION_FELDER["sonstiges"]``) und im Client
(``frontend/src/lib/fieldDefinitions.ts::SONSTIGES_FELDER``). Verbunden waren sie nur durch den Kommentar «Spiegel von …».
Die Kategorie ``abgabe`` (§9.2, 05.09.2026) kam nur im Backend an: der Client fand keinen Schlüssel, nahm die Liste für
ungepflegte Geräte, das Formular zeichnete für ein Abgabe-Gerät nur den Erlös (mit dem Erzeuger-Label) und verwarf den
Sensor-Vorschlag zu ``abgabe_kwh`` — wer über das Formular abschloss, speicherte die Abgabe nicht (#443, rilmor-mhrs).

Geprüft je Kategorie: die **Feldnamen** in Menge und Reihenfolge, die **Labels**, wo beide Seiten eines tragen, und die
**Kategorien** selbst. Bewusst regex-basiert über die TypeScript-Quelle (wie ``check:spiegel-backend``): kein Node, kein
Bundling im Backend-Gate.
"""

from __future__ import annotations

import re
from pathlib import Path

from backend.core.field_definitions.registry import INVESTITION_FELDER

_TS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "fieldDefinitions.ts"


def _client_felder() -> dict[str, list[tuple[str, str]]]:
    """``SONSTIGES_FELDER`` aus der TypeScript-Quelle: Kategorie → [(feld, label)] in Quellreihenfolge."""
    text = _TS.read_text(encoding="utf-8")
    start = text.index("const SONSTIGES_FELDER: Record<string, FeldDefinition[]> = {")
    ende = text.index("\n}\n", start)
    block = text[start:ende]
    out: dict[str, list[tuple[str, str]]] = {}
    kategorie = None
    for zeile in block.splitlines()[1:]:
        m = re.match(r"^  (\w+): \[", zeile)
        if m:
            kategorie = m.group(1)
            out[kategorie] = []
            continue
        f = re.search(r"\{\s*feld:\s*'(\w+)',\s*label:\s*'([^']*)'", zeile)
        if f and kategorie is not None:
            out[kategorie].append((f.group(1), f.group(2)))
    return out


def _backend_felder() -> dict[str, list[tuple[str, str]]]:
    return {
        kat: [(f["feld"], f.get("label", "")) for f in felder]
        for kat, felder in INVESTITION_FELDER["sonstiges"].items()
    }


def test_client_liste_ist_lesbar():
    """Gegenprobe gegen eine blinde Abwesenheit: der Regex findet die bekannten Kategorien mit Feldern."""
    client = _client_felder()
    assert client.get("verbraucher"), client
    assert ("zaehlerstand", "Zählerstand") in client.get("zaehler", [])


def test_kategorien_gleich():
    assert sorted(_client_felder()) == sorted(_backend_felder())


def test_feldnamen_je_kategorie_gleich_in_menge_und_reihenfolge():
    client, backend = _client_felder(), _backend_felder()
    abweichend = {
        kat: {"backend": [f for f, _ in backend[kat]], "client": [f for f, _ in client.get(kat, [])]}
        for kat in backend
        if [f for f, _ in backend[kat]] != [f for f, _ in client.get(kat, [])]
    }
    assert not abweichend, abweichend


def test_labels_gleich_wo_beide_eines_tragen():
    client, backend = _client_felder(), _backend_felder()
    abweichend = []
    for kat, felder in backend.items():
        c = dict(client.get(kat, []))
        for feld, label in felder:
            if label and c.get(feld) and c[feld] != label:
                abweichend.append((kat, feld, label, c[feld]))
    assert not abweichend, abweichend


def test_abgabe_nicht_in_der_liste_fuer_ungepflegte_geraete():
    """Spiegel von ``auswahl._sonstiges_felder_ungepflegt``: weder Zähler- noch Abgabe-Kategorie geben ein Feld an ein
    Gerät ohne gepflegte Kategorie (dort liest jeder wertführende Pfad «Verbraucher» — N-244)."""
    from backend.core.field_definitions.auswahl import _sonstiges_felder_ungepflegt

    assert "abgabe_kwh" not in {f["feld"] for f in _sonstiges_felder_ungepflegt()}
    text = _TS.read_text(encoding="utf-8")
    start = text.index("const SONSTIGES_FELDER_UNGEPFLEGT")
    block = text[start:text.index("})()", start)]
    assert "!istZaehlerKategorie(k)" in block and "!istAbgabeKategorie(k)" in block, block


def test_jede_kategorie_hat_einen_anzeigenamen():
    """N-789 (Master-Entscheid 10.11.2026): jede Backend-Kategorie hat ein Label in Anwender-Sprache
    (``SONSTIGES_KATEGORIE_LABEL``) — der Daten-Checker nennt sie in Meldungen; eine neue Kategorie erschiene sonst
    als Registry-Schlüssel. Kein Abgleich mit Client-Texten."""
    from backend.core.field_definitions import SONSTIGES_ABGABE_LABEL, SONSTIGES_KATEGORIE_LABEL

    fehlend = [k for k in INVESTITION_FELDER["sonstiges"] if not SONSTIGES_KATEGORIE_LABEL.get(k)]
    assert not fehlend, f"Kategorie ohne Anzeigenamen in SONSTIGES_KATEGORIE_LABEL: {fehlend}"
    assert SONSTIGES_KATEGORIE_LABEL["abgabe"] == SONSTIGES_ABGABE_LABEL
