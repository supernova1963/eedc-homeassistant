"""#263/T1: die Geräte-Sammelspalten der Tagesansicht kennen beide Pfade.

**Der Befund** (gemeldet von OB73-gif, 2026-08-20): Er sah in der Monatsansicht
die Heizen/Kühlen-Aufteilung seiner Splitklima — und in der Tagesansicht *„nur
Wärmepumpe aufgeführt und die Werte sind leer"*.

**Die Ursache waren zwei Pfade für dieselbe Größe:**

* ``TagesEnergieProfil.waermepumpe_kw`` kommt aus dem **Zähler-Snapshot**
  (``snap_h["wp"]`` ← ``verbrauch_wp``) und setzt einen zugeordneten
  **kWh-Zählersensor** voraus.
* ``TagesEnergieProfil.komponenten['waermepumpe_<id>']`` kommt aus dem
  **Leistungspfad** — und **daraus** rechnet der Monats-Modus-Split.

Wer eine Wärmepumpe oder Klimaanlage **ohne kWh-Zähler, aber mit
Leistungssensor** betreibt (bei Split-Klimaanlagen der Normalfall), bekam
deshalb im Monat eine Aufteilung und im Tag eine leere Spalte — während der
Wert in der gerätebenannten Spalte danebenstand.

⚑ **Und die leere Zelle war nicht das Schlimmste:** ``berechneHausverbrauch``
zieht die Wärmepumpe über ``s.waermepumpe_kw ?? 0`` ab. Fehlte der Zähler,
wurde **nichts** abgezogen — der Hausverbrauch stand um den WP-Verbrauch zu
hoch. Er liest denselben Wert und heilt mit dieser Auflösung mit.

**Warum die Proben hier auf die ROUTE zeigen und nicht auf den Layer:** Die
Layer-Funktion allein wäre grün, ohne dass ein einziger Anwender etwas davon
sähe — genau der Fehler, an dem der `hvac_action`-Wächter gescheitert ist
(§6 des Konzepts: eine Probe auf eine Signatur, die kein Produktivpfad
benutzt).

Konzept: `docs/KONZEPT-263-INNENGERAETE.md` §7.
"""

from __future__ import annotations

from datetime import date

from backend.core.berechnungen import (
    WAERMEPUMPE_KOMPONENTEN_PREFIXE,
    WALLBOX_KOMPONENTEN_PREFIXE,
    geraete_spalte_kw,
)
from backend.models import Anlage, Investition  # noqa: F401  (Base.metadata)
from backend.models.tages_energie_profil import TagesEnergieProfil  # noqa: F401


async def _stunden(db, *, waermepumpe_kw, komponenten, wallbox_kw=None):
    """Legt eine Anlage mit einer Klimaanlage an und ruft die echte Route."""
    from backend.api.routes.energie_profil.views import get_stundenwerte

    anlage = Anlage(anlagenname="T1", leistung_kwp=10.0,
                    installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Splitklima",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=3000.0,
        parameter={"wp_art": "luft_luft"},
    )
    db.add(inv)
    await db.flush()

    for h in range(24):
        db.add(TagesEnergieProfil(
            anlage_id=anlage.id, datum=date(2025, 6, 15), stunde=h,
            waermepumpe_kw=waermepumpe_kw,
            wallbox_kw=wallbox_kw,
            komponenten=komponenten(inv.id) if callable(komponenten) else komponenten,
        ))
    await db.commit()

    antwort = await get_stundenwerte(
        anlage_id=anlage.id, datum=date(2025, 6, 15), db=db,
    )
    return antwort, inv.id


async def test_t1_ohne_zaehler_traegt_der_leistungspfad_die_spalte(db):
    """Der Melder-Fall: Leistungssensor ja, kWh-Zähler nein.

    **Der Sprengsatz:** Vor der Behebung stand hier 24-mal ``None``, obwohl der
    Wert in derselben Zeile unter ``komponenten`` lag.
    """
    antwort, inv_id = await _stunden(
        db, waermepumpe_kw=None,
        komponenten=lambda i: {f"waermepumpe_{i}": -0.5},
    )

    werte = [s.waermepumpe_kw for s in antwort.stunden]
    assert werte == [0.5] * 24, "Leistungspfad muss die Spalte tragen"

    # Und der Betrag ist Absicht: `komponenten` führt Senken negativ (N-261),
    # die Sammelspalte ist eine Menge. Ein −0,5 dort hieße „so viel wurde
    # NICHT verbraucht".
    assert all(v > 0 for v in werte)


