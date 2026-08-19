"""#263 K-2, S3+S4: den Modus-Strom summieren, ausweisen und die JAZ sperren.

Fortsetzung von `test_263_k2_betriebsmodus_lesen_mitschreiben.py` (S1+S2). Dort
entsteht die Stundenspur, hier wird sie zu Monatsgrößen und zu dem, was der
Anwender sieht.

⚠ **Ehrlich zur Belegbarkeit — unverändert seit S1:** Es gibt **kein Testgerät
im Zugriff.** Alles hier ist gegen Fixtures und eine echte SQLite-Instanz
abgenommen, nicht gegen echte MELCloud-Daten.

---

**Die vier Wächter, auf die es ankommt:**

1. `test_feldnamen_folgen_dem_kanon` — die drei Feldnamen sind an
   `AUFGETEILTE_MODI` gebunden. Eine siebte Betriebsart kostet damit **einen
   Eintrag im Kanon**, und dieser Test sagt sofort, was dazu fehlt. Ohne ihn
   wäre „eine spätere Betriebsart kostet ein Feld, keine Migration“
   (Konzept §3.1, Folge 4) eine Behauptung.
2. `test_teilmengen_werden_nirgends_addiert` — baumweit: keine Bilanz-Read-Site
   summiert Heiz- und Kühlstrom zum Gesamtverbrauch dazu (Konzept §9).
3. `test_keine_jaz_stelle_rechnet_mit_abgeleiteter_waerme` — die sieben Stellen
   aus §3.5, funktions-granular.
4. `test_gemessen_schlaegt_abgeleitet` — die Quellen-Hierarchie, nicht eine
   Sonderregel, schützt eine gemessene Heizwärme.

Konzept: `docs/KONZEPT-263-klima-split.md` §3.1 · §3.2 · §3.4 · §3.5 · §4.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest

from backend.core.berechnungen import (
    ModusStunde,
    abgeleitete_heizwaerme_kwh,
    falte_modus_split_tag,
    heiz_effizienz_gepflegt,
    heizwaerme_ist_abgeleitet,
    summiere_modus_split,
    teilmengen_passen,
    unbekannte_modi,
    waermepumpe_kwh_je_investition,
)
from backend.core.betriebsmodus import (
    AUFGETEILTE_MODI,
    AUS,
    HEIZEN,
    KUEHLEN,
    LUEFTEN,
    MODUS_ABDECKUNG_FELD,
    MODUS_SPLIT_FELDER,
    MODUS_STROM_FELD,
    UNBESTIMMT,
)

BACKEND = Path(__file__).resolve().parents[1]


# ============================================================================
# Wächter 1 — die Feldnamen folgen dem Kanon (Schärfung ①)
# ============================================================================

def test_feldnamen_folgen_dem_kanon():
    """Für jeden aufgeteilten Modus genau ein Feld, und der Name ist gebunden.

    **Das ist der Wächter, der die Zukunftsaussage trägt.** Wer eine siebte
    Betriebsart in `AUFGETEILTE_MODI` aufnimmt, bekommt hier sofort gesagt,
    dass ihr Feld fehlt — statt dass die Aufteilung sie still verschluckt.
    """
    assert set(MODUS_STROM_FELD) == set(AUFGETEILTE_MODI), (
        "Jeder Modus in AUFGETEILTE_MODI braucht genau ein Strom-Feld und "
        "umgekehrt — sonst fällt eine Betriebsart still in „nicht aufgeteilt“."
    )
    for modus, feld in MODUS_STROM_FELD.items():
        assert feld == f"modus_strom_{modus}_kwh", (
            f"Feldname {feld!r} folgt nicht der Konvention "
            f"`modus_strom_<modus>_kwh` für {modus!r}."
        )
    assert set(MODUS_SPLIT_FELDER) == set(MODUS_STROM_FELD.values()) | {
        MODUS_ABDECKUNG_FELD
    }


def test_die_feldnamen_kollidieren_nicht_mit_der_getrennten_strommessung():
    """E-G: `strom_heizen_kwh` behält **eine** Bedeutung.

    Der Grund für eigene Namen: drei Stellen schließen aus der Anwesenheit von
    `strom_heizen_kwh` auf die getrennte Strommessung (zwei physische Zähler).
    Trüge der Modus-Split denselben Namen, kippten sie mit — und die
    Klimaanlage bekäme ein `cop_heizen` aus abgeleiteter Wärme.
    """
    assert "strom_heizen_kwh" not in MODUS_SPLIT_FELDER
    assert "strom_warmwasser_kwh" not in MODUS_SPLIT_FELDER


# ============================================================================
# Die Faltung — Vorzeichen, Verweildauer, Normierung
# ============================================================================

def test_der_leistungspfad_ist_negativ_und_wird_als_betrag_gezaehlt():
    """Die Vorzeichen-Falle: `komponenten` führt die WP negativ, `komponenten_kwh` positiv.

    `live_tagesverlauf_service` schreibt für alles mit `seite: "senke"` ein
    `-abs(...)`. Wer das durchreicht, bekommt eine negative Aufteilung.
    """
    split = falte_modus_split_tag([
        ModusStunde(kwh=-1.5, modus=HEIZEN),
        ModusStunde(kwh=-2.5, modus=KUEHLEN),
    ])
    assert split.teilmenge_kwh(HEIZEN) == pytest.approx(1.5)
    assert split.teilmenge_kwh(KUEHLEN) == pytest.approx(2.5)
    assert split.aufgeteilt_kwh == pytest.approx(4.0)


def test_das_volle_kanon_dict_kommt_zurueck_nicht_nur_zwei_skalare():
    """Schärfung ②: K-1 (SEER) ist damit ein Lesevorgang, kein Umbau."""
    split = falte_modus_split_tag([
        ModusStunde(kwh=-1.0, modus=HEIZEN),
        ModusStunde(kwh=-2.0, modus=LUEFTEN),
        ModusStunde(kwh=-0.1, modus=AUS),
        ModusStunde(kwh=-0.4, modus=UNBESTIMMT),
    ])
    assert split.kwh_je_modus[LUEFTEN] == pytest.approx(2.0)
    assert split.kwh_je_modus[AUS] == pytest.approx(0.1)
    assert split.kwh_je_modus[UNBESTIMMT] == pytest.approx(0.4)
    # Aber nur Heizen/Kühlen gelten als „aufgeteilt“.
    assert split.aufgeteilt_kwh == pytest.approx(1.0)
    assert split.erfasst_kwh == pytest.approx(3.5)
    assert unbekannte_modi(split) == set()


def test_ohne_signal_zaehlt_die_stunde_nicht_zur_abdeckung():
    """`None` heißt „nicht hingesehen“ — und ist nicht `unbestimmt`.

    Der Unterschied ist der ganze Zweck von `modus_abdeckung_h`: er trennt
    „das Gerät lief in einer anderen Betriebsart“ von „eedc hat nicht
    gemessen“ (Konzept §3.3).
    """
    split = falte_modus_split_tag([
        ModusStunde(kwh=-1.0, modus=HEIZEN),
        ModusStunde(kwh=-3.0, modus=None),
        ModusStunde(kwh=-0.5, modus=UNBESTIMMT),
    ])
    assert split.abdeckung_h == 2.0          # heizen + unbestimmt
    assert split.aufgeteilt_kwh == pytest.approx(1.0)


def test_eine_stunde_ohne_menge_zaehlt_trotzdem_zur_abdeckung():
    """Das Gerät stand — auch das ist eine Messung, keine Lücke."""
    split = falte_modus_split_tag([ModusStunde(kwh=0.0, modus=AUS)])
    assert split.abdeckung_h == 1.0
    assert split.ist_leer is False


def test_die_normierung_zieht_auf_die_zaehlersumme():
    """E-H: Form vom Leistungspfad, Menge vom Zählerpfad (Präzedenz v3.45.5)."""
    stunden = [ModusStunde(kwh=-1.0, modus=HEIZEN), ModusStunde(kwh=-3.0, modus=KUEHLEN)]
    roh = falte_modus_split_tag(stunden)
    assert roh.aufgeteilt_kwh == pytest.approx(4.0)

    normiert = falte_modus_split_tag(stunden, tages_kwh=8.0)
    assert normiert.aufgeteilt_kwh == pytest.approx(8.0)
    # Das VERHÄLTNIS bleibt — normiert wird das Niveau, nicht die Aufteilung.
    assert normiert.teilmenge_kwh(HEIZEN) == pytest.approx(2.0)
    assert normiert.teilmenge_kwh(KUEHLEN) == pytest.approx(6.0)


def test_ohne_zaehlersumme_gilt_die_rohsumme():
    """Die Normierung ist **opportunistisch** — an der Demo-Box gemessen ist
    `komponenten_kwh` über alle Tageszeilen NULL. Fehlt sie, darf nichts
    schiefgehen; die Invariante fängt den Rest."""
    split = falte_modus_split_tag(
        [ModusStunde(kwh=-2.0, modus=HEIZEN)], tages_kwh=None
    )
    assert split.teilmenge_kwh(HEIZEN) == pytest.approx(2.0)


def test_unbeobachtete_stunden_werden_nicht_hochgerechnet():
    """Konzept §4: Der Rest ist „nicht aufgeteilt“, keine Extrapolation.

    Drei Stunden, nur eine mit Signal. Die Aufteilung darf **nicht** so tun,
    als gälte das Verhältnis für den ganzen Tag.
    """
    split = falte_modus_split_tag(
        [
            ModusStunde(kwh=-1.0, modus=HEIZEN),
            ModusStunde(kwh=-1.0, modus=None),
            ModusStunde(kwh=-1.0, modus=None),
        ],
        tages_kwh=3.0,
    )
    assert split.teilmenge_kwh(HEIZEN) == pytest.approx(1.0)
    # 2 kWh bleiben unzugeordnet — sie erscheinen als „nicht aufgeteilt“.
    assert 3.0 - split.aufgeteilt_kwh == pytest.approx(2.0)


def test_die_normierung_ist_tagesweise_nicht_monatsweise():
    """Ein Tag ohne Zählerspur darf nicht mit dem Faktor eines anderen skaliert werden."""
    mit_zaehler = falte_modus_split_tag(
        [ModusStunde(kwh=-1.0, modus=HEIZEN)], tages_kwh=10.0
    )
    ohne_zaehler = falte_modus_split_tag([ModusStunde(kwh=-1.0, modus=HEIZEN)])
    monat = summiere_modus_split([mit_zaehler, ohne_zaehler])
    assert monat.teilmenge_kwh(HEIZEN) == pytest.approx(11.0)
    assert monat.abdeckung_h == 2.0


# ============================================================================
# Die Invariante — der eigentliche Schutz
# ============================================================================

def test_teilmengen_passen_erkennt_den_widerspruch():
    split = falte_modus_split_tag([
        ModusStunde(kwh=-6.0, modus=HEIZEN), ModusStunde(kwh=-6.0, modus=KUEHLEN),
    ])
    assert teilmengen_passen(split, 12.0) is True
    assert teilmengen_passen(split, 12.4) is True      # Rundungstoleranz
    assert teilmengen_passen(split, 10.0) is False     # Achse-2-Drift / Handpflege
    assert teilmengen_passen(split, None) is False     # kein Bezug ⇒ keine Teilmenge


# ============================================================================
# Die abgeleitete Wärme — nie aus einem Default
# ============================================================================

@pytest.mark.parametrize(("parameter", "erwartet"), [
    ({"effizienz_modus": "gesamt_jaz", "jaz": 3.5}, 3.5),
    ({"effizienz_modus": "scop", "scop_heizung": 4.5}, 4.5),
    ({"effizienz_modus": "getrennte_cops", "cop_heizung": 3.9}, 3.9),
    ({"jaz": 3.0}, 3.0),                       # Default-Modus ist gesamt_jaz
    ({}, None),                                # NICHTS gepflegt ⇒ keine Aussage
    ({"effizienz_modus": "gesamt_jaz"}, None),
    ({"effizienz_modus": "scop", "scop_heizung": 0}, None),   # 0 ist ungepflegt
    (None, None),
])
def test_die_heiz_effizienz_kommt_nur_aus_gepflegten_werten(parameter, erwartet):
    """Konzept §3.4: **nie aus einem Default.**

    `PARAM_WAERMEPUMPE_DEFAULTS` trägt `jaz: 3.5`. Wer die Defaults anwendet,
    erfindet für jede ungepflegte Wärmepumpe eine Wärmemenge — und damit eine
    Ersparnis, eine CO₂-Zahl und einen Kostenvergleich (die N-258-Klasse).
    """
    assert heiz_effizienz_gepflegt(parameter) == erwartet


def test_ohne_gepflegte_effizienz_gibt_es_keine_waerme_statt_einer_null():
    assert abgeleitete_heizwaerme_kwh(100.0, {}) is None
    assert abgeleitete_heizwaerme_kwh(100.0, {"jaz": 3.5}) == pytest.approx(350.0)
    assert abgeleitete_heizwaerme_kwh(None, {"jaz": 3.5}) is None


def test_der_defaultwert_wird_wirklich_nicht_gezogen():
    """Gegenprobe zum Satz oben — der Default existiert und ist 3,5."""
    from backend.core.investition_parameter import PARAM_WAERMEPUMPE_DEFAULTS

    assert PARAM_WAERMEPUMPE_DEFAULTS["jaz"] == 3.5
    assert heiz_effizienz_gepflegt({}) is None


# ============================================================================
# Die Key-Auflösung — die ID ist kein Präfix
# ============================================================================

def test_die_investitions_id_wird_exakt_getrennt():
    """`waermepumpe_1` und `waermepumpe_12` sind verschiedene Geräte."""
    je_inv = waermepumpe_kwh_je_investition({
        "waermepumpe_1": -2.0,
        "waermepumpe_12": -5.0,
        "waermepumpe_1_heizen": -1.0,     # Suffix-Key derselben Investition
        "waermepumpe_1_warmwasser": -0.5,
        "waermepumpe_gesamt": -99.0,      # keine ID ⇒ fällt heraus
        "pv_3": 4.0,
    })
    assert je_inv == {"1": pytest.approx(3.5), "12": pytest.approx(5.0)}


def test_beide_vorzeichen_welten_ergeben_betraege():
    """Leistungspfad negativ, Zählerpfad positiv — hier kommt beides als Betrag an."""
    assert waermepumpe_kwh_je_investition({"waermepumpe_7": -4.0}) == {"7": 4.0}
    assert waermepumpe_kwh_je_investition({"waermepumpe_7": 4.0}) == {"7": 4.0}


# ============================================================================
# Wächter 2 — die Teilmengen werden nirgends addiert (Konzept §9)
# ============================================================================

def test_teilmengen_werden_nirgends_addiert():
    """Baumweit: keine Stelle addiert eine Teilmenge zu einer Gesamtstrom-Größe.

    Die Teilmengen sind Ausweis, nie Summand (Konzept §3.1). Der Fehler, gegen
    den das gebaut ist, ist real und dokumentiert: bei der Wallbox ergab
    `ladung_kwh + ladung_pv_kwh` einmal 23,24 statt 14
    (`komponenten_beitraege.py`).

    ⚑ **Dieser Wächter war beim ersten Bau STUMM, und die Probe hat es gezeigt.**
    Sprengsatz F setzte `wp.strom_kwh + wp.modus_strom_heizen_kwh` in die
    Cockpit-Antwort — der Test blieb grün, weil er nur Additionen **zweier
    benannter Modus-Felder** suchte. Die reale Gefahr ist aber genau die andere:
    Teilmenge **plus Gesamtgröße**. Er sucht deshalb jetzt nach der Kombination
    aus einem Modus-Feld und einem Gesamtstrom-Bezeichner in derselben Addition.
    """
    felder = list(MODUS_STROM_FELD.values())
    #: Bezeichner, hinter denen der **Gesamt**strom steckt. Ein Modus-Feld in
    #: derselben Addition wie einer von ihnen ist immer eine Doppelzählung.
    gesamt_namen = [
        "stromverbrauch_kwh", "strom_kwh", "wp_strom", "gesamt_strom",
    ]
    #: Wo eine Addition legitim ist — mit Begründung, nicht als Freibrief.
    erlaubt = {
        # Die Faltung selbst: Σ über Stunden und Tage. Das IST die Bildung der
        # Teilmenge, nicht ihre Vermischung mit dem Gesamtwert.
        "core/berechnungen/modus_split.py",
        # Der Schreiber und der Checker summieren die zwei Teilmengen
        # ausdrücklich, um sie GEGEN den Gesamtwert zu prüfen (E-H-Invariante).
        "services/energie_profil/modus_split_schreiben.py",
        "services/daten_checker/monatsdaten.py",
        # Der P10-Akkumulator addiert Monatswerte derselben Größe über Geräte.
        "services/monats_fakten.py",
        # Der per-Zeilen-Resolver liest sie nur (`_f(...)`).
        "core/berechnungen/imd_monatsaggregat.py",
    }
    treffer: list[str] = []
    for pfad in BACKEND.rglob("*.py"):
        rel = str(pfad.relative_to(BACKEND))
        if "tests/" in rel or pfad.name.startswith("test_") or rel in erlaubt:
            continue
        text = pfad.read_text(encoding="utf-8")
        if not any(f in text for f in felder):
            continue
        for nr, zeile in enumerate(text.splitlines(), 1):
            nackt = zeile.lstrip()
            if nackt.startswith("#") or nackt.startswith("*"):
                continue
            if "+" not in zeile:
                continue
            if not any(f in zeile for f in felder):
                continue
            # Ein Modus-Feld UND eine Gesamtgröße in derselben Addition.
            if any(g in zeile for g in gesamt_namen):
                treffer.append(f"{rel}:{nr}: {zeile.strip()}")
    assert treffer == [], (
        "Der Modus-Split ist eine TEILMENGE des Gesamtstroms und darf nie zu "
        "ihm addiert werden (Konzept §3.1 — die Wallbox-Doppelzählung):\n"
        + "\n".join(treffer)
    )


# ============================================================================
# Wächter 3 — keine JAZ/COP-Stelle rechnet mit abgeleiteter Wärme (§3.5)
# ============================================================================

#: Die sieben Stellen aus Konzept §3.5, die Wärme durch Strom **teilen**.
#: Jede muss die Herkunft auswerten — über `WpFakten.jaz_belastbar`,
#: `waerme_abgeleitet_kwh` oder direkt `heizwaerme_ist_abgeleitet`.
JAZ_STELLEN: tuple[tuple[str, str], ...] = (
    ("backend/api/routes/cockpit/uebersicht.py", "wp_waerme_abgeleitet"),
    ("backend/api/routes/cockpit/komponenten.py", "jaz_belastbar"),
    ("backend/api/routes/investitionen/dashboards.py", "waerme_abgeleitet"),
    ("backend/services/pdf/builders/jahresbericht.py", "wp_waerme_abgeleitet"),
    ("backend/api/routes/ha_export.py", "waerme_abgeleitet"),
)


@pytest.mark.parametrize(("datei", "marker"), JAZ_STELLEN)
def test_keine_jaz_stelle_rechnet_mit_abgeleiteter_waerme(datei, marker):
    """Konzept §3.5 — die eine Regel, die aus der Ableitung folgt.

    Sie trennt **teilen** von **multiplizieren**: Gaskosten, CO₂ und
    Alternativkosten dürfen die abgeleitete Wärme benutzen (mit Kennzeichnung),
    JAZ und COP nicht — dort käme exakt die gepflegte JAZ heraus, eine Zahl,
    die nichts misst und trotzdem wie eine Messung aussieht.
    """
    text = (BACKEND.parent / datei).read_text(encoding="utf-8")
    assert marker in text, (
        f"{datei} teilt Wärme durch Strom, wertet die Herkunft aber nicht aus. "
        f"Erwartet: {marker!r}. Ohne die Sperre zeigt eine Klimaanlage mit "
        f"gepflegter JAZ genau diese JAZ als „gemessen“ an (Konzept §3.5)."
    )


def test_die_jaz_sperre_haengt_am_wert_nicht_an_der_bauart():
    """Eine Luft-Wasser-WP ohne Wärmemengenzähler fällt unter dieselbe Regel.

    Das ist die K-0c-Linie: die Bewertbarkeit hängt an der **Pflege**, nicht an
    der Bauart. `heizwaerme_ist_abgeleitet` kennt `wp_art` deshalb gar nicht.
    """
    import inspect

    from backend.core.berechnungen import modus_split

    quelle = inspect.getsource(modus_split.heizwaerme_ist_abgeleitet)
    assert "wp_art" not in quelle and "luft_luft" not in quelle


def test_wpfakten_sperrt_die_jaz_sobald_ein_teil_abgeleitet_ist():
    from backend.services.monats_fakten import WpFakten

    gemessen = WpFakten(strom_kwh=100.0, waerme_kwh=350.0)
    assert gemessen.jaz_belastbar is True

    abgeleitet = WpFakten(strom_kwh=100.0, waerme_kwh=350.0, waerme_abgeleitet_kwh=350.0)
    assert abgeleitet.jaz_belastbar is False


def test_die_marke_wird_aus_der_provenance_gelesen():
    assert heizwaerme_ist_abgeleitet(
        {"verbrauch_daten.heizenergie_kwh": {"abgeleitet": "jaz_modus_split"}}
    ) is True
    assert heizwaerme_ist_abgeleitet(
        {"verbrauch_daten.heizenergie_kwh": {"abgeleitet": "kwp_anteil"}}
    ) is False
    assert heizwaerme_ist_abgeleitet({"verbrauch_daten.heizenergie_kwh": {}}) is False
    assert heizwaerme_ist_abgeleitet(None) is False


def test_die_regel_kennung_ist_importiert_statt_abgeschrieben():
    """Eine Umbenennung darf keine zwei Wahrheiten hinterlassen (Muster: P7/N-141)."""
    from backend.core.berechnungen.modus_split import REGEL_JAZ_MODUS_SPLIT
    from backend.services.provenance import ABGELEITET_JAZ_MODUS

    assert ABGELEITET_JAZ_MODUS is REGEL_JAZ_MODUS_SPLIT
    quelle = (BACKEND / "services" / "provenance.py").read_text(encoding="utf-8")
    assert "ABGELEITET_JAZ_MODUS = REGEL_JAZ_MODUS_SPLIT" in quelle


# ============================================================================
# Nicht-aufgeteilt und die Anzeige-Regeln
# ============================================================================

def test_nicht_aufgeteilt_wird_gerechnet_und_nie_gespeichert():
    """Konzept §3.1, Folge 2 — damit ist es immer vollständig."""
    from backend.services.monats_fakten import WpFakten

    wp = WpFakten(
        strom_kwh=1240.0,
        modus_strom_bezug_kwh=1240.0,   # ein Gerät, alles mit Split
        modus_strom_heizen_kwh=520.0,
        modus_strom_kuehlen_kwh=680.0,
        modus_abdeckung_h=700.0,
    )
    assert wp.modus_nicht_aufgeteilt_kwh == pytest.approx(40.0)
    assert wp.hat_modus_split is True
    # Der Rest ist kein gespeichertes Feld.
    assert "nicht_aufgeteilt" not in " ".join(MODUS_SPLIT_FELDER)


def test_nicht_aufgeteilt_wird_nie_negativ():
    from backend.services.monats_fakten import WpFakten

    wp = WpFakten(
        strom_kwh=10.0, modus_strom_bezug_kwh=10.0,
        modus_strom_heizen_kwh=8.0, modus_strom_kuehlen_kwh=5.0,
    )
    assert wp.modus_nicht_aufgeteilt_kwh == 0.0


def test_ohne_abdeckung_gibt_es_keine_aufteilung_statt_einer_null():
    """ADR-002/P4 — eine 0 hieße „hat nicht geheizt“. Das weiß eedc nicht."""
    from backend.services.monats_fakten import WpFakten

    assert WpFakten(strom_kwh=1000.0).hat_modus_split is False


# ============================================================================
# Lader und Schreibpfad gegen eine echte DB
# ============================================================================

async def _anlage_mit_klima(db, *, parameter: dict | None = None):
    """Anlage + eine Split-Klimaanlage. Gibt (anlage, investition) zurück."""
    from backend.models import Anlage, Investition

    anlage = Anlage(anlagenname="K2-S3", leistung_kwp=10.0,
                    installationsdatum=date(2025, 1, 1))
    db.add(anlage)
    await db.flush()
    inv = Investition(
        anlage_id=anlage.id, typ="waermepumpe", bezeichnung="Klima Wohnzimmer",
        anschaffungsdatum=date(2025, 1, 1), anschaffungskosten_gesamt=6000.0,
        parameter={"wp_art": "luft_luft", **(parameter or {})},
    )
    db.add(inv)
    await db.flush()
    await db.commit()
    return anlage, inv


async def _stunden_schreiben(db, anlage_id, inv_id, tag: date, muster, *, tages_kwh=None):
    """Schreibt Stundenzeilen (Modus + Menge) und optional die Tages-Zählersumme."""
    from backend.models.tages_energie_profil import (
        TagesEnergieProfil, TagesZusammenfassung,
    )

    for stunde, (modus, kwh) in enumerate(muster):
        db.add(TagesEnergieProfil(
            anlage_id=anlage_id, datum=tag, stunde=stunde,
            # ⚠ negativ — der Leistungspfad führt Verbraucher als Senke.
            komponenten={f"waermepumpe_{inv_id}": -kwh} if kwh is not None else None,
            betriebsmodus_je_wp={str(inv_id): modus} if modus else None,
        ))
    if tages_kwh is not None:
        db.add(TagesZusammenfassung(
            anlage_id=anlage_id, datum=tag,
            komponenten_kwh={f"waermepumpe_{inv_id}": tages_kwh},
        ))
    await db.commit()


async def _imd(db, inv_id, jahr, monat, daten: dict):
    from backend.models.investition import InvestitionMonatsdaten

    imd = InvestitionMonatsdaten(
        investition_id=inv_id, jahr=jahr, monat=monat,
        verbrauch_daten=dict(daten), source_provenance={},
    )
    db.add(imd)
    await db.commit()
    return imd


async def test_lader_faltet_die_stundenzeilen_je_monat(db):
    from backend.services.energie_profil import lade_modus_split_monat

    anlage, inv = await _anlage_mit_klima(db)
    await _stunden_schreiben(db, anlage.id, inv.id, date(2025, 6, 10), [
        (HEIZEN, 1.0), (HEIZEN, 1.0), (KUEHLEN, 2.0), (None, 5.0),
    ])
    splits = await lade_modus_split_monat(db, anlage.id, 2025, 6)
    split = splits[str(inv.id)]
    assert split.teilmenge_kwh(HEIZEN) == pytest.approx(2.0)
    assert split.teilmenge_kwh(KUEHLEN) == pytest.approx(2.0)
    assert split.abdeckung_h == 3.0


async def test_lader_normiert_auf_die_tages_zaehlersumme(db):
    """Der Zählerpfad kennt die Menge, der Leistungspfad die Form (E-H)."""
    from backend.services.energie_profil import lade_modus_split_monat

    anlage, inv = await _anlage_mit_klima(db)
    await _stunden_schreiben(
        db, anlage.id, inv.id, date(2025, 6, 10),
        [(HEIZEN, 1.0), (KUEHLEN, 3.0)],
        tages_kwh=8.0,      # Zähler sagt doppelt so viel wie die Leistungs-Σ
    )
    split = (await lade_modus_split_monat(db, anlage.id, 2025, 6))[str(inv.id)]
    assert split.aufgeteilt_kwh == pytest.approx(8.0)
    assert split.teilmenge_kwh(HEIZEN) == pytest.approx(2.0)


async def test_lader_meldet_geraete_ohne_signal_gar_nicht(db):
    """P4: Abwesenheit heißt „keine Aussage“, nicht „null“."""
    from backend.services.energie_profil import lade_modus_split_monat

    anlage, inv = await _anlage_mit_klima(db)
    await _stunden_schreiben(db, anlage.id, inv.id, date(2025, 6, 10),
                             [(None, 2.0), (None, 3.0)])
    assert await lade_modus_split_monat(db, anlage.id, 2025, 6) == {}


async def test_schreiber_legt_die_drei_felder_an(db):
    from backend.services.energie_profil.modus_split_schreiben import (
        schreibe_modus_split_monat,
    )

    anlage, inv = await _anlage_mit_klima(db)
    await _stunden_schreiben(db, anlage.id, inv.id, date(2025, 6, 10), [
        (HEIZEN, 2.0), (KUEHLEN, 3.0), (AUS, 0.1),
    ])
    imd = await _imd(db, inv.id, 2025, 6, {"stromverbrauch_kwh": 10.0})

    ergebnis = await schreibe_modus_split_monat(db, anlage.id, 2025, 6)
    await db.commit()
    await db.refresh(imd)

    assert ergebnis.geschrieben == 1
    assert imd.verbrauch_daten[MODUS_STROM_FELD[HEIZEN]] == pytest.approx(2.0)
    assert imd.verbrauch_daten[MODUS_STROM_FELD[KUEHLEN]] == pytest.approx(3.0)
    assert imd.verbrauch_daten[MODUS_ABDECKUNG_FELD] == pytest.approx(3.0)
    # Der Gesamtwert bleibt unangetastet — er ist die einzige Bilanzgröße.
    assert imd.verbrauch_daten["stromverbrauch_kwh"] == 10.0


async def test_schreiber_ruehrt_strom_heizen_kwh_nicht_an(db):
    """N-281: das Feld der getrennten Strommessung bleibt unberührt (E-G)."""
    from backend.services.energie_profil.modus_split_schreiben import (
        schreibe_modus_split_monat,
    )

    anlage, inv = await _anlage_mit_klima(db, parameter={"getrennte_strommessung": True})
    await _stunden_schreiben(db, anlage.id, inv.id, date(2025, 6, 10),
                             [(HEIZEN, 2.0), (KUEHLEN, 1.0)])
    imd = await _imd(db, inv.id, 2025, 6, {
        "strom_heizen_kwh": 7.0, "strom_warmwasser_kwh": 3.0,
    })
    await schreibe_modus_split_monat(db, anlage.id, 2025, 6)
    await db.commit()
    await db.refresh(imd)

    assert imd.verbrauch_daten["strom_heizen_kwh"] == 7.0
    assert imd.verbrauch_daten["strom_warmwasser_kwh"] == 3.0
    assert imd.verbrauch_daten[MODUS_STROM_FELD[HEIZEN]] == pytest.approx(2.0)


async def test_schreiber_verwirft_den_widerspruch_statt_zu_kappen(db):
    """E-H: Σ Teilmengen > Gesamt ⇒ gar nichts schreiben, und Altes wegräumen."""
    from backend.services.energie_profil.modus_split_schreiben import (
        schreibe_modus_split_monat,
    )

    anlage, inv = await _anlage_mit_klima(db)
    await _stunden_schreiben(db, anlage.id, inv.id, date(2025, 6, 10),
                             [(HEIZEN, 6.0), (KUEHLEN, 6.0)])
    # Ein zu kleiner Gesamtwert (von Hand gepflegt) plus ein alter Split.
    imd = await _imd(db, inv.id, 2025, 6, {
        "stromverbrauch_kwh": 5.0,
        MODUS_STROM_FELD[HEIZEN]: 3.0,
        MODUS_ABDECKUNG_FELD: 2.0,
    })
    ergebnis = await schreibe_modus_split_monat(db, anlage.id, 2025, 6)
    await db.commit()
    await db.refresh(imd)

    assert ergebnis.geschrieben == 0
    assert ergebnis.widerspruch == [inv.id]
    # Kein gekappter Wert und auch kein Rest von früher.
    for feld in MODUS_SPLIT_FELDER:
        assert feld not in imd.verbrauch_daten
    assert imd.verbrauch_daten["stromverbrauch_kwh"] == 5.0


async def test_die_waerme_wird_nur_mit_gepflegter_jaz_abgeleitet(db):
    from backend.services.energie_profil.modus_split_schreiben import (
        schreibe_modus_split_monat,
    )

    anlage, inv = await _anlage_mit_klima(db, parameter={"jaz": 3.5})
    await _stunden_schreiben(db, anlage.id, inv.id, date(2025, 6, 10),
                             [(HEIZEN, 10.0)])
    imd = await _imd(db, inv.id, 2025, 6, {"stromverbrauch_kwh": 20.0})

    ergebnis = await schreibe_modus_split_monat(db, anlage.id, 2025, 6)
    await db.commit()
    await db.refresh(imd)

    assert ergebnis.waerme_abgeleitet == 1
    assert imd.verbrauch_daten["heizenergie_kwh"] == pytest.approx(35.0)
    assert heizwaerme_ist_abgeleitet(imd.source_provenance) is True


async def test_ohne_jaz_entsteht_keine_waerme_statt_einer_null(db):
    from backend.services.energie_profil.modus_split_schreiben import (
        schreibe_modus_split_monat,
    )

    anlage, inv = await _anlage_mit_klima(db)          # keine JAZ gepflegt
    await _stunden_schreiben(db, anlage.id, inv.id, date(2025, 6, 10),
                             [(HEIZEN, 10.0)])
    imd = await _imd(db, inv.id, 2025, 6, {"stromverbrauch_kwh": 20.0})
    await schreibe_modus_split_monat(db, anlage.id, 2025, 6)
    await db.commit()
    await db.refresh(imd)

    assert "heizenergie_kwh" not in imd.verbrauch_daten


async def test_gemessen_schlaegt_abgeleitet(db):
    """Wächter 4 — und zwar **durch die Quellen-Hierarchie**, nicht durch ein `if`.

    `auto:monatsabschluss` ist AUTO_AGGREGATION (3), eine Handeingabe ist
    MANUAL (1). Der Provenance-Helfer weist den abgeleiteten Wert deshalb ab —
    im Schreibpfad steht dafür bewusst keine Sonderregel (Konzept §3.4,
    Präzedenz ADR-002/P7 bei der PV).
    """
    from backend.services.energie_profil.modus_split_schreiben import (
        schreibe_modus_split_monat,
    )
    from backend.services.provenance import write_json_subkey_with_provenance

    anlage, inv = await _anlage_mit_klima(db, parameter={"jaz": 3.5})
    await _stunden_schreiben(db, anlage.id, inv.id, date(2025, 6, 10),
                             [(HEIZEN, 10.0)])
    imd = await _imd(db, inv.id, 2025, 6, {"stromverbrauch_kwh": 20.0})
    # Ein Wärmemengenzähler-Wert, von Hand gepflegt.
    await write_json_subkey_with_provenance(
        db, imd, "verbrauch_daten", "heizenergie_kwh", 42.0,
        source="manual:form", writer="test",
    )
    await db.commit()

    ergebnis = await schreibe_modus_split_monat(db, anlage.id, 2025, 6)
    await db.commit()
    await db.refresh(imd)

    assert imd.verbrauch_daten["heizenergie_kwh"] == 42.0, (
        "Eine gemessene Heizwärme darf von der Ableitung nicht überschrieben werden."
    )
    assert ergebnis.waerme_abgeleitet == 0
    assert heizwaerme_ist_abgeleitet(imd.source_provenance) is False
    # Die Aufteilung selbst entsteht trotzdem — sie hat keinen Konkurrenten.
    assert imd.verbrauch_daten[MODUS_STROM_FELD[HEIZEN]] == pytest.approx(10.0)


async def test_der_schreiber_ist_idempotent(db):
    from backend.services.energie_profil.modus_split_schreiben import (
        schreibe_modus_split_monat,
    )

    anlage, inv = await _anlage_mit_klima(db)
    await _stunden_schreiben(db, anlage.id, inv.id, date(2025, 6, 10),
                             [(HEIZEN, 2.0), (KUEHLEN, 3.0)])
    imd = await _imd(db, inv.id, 2025, 6, {"stromverbrauch_kwh": 10.0})

    await schreibe_modus_split_monat(db, anlage.id, 2025, 6)
    await db.commit()
    erste = dict(imd.verbrauch_daten)
    await schreibe_modus_split_monat(db, anlage.id, 2025, 6)
    await db.commit()
    await db.refresh(imd)
    assert imd.verbrauch_daten == erste


async def test_lader_nimmt_stunden_ohne_signal_in_den_normierungs_nenner(db):
    """Der Fund aus der Instanz-Messung — und der Grund für die Zwei-Schritt-Query.

    Der erste Entwurf filterte in SQL auf `betriebsmodus_je_wp IS NOT NULL`.
    Damit fehlten die Standby-Stunden **auch im Nenner** der Normierung, und
    die erfassten Stunden wurden auf die volle Tagesmenge hochgerechnet:
    `Σ Teilmengen` traf exakt den Gesamtwert, „nicht aufgeteilt“ wurde 0.

    Genau das schließt Entscheid E-H aus — hier ist die Probe dafür.
    """
    from backend.services.energie_profil import lade_modus_split_monat

    anlage, inv = await _anlage_mit_klima(db)
    # 3 kWh beobachtet (Heizen), 1 kWh unbeobachtet. Zähler sagt 8 kWh.
    await _stunden_schreiben(
        db, anlage.id, inv.id, date(2025, 6, 10),
        [(HEIZEN, 3.0), (None, 1.0)],
        tages_kwh=8.0,
    )
    split = (await lade_modus_split_monat(db, anlage.id, 2025, 6))[str(inv.id)]

    # Nenner = 4 kWh (beide Stunden), Faktor 2 ⇒ Heizen 6 kWh.
    assert split.teilmenge_kwh(HEIZEN) == pytest.approx(6.0)
    # 2 kWh bleiben „nicht aufgeteilt“ — nicht 0.
    assert 8.0 - split.aufgeteilt_kwh == pytest.approx(2.0)
    assert split.abdeckung_h == 1.0


# ============================================================================
# E-B — die Kühlhälfte kostet, sie spart nicht
# ============================================================================

def test_kuehlstrom_geht_nicht_in_den_ersparnis_vergleich():
    """Entscheid E-B — und der Fund, der ihn an einer Instanz sichtbar machte.

    Gemessen (Klimaanlage, Juni, Gas ersetzt): 26,4 kWh Heizen · 158,4 kWh
    Kühlen · 92,4 kWh abgeleitete Wärme. Vor diesem Bau stand dort eine
    **Ersparnis von −45,04 €** und **−52 kg CO₂** — die Formel stellte die
    Stromkosten des *Kühlens* gegen die vermiedenen Gaskosten des *Heizens*.

    Das ist kein Rechenfehler, sondern ein Kategorienfehler: Kühlen ersetzt
    keine Heizung. Ohne die Klimaanlage gäbe es schlicht keine Kühlung.
    """
    from backend.services.wp_wirtschaftlichkeit import berechne_wp_ersparnis

    gemeinsam = dict(
        wp_waerme_kwh=92.4,
        wp_strom_kwh=191.2,
        wp_strompreis_cent=30.0,
        wp_parameter={"alter_energietraeger": "gas", "alter_preis_cent_kwh": 12},
    )
    ohne_split = berechne_wp_ersparnis(**gemeinsam)
    mit_split = berechne_wp_ersparnis(**gemeinsam, strom_kuehlen_kwh=158.4)

    # Die Stromkosten sind in beiden Fällen dieselben — sie fallen ja an.
    assert mit_split.wp_kosten_euro == pytest.approx(ohne_split.wp_kosten_euro)
    # Der Kühlanteil wird eigens ausgewiesen.
    assert mit_split.kuehl_kosten_euro == pytest.approx(158.4 * 0.30)
    # Und er hebt die Ersparnis aus dem Negativen.
    assert ohne_split.ersparnis_euro < 0
    assert mit_split.ersparnis_euro > 0
    assert mit_split.ersparnis_euro == pytest.approx(
        ohne_split.ersparnis_euro + 158.4 * 0.30
    )


def test_ohne_split_bleibt_die_ersparnis_unveraendert():
    """Kein Modus erfasst ⇒ Verhalten wie vor #263 K-2 (Default 0.0)."""
    from backend.services.wp_wirtschaftlichkeit import berechne_wp_ersparnis

    args = dict(
        wp_waerme_kwh=17500.0, wp_strom_kwh=4375.0, wp_strompreis_cent=30.0,
        wp_parameter={"alter_energietraeger": "gas", "alter_preis_cent_kwh": 12},
    )
    assert berechne_wp_ersparnis(**args).ersparnis_euro == pytest.approx(
        berechne_wp_ersparnis(**args, strom_kuehlen_kwh=0.0).ersparnis_euro
    )


