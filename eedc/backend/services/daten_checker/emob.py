"""
Daten-Checker — E-Mob-Pool-Pflege & Sensor-Doppelmapping (`EmobChecks`).

Reiner Move aus dem früheren Modul `daten_checker.py` (Tier-4 Achse C).
"""

from backend.models.anlage import Anlage

from .kategorien import CheckErgebnis, CheckKategorie, CheckSeverity


class EmobChecks:
    """Diagnose für parallel gepflegte Wallbox-/E-Auto-Investitionen."""

    # E-Mob-Pool-Pflege (Wallbox + E-Auto parallel gepflegt). Schwellen aus
    # dem Konzept KONZEPT-WALLBOX-EAUTO.md Phase 2a, justiert auf typische
    # Setups (Krümel-Pflege durch evcc-Imports an einer der beiden Quellen
    # darf keinen Fehlalarm auslösen).
    EMOB_POOL_MIN_KWH_PRO_MONAT = 10.0   # unterhalb = Krümel, ignorieren
    EMOB_POOL_AEHNLICHKEITS_RATIO = 0.3  # min/max ≥ 0.3 = beide nennenswert
    EMOB_POOL_PV_INKONSISTENZ = 0.10     # |WB.pv − EA.pv| / max > 10 % auffällig
    EMOB_POOL_MINDEST_MONATE = 3         # eine Monatslücke ist kein Pflege-Muster
    EMOB_POOL_FENSTER_MONATE = 12        # Beobachtungsfenster

    def _check_emob_pool_pflege(self, anlage: Anlage) -> list[CheckErgebnis]:
        """E-Auto- + Wallbox-Investition parallel gepflegt → Pflege-Konflikt.

        Wallbox (Loadpoint-Sicht) und E-Auto (Vehicle-Sicht) messen häufig
        denselben Stromfluss aus zwei Perspektiven. Seit Phase 2a wählen die
        Read-Sites die Quelle strukturell (Wallbox vorhanden → Wallbox) und die
        Migration konsolidiert Bestände in den Wallbox-Slot. Was die Migration
        nicht verlustfrei auflösen kann (z. B. Total auf der einen, PV-Split nur
        auf der anderen Seite) bleibt als Doppel-Pflege stehen.

        Diese Diagnose erkennt das Pflege-Muster („beide Quellen über mehrere
        Monate hinweg nennenswert befüllt") und lenkt den Anwender auf eine
        bewusste Entscheidung — nur eine Quelle pflegen.

        Severities:
        - INFO: ≥ MINDEST_MONATE Monate mit Doppel-Pflege (Pool wirkt).
        - WARNING: zusätzlich PV-Inkonsistenz (`|WB.pv − EA.pv| / max > 10 %`)
          in mindestens einem dieser Monate — Indiz für *echte* Doppelung,
          nicht nur zweifache Pflege identischer Werte.
        """
        from backend.core.field_definitions import (
            get_eauto_ladung_kwh,
            get_emob_pv_netz_kwh,
        )
        from backend.core.investition_parameter import ist_dienstlich

        kat = CheckKategorie.EMOB_POOL_PFLEGE.value
        ergebnisse: list[CheckErgebnis] = []

        eautos = [
            i for i in anlage.investitionen
            if i.typ == "e-auto" and not ist_dienstlich(i)
        ]
        wallboxen = [
            i for i in anlage.investitionen
            if i.typ == "wallbox" and not ist_dienstlich(i)
        ]
        if not eautos or not wallboxen:
            return ergebnisse  # Pflege-Konflikt unmöglich ohne beide Seiten.

        # Wallbox-Schwäche A (KONZEPT-WALLBOX-EAUTO.md »Bekannte Schwächen«):
        # Für die E-Auto-Seite NICHT der `verbrauch_kwh`-Fallback aus
        # get_eauto_ladung_kwh — bei einem E-Auto ist `verbrauch_kwh` der
        # Fahrverbrauch, nicht die Heimladung. Sonst wertet der Pflege-Check ein
        # E-Auto mit gepflegtem Fahrverbrauch fälschlich als „Heimladung tragend"
        # und feuert einen Konflikt, obwohl die Wallbox die einzige Heimladungs-
        # Quelle ist. Nur das explizite `ladung_kwh` zählt hier als Heimladung.
        def _ea_heimladung_kwh(data: dict) -> float:
            return float((data or {}).get("ladung_kwh") or 0)

        # Beobachtungsfenster: die letzten N Monate, in denen mindestens eine
        # Investition aktiv war.
        from datetime import date

        heute = date.today()
        fenster_monate: list[tuple[int, int]] = []
        for offset in range(self.EMOB_POOL_FENSTER_MONATE):
            jahr = heute.year + ((heute.month - 1 - offset) // 12)
            monat = ((heute.month - 1 - offset) % 12) + 1
            fenster_monate.append((jahr, monat))

        doppel_monate: list[tuple[int, int, float, float]] = []
        inkonsistenz_monate: list[tuple[int, int, float, float]] = []

        for jahr, monat in fenster_monate:
            ea_ladung = ea_pv = 0.0
            wb_ladung = wb_pv = 0.0
            for inv in eautos:
                if not inv.ist_aktiv_im_monat(jahr, monat):
                    continue
                for imd in inv.monatsdaten:
                    if imd.jahr != jahr or imd.monat != monat:
                        continue
                    data = imd.verbrauch_daten or {}
                    total = _ea_heimladung_kwh(data)
                    pv, _netz = get_emob_pv_netz_kwh(data, total_kwh=total)
                    ea_ladung += total
                    ea_pv += pv
            for inv in wallboxen:
                if not inv.ist_aktiv_im_monat(jahr, monat):
                    continue
                for imd in inv.monatsdaten:
                    if imd.jahr != jahr or imd.monat != monat:
                        continue
                    data = imd.verbrauch_daten or {}
                    total = get_eauto_ladung_kwh(data)
                    pv, _netz = get_emob_pv_netz_kwh(data, total_kwh=total)
                    wb_ladung += total
                    wb_pv += pv

            min_ladung = min(ea_ladung, wb_ladung)
            max_ladung = max(ea_ladung, wb_ladung)
            if min_ladung < self.EMOB_POOL_MIN_KWH_PRO_MONAT:
                continue  # Krümel-Pflege auf einer Seite — kein Konflikt.
            ratio = min_ladung / max_ladung if max_ladung > 0 else 0.0
            if ratio < self.EMOB_POOL_AEHNLICHKEITS_RATIO:
                continue  # eine Seite dominant — Pool-Heuristik wählt klar.

            doppel_monate.append((jahr, monat, ea_ladung, wb_ladung))

            # PV-Konsistenz: beide Sichten sollen denselben Stromfluss messen,
            # also auch denselben PV-Anteil. Abweichung > 10 % ist Pflege-
            # Konflikt, nicht nur Doppel-Pflege.
            max_pv = max(ea_pv, wb_pv)
            if max_pv > 0:
                pv_diff = abs(ea_pv - wb_pv) / max_pv
                if pv_diff > self.EMOB_POOL_PV_INKONSISTENZ:
                    inkonsistenz_monate.append((jahr, monat, ea_pv, wb_pv))

        if len(doppel_monate) < self.EMOB_POOL_MINDEST_MONATE:
            return ergebnisse

        beispiel_monate = ", ".join(
            f"{m:02d}/{j} (EA {ea:.0f} kWh / WB {wb:.0f} kWh)"
            for j, m, ea, wb in doppel_monate[:3]
        )

        if inkonsistenz_monate:
            j, m, ea_pv, wb_pv = inkonsistenz_monate[0]
            ergebnisse.append(CheckErgebnis(
                kategorie=kat,
                schwere=CheckSeverity.WARNING.value,
                meldung=(
                    "Pflege-Konflikt: E-Auto- und Wallbox-PV-Anteil "
                    "weichen voneinander ab"
                ),
                details=(
                    f"In {len(doppel_monate)} Monaten der letzten "
                    f"{self.EMOB_POOL_FENSTER_MONATE} sind sowohl die "
                    "E-Auto- als auch die Wallbox-Investition mit "
                    "Heimladung gepflegt (Beispiele: "
                    f"{beispiel_monate}). Im Monat {m:02d}/{j} liegt der "
                    f"PV-Anteil bei EA={ea_pv:.0f} kWh, WB={wb_pv:.0f} kWh "
                    f"— Abweichung > {int(self.EMOB_POOL_PV_INKONSISTENZ*100)} %, "
                    "obwohl beide Sichten denselben Stromfluss messen "
                    "sollten. eedc führt die Heimladung kanonisch an der "
                    "Wallbox (sie misst den Ladepunkt); der parallel am "
                    "E-Auto gepflegte Wert wird in den Auswertungen ignoriert. "
                    "Damit dein PV-Anteil stimmt: pflege die Heimladung nur an "
                    "der Wallbox und lasse die E-Auto-Heimladung leer "
                    "(km, Verbrauch, Extern und V2H bleiben am E-Auto)."
                ),
            ))
        else:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat,
                schwere=CheckSeverity.INFO.value,
                meldung=(
                    "E-Auto- und Wallbox-Investition tragen beide Heimladung "
                    "— die Wallbox ist die Quelle"
                ),
                details=(
                    f"In {len(doppel_monate)} Monaten der letzten "
                    f"{self.EMOB_POOL_FENSTER_MONATE} sind beide Sichten "
                    "mit Heimladung gepflegt (Beispiele: "
                    f"{beispiel_monate}). Wallbox- und E-Auto-Investition "
                    "messen oft denselben Stromfluss aus zwei Perspektiven; "
                    "eedc führt die Heimladung kanonisch an der Wallbox, die "
                    "parallel am E-Auto gepflegte Heimladung wird in den "
                    "Auswertungen nicht verwendet. Sauberer ist, nur die "
                    "Wallbox zu pflegen und die E-Auto-Heimladung leer zu "
                    "lassen (km/Verbrauch/Extern/V2H bleiben am E-Auto)."
                ),
            ))

        return ergebnisse

    def _check_emob_sensor_doppelmapping(self, anlage: Anlage) -> list[CheckErgebnis]:
        """Gleiche Sensor-Entity an Wallbox UND E-Auto gemappt → Doppelzählung.

        Ist dieselbe HA-Entity (Live-`leistung_w` oder ein kWh-Zähler) sowohl
        einer Wallbox- als auch einer E-Auto-Investition zugeordnet, messen beide
        denselben Ladestrom. Der Live-Energiefluss dedupliziert das (Wallbox-
        Priorität), aber die Monats-/Stunden-Aggregation poolt nur über
        `parent_investition_id` — ohne gesetzten Link zählt sie die Ladung
        DOPPELT (#314-Untersuchung). Deterministische Diagnose aus dem
        `sensor_mapping`: lenkt den Anwender darauf, eine der beiden Zuordnungen
        zu entfernen. Brücke vor Phase 2a (kanonische Quelle),
        docs/KONZEPT-WALLBOX-EAUTO.md.
        """
        kat = CheckKategorie.EMOB_POOL_PFLEGE.value
        mapping = anlage.sensor_mapping or {}
        inv_mapping = mapping.get("investitionen", {}) or {}
        typ_by_id = {str(i.id): i.typ for i in anlage.investitionen}
        name_by_id = {str(i.id): i.bezeichnung for i in anlage.investitionen}

        # Alle einer Investition zugeordneten Entity-IDs einsammeln (Live-Strings
        # + Zähler-`sensor_id`), dann Entity → nutzende Investitionen invertieren.
        entity_use: dict[str, set[str]] = {}
        for inv_id, inv_data in inv_mapping.items():
            if not isinstance(inv_data, dict):
                continue
            entities: set[str] = set()
            live = inv_data.get("live")
            if isinstance(live, dict):
                entities.update(str(v) for v in live.values() if v)
            felder = inv_data.get("felder")
            if isinstance(felder, dict):
                for cfg in felder.values():
                    if (isinstance(cfg, dict) and cfg.get("strategie") == "sensor"
                            and cfg.get("sensor_id")):
                        entities.add(str(cfg["sensor_id"]))
            for eid in entities:
                entity_use.setdefault(eid, set()).add(str(inv_id))

        ergebnisse: list[CheckErgebnis] = []
        for eid, inv_ids in entity_use.items():
            typen = {typ_by_id.get(iid) for iid in inv_ids}
            if "wallbox" not in typen or "e-auto" not in typen:
                continue
            wb = sorted(name_by_id.get(i, i) for i in inv_ids
                        if typ_by_id.get(i) == "wallbox")
            ea = sorted(name_by_id.get(i, i) for i in inv_ids
                        if typ_by_id.get(i) == "e-auto")
            ergebnisse.append(CheckErgebnis(
                kategorie=kat,
                schwere=CheckSeverity.WARNING.value,
                meldung="Gleicher Sensor an Wallbox und E-Auto zugeordnet",
                details=(
                    f"Die Entity „{eid}“ ist sowohl der Wallbox "
                    f"({', '.join(wb)}) als auch dem E-Auto ({', '.join(ea)}) "
                    "zugeordnet — beide messen denselben Ladestrom. In Monats-/"
                    "Jahresauswertungen wird die Ladung dadurch doppelt gezählt "
                    "(im Live-Energiefluss nicht). Bitte die Zuordnung an einer "
                    "der beiden Investitionen entfernen — Faustregel: die Wallbox "
                    "misst den Stromfluss, das E-Auto trägt Nutzung/Kilometer."
                ),
            ))
        return ergebnisse
