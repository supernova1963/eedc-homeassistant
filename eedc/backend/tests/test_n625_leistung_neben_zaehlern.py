"""N-625 — liefert die Zählertabelle die PV-Achse, steht keine Leistungs-Summe daneben.

**Der Fund.** Ohne HA-Stundenwerte summiert der Tageslauf die Leistungs-Serien der Kurve
als kWh in ``komponenten_kwh`` (``energie_profil/aggregator.py::summiere_live_komponenten``).
Die Zählertabelle überschrieb danach nur ihre eigenen Keys — die Gesamtleistung
``pv_gesamt`` neben ``pv_<id>``/``bkw_<id>`` blieb stehen, ebenso eine Einzel-Serie
``pv_<bkw>`` neben dem Zähler-Key ``bkw_<bkw>``. ``lade_monats_summen_aus_tagen`` zählt
jeden ``pv_``/``bkw_``-Key: laufender Monat 126 statt 63, Cockpit → Tag „PV-Anlage" 39
statt 18. Seit ``13aed23c`` (v3.26.8).

**Reichweite** (Bauplan PV-Achse T2): erreichbar, wo die Leistungs-Summe läuft (keine
HA-Stundenwerte) UND die Kurve eine PV-Serie trägt — ``live``-Zuordnung ohne HA-Stunden,
oder Leistung aus HA mit Zählern aus MQTT. Eine reine MQTT-Anlage ohne ``live``-Zuordnung
zählt nicht doppelt (Gegenprüfung über den echten Weg, 21 = 21).

**Die Regel.** Liefert die Zählertabelle einen PV-Key des Tages, stehen in
``komponenten_kwh`` nur IHRE PV-Keys. Die Stundenachse kommt nur aus Zählern
(Σ Stunden == Σ Keys); ohne PV-Key der Zählertabelle bleibt alles wie bisher.

**Datenstand:** Matrix-Bausteine, Standalone (Zählerstände in ``sensor_snapshots``, kein
HA), echter ``aggregate_day``; die Kurve wird vorgereicht wie in der Matrix.
"""

from __future__ import annotations

import shutil
import tempfile
from datetime import date

from sqlalchemy import select

from backend.core.berechnungen import summe_pv_bkw_kwh
from backend.models import Anlage
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.tests import pv_achse_matrix as mx

TAG = date(2026, 6, 10)


def _kurve(serien: dict[str, float]) -> dict:
    """Stunden-Leistungskurve (Vollbackfill-Form): ``{serien_key: kW in den Produktionsstunden}``."""
    def werte(h):
        return {k: (v if h in mx.PROD_STUNDEN else 0.0) for k, v in serien.items()}
    return {"serien": [{"key": k, "kategorie": "pv", "seite": "quelle", "bidirektional": False} for k in serien],
            "punkte": [{"zeit": f"{h:02d}:00", "werte": werte(h)} for h in range(24)],
            "vortagsrand": [{"zeit": "23:00", "werte": werte(23)}]}


async def _tag(form: mx.Form, serien_fn) -> tuple[dict, float, dict]:
    """→ (komponenten_kwh mit Namen statt IDs, Σ Stunden pv_kw, ids)."""
    from backend.services.energie_profil.aggregator import aggregate_day
    from backend.services.energie_profil.source import Source

    verz = tempfile.mkdtemp(prefix="eedc-n625-")
    try:
        engine, db = await mx._neue_db(f"{verz}/x.db")
        try:
            aid, ids = await mx.seed_anlage(db, form)
            await mx.seed_snapshots(db, form, aid, ids)
            anlage = (await db.execute(select(Anlage).where(Anlage.id == aid))).scalar_one()
            with mx._umgebung(mx._ha_aus()):
                await aggregate_day(anlage, TAG, db, source=Source.SCHEDULER,
                                    prefetched_tagesverlauf=_kurve(serien_fn(ids)))
                await db.commit()
            tz = (await db.execute(select(TagesZusammenfassung).where(
                TagesZusammenfassung.anlage_id == aid, TagesZusammenfassung.datum == TAG))).scalar_one()
            teps = (await db.execute(select(TagesEnergieProfil).where(
                TagesEnergieProfil.anlage_id == aid, TagesEnergieProfil.datum == TAG))).scalars().all()
            rev = {str(v): k for k, v in ids.items()}
            komp = {}
            for k, v in (tz.komponenten_kwh or {}).items():
                pre, _, i = str(k).rpartition("_")
                komp[f"{pre}_{rev[i]}" if i in rev else k] = round(v, 4) if isinstance(v, (int, float)) else v
            return komp, round(sum(r.pv_kw or 0.0 for r in teps), 4), ids
        finally:
            await db.close()
            await engine.dispose()
    finally:
        shutil.rmtree(verz, ignore_errors=True)


def _pv(komp: dict) -> dict:
    return {k: v for k, v in komp.items() if str(k).startswith(("pv_", "bkw_"))}


async def test_gesamtleistung_neben_allen_zaehlern_faellt_weg():
    """Gesamtleistung 3,5 kW + Anlagenzähler + alle drei Einzelzähler (F02): 21, nicht 42."""
    komp, stunden, _ = await _tag(mx.FORMEN["F02"], lambda ids: {"pv_gesamt": 3.5})
    assert "pv_gesamt" not in komp
    assert _pv(komp) == {"pv_Süd": 12.0, "pv_West": 6.0, "bkw_Balkon": 3.0}
    assert summe_pv_bkw_kwh(komp) == stunden == 21.0


async def test_bkw_leistungsserie_neben_bkw_zaehler_faellt_weg():
    """Einzel-Leistungsserien je Erzeuger, alle mit Zähler, ohne Anlagenzähler (F06): die
    Serie des Balkonkraftwerks heißt ``pv_<bkw>``, sein Zähler-Key ``bkw_<bkw>`` — 21, nicht 24."""
    komp, stunden, _ = await _tag(mx.FORMEN["F06"], lambda ids: {
        f"pv_{ids['Süd']}": 2.0, f"pv_{ids['West']}": 1.0, f"pv_{ids['Balkon']}": 0.5})
    assert "pv_Balkon" not in komp
    assert _pv(komp) == {"pv_Süd": 12.0, "pv_West": 6.0, "bkw_Balkon": 3.0}
    assert summe_pv_bkw_kwh(komp) == stunden == 21.0


async def test_teil_zaehler_stundenachse_und_keys_gleich():
    """Gesamtleistung, aber nur Süd und Balkon mit Zähler, kein Anlagenzähler (F07): die
    Stundenachse kennt nur die Zähler (15) — die Keys auch, nicht 36."""
    komp, stunden, _ = await _tag(mx.FORMEN["F07"], lambda ids: {"pv_gesamt": 3.5})
    assert _pv(komp) == {"pv_Süd": 12.0, "bkw_Balkon": 3.0}
    assert summe_pv_bkw_kwh(komp) == stunden == 15.0


async def test_reine_leistungs_anlage_unveraendert():
    """Keine PV-Zähler: die Leistungs-Summe ist die einzige PV-Angabe des Tages und bleibt."""
    form = mx.Form("L", "nur Leistung, keine PV-Zähler", (mx._sued(), mx._west(), mx._bkw()), None)
    komp, _stunden, _ = await _tag(form, lambda ids: {"pv_gesamt": 3.5})
    assert _pv(komp) == {"pv_gesamt": 21.0}