def test_der_kuehlanteil_kann_den_gesamtstrom_nicht_uebersteigen():
    """Zusicherung für Aufrufer, die ihre Zahlen aus einer anderen Quelle ziehen."""
    from backend.services.wp_wirtschaftlichkeit import berechne_wp_ersparnis

    r = berechne_wp_ersparnis(
        wp_waerme_kwh=100.0, wp_strom_kwh=50.0, wp_strompreis_cent=30.0,
        wp_parameter={"alter_energietraeger": "gas"},
        strom_kuehlen_kwh=9999.0,
    )
    assert r.kuehl_kosten_euro == pytest.approx(50.0 * 0.30)
    r2 = berechne_wp_ersparnis(
        wp_waerme_kwh=100.0, wp_strom_kwh=50.0, wp_strompreis_cent=30.0,
        wp_parameter={"alter_energietraeger": "gas"}, strom_kuehlen_kwh=-5.0,
    )
    assert r2.kuehl_kosten_euro == 0.0


def test_kuehlstrom_geht_nicht_in_die_co2_ersparnis():
    """Dieselbe E-B-Regel für CO₂ — an der Instanz mit −52 kg gemessen.

    Die vermiedene Emission ist „Gas, das nicht verbrannt wurde, minus Strom,
    der dafür geflossen ist". Kühlstrom hat auf der Gas-Seite kein Gegenstück;
    er erzeugt seine eigene Emission, die über den Eigenverbrauch/Netzbezug in
    die Anlagenbilanz eingeht — aber nicht als schlechtere **Heiz**bilanz.
    """
    from backend.core.calculations import co2_wp_ersparnis_kg

    ohne = co2_wp_ersparnis_kg(92.4, 191.2, "gas")
    mit = co2_wp_ersparnis_kg(92.4, 191.2, "gas", strom_kuehlen_kwh=158.4)
    assert ohne < 0
    assert mit > 0
    # Nur der Heizstrom (191,2 − 158,4 = 32,8 kWh) wird gegengerechnet.
    assert mit == pytest.approx(co2_wp_ersparnis_kg(92.4, 32.8, "gas"))


