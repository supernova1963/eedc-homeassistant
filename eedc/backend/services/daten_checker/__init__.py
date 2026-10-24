"""
Daten-Checker Service.

Prüft Anlage-Daten systematisch auf Vollständigkeit und Plausibilität.
5 Prüfkategorien: Stammdaten, Strompreise, Investitionen,
Monatsdaten-Vollständigkeit, Monatsdaten-Plausibilität.

Tier-4 Achse C: Das frühere Einzelmodul `daten_checker.py` wurde in ein
Package aufgeteilt. Die Checks bleiben `self`-Methoden mit geteiltem
Instanz-State — der Split erfolgt über Mixin-Klassen je Themenfeld. Dieses
`__init__.py` re-exportiert `DatenChecker` (und die Enums/Dataclasses), damit
`from backend.services.daten_checker import DatenChecker` unverändert
funktioniert (einziger Consumer: api/routes/daten_checker.py).
"""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.models.investition import Investition
from backend.services.prognose_auswahl import lade_aktive_prognose
from backend.services.snapshot.reader import MQTT_AKTIV_TAGE, mqtt_zaehler_keys

from .kategorien import (
    CheckSeverity,
    CheckKategorie,
    CheckErgebnis,
    MonatsdatenAbdeckung,
    DatenCheckResult,
)
from ._helpers import _CheckHelpers
from backend.models.tages_energie_profil import TagesEnergieProfil
from .stammdaten import StammdatenChecks
from .monatsdaten import ErfassungsortChecks, MonatsdatenChecks
from .energieprofil import EnergieprofilChecks
from .sensoren import SensorChecks
from .emob import EmobChecks
from .waermepumpe import WaermepumpeChecks
from .zaehler import ZaehlerChecks
from .datenquelle import DatenquelleChecks
from .wp_tarif import WpTarifChecks


# ─── Service ─────────────────────────────────────────────────────────────────

