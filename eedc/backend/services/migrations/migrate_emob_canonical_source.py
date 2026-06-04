"""Phase 2a Etappe 4: einmalige Daten-Migration auf die kanonische
E-Mob-Heimladungs-Quelle (Wallbox).

Hintergrund
-----------
Die Read-Sites (Etappe 2) wählen die Heimladungs-Quelle jetzt **strukturell**:
existiert eine Wallbox mit Heimladung, ist sie die Quelle — der E-Auto-Wert
wird ignoriert. Für *un-migrierte* Bestände, in denen die Heimladung historisch
(auch) auf dem E-Auto liegt, würde der Read damit den (ggf. kleineren oder
leeren) Wallbox-Wert zeigen und unterzählen. Diese Migration konsolidiert die
Heimladung in den kanonischen Wallbox-Slot, sodass der strukturelle Read im
Steady-State stimmt.

Regeln (docs/KONZEPT-WALLBOX-EAUTO.md, Phase 2a Entscheidungen 2–4)
------------------------------------------------------------------
Nur Anlagen mit **genau einer** (nicht-dienstlichen) Wallbox + ≥1 (nicht-
dienstlichem) E-Auto. Pro **aktivem** Monat (Anschaffung→Stilllegung beider
Seiten), in dem das E-Auto Heimladung trägt UND die Wallbox aktiv ist:

- **Höherer Wert gewinnt** (Entsch. 2): die Quelle mit der größeren Heim-
  ladungs-Summe (`pv+netz`) liefert die überlebende, in sich konsistente Trias.
  Gewinnt das E-Auto, wird seine Trias in die Wallbox-IMD geschrieben (IMD wird
  angelegt, falls für den Monat keine existiert). Die E-Auto-Heim-Keys
  (`ladung_kwh`/`ladung_pv_kwh`/`ladung_netz_kwh`) werden in jedem Fall geräumt.
- **Unauflösbar → stehenlassen** (Entsch. 2): wenn der Gewinner keinen
  PV-Split trägt (`pv==0`), der Verlierer aber schon (`pv>0`) — „Total auf der
  einen, PV-Split nur auf der anderen Seite" → keine verlustfreie Trias bildbar.
  Diese Monate bleiben unverändert und tauchen im Daten-Checker
  (`_check_emob_pool_pflege`) auf, wo der Anwender bewusst entscheidet.
- **Multi-Wallbox → ganze Anlage überspringen** (Entsch. 4): mehrdeutiges
  Ziel; Daten-Checker surfacet.
- **Nur aktive Monate** (Entsch. 3): Monate vor Wallbox-Anschaffung (E-Auto am
  Schuko geladen) bleiben beim E-Auto — dort ist es korrekt die Quelle.

Idempotenz
----------
`_apply_once` (Key `phase_2a_emob_canonical_source`) verhindert einen zweiten
Lauf. Zusätzlich ist die Logik natürlich idempotent: nach dem ersten Lauf
tragen die E-Autos keine Heimladung mehr → keine Monate → No-op.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.core.field_definitions import get_eauto_ladung_kwh, get_emob_pv_netz_kwh
from backend.core.investition_parameter import ist_dienstlich
from backend.models.investition import Investition, InvestitionMonatsdaten

logger = logging.getLogger(__name__)

_HEIM_KEYS = ("ladung_kwh", "ladung_pv_kwh", "ladung_netz_kwh")


def _heim_trias(data: dict) -> tuple[float, float]:
    """(pv, netz) einer IMD über den SoT-Helper (Netz ggf. aus Total − PV)."""
    pv, netz = get_emob_pv_netz_kwh(data or {}, total_kwh=get_eauto_ladung_kwh(data or {}))
    return pv, netz


async def migrate_emob_canonical_source(session: AsyncSession) -> None:
    invs = (await session.execute(select(Investition))).scalars().all()
    by_anlage: dict[int, list[Investition]] = {}
    for i in invs:
        by_anlage.setdefault(i.anlage_id, []).append(i)

    migriert_monate = 0          # Monate, in denen die E-Auto-Trias in die WB wanderte
    nur_geleert_monate = 0       # Monate, in denen die WB bereits kanonisch war (nur EA geräumt)
    unaufloesbar = 0
    multi_wb_anlagen = 0
    betroffene_anlagen: set[int] = set()

    for anlage_id, anlage_invs in by_anlage.items():
        eautos = [i for i in anlage_invs if i.typ == "e-auto" and not ist_dienstlich(i)]
        wallboxen = [i for i in anlage_invs if i.typ == "wallbox" and not ist_dienstlich(i)]
        if not eautos or not wallboxen:
            continue
        if len(wallboxen) > 1:
            multi_wb_anlagen += 1
            continue
        wb = wallboxen[0]
        ea_by_id = {e.id: e for e in eautos}

        ea_imds = (await session.execute(
            select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id.in_(list(ea_by_id.keys()))
            )
        )).scalars().all()
        wb_imds = (await session.execute(
            select(InvestitionMonatsdaten).where(
                InvestitionMonatsdaten.investition_id == wb.id
            )
        )).scalars().all()
        wb_imd_by_month: dict[tuple[int, int], InvestitionMonatsdaten] = {
            (m.jahr, m.monat): m for m in wb_imds
        }

        # Monate sammeln, in denen ein aktives E-Auto Heimladung trägt.
        monate: set[tuple[int, int]] = set()
        for m in ea_imds:
            inv = ea_by_id[m.investition_id]
            if not inv.ist_aktiv_im_monat(m.jahr, m.monat):
                continue
            pv, netz = _heim_trias(m.verbrauch_daten or {})
            if pv + netz > 0:
                monate.add((m.jahr, m.monat))

        for (jahr, monat) in sorted(monate):
            # Wallbox muss im Monat aktiv sein — sonst ist das E-Auto korrekt die
            # Quelle (z. B. Schuko-Ladung vor der Wallbox-Anschaffung).
            if not wb.ist_aktiv_im_monat(jahr, monat):
                continue

            # E-Auto-Seite (Summe über alle aktiven E-Autos des Monats).
            ea_pv = ea_netz = 0.0
            ea_month_imds: list[InvestitionMonatsdaten] = []
            for m in ea_imds:
                if m.jahr != jahr or m.monat != monat:
                    continue
                if not ea_by_id[m.investition_id].ist_aktiv_im_monat(jahr, monat):
                    continue
                pv, netz = _heim_trias(m.verbrauch_daten or {})
                ea_pv += pv
                ea_netz += netz
                ea_month_imds.append(m)
            if ea_pv + ea_netz <= 0:
                continue

            # Wallbox-Seite.
            wb_imd = wb_imd_by_month.get((jahr, monat))
            if wb_imd is not None:
                wb_pv, wb_netz = _heim_trias(wb_imd.verbrauch_daten or {})
            else:
                wb_pv = wb_netz = 0.0

            ea_total = ea_pv + ea_netz
            wb_total = wb_pv + wb_netz
            ea_wins = ea_total > wb_total
            winner_pv = ea_pv if ea_wins else wb_pv
            loser_pv = wb_pv if ea_wins else ea_pv

            # Unauflösbar: Gewinner ohne PV-Split, Verlierer mit PV → lossy.
            if winner_pv == 0 and loser_pv > 0:
                unaufloesbar += 1
                continue

            if ea_wins:
                # E-Auto-Trias in die Wallbox schreiben (IMD ggf. anlegen).
                if wb_imd is None:
                    wb_imd = InvestitionMonatsdaten(
                        investition_id=wb.id, jahr=jahr, monat=monat,
                        verbrauch_daten={},
                    )
                    session.add(wb_imd)
                    wb_imd_by_month[(jahr, monat)] = wb_imd
                vd = dict(wb_imd.verbrauch_daten or {})
                vd["ladung_pv_kwh"] = round(ea_pv, 3)
                vd["ladung_netz_kwh"] = round(ea_netz, 3)
                vd["ladung_kwh"] = round(ea_pv + ea_netz, 3)
                wb_imd.verbrauch_daten = vd
                flag_modified(wb_imd, "verbrauch_daten")
                migriert_monate += 1
            else:
                # Wallbox ist bereits die (≥) kanonische Quelle — nur E-Auto räumen.
                nur_geleert_monate += 1

            # E-Auto-Heim-Keys in allen Monats-IMDs räumen (km/Verbrauch/Extern/
            # V2H bleiben — fahrzeugspezifisch).
            for m in ea_month_imds:
                vd = dict(m.verbrauch_daten or {})
                if any(k in vd for k in _HEIM_KEYS):
                    for k in _HEIM_KEYS:
                        vd.pop(k, None)
                    m.verbrauch_daten = vd
                    flag_modified(m, "verbrauch_daten")

            betroffene_anlagen.add(anlage_id)

    await session.commit()

    logger.info(
        "Phase-2a-Emob-Migration: %d Monate Trias→Wallbox, %d Monate nur E-Auto "
        "geräumt, %d unauflösbar (Daten-Checker), %d Multi-WB-Anlagen übersprungen, "
        "%d Anlagen betroffen.",
        migriert_monate, nur_geleert_monate, unaufloesbar, multi_wb_anlagen,
        len(betroffene_anlagen),
    )

    if betroffene_anlagen or unaufloesbar or multi_wb_anlagen:
        try:
            from backend.services.activity_service import log_activity
            await log_activity(
                kategorie="migration",
                aktion="E-Mob-Heimladung auf Wallbox konsolidiert (Phase 2a)",
                details=(
                    f"{len(betroffene_anlagen)} Anlage(n): {migriert_monate} Monate "
                    f"E-Auto-Heimladung in die Wallbox verschoben, {nur_geleert_monate} "
                    f"Monate nur das (redundante) E-Auto geräumt. "
                    f"{unaufloesbar} Monat(e) blieben unverändert (uneindeutige "
                    f"Daten → Daten-Checker), {multi_wb_anlagen} Anlage(n) mit "
                    "mehreren Wallboxen übersprungen. Heimladung wird ab jetzt "
                    "kanonisch an der Wallbox geführt."
                ),
                erfolg=True,
            )
        except Exception as e:
            logger.warning(f"Activity-Log (Emob-Migration) fehlgeschlagen: {type(e).__name__}: {e}")
