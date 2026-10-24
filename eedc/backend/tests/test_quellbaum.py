"""Selbsttests der geteilten Dateiquelle `quellbaum.py`.

Die Quelle ist Unterbau für neun baumweite Prüfer. Läuft sie leer oder nimmt
sie Fremdcode auf, meldet **jeder** dieser Prüfer eine Wahrheit, die er nicht
gemessen hat. Deshalb prüft diese Datei die Quelle selbst — und zwar mit
Untergrenzen, nicht nur auf „ist eine Liste".
"""

from __future__ import annotations

import ast

from backend.tests import quellbaum as qb


def test_produktivbaum_enthaelt_keinen_fremdcode():
    """Kein `venv/`, kein `__pycache__/`, kein `tests/` im Produktivbaum.

    Das ist der Defekt, an dem `test_n252_speicher_wirkungsgrad_deckung.py`
    3491 Fremddateien mitgemessen hat (`"/venv/" in rel` greift bei einem
    **relativen** Pfad nie).
    """
    verstoesse = [
        d.rel
        for d in qb.produktivbaum()
        if d.rel.startswith(("venv/", "tests/")) or "__pycache__" in d.rel
    ]
    assert not verstoesse, f"Fremde Dateien im Produktivbaum: {verstoesse[:10]}"


def test_die_gegenprobe_haette_anschlagen_koennen(tmp_path, monkeypatch):
    """Der Filter tut etwas: gepflanzter Fremdcode wird gefunden UND ausgeschlossen.

    Ohne diese Zusicherung wäre der Test darüber wertlos — er würde auch dann
    grün melden, wenn es gar kein virtualenv gäbe und der Filter nichts tut.

    Bis 24.10.2026 zählte die Probe nur `.py` unter dem echten `backend/venv/`
    und skippte ohne es (beide CI-Runner installieren nach `site-packages`).
    Jetzt pflanzt sie einen eigenen Baum unter `tmp_path` — `venv/` und
    `__pycache__/` samt Produkt- und Testdatei — und fragt `_sammle` (die
    Filterfunktion hinter `produktivbaum()`/`probenbaum()`, ungecacht: der
    Cache der echten Bäume bleibt unberührt). Gibt es das echte `backend/venv/`
    (Dev-Box), läuft die alte Zählung zusätzlich.
    """
    echtes_venv = qb.BACKEND / "venv"
    if echtes_venv.is_dir():
        fremde = sum(1 for _ in echtes_venv.rglob("*.py"))
        assert fremde > 100, (
            f"Nur {fremde} .py unter backend/venv/ — die Gegenprobe misst nichts."
        )

    wurzel = tmp_path / "backend"
    for rel in (
        "main.py",
        "core/modul.py",
        "venv/lib/python3.11/site-packages/fremd/fremd.py",
        "core/__pycache__/modul.py",
        "tests/test_probe.py",
        "tests/venv/fremd_im_testbaum.py",
    ):
        datei = wurzel / rel
        datei.parent.mkdir(parents=True, exist_ok=True)
        datei.write_text("X = 1\n")
    monkeypatch.setattr(qb, "BACKEND", wurzel)

    # Gegenprobe: ohne Filter läge der Fremdcode in der Prüfmenge.
    alle = {p.relative_to(wurzel).as_posix() for p in wurzel.rglob("*.py")}
    assert "venv/lib/python3.11/site-packages/fremd/fremd.py" in alle
    assert "core/__pycache__/modul.py" in alle

    produktiv, kaputt_p = qb._sammle(tests=False)
    proben, kaputt_t = qb._sammle(tests=True)
    assert [d.rel for d in produktiv] == ["core/modul.py", "main.py"]
    assert [d.rel for d in proben] == ["tests/test_probe.py"]
    assert kaputt_p == () and kaputt_t == ()


def test_probenbaum_enthaelt_nur_tests():
    verstoesse = [d.rel for d in qb.probenbaum() if not d.rel.startswith("tests/")]
    assert not verstoesse, f"Nicht-Tests im Testbaum: {verstoesse[:10]}"


def test_beide_baeume_sind_disjunkt_und_nicht_leer():
    """Die Prüfmenge darf nicht leer laufen (die N-318-Klasse)."""
    p = {d.rel for d in qb.produktivbaum()}
    t = {d.rel for d in qb.probenbaum()}
    assert not (p & t), f"Datei in beiden Bäumen: {sorted(p & t)[:5]}"
    assert len(p) > 200, f"Produktivbaum nur {len(p)} Dateien — Filter zu scharf?"
    assert len(t) > 200, f"Testbaum nur {len(t)} Dateien — Filter zu scharf?"


def test_bekannte_dateien_sind_dabei():
    """Namentlich, damit ein zu scharfer Filter nicht nur an der Zahl auffällt."""
    p = {d.rel for d in qb.produktivbaum()}
    for erwartet in (
        "services/monats_fakten/__init__.py",   # seit Vorlage 10 (19.09.2026) ein Paket
        "core/investition_kennwerte.py",
        "api/routes/cockpit/uebersicht.py",
        "main.py",
    ):
        assert erwartet in p, f"{erwartet} fehlt im Produktivbaum"


def test_der_cache_parst_nicht_zweimal():
    """Zwei Aufrufe liefern **dieselben** Objekte, nicht nur gleiche.

    Das ist der ganze Zweck: 16 Aufrufe in
    `test_wurzelmuster_konformitaet.py` kosteten 27,36 s, mit dieser Quelle
    8,78 s. Ein Cache, der bei Gleichheit statt Identität stehen bliebe, würde
    weiterhin parsen.
    """
    a = qb.produktivbaum()
    b = qb.produktivbaum()
    assert a is b
    assert a[0].baum is b[0].baum


def test_jede_datei_traegt_quelle_und_baum():
    for d in qb.produktivbaum()[:20]:
        assert isinstance(d.baum, ast.Module)
        assert d.quelle, f"{d.rel} hat leeren Quelltext"
        assert d.rel == d.pfad.relative_to(qb.BACKEND).as_posix()


def test_kein_export_heisst_wie_eine_probe():
    """Kein öffentlicher Name aus `quellbaum` beginnt mit `test`.

    Sonst sammelt pytest ihn beim Importeur als Testfunktion ein. Genau das
    ist beim ersten Lauf passiert: `testbaum` erschien in
    `test_konformitaet_echte_uhr_in_tests.py` als eigener „Test", der nichts
    prüfte und trotzdem grün zählte.
    """
    verstoesse = [n for n in dir(qb) if not n.startswith("_") and n.startswith("test")]
    assert not verstoesse, (
        f"pytest sammelt diese Namen beim Importeur als Proben ein: {verstoesse}"
    )


def test_nichts_wird_still_uebersprungen():
    """Heute parst der ganze Baum. Kommt eine defekte Datei dazu, meldet die
    Quelle das — statt sie stillschweigend aus der Deckung fallen zu lassen."""
    assert qb.nicht_parsebar() == ()