class DatenChecker(
    StammdatenChecks,
    MonatsdatenChecks,
    ErfassungsortChecks,
    EnergieprofilChecks,
    SensorChecks,
    EmobChecks,
    WaermepumpeChecks,
    ZaehlerChecks,
    DatenquelleChecks,
    WpTarifChecks,
    _CheckHelpers,
):
    """Prüft alle Daten einer Anlage auf Vollständigkeit und Plausibilität."""

    def __init__(self, db):
        self.db = db
        self._abdeckung: Optional[MonatsdatenAbdeckung] = None

    async def check_anlage(self, anlage_id: int) -> DatenCheckResult:
        """Führt alle Prüfungen für eine Anlage durch."""
        # Anlage mit Beziehungen laden
        result = await self.db.execute(
            select(Anlage)
            .options(
                selectinload(Anlage.investitionen).selectinload(Investition.monatsdaten),
                selectinload(Anlage.strompreise),
            )
            .where(Anlage.id == anlage_id)
        )
        anlage = result.scalar_one_or_none()
        if not anlage:
            raise ValueError(f"Anlage {anlage_id} nicht gefunden")

        # Monatsdaten separat laden (nicht über Relationship)
        md_result = await self.db.execute(
            select(Monatsdaten)
            .where(Monatsdaten.anlage_id == anlage_id)
            .order_by(Monatsdaten.jahr, Monatsdaten.monat)
        )
        monatsdaten = list(md_result.scalars().all())

        # Aktive PVGIS-Prognose laden (für Plausibilitätsprüfung) — über den
        # Auswahl-SoT. Vorher stand hier `scalar_one_or_none()` auf eine Query
        # OHNE `limit`: bei zwei aktiven Prognosen warf SQLAlchemy
        # `MultipleResultsFound` und die ganze Daten-Checker-Seite antwortete mit
        # HTTP 500 — eine Fehlerseite genau dort, wo der Nutzer Datenprobleme
        # nachsehen will (N84/P5).
        pvgis_prognose = await lade_aktive_prognose(self.db, anlage_id)

        # PV-Erzeugung und PVGIS-Lookup vorab berechnen (wird mehrfach benötigt)
        pv_erzeugung_map = await self._get_pv_erzeugung_map(anlage)
        pvgis_monat_map = self._get_pvgis_monat_map(pvgis_prognose)
        pr, pr_count = self._calculate_performance_ratio(
            pv_erzeugung_map, pvgis_monat_map, monatsdaten
        )

        # Alle Prüfungen durchführen
        ergebnisse: list[CheckErgebnis] = []
        ergebnisse.extend(self._check_stammdaten(anlage, pvgis_prognose, pr, pr_count))
        # N-267: Gibt es ueberhaupt Stundenwerte? Ein Zeittarif wird ueber sie
        # gewichtet; ohne sie rechnet eedc mit dem Hochtarif. Vom async Aufrufer
        # erhoben — `_check_strompreise` bleibt synchron.
        hat_stundenwerte = await self._hat_stundenwerte(anlage)
        ergebnisse.extend(self._check_strompreise(
            anlage, monatsdaten, hat_stundenwerte=hat_stundenwerte
        ))
        # N-767: eigener Wärmepumpen-Tarif — der PV-Anteil der WP wird zum Haushaltstarif bewertet (benannte Grenze).
        ergebnisse.extend(await self._check_wp_eigener_tarif(anlage))
        ergebnisse.extend(self._check_investitionen(anlage, monatsdaten))
        # N-597: Aufteilung nach Betriebsart, die der Abschluss nicht speichern kann.
        ergebnisse.extend(await self._check_modus_split_nicht_gespeichert(anlage))
        ergebnisse.extend(self._check_monatsdaten_vollstaendigkeit(anlage, monatsdaten))
        ergebnisse.extend(self._check_geraetewerte_ohne_monatszeile(anlage, monatsdaten))
        ergebnisse.extend(await self._check_monatsdaten_plausibilitaet(
            anlage, monatsdaten, pvgis_prognose, pv_erzeugung_map, pvgis_monat_map, pr, pr_count
        ))
        # N-328: Welche Felder bekommen ihre Zählerstände per MQTT? EINE Abfrage
        # für die ganze Abdeckungs-Prüfung. Fenster = aktive Topics: ein Topic,
        # das seit Wochen schweigt, ist eine echte Lücke und soll gemeldet werden.
        mqtt_zaehler = await mqtt_zaehler_keys(
            self.db, anlage_id,
            seit=datetime.now() - timedelta(days=MQTT_AKTIV_TAGE),
        )
        ergebnisse.extend(
            self._check_energieprofil_abdeckung(anlage, monatsdaten, mqtt_zaehler)
        )
        ergebnisse.extend(await self._check_energieprofil_plausibilitaet(anlage))
        # E7 (Zählerlücken wie HA): Bestandstage ohne Regelmarke + Reparaturweg.
        ergebnisse.extend(await self._check_bestandstage_ohne_regelmarke(anlage))
        # HA-Bauform S5 (S5-E2 b): Tage ohne Kanal-Deckung — INFO, Lesart 1 sichtbar, kein Handgriff.
        ergebnisse.extend(await self._check_tage_ohne_kanal_deckung(anlage))
        # Nachträge II: Tage mit mehr Einspeisung als Erzeugung + Entladung.
        ergebnisse.extend(await self._check_einspeisung_ueber_erzeugung(anlage))
        # N-567: Nachtrag nach eingefrorenem Zähler — nur benannt (eedc folgt HA).
        ergebnisse.extend(await self._check_nachtrag_nach_eingefrorenem_zaehler(anlage))
        # #425: dieselbe Menge für die Wallbox-Regel der Topic-Erwartung.
        ergebnisse.extend(await self._check_mqtt_topic_abdeckung(anlage, mqtt_zaehler))
        ergebnisse.extend(await self._check_zaehler_ruecksprung(anlage))
        ergebnisse.extend(await self._check_ha_zaehlersprung(anlage))
        # N-639: Rückgang von HAs Summe — über den ganzen Spiegel (ein alter Monat trifft „Aus HA laden" genauso).
        ergebnisse.extend(await self._check_ha_rueckgang(anlage))
        ergebnisse.extend(await self._check_sensor_mapping_lts(anlage))
        ergebnisse.extend(await self._check_sensor_mapping_einheit(anlage))
        ergebnisse.extend(await self._check_provenance_conflicts(anlage))
        ergebnisse.extend(await self._check_datenquelle_status(anlage))
        ergebnisse.extend(await self._check_zeitzone_ha(anlage))
        ergebnisse.extend(await self._check_datenquelle_drift(anlage))
        ergebnisse.extend(await self._check_connector_monatswert(anlage))
        ergebnisse.extend(await self._check_batterie_vorzeichen_historie(anlage))
        ergebnisse.extend(await self._check_soc_nur_ein_speicher(anlage))
        ergebnisse.extend(await self._check_klima_modus_sensor(anlage))
        # P-433-0 (Konzept #433 E12 b): der zugeordnete Modus-Sensor liefert einen Wert außerhalb der Werte-Tabelle.
        ergebnisse.extend(await self._check_klima_modus_wert(anlage))
        ergebnisse.extend(await self._check_leere_tage_trotz_zaehler(anlage))
        ergebnisse.extend(await self._check_pv_ueber_erfassung(anlage))
        # N-588 F5: Messpunkt-Vertrag der Wandlungsverluste (Anlagenzähler gegen String-Zähler).
        ergebnisse.extend(await self._check_messpunkt(anlage))
        # N-662: Anlagenzähler steht, obwohl Einspeisung bzw. Strings wachsen (Ursache negativer Autarkie).
        ergebnisse.extend(await self._check_pv_zaehler_steht(anlage))
        ergebnisse.extend(self._check_wp_arbeitszahl_unplausibel(anlage))
        ergebnisse.extend(self._check_emob_pool_pflege(
            anlage, bloecke=await self._emob_bloecke_fuer_pflege(anlage),
        ))
        ergebnisse.extend(self._check_emob_pv_ueber_gesamt(anlage))
        ergebnisse.extend(self._check_phev_anteil_unbestimmt(anlage))
        ergebnisse.extend(self._check_emob_sensor_doppelmapping(anlage))
        ergebnisse.extend(await self._check_emob_doppelzaehlung_tage(anlage))
        ergebnisse.extend(await self._check_vergleichspreis_fehlt(anlage))
        # N-426-Nachtrag: die erste Wetterfeld-Kategorie. Anlagenweit, eine
        # Zeile — sie zaehlt die leeren Monate und wie viele davon die eigene
        # Messreihe erreicht (Stufe 1+2, kein Netzabruf).
        ergebnisse.extend(await self._check_wetterwert_fehlt(anlage, monatsdaten))
        ergebnisse.extend(self._check_erfassungsort_positionen(anlage))
        # #377/D3: Verbrauchszähler (Gas/Wasser/Öl) — Quelle, Reihenbruch,
        # Inaktiv-Falle. Eigene Fragen, kein zweiter Turm über die
        # Energieprofil-Abdeckung (Begründung in `zaehler.py`).
        ergebnisse.extend(await self._check_zaehlerstaende(anlage))

        # Zusammenfassung
        zusammenfassung = {"error": 0, "warning": 0, "info": 0, "ok": 0}
        for e in ergebnisse:
            zusammenfassung[e.schwere] += 1

        return DatenCheckResult(
            anlage_id=anlage.id,
            anlage_name=anlage.anlagenname,
            ergebnisse=ergebnisse,
            zusammenfassung=zusammenfassung,
            monatsdaten_abdeckung=self._abdeckung,
        )

    async def _hat_stundenwerte(self, anlage: Anlage) -> bool:
        """N-267: gibt es Stundenwerte, über die ein Zeittarif gewichtet wird? Wahr, wenn die Anlage Stundenzeilen
        (``TagesEnergieProfil``) ODER Kanal-Stunden der Bilanz-Gruppe hat (HA-Bauform S3, E-S3-3, Bauplan §5: die
        Gewichte des Zeitfenster-Tarifs kommen seit E4f aus dem Netzbezugs-Kanal, ``kanal/preis_leser.py``).

        Die Stundenzeilen fragt dieselbe Anweisung wie bisher; nur ohne sie EINE weitere: die ``sum``-Kanäle der Anlage,
        die mindestens eine Zeile tragen (``EXISTS`` über den Primärschlüssel, kein Vollscan). Welcher davon zur
        Bilanz-Gruppe gehört, entscheidet ``_ist_bilanz_kanal`` ohne weitere Abfrage."""
        from sqlalchemy import exists

        from backend.models.kanal import ART_SUM, Kanal, KanalStatistik

        if (await self.db.execute(
            select(TagesEnergieProfil.id).where(TagesEnergieProfil.anlage_id == anlage.id).limit(1)
        )).first():
            return True
        keys = (await self.db.execute(select(Kanal.key).where(
            Kanal.anlage_id == anlage.id, Kanal.art == ART_SUM, exists().where(KanalStatistik.kanal_id == Kanal.id),
        ))).scalars().all()
        invs = {str(i.id): i for i in anlage.investitionen}
        return any(_ist_bilanz_kanal(k, invs) for k in keys)


