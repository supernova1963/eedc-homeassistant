"""
Daten-Checker — E-Mob-Pool-Pflege & Sensor-Doppelmapping (`EmobChecks`).

Reiner Move aus dem früheren Modul `daten_checker.py` (Tier-4 Achse C).
"""

from datetime import date, timedelta

from sqlalchemy import select

from backend.models.anlage import Anlage

from .kategorien import (
    CheckErgebnis, CheckKategorie, CheckSeverity, LINK_ENERGIEPROFIL,
)
from backend.core.zahlenformat import fmt_zahl


class EmobChecks:
    """Diagnose für parallel gepflegte Wallbox-/E-Auto-Investitionen."""

    # ⭐ N-555 Stufe 2 (Konzept Heimladung/Fahrverbrauch 7.2, Regel 7): die Pflegeprüfung
    # der E-Mobilität fragt nicht mehr „tragen Wallbox UND Auto Heimladung?" — nach
    # Regel 2 ist das der Normalfall (ein Auto mit eigener Messung trägt sie, die Wallbox
    # den Rest). Sie fragt zwei Dinge, beide aus dem Monats-Entscheid der EINEN Funktion
    # (`entscheide_emob_heimladung`), nicht aus einer eigenen Faltung.
    #
    #: Unterhalb dieser Menge je Monat ist ein Überschuss Zählerauflösung, kein Befund.
    EMOB_POOL_MIN_KWH_PRO_MONAT = 10.0
    #: … und unterhalb dieses Anteils an der Wallbox auch (zwei Messpunkte desselben
    #: Flusses, Sitzung über den Monatswechsel bis Stufe 3). Toleranz = max(beide).
    EMOB_POOL_UEBERSCHUSS_ANTEIL = 0.10
    EMOB_POOL_FENSTER_MONATE = 12        # Beobachtungsfenster

    @staticmethod
    def _emob_doppel_entity_eautos(anlage: Anlage) -> set[int]:
        """E-Autos, deren Sensor-Entity auch an einer Wallbox hängt (s. Doppelmapping)."""
        mapping = (anlage.sensor_mapping or {}).get("investitionen", {}) or {}
        typ_by_id = {str(i.id): i.typ for i in anlage.investitionen}
        entity_use: dict[str, set[str]] = {}
        for inv_id, inv_data in mapping.items():
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
        doppel: set[int] = set()
        for inv_ids in entity_use.values():
            if any(typ_by_id.get(i) == "wallbox" for i in inv_ids):
                doppel.update(int(i) for i in inv_ids if typ_by_id.get(i) == "e-auto")
        return doppel

    def _check_emob_pool_pflege(
        self, anlage: Anlage, heute: "date | None" = None,
    ) -> list[CheckErgebnis]:
        """Regel 7: „Autos zusammen mehr als die Wallbox" und „Heimladung am Dienstwagen fehlt".

        (a) **Warnung** — die eigenen Messungen der Autos (privat und Dienstwagen)
            übersteigen die Summe der privaten Wallboxen um mehr als
            max(``EMOB_POOL_MIN_KWH_PRO_MONAT``, ``EMOB_POOL_UEBERSCHUSS_ANTEIL`` × Wallbox)
            — nur wenn die Wallbox einen Wert trägt (auch 0). Gerichtet: die frühere
            Ähnlichkeitsregel (min/max ≥ 0,3) schwieg genau im groben Fall. eedc rechnet
            mit den erfassten Werten weiter (E2).
        (b) **Hinweis** (E7) — die private Wallbox hat geladen, ein Dienstwagen ist
            gefahren, es gibt keine dienstliche Wallbox in Betrieb, und der Dienstwagen
            hat keine eigene Messung. Eine 0 am Dienstwagen ist eine Messung und schaltet
            ab; ein „Akzeptiert" gibt es bewusst nicht.

        Nicht mehr gemeldet: „Ladewerte am E-Auto neben der Wallbox" (Regel 2: der
        Normalfall). Ein alter Gesamtwert mit „Herkunft unbekannt" ist keine Messung
        (Regel 8) und zählt in (a) nicht; ein Auto, dessen Sensor auch an der Wallbox
        hängt, meldet schon `_check_emob_sensor_doppelmapping` — es zählt hier nicht.

        ``heute`` (Probe) legt das Fenster fest; ohne ihn die Uhr des Prozesses.
        """
        from backend.core.field_definitions import ist_heim_gesamt
        from backend.core.investition_parameter import ist_dienstlich
        from backend.services.eauto_wirtschaftlichkeit import (
            ART_GEMESSEN,
            entscheide_emob_heimladung,
        )

        kat = CheckKategorie.EMOB_POOL_PFLEGE.value
        ergebnisse: list[CheckErgebnis] = []

        emob = [i for i in anlage.investitionen if i.typ in ("e-auto", "wallbox")]
        privat_wb = [i for i in emob if i.typ == "wallbox" and not ist_dienstlich(i)]
        if not privat_wb:
            return ergebnisse  # ohne private Wallbox gibt es keinen Rest und keinen Widerspruch
        doppel = self._emob_doppel_entity_eautos(anlage)

        heute = heute or date.today()
        ueberschuss_monate: list[tuple[int, int, float, float]] = []
        dienstwagen_monate: dict[int, list[tuple[int, int]]] = {}
        name = {i.id: i.bezeichnung for i in emob}
        for offset in range(self.EMOB_POOL_FENSTER_MONATE):
            jahr = heute.year + ((heute.month - 1 - offset) // 12)
            monat = ((heute.month - 1 - offset) % 12) + 1
            in_betrieb = [i for i in emob if i.ist_aktiv_im_monat(jahr, monat)]
            if not any(i in privat_wb for i in in_betrieb):
                continue
            zeilen: dict[int, dict] = {}
            heim_gesamt: set[int] = set()
            for inv in in_betrieb:
                for imd in inv.monatsdaten:
                    if imd.jahr == jahr and imd.monat == monat:
                        zeilen[inv.id] = imd.verbrauch_daten or {}
                        if inv.typ == "e-auto" and ist_heim_gesamt(
                            zeilen[inv.id], imd.source_provenance,
                        ):
                            heim_gesamt.add(inv.id)
            eautos = [i for i in in_betrieb if i.typ == "e-auto" and not ist_dienstlich(i)]
            dienstwagen = [i for i in in_betrieb if i.typ == "e-auto" and ist_dienstlich(i)]
            dwb = [i for i in in_betrieb if i.typ == "wallbox" and ist_dienstlich(i)]
            e = entscheide_emob_heimladung(
                eauto_je_inv={i.id: zeilen[i.id] for i in eautos if i.id in zeilen},
                wallbox_zeilen=[zeilen[w.id] for w in privat_wb if w.id in zeilen],
                wallbox_in_betrieb=True,
                dienstwagen_je_inv={i.id: zeilen[i.id] for i in dienstwagen if i.id in zeilen},
                dienstliche_wallbox_je_inv={i.id: zeilen.get(i.id, {}) for i in dwb},
                dienstliche_wallbox_in_betrieb=bool(dwb),
                heim_gesamt=heim_gesamt,
                wallbox_ids={w.id for w in privat_wb},
                eauto_in_betrieb=[i.id for i in eautos],
                dienstwagen_in_betrieb=[i.id for i in dienstwagen],
            )
            wallbox = e.wallbox_summe.ladung_kwh
            # (a) Autos zusammen mehr als die Wallbox
            if e.wallbox_hat_wert:
                messung = sum(
                    a.ladung_kwh for i, a in e.je_auto.items()
                    if a.art == ART_GEMESSEN and i not in doppel
                ) + sum(
                    e.dienstlich_je_inv[i].pv_kwh + e.dienstlich_je_inv[i].netz_kwh
                    for i in e.dienstwagen_gemessen if i not in doppel
                )
                toleranz = max(
                    self.EMOB_POOL_MIN_KWH_PRO_MONAT,
                    self.EMOB_POOL_UEBERSCHUSS_ANTEIL * wallbox,
                )
                if messung - wallbox > toleranz:
                    ueberschuss_monate.append((jahr, monat, messung, wallbox))
            # (b) Heimladung am Dienstwagen fehlt (E7)
            if wallbox > 0 and not e.dienstliche_wallbox_in_betrieb:
                for i in e.dienstwagen_ungemessen:
                    if float((zeilen.get(i) or {}).get("km_gefahren") or 0) > 0:
                        dienstwagen_monate.setdefault(i, []).append((jahr, monat))

        if ueberschuss_monate:
            beispiele = "; ".join(
                f"{m:02d}/{j}: Autos {fmt_zahl(a, 0)} kWh, Wallbox {fmt_zahl(w, 0)} kWh"
                for j, m, a, w in ueberschuss_monate[:3]
            )
            ergebnisse.append(CheckErgebnis(
                kategorie=kat,
                schwere=CheckSeverity.WARNING.value,
                meldung="Die Autos haben zusammen mehr zu Hause geladen, als die Wallbox gemessen hat",
                details=(
                    f"In {len(ueberschuss_monate)} Monaten der letzten "
                    f"{self.EMOB_POOL_FENSTER_MONATE} übersteigen die eigenen Heimlade-Messungen "
                    f"der Autos die Wallbox ({beispiele}). Mögliche Ursachen: Streudaten am "
                    "Auto, eine Quelle am Auto, die auch das Laden unterwegs zählt, oder ein "
                    "Auto, das an der Steckdose statt an der Wallbox geladen hat. eedc rechnet "
                    "mit den erfassten Werten weiter; der Rest der Wallbox ist in diesen "
                    "Monaten 0. Prüfe die Heimlade-Werte der Autos („Heim: PV“, „Heim: Netz“, "
                    "„Heim: gesamt“) für diese Monate."
                ),
            ))
        for i, monate in sorted(dienstwagen_monate.items()):
            liste = ", ".join(f"{m:02d}/{j}" for j, m in monate[:3])
            ergebnisse.append(CheckErgebnis(
                kategorie=kat,
                schwere=CheckSeverity.INFO.value,
                meldung=f"Heimladung am Dienstwagen „{name.get(i, i)}“ fehlt",
                details=(
                    f"Die private Wallbox hat geladen und der Dienstwagen ist gefahren "
                    f"({liste}), aber am Dienstwagen ist keine Heimladung erfasst. Lädt er zu "
                    "Hause, zählt seine Ladung sonst privat und dienstlich. Trage seine "
                    "Heimladung am Dienstwagen ein („Heim: gesamt“ oder „Heim: PV/Netz“). "
                    "Wer ihn nur beim Arbeitgeber lädt, trägt 0 ein — 0 ist ein Wert, dann "
                    "schweigt dieser Hinweis."
                ),
            ))
        return ergebnisse

    #: #331: unterhalb dieser Monatszahl ohne Fahrverbrauch ist eine Lücke
    #: kein Muster — ein einzelner nachzupflegender Monat wird nicht gemeldet.
    PHEV_MINDEST_MONATE_OHNE_VERBRAUCH = 2

    # N-201: Ab welcher Abweichung ist `ladung_pv_kwh > ladung_kwh` ein
    # Widerspruch und nicht Rundung? Beide Werte werden in kWh mit einer
    # Nachkommastelle gepflegt bzw. importiert; 0,1 kWh deckt die Rundung ab,
    # ohne einen echten Fall zu verschlucken (der gemessene Anlassfall liegt
    # 14,5 kWh auseinander).
    EMOB_PV_UEBERHANG_TOLERANZ_KWH = 0.1

    def _check_emob_pv_ueber_gesamt(self, anlage: Anlage) -> list[CheckErgebnis]:
        """Eine Monatszeile, in der die PV-Ladung größer ist als die Ladung (N-201).

        **Was hier schiefsteht.** ``ladung_pv_kwh`` ist ein *Teil* von
        ``ladung_kwh`` — es kann nicht mehr Strom aus PV geladen worden sein,
        als insgesamt geladen wurde. An Anlage 1 stand für 06/2026 real
        ``100,5 kWh PV`` bei ``86,0 kWh Gesamt``.

        **Warum trotzdem nirgends eine falsche Zahl steht.** Die Rechenkette
        fängt den Widerspruch strukturell ab: ``summiere_emob_quelle``
        konstruiert ``ladung_kwh`` als ``pv + netz``, statt das Feld zu lesen,
        und ``get_emob_pv_netz_kwh`` klemmt den abgeleiteten Netz-Anteil mit
        ``max(0, total − pv)``. Damit gilt ``ladung_kwh ≥ pv`` immer (#262,
        gewächtert in ``test_n314_pv_ladeanteil_spanne.py``).

        ⭐ **Und genau das ist der Grund, warum es eine Meldung braucht.** Die
        Garantie repariert die *Rechnung*, nicht die *Zeile*: Der gepflegte Wert
        ``ladung_kwh = 86,0`` wird dabei stillschweigend verworfen und durch
        ``pv + netz`` ersetzt. Der Anwender sieht eine Gesamtladung, die er nie
        eingetragen hat, und erfährt nie, dass einer seiner beiden Werte falsch
        ist. ``monats_fakten.pv_ladeanteil_prozent`` hält das im Docstring als
        offene Lücke fest — diese Prüfung schließt sie.

        **WARNING, nicht ERROR** und ohne Reparatur-Knopf: eedc kann nicht
        wissen, welcher der beiden Werte der richtige ist — raten wäre hier
        dasselbe wie beim Reihenbruch eines Zählerstands. Der Weg steht daneben
        (``feedback_kein_grosser_heiler_knopf``).

        ⚠ **Nur wenn BEIDE Felder gepflegt sind.** Fehlt ``ladung_kwh``, ist die
        Zeile unvollständig, nicht widersprüchlich — das ist die Frage der
        Vollständigkeits-Prüfungen, kein zweiter Turm darüber.
        """
        kat = CheckKategorie.MONATSDATEN_PLAUSIBILITAET.value
        ergebnisse: list[CheckErgebnis] = []

        # Checker-Pfad: liest die Rohzeile bewusst selbst (ADR-002/P10 nimmt
        # Schreib-, Import- und Checker-Pfade aus). Der Sinn dieser Prüfung ist
        # ja gerade, den Zustand VOR der SoT-Auflösung zu sehen — über die
        # Fakten-Schicht gelesen wäre der Widerspruch bereits weggeklemmt.
        treffer: list[tuple[int, str, int, int, float, float]] = []
        for inv in anlage.investitionen:
            if inv.typ not in ("wallbox", "e-auto"):
                continue
            name = inv.bezeichnung or f"#{inv.id}"
            for imd in inv.monatsdaten:
                daten = imd.verbrauch_daten or {}
                gesamt = daten.get("ladung_kwh")
                pv = daten.get("ladung_pv_kwh")
                if gesamt is None or pv is None:
                    continue
                try:
                    gesamt_f, pv_f = float(gesamt), float(pv)
                except (TypeError, ValueError):
                    continue
                if pv_f > gesamt_f + self.EMOB_PV_UEBERHANG_TOLERANZ_KWH:
                    treffer.append(
                        (inv.id, name, imd.jahr, imd.monat, gesamt_f, pv_f)
                    )

        if not treffer:
            return ergebnisse

        # Datums-Listen absteigend (Regel 0a), Gerät als zweites Kriterium.
        treffer.sort(key=lambda t: (-t[2], -t[3], t[1]))
        MAX_EINZEL = 10
        for inv_id, name, jahr, monat, gesamt_f, pv_f in treffer[:MAX_EINZEL]:
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.WARNING.value,
                meldung=(
                    f"{name}: PV-Ladung größer als Gesamtladung "
                    f"({monat:02d}/{jahr}: {fmt_zahl(pv_f, 1)} kWh von {fmt_zahl(gesamt_f, 1)} kWh)"
                ),
                details=(
                    "Die PV-Ladung ist ein Teil der Gesamtladung und kann nicht "
                    "größer sein. eedc rechnet deshalb mit PV + Netz weiter und "
                    f"legt die eingetragenen {fmt_zahl(gesamt_f, 1)} kWh beiseite — die "
                    "Zahl, die du siehst, ist dann nicht die, die du erfasst "
                    "hast. Welcher der beiden Werte stimmt, kann eedc nicht "
                    "wissen: Trage den Monat noch einmal nach."
                ),
                link=f"/einstellungen/daten?erfassen={jahr}-{monat:02d}",
                investition_id=inv_id,
            ))

        if len(treffer) > MAX_EINZEL:
            rest = len(treffer) - MAX_EINZEL
            ergebnisse.append(CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.INFO.value,
                meldung=f"… plus {rest} weitere(r) Monat(e) mit demselben Widerspruch",
            ))

        return ergebnisse

    def _check_phev_anteil_unbestimmt(self, anlage: Anlage) -> list[CheckErgebnis]:
        """PHEV gepflegt, aber der elektrische Anteil ist nicht bestimmbar.

        Trägt ein Fahrzeug einen `eigener_verbrauch_l_100km`, hat es laut
        Entscheidung 3 des Konzepts einen Verbrenner. Um seine Kilometer
        aufzuteilen, braucht eedc **eine** von zwei Angaben: den monatlich
        erfassten Fahrverbrauch (`verbrauch_kwh`, der gemessene Weg) oder einen
        gepflegten `elektrischer_fahranteil_prozent` (der geschätzte).

        Fehlen beide, rechnet eedc **100 % elektrisch** — das heutige Verhalten,
        bewusst gewählt statt eines erfundenen Richtwerts. Ersparnis und
        CO₂-Bilanz fallen dadurch zu gut aus, und genau das darf nicht still
        passieren ([[feedback_daten_checker_kein_akzeptiert]]).
        """
        from backend.core.investition_parameter import ist_dienstlich
        from backend.services.eauto_wirtschaftlichkeit import (
            eigener_verbrauch_l_100km,
            fahranteil_prozent,
        )

        kat = CheckKategorie.PHEV_ANTEIL_UNBESTIMMT.value
        ergebnisse: list[CheckErgebnis] = []

        for inv in anlage.investitionen:
            if inv.typ != "e-auto" or ist_dienstlich(inv):
                continue
            if eigener_verbrauch_l_100km(inv.parameter) is None:
                continue  # BEV — nichts aufzuteilen.
            # Über den SoT-Helper, nicht über den Rohwert: „nicht gepflegt"
            # heißt auch ein geleertes Feld (`""`) oder ein unbrauchbarer Wert.
            # `is not None` auf dem Rohwert sah in beiden Fällen einen Wert und
            # ließ den Check schweigen, während `teile_fahrleistung` mangels
            # Zahl auf „100 % elektrisch" fiel — der Check verstummte genau in
            # der Lage, für die er gebaut ist. `0` bleibt ein gepflegter Wert.
            if fahranteil_prozent(inv.parameter) is not None:
                continue  # geschätzter Weg ist gepflegt.

            # Monate MIT gefahrenen km, aber OHNE erfassten Fahrverbrauch —
            # nur die sind unbestimmt. Ein Monat ohne km teilt nichts auf.
            monate_ohne = [
                imd for imd in getattr(inv, "monatsdaten", []) or []
                if ((imd.verbrauch_daten or {}).get("km_gefahren") or 0) > 0
                and not ((imd.verbrauch_daten or {}).get("verbrauch_kwh") or 0)
            ]
            if len(monate_ohne) < self.PHEV_MINDEST_MONATE_OHNE_VERBRAUCH:
                continue

            ergebnisse.append(CheckErgebnis(
                kategorie=kat,
                schwere=CheckSeverity.WARNING.value,
                meldung=(
                    f"{inv.bezeichnung}: Verbrenner-Verbrauch gepflegt, aber "
                    "der elektrische Fahranteil ist nicht bestimmbar"
                ),
                details=(
                    f"In {len(monate_ohne)} Monaten sind Kilometer erfasst, "
                    "aber kein elektrischer Fahrverbrauch (Monatsfeld "
                    "Verbrauch in kWh). Ohne ihn und ohne gepflegten "
                    "elektrischen Fahranteil in Prozent rechnet eedc diese "
                    "Monate mit 100 % elektrisch gefahrenen Kilometern — "
                    "Ersparnis und "
                    "CO₂-Einsparung fallen dadurch zu gut aus. Abhilfe: "
                    "entweder den monatlichen Fahrverbrauch erfassen (dann "
                    "rechnet eedc den Anteil gemessen) oder in der "
                    "Investition einen geschätzten Fahranteil eintragen."
                ),
                investition_id=inv.id,
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

    # ── N-186: die Alt-Tage von F-14 ────────────────────────────────────────
    #: Unterhalb dieser Schwelle ist die Überschneidung Krümel (Rundung,
    #: Standby) und kein doppelt gezählter Ladevorgang.
    EMOB_DOPPEL_MIN_KWH_PRO_TAG = 1.0
    #: Fenster der Rückschau — dieselbe Größenordnung wie der Drift-Check.
    EMOB_DOPPEL_FENSTER_TAGE = 180

    async def _check_emob_doppelzaehlung_tage(self, anlage: Anlage) -> list[CheckErgebnis]:
        """Gespeicherte Tage, an denen Wallbox UND E-Auto dieselbe Ladung tragen.

        F-14 (#356) hat die strukturelle Quellen-Regel gebaut: trägt eine
        Wallbox die Ladeenergie, ist sie die Quelle. Das gilt für **neue**
        Tage. Was vorher geschrieben wurde, steht weiter in
        ``TagesZusammenfassung.komponenten_kwh`` — an Gernots Anlage am
        2026-08-06 mit 29,32 statt 12,00 kWh.

        ⚠ **Warum ein Checker und keine Start-Migration:** die Heilung
        überschreibt Tages- und Stundenwerte. Ein Lauf, der beim Hochfahren
        ungefragt Messwerte ersetzt, ist genau der „große Heiler-Knopf", den
        dieses Projekt nicht will ([[feedback_kein_grosser_heiler_knopf]] ·
        [[feedback_reparatur_statt_loesch_features]]). Der Anwender sieht den
        Befund, die betroffenen Tage und entscheidet.

        ⚠ **Kein Befund heißt hier nicht „geprüft und sauber", sondern
        „geprüft, soweit Tageswerte vorliegen"** — Tage ohne
        ``komponenten_kwh`` kann diese Prüfung nicht bewerten.
        """
        from backend.models.tages_energie_profil import TagesZusammenfassung
        from backend.services.repair_orchestrator import REAGGREGATE_RANGE_MAX_DAYS

        kat = CheckKategorie.EMOB_DOPPELZAEHLUNG_TAGE.value

        eautos = [i for i in anlage.investitionen if i.typ == "e-auto"]
        wallboxen = [i for i in anlage.investitionen if i.typ == "wallbox"]
        if not eautos or not wallboxen:
            return []

        bis = date.today()
        von = bis - timedelta(days=self.EMOB_DOPPEL_FENSTER_TAGE)
        rows = (await self.db.execute(
            select(TagesZusammenfassung).where(
                TagesZusammenfassung.anlage_id == anlage.id,
                TagesZusammenfassung.datum >= von,
                TagesZusammenfassung.datum <= bis,
            ).order_by(TagesZusammenfassung.datum)
        )).scalars().all()

        wb_keys = {f"wallbox_{w.id}" for w in wallboxen}
        ea_keys = {f"eauto_{e.id}" for e in eautos}

        befunde: list[tuple[date, float, float]] = []
        for tz in rows:
            komp = tz.komponenten_kwh or {}
            # Senken stehen negativ im JSON (Butterfly-Konvention) — der Betrag
            # ist die Energie. Genau diese Vorzeichenfrage hat bei #356 eine
            # Invariante blind gemacht, deshalb hier ausdrücklich `abs`.
            wb = sum(abs(v) for k, v in komp.items()
                     if k in wb_keys and isinstance(v, (int, float)))
            ea = sum(abs(v) for k, v in komp.items()
                     if k in ea_keys and isinstance(v, (int, float)))
            if min(wb, ea) >= self.EMOB_DOPPEL_MIN_KWH_PRO_TAG:
                befunde.append((tz.datum, wb, ea))

        if not befunde:
            return [CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK.value,
                meldung=(
                    f"Keine doppelt gezählten Ladetage in den letzten "
                    f"{self.EMOB_DOPPEL_FENSTER_TAGE} Tagen"
                ),
            )]

        summe_zuviel = sum(min(wb, ea) for _d, wb, ea in befunde)
        aeltester, neuester = befunde[0][0], befunde[-1][0]
        range_von = max(
            aeltester, neuester - timedelta(days=REAGGREGATE_RANGE_MAX_DAYS - 1)
        )
        rest_aelter = sum(1 for d, _w, _e in befunde if d < range_von)

        details = (
            f"An {len(befunde)} Tag(en) tragen Wallbox und E-Auto beide eine "
            f"Ladung — insgesamt rund {fmt_zahl(summe_zuviel, 0)} kWh, die im "
            f"Tagesverlauf doppelt erscheinen. eedc zählt eine Ladung "
            f"inzwischen nur noch einmal (die Wallbox ist die Quelle); diese Tage "
            f"wurden vorher geschrieben und bleiben stehen, bis sie neu "
            f"berechnet werden. "
            f"„Zeitraum neu aggregieren“ holt {range_von.isoformat()} bis "
            f"{neuester.isoformat()} nach (max. "
            f"{REAGGREGATE_RANGE_MAX_DAYS} Tage/Lauf)."
        )
        if rest_aelter > 0:
            details += (
                f" {rest_aelter} ältere(r) Tag(e) liegen außerhalb des "
                f"Fensters — nach dem Lauf erneut prüfen."
            )
        details += (
            " Reichweite: der Lauf heilt Tages- und Stundenwerte, NICHT die "
            "Monatswerte."
        )

        beispiele = ", ".join(
            f"{d.isoformat()} (Wallbox {fmt_zahl(wb, 1)} + E-Auto {fmt_zahl(ea, 1)} kWh)"
            for d, wb, ea in sorted(befunde, key=lambda x: min(x[1], x[2]),
                                    reverse=True)[:3]
        )
        return [CheckErgebnis(
            kategorie=kat, schwere=CheckSeverity.WARNING.value,
            meldung=(
                f"{len(befunde)} Tag(e) zählen dieselbe Ladung doppelt "
                f"({aeltester.isoformat()} … {neuester.isoformat()})"
            ),
            details=f"{details} Größte Fälle: {beispiele}.",
            link=LINK_ENERGIEPROFIL,
            action_kind="reaggregate_range",
            action_params={
                "anlage_id": anlage.id,
                "von": range_von.isoformat(),
                "bis": neuester.isoformat(),
            },
            action_label="Zeitraum neu aggregieren",
        )]

    async def _check_vergleichspreis_fehlt(self, anlage: Anlage) -> list[CheckErgebnis]:
        """Monatszeilen ohne Ø-Benzinpreis — der E-Auto-Vergleich rechnet dann still weiter.

        **Der Melder-Fall (Discussion #394, gruaGit, 23.08.2026):** Er fragte
        nach historischen Benzinpreisen für die Amortisation, bekam die Antwort
        „eedc trägt jeden Monat ohne Preis automatisch nach" — und fand für
        Juni 2026 ein leeres Feld. Die Automatik gab es, sie lief nur
        **wöchentlich** und ohne Startlauf; eine Monatszeile, die zwischen zwei
        Läufen entsteht (Monatsabschluss, Import, Erst-Einrichtung), blieb
        solange leer. Der Takt ist mit demselben Paket täglich geworden, der
        Startlauf ist dazugekommen — **diese Prüfung ist die zweite Hälfte**:
        Sie sagt es, wenn es doch einmal fehlt, statt es den Anwender an einem
        leeren Feld raten zu lassen.

        **Warum das kein kosmetischer Befund ist:** Ohne Monatspreis fällt
        ``resolve_eauto_benzinpreis`` auf den Investitions-Parameter bzw.
        1,65 €/L zurück — ohne Kennzeichnung. Der Fortschritt behauptet dann
        eine Messung und liefert ein Modell.

        **Nur mit E-Auto** (``typ == "e-auto"``, auch dienstlich — der Vergleich
        ist dort ebenso hinterlegt): ohne E-Auto ist das Feld bedeutungslos, und
        eine Warnung, die niemanden betrifft, ist genau die Sorte, die man nie
        wieder los wird.

        **Erst ab dem Anschaffungsmonat des ältesten E-Autos.** Zwei
        Datums-Ebenen, zwei Fragen: hier zählt „ab wann ist dieses Gerät
        dabei?", also ``anschaffungsdatum`` der Investition — nicht
        ``Anlage.installationsdatum``, das filtert keine Auswertung.

        **Und erst ab 2005:** Weiter zurück reicht das Oil Bulletin nicht. Ein
        Monat davor wäre eine wahre Warnung ohne Weg — die kennen wir aus #389.
        """
        from backend.models.monatsdaten import Monatsdaten
        from backend.services.kraftstoff_preis_service import kraftstoffpreis_ab_monat

        kat = CheckKategorie.VERGLEICHSPREIS_FEHLT.value

        # ⭐ Geteilter SoT mit der SCHREIB-Seite (``backfill_*_kraftstoffpreise``).
        # Bis 17.09.2026 stand die Bedingung nur hier, und der wöchentliche
        # Backfill-Job füllte ungefragt jede Anlage — ein Melder ohne E-Auto
        # bekam dadurch einen Quellen-Konflikt auf ``kraftstoffpreis_euro``
        # gemeldet (Forum simon42 T89667, PN rapahl). Versprechen und Schreiben
        # benutzen jetzt dieselbe Funktion, wie ``erwartete_komponenten_keys``
        # es für die Komponenten-Menge tut.
        ab = kraftstoffpreis_ab_monat(anlage.investitionen)
        if ab is None:
            return []
        ab_jahr, ab_monat = ab

        rows = (await self.db.execute(
            select(Monatsdaten).where(
                Monatsdaten.anlage_id == anlage.id,
                Monatsdaten.kraftstoffpreis_euro.is_(None),
            ).order_by(Monatsdaten.jahr, Monatsdaten.monat)
        )).scalars().all()

        offen = [
            md for md in rows
            if (md.jahr, md.monat) >= (ab_jahr, ab_monat)
        ]

        if not offen:
            return [CheckErgebnis(
                kategorie=kat, schwere=CheckSeverity.OK.value,
                meldung="Alle Monate mit E-Auto tragen einen Ø-Benzinpreis",
            )]

        def _mm(md) -> str:
            return f"{md.monat:02d}/{md.jahr}"

        beispiele = ", ".join(_mm(md) for md in offen[:3])
        if len(offen) > 3:
            beispiele += f" … {_mm(offen[-1])}"

        return [CheckErgebnis(
            kategorie=kat, schwere=CheckSeverity.WARNING.value,
            meldung=(
                f"{len(offen)} Monat(e) ohne Ø-Benzinpreis "
                f"({_mm(offen[0])} … {_mm(offen[-1])})"
            ),
            details=(
                "Der Monatsdurchschnitt aus dem EU Weekly Oil Bulletin ist die "
                "Grundlage des E-Auto-Vergleichs. Wo er fehlt, rechnet eedc mit "
                "dem Modellwert aus den Investitions-Parametern weiter — die "
                "Ersparnis dieser Monate trägt dann den heutigen Preis statt "
                "des damaligen. Nachpflegen holt die Wochenpreise für alle "
                "offenen Monate; bestehende Werte bleiben unberührt. "
                f"Betroffen: {beispiele}."
            ),
            link=LINK_ENERGIEPROFIL,
            action_kind="kraftstoffpreis_backfill",
            action_params={"anlage_id": anlage.id},
            action_label="Vergleichspreise nachpflegen",
        )]