async def test_t1_mit_zaehler_bleibt_der_zaehler_die_wahrheit(db):
    """Die Gegenprobe, ohne die der Fallback eine zweite Wahrheit wäre.

    Wo beide Pfade Werte tragen, gewinnt der Zähler — sie können abweichen
    (Achse-2-Drift, #356), und dann darf nicht die Anzeige entscheiden.
    """
    antwort, _ = await _stunden(
        db, waermepumpe_kw=1.5,
        komponenten=lambda i: {f"waermepumpe_{i}": -0.5},
    )
    assert [s.waermepumpe_kw for s in antwort.stunden] == [1.5] * 24


async def test_t1_ohne_beides_bleibt_es_leer_statt_null(db):
    """Kein Gerät, keine Spur ⇒ ``None`` — **keine erfundene Null**.

    Die F-42-Klasse: eine 0 behauptet „gemessen und nichts verbraucht", ein
    Strich sagt „keine Aussage". Hier gibt es keine Aussage.
    """
    antwort, _ = await _stunden(
        db, waermepumpe_kw=None, komponenten={"sonstige_99": -3.0},
    )
    assert all(s.waermepumpe_kw is None for s in antwort.stunden)


async def test_t1_gilt_auch_fuer_die_wallbox(db):
    """Dieselbe Lücke, dasselbe Gerät-Muster — Gernots Auflage „einheitlich"."""
    antwort, _ = await _stunden(
        db, waermepumpe_kw=None, wallbox_kw=None,
        komponenten={"wallbox_7": -2.0, "eauto_8": -1.0},
    )
    assert [s.wallbox_kw for s in antwort.stunden] == [3.0] * 24


async def test_t1_bilanzgroessen_bleiben_unberuehrt(db):
    """⛔ Die Abgrenzung ist Teil der Entscheidung, nicht ein Versehen.

    An ``pv_kw`` und ``verbrauch_kw`` hängen Performance-Ratio sowie
    Überschuss/Defizit. Ein Fallback dort änderte die **Bilanz**, nicht eine
    Anzeige — das wäre ein eigener Vorgang mit eigener Messung. Diese Probe
    hält die Grenze fest, damit sie nicht beiläufig verschoben wird.
    """
    antwort, _ = await _stunden(
        db, waermepumpe_kw=None,
        komponenten={"pv-module_3": 2.0, "waermepumpe_1": -0.5},
    )
    assert all(s.pv_kw is None for s in antwort.stunden)
    assert all(s.verbrauch_kw is None for s in antwort.stunden)


def test_t1_die_aufloesung_liegt_im_layer_und_nicht_in_der_route():
    """ADR-001: die Regel ist eine Formel, kein Routen-Detail.

    Ohne diese Probe könnte jemand die drei Zeilen in die Route zurückholen —
    und die nächste Fläche, die dieselbe Auflösung braucht, bekäme eine zweite
    Kopie (die N-138-Klasse).
    """
    assert geraete_spalte_kw(None, {"waermepumpe_4": -0.9},
                             WAERMEPUMPE_KOMPONENTEN_PREFIXE) == 0.9
    assert geraete_spalte_kw(2.0, {"waermepumpe_4": -0.9},
                             WAERMEPUMPE_KOMPONENTEN_PREFIXE) == 2.0
    assert geraete_spalte_kw(None, {"sonstige_1": -1.0},
                             WAERMEPUMPE_KOMPONENTEN_PREFIXE) is None
    # Ein VORHANDENER Key mit 0 ist eine echte Null und bleibt eine.
    assert geraete_spalte_kw(None, {"wallbox_2": 0.0},
                             WALLBOX_KOMPONENTEN_PREFIXE) == 0.0