def _ist_bilanz_kanal(key: str, invs_by_id: dict) -> bool:
    """Gehört der Kanal ``basis:<feld>`` bzw. ``inv:<id>:<feld>`` zur Bilanz-Gruppe (``bilanz_adapter.BILANZ_ACHSEN``)?
    Dieselbe Abbildung Feld → Kategorie → Achse wie der Tagespfad (``snapshot/keys._categorize_counter`` →
    ``spannen.achse_der_kategorie``, wie bis E-S5-4 der Monats-Deckel). Abgeleitete und Modus-Kanäle gehören nicht dazu."""
    from backend.core.berechnungen.spannen import achse_der_kategorie
    from backend.services.kanal.bilanz_adapter import BILANZ_ACHSEN
    from backend.services.snapshot.keys import _categorize_counter

    teile = key.split(":")
    if len(teile) == 2 and teile[0] == "basis":
        kategorie = _categorize_counter(teile[1], None, None)
    elif len(teile) == 3 and teile[0] == "inv" and teile[1] in invs_by_id:
        inv = invs_by_id[teile[1]]
        kategorie = _categorize_counter(teile[2], inv.typ, inv.parameter)
    else:
        return False
    return achse_der_kategorie(kategorie) in BILANZ_ACHSEN


__all__ = [
    "DatenChecker",
    "CheckSeverity",
    "CheckKategorie",
    "CheckErgebnis",
    "MonatsdatenAbdeckung",
    "DatenCheckResult",
]
