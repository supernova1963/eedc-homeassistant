"""Der E-Mobilitäts-Kontext einer Sicht, die ``InvestitionMonatsdaten`` selbst lädt — N-555 Stufe 2.

Konzept Heimladung/Fahrverbrauch, Fassung 7.1, §4 (Regel 2, 3, 8). Die eine Funktion
(``eauto_wirtschaftlichkeit.entscheide_emob_heimladung``) braucht je Monat mehr als die privaten
Zeilen, seit ein Auto seine eigene Messung trägt:

* die **Dienstwagen** und **dienstlichen Wallboxen** — eine gemessene dienstliche Ladung fehlt im
  Rest der privaten Wallbox, eine dienstliche Wallbox in Betrieb macht die Felder der Dienstwagen
  wirkungslos (Regel 3);
* die **Herkunft** von ``ladung_kwh`` am E-Auto — „Heim: gesamt" oder alter Gesamtwert
  (Regel 8, E5; ``field_definitions.ist_heim_gesamt``);
* „Wallbox **in Betrieb**" auch ohne Monatszeile, für die Anreicherung (Phase 5) und den Entscheid.

**Warum ein eigenes Modul statt fünf Anpassungen.** Bis Stufe 2 baute jede dieser Sichten ihren
Kontext selbst (E-Auto-Hub, Wallbox-Hub, Aussichten, HA-Export zweimal) — mit derselben
Anreicherung, demselben ``build_emob_pool_ctx``-Aufruf und denselben Filtern. Das war die F-17-Lage
(„ein Mechanismus, den nur eine Route besitzt, baut die vierte Sicht nicht nach, sondern gar
nicht"). Mit den neuen Eingängen wären es fünf Stellen gewesen, an denen je einer fehlen kann —
jetzt ist es eine. Die Monats-Fakten bauen ihren Entscheid in ``monats_fakten/bau.py`` mit
denselben Eingängen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.field_definitions import ist_heim_gesamt
from backend.core.investition_parameter import ist_dienstlich
from backend.services.eauto_wirtschaftlichkeit import EmobPoolCtx, build_emob_pool_ctx
from backend.services.emob_heimlade_quellen import laufende_heimlade_quellen
from backend.services.emob_ladeanteil import reichere_monatszeilen_an_mit_quoten

__all__ = ["EmobKontext", "lade_emob_kontext"]


@dataclass
class EmobKontext:
    """Kontext + Zeilen einer Sicht."""
    #: Der Pool-Kontext mit dem Entscheid je Monat (``ctx.entscheide``).
    ctx: EmobPoolCtx
    #: ``(inv_id, jahr, monat) → verbrauch_daten`` aller E-Auto-/Wallbox-Zeilen in Betrieb —
    #: die privaten mit abgeleitetem PV-Anteil (Phase 5), die dienstlichen unverändert.
    daten: dict = field(default_factory=dict)
    #: Die abgeleitete PV-Quote je Monat, soweit geladen.
    quoten: dict = field(default_factory=dict)


async def lade_emob_kontext(
    db: AsyncSession,
    anlage_id: int,
    investitionen: Iterable,
    imd_zeilen: Iterable,
) -> EmobKontext:
    """Baut den E-Mob-Kontext aus den schon geladenen Monatszeilen einer Sicht.

    Args:
        investitionen: die Investitionen der Anlage (beliebige Typen; gefiltert wird hier).
        imd_zeilen: ``InvestitionMonatsdaten``-Objekte (beliebige Typen) — ihr
            ``source_provenance`` entscheidet „Heim: gesamt" oder Altwert.
    """
    emob = {i.id: i for i in investitionen if i.typ in ("e-auto", "wallbox")}
    privat_eautos = {i for i, inv in emob.items() if inv.typ == "e-auto" and not ist_dienstlich(inv)}
    privat_wallboxen = {i for i, inv in emob.items() if inv.typ == "wallbox" and not ist_dienstlich(inv)}
    dienstwagen = {i for i, inv in emob.items() if inv.typ == "e-auto" and ist_dienstlich(inv)}
    dienstliche_wallboxen = {
        i for i, inv in emob.items() if inv.typ == "wallbox" and ist_dienstlich(inv)
    }

    roh: dict = {}
    heim_gesamt: set = set()
    for imd in imd_zeilen:
        inv = emob.get(imd.investition_id)
        if inv is None or not inv.ist_aktiv_im_monat(imd.jahr, imd.monat):
            continue
        schluessel = (imd.investition_id, imd.jahr, imd.monat)
        daten = imd.verbrauch_daten or {}
        roh[schluessel] = daten
        if inv.typ == "e-auto" and ist_heim_gesamt(daten, imd.source_provenance):
            heim_gesamt.add(schluessel)

    def _wallbox_in_betrieb(jahr: int, monat: int) -> bool:
        return any(emob[i].ist_aktiv_im_monat(jahr, monat) for i in privat_wallboxen)

    def _eautos_in_betrieb(jahr: int, monat: int) -> list[int]:
        return [i for i in privat_eautos if emob[i].ist_aktiv_im_monat(jahr, monat)]

    def _dienstwagen_in_betrieb(jahr: int, monat: int) -> list[int]:
        return [i for i in dienstwagen if emob[i].ist_aktiv_im_monat(jahr, monat)]

    def _dienstliche_wallbox_in_betrieb(jahr: int, monat: int) -> bool:
        return any(emob[i].ist_aktiv_im_monat(jahr, monat) for i in dienstliche_wallboxen)

    privat = [k for k in roh if k[0] in privat_eautos or k[0] in privat_wallboxen]
    angereichert, quoten = await reichere_monatszeilen_an_mit_quoten(
        db,
        anlage_id,
        [((j, m), i in privat_wallboxen, roh[(i, j, m)]) for (i, j, m) in privat],
        wallbox_in_betrieb=_wallbox_in_betrieb,
    )
    daten = dict(roh)
    daten.update(zip(privat, angereichert))

    ctx = build_emob_pool_ctx(
        daten,
        privat_eautos,
        privat_wallboxen,
        wallbox_in_betrieb=_wallbox_in_betrieb,
        quoten=quoten,
        quellen_je_monat=await laufende_heimlade_quellen(db, anlage_id, list(emob.values())),
        dienstwagen_ids=dienstwagen,
        dienstliche_wallbox_ids=dienstliche_wallboxen,
        dienstliche_wallbox_in_betrieb=_dienstliche_wallbox_in_betrieb,
        heim_gesamt_keys=heim_gesamt,
        # Regel 2 Schritt 3: Empfänger des Rests sind alle privaten Autos in Betrieb,
        # auch die ohne Monatszeile (0 km, E6).
        eauto_in_betrieb=_eautos_in_betrieb,
        # W-1: „nur eine Wallbox" nur ohne privates Auto UND ohne Dienstwagen in Betrieb.
        dienstwagen_in_betrieb=_dienstwagen_in_betrieb,
    )
    return EmobKontext(ctx=ctx, daten=daten, quoten=quoten)
