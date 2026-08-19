"""CO₂-Bilanz eines Monats aus seinem ``MonatsFakt`` — die eine Komposition.

**Anlass: F-47 (2026-08-19).** Der Community-Server hat CO₂ bis dahin *selbst*
gerechnet (``statistics.py``: ``Eigenverbrauch × 0,38``, den Eigenverbrauch
ebenfalls rekonstruiert) — gegen den Vertrag „der Server rechnet nichts nach"
und gegen ADR-001/DI-2. Wärmepumpe und E-Mobilität fehlten dort ganz: bei
318,9 t ausgewiesener Ersparnis ergaben allein die Wärmepumpen ≈ 70,3 t, also
gut 22 % zu wenig. Damit der Client die Zahl mitschicken kann, braucht er sie
an einer Stelle — und zwar an **derselben**, aus der Cockpit → Nachhaltigkeit
sie zeigt.

``berechne_co2_bilanz`` (``core/calculations.py``) bleibt die einzige erlaubte
**Konstruktions**-Stelle der Kennzahl (ADR-001/DI-2). Was hier dazukommt, ist
die Stufe davor: das **Zusammenstellen seiner Eingaben** aus einem Monats-Fakt.
Genau davor warnt sein Docstring — *„die Aufrufer aggregieren die Eingaben
jeweils selbst … sonst driftet die Eingabe (Lehre #326)"* —, und genau deshalb
steht die Komposition jetzt einmal hier statt ein weiteres Mal in jedem
Aufrufer.

⚠ **Diese Datei ist eine Zusammenfassung, keine neue Rechnung.** Sie ist
zeilenweise aus ``api/routes/cockpit/nachhaltigkeit.py`` übernommen; wer sie
ändert, ändert die CO₂-Zahl in Cockpit *und* im Gemeinschaftsdatensatz.
"""

from __future__ import annotations

from typing import Mapping

from backend.core.calculations import Co2Bilanz, berechne_co2_bilanz
from backend.services.eauto_wirtschaftlichkeit import (
    fossil_getankte_liter,
    km_gewichtete_eauto_params,
)
from backend.services.monats_fakten import MonatsFakt


def co2_bilanz_aus_fakt(
    fakt: MonatsFakt,
    eauto_parameter: Mapping[int, dict | None],
) -> Co2Bilanz:
    """Die kanonische CO₂-Bilanz eines Monats.

    Args:
        fakt: der aufgelöste Monat (ADR-002/P10). Sein
            ``kennzahlen.eigenverbrauch_kwh`` trägt bereits V2H, den Erzeuger
            hinter dem Zähler und die P7-Auflösung — deshalb wird er hier
            **nicht** aus Erzeugung minus Einspeisung nachgebaut.
        eauto_parameter: ``{investition_id: parameter-JSON}`` der E-Autos.
            Der Vergleichs-Verbrenner wird je Fahrzeug mit **dessen** gepflegtem
            ``vergleich_verbrauch_l_100km`` gerechnet, km-gewichtet (G20-2).

    Returns:
        ``Co2Bilanz`` mit PV-, WP- und E-Mob-Anteil sowie der Summe.
    """
    vergleich_l_100km, _ = km_gewichtete_eauto_params(
        eauto_params_und_km=[
            (eauto_parameter.get(inv_id), km)
            for inv_id, km in fakt.emob.km_je_fahrzeug.items()
        ]
    )
    return berechne_co2_bilanz(
        eigenverbrauch_kwh=fakt.kennzahlen.eigenverbrauch_kwh,
        wp_waerme_kwh=fakt.wp.waerme_kwh,
        wp_strom_kwh=fakt.wp.strom_kwh,
        # #263 K-2 (E-B): Kühlen ersetzt keine Heizung — sein Strom gehört
        # nicht in die vermiedene Heiz-Emission.
        wp_strom_kuehlen_kwh=fakt.wp.modus_strom_kuehlen_kwh,
        emob_km=fakt.emob.km,
        emob_netz_ladung_kwh=fakt.emob.ladung_netz_kwh,
        benzin_verbrauch_liter=fakt.emob.km / 100 * vergleich_l_100km,
        # #331: der real getankte Anteil eines Plug-in-Hybrids mindert die
        # vermiedene Emission. Für ein BEV ist er 0.
        fossil_getankt_liter=fossil_getankte_liter(
            km_je_fahrzeug=fakt.emob.km_je_fahrzeug,
            fahrverbrauch_je_fahrzeug=fakt.emob.fahrverbrauch_je_fahrzeug,
            params_je_fahrzeug=eauto_parameter,
        ),
    )