def test_ohne_split_bleibt_die_co2_ersparnis_unveraendert():
    from backend.core.calculations import co2_wp_ersparnis_kg

    assert co2_wp_ersparnis_kg(17500.0, 4375.0, "gas") == pytest.approx(
        co2_wp_ersparnis_kg(17500.0, 4375.0, "gas", strom_kuehlen_kwh=0.0)
    )


def test_nicht_aufgeteilt_bezieht_sich_nur_auf_geraete_mit_split():
    """Zweiter Fund aus der Instanz-Messung — der anlagenweite Bezug.

    Gemessen an einer Anlage mit **zwei** Wärmepumpen: einer Klimaanlage mit
    Modus-Split (191,2 kWh) und einer Luft-Wasser-WP **ohne** Modus-Sensor
    (90 kWh). `Gesamt − Σ Teilmengen` ergab „nicht aufgeteilt 96,4 kWh" — 90
    davon gehörten dem anderen Gerät, das gar keine Aufteilung hat.

    `Gesamt − Σ` ist nur **je Gerät** richtig. Anlagenweit braucht es den
    Strom der Geräte mit Split als Bezug.
    """
    from backend.services.monats_fakten import WpFakten

    wp = WpFakten(
        strom_kwh=281.2,                 # beide Geräte
        modus_strom_bezug_kwh=191.2,     # nur die Klimaanlage
        modus_strom_heizen_kwh=26.4,
        modus_strom_kuehlen_kwh=158.4,
        modus_abdeckung_h=440.0,
    )
    assert wp.modus_nicht_aufgeteilt_kwh == pytest.approx(6.4)


def test_der_bezug_entsteht_nur_bei_erfasster_abdeckung():
    """Ein Monat ohne Modus-Spur trägt nichts zum Bezug bei."""
    from backend.core.berechnungen import imd_typ_beitrag

    class _Inv:
        typ = "waermepumpe"
        parameter: dict = {}

    mit = imd_typ_beitrag(_Inv(), {
        "stromverbrauch_kwh": 100.0,
        MODUS_STROM_FELD[HEIZEN]: 40.0,
        MODUS_ABDECKUNG_FELD: 700.0,
    })
    assert mit.wp_modus_strom_bezug == pytest.approx(100.0)

    ohne = imd_typ_beitrag(_Inv(), {"stromverbrauch_kwh": 100.0})
    assert ohne.wp_modus_strom_bezug == 0.0
