"""Prognose-Kanon — EIN kanonischer Rechenweg für die PV-Tagesprognose.

Single Source of Truth für „PV-Tagesprognose heute (+ Rest, + morgen/
übermorgen, + VM/NM, + Stundenprofil)". Vor diesem Service holten vier Pfade
(``live_wetter``, ``solar_forecast_service``, ``eedc_prognose_service``,
``ha_export_prognose``) OpenMeteo je eigenständig, korrigierten an
verschiedenen Stellen (GTI vs. Energie-Slot) und mit verschiedenen
losses-Quellen → vier verschiedene „heute"-Werte (Rainer-PN 2026-06-26).

Bau-Vertrag: ``docs/drafts/archive/KONZEPT-PROGNOSE-KANON.md``.

Kanon-Rechenweg (abgenommen):

1. **Orientierungsgruppen** (``pv_orientation.orientierungs_gruppen``) — Multi-
   String-Fan-out wie der Live-Pfad: pro Gruppe ein OpenMeteo-Abruf
   (``get_solar_prognose``, PVGIS-Losses via ``resolve_system_losses``,
   Wettermodell aus ``Anlage.wetter_modell`` — A30/N16).
2. **Gruppen slot-weise summieren** → rohes OM-kWh-Stundenprofil/Tag
   (= „OpenMeteo"-Spalte überall, multi-string, unkorrigiert).
3. **eedc-Korrektur PRO ENERGIE-SLOT** (``korrigiere_tagesprofil`` +
   Kaskade ``korrekturfaktoren_fuer_tag``): GTI bleibt voll im Basismodell
   (GTI→kWh mit Temp/Schnee), nur der gelernte Residual-Faktor liegt auf der
   Energie — self-consistent (Faktor = Σ IST_kWh / Σ Prognose_kWh) und
   Invariante ``tageswert == Σ Export-Slots``.
4. **VM/NM**-Split an Solar-Noon; **rest_heute**/**ist_bisher**/
   **heute_rollend** aus den korrigierten Slots + ``TagesEnergieProfil``.
5. **Bestandsfilter je Prognosetag** (N31): Anschaffungs-/Stilllegungsdatum
   werden gegen das jeweilige TAGESDATUM geprüft, nicht gegen heute — ein am
   Tag +5 stillgelegter String zählt ab Tag +5 nicht mehr mit.

Konsumenten (alle über diesen Service → per Konstruktion derselbe Wert):
``eedc_prognose_service`` (dünner Adapter), ``live_wetter`` (Anzeige +
Persistenz + Chart-Slots), ``ha_export_prognose`` (MQTT), ``api/routes/
prognosen`` (Vergleich eedc-/OM-Spalte).

Robustheit: fehlende Koordinaten/kWp/OpenMeteo → ``None``. Multi-String-
Unvollständigkeit (#306) wird pro Tag als ``om_vollstaendig=False`` markiert,
damit der Persist-Pfad einen kollabierten Tageswert NICHT einfriert.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select

from backend.core.berechnungen.prognose_korrektur import (
    KorrigiertesTagesprofil,
    korrigiere_tagesprofil,
)
from backend.models.investition import Investition
from backend.services.prognose_auswahl import lade_aktive_prognose
from backend.models.tages_energie_profil import TagesEnergieProfil
from backend.services import solar_forecast_service as sfs
from backend.services.korrekturprofil_lookup import korrekturfaktoren_fuer_tag
from backend.services.pv_orientation import (
    Orientierungsgruppe,
    get_pv_azimut,
    get_pv_neigung,
    orientierungs_gruppen,
    resolve_system_losses,
)
from backend.core.investition_kennwerte import get_erzeuger_kwp, get_wr_grenze_kw
from backend.core.berechnungen.wr_kappung import (
    hat_kappung,
    kappe_profil,
    kappungs_faktor,
)

logger = logging.getLogger(__name__)

_BERLIN_TZ = ZoneInfo("Europe/Berlin")


@dataclass
class KanonTag:
    """Kanonische Prognose eines Tages (Offset ab heute)."""

    datum: str
    om_kwh: Optional[float]            # Multi-String roh-OM-Tagessumme (= OM-Spalte)
    eedc_kwh: Optional[float]          # korrigierte Tagessumme (= Σ Export-Slots)
    vm_kwh: Optional[float]            # eedc vor Solar-Noon
    nm_kwh: Optional[float]            # eedc ab Solar-Noon
    # Korrigiertes Stundenprofil (eedc); None im OpenMeteo-Schätzpfad ohne
    # Hourly-Basis (dann eedc_kwh = Σ Tages-Ertrag × Skalar).
    profil: Optional[KorrigiertesTagesprofil]
    om_stundenprofil_kwh: Optional[list]   # 24 roh-OM-Slots (multi-string)
    om_vollstaendig: bool             # #306: False wenn Fan-out untergewichtet


@dataclass
class KanonPrognose:
    """Kanonische Prognose über mehrere Tage. ``tage[i]`` = heute + i Tage."""

    tage: list[Optional[KanonTag]]
    rest_heute_kwh: Optional[float]    # laufende Stunde anteilig + Σ Slots danach (#339)
    ist_bisher_kwh: Optional[float]    # IST heute bis jetzt (TagesEnergieProfil)
    heute_rollend_kwh: Optional[float]  # ist_bisher + rest_heute
    skalar_fallback: Optional[float]   # Legacy-Lernfaktor (Diagnose/Fallback)


# Untergrenze des Kanon-Horizonts: so viele Tage, wie der weitest blickende
# Konsument braucht — MQTT/HA-Export und der Prognosen-Vergleich lesen fix
# `tage[0..3]`.
#
# Bis A29 stand hier eine zweite, inzwischen überholte Begründung: der
# OpenMeteo-Cache-Key enthielt `days`, weshalb ein abweichender Horizont einen
# ANDEREN Snapshot desselben Tages zog und 4 der erzwungene gemeinsame Nenner
# war. Seit E15 bestimmt nicht mehr der Aufrufer den Cache-Key, sondern das
# Wettermodell (`services/wetter/cache.snapshot_days`) — `days` ist hier wieder
# das, was es sein soll: wie viele Tage der Kanon RECHNET.
KANON_MIN_DAYS = 4


def kanon_days(horizont_tage: int) -> int:
    """``days`` für ``kanon_tagesprognose`` aus dem gewünschten Horizont.

    EINE Horizont-Formel für alle Aufrufer mit variablem Ziel (Tagesprognose-
    Datumspicker, ``/solar-prognose?tage=N``): mindestens ``KANON_MIN_DAYS``,
    darüber der angefragte Horizont. OpenMeteo deckelt selbst bei 16
    (``fetch_gti_forecast``), der Picker erlaubt +14 → maximal 15.
    """
    return max(int(horizont_tage), KANON_MIN_DAYS)


async def _pv_invs_im_horizont(db, anlage, von: date, bis: date) -> list[Investition]:
    """PV-/BKW-Investitionen, die im Horizont [von, bis] **irgendwann** aktiv sind.

    Obermenge für den Fan-out; die tagesgenaue Gewichtung passiert danach über
    ``ist_aktiv_an`` je Prognosetag (N31). Vorher filterte der Kanon gegen HEUTE
    und ignorierte das Anschaffungsdatum — ein am Zieltag bereits stillgelegter
    (oder erst später angeschaffter) String zählte im ganzen Horizont mit.
    """
    res = await db.execute(
        select(Investition).where(
            Investition.anlage_id == anlage.id,
            Investition.typ.in_(["pv-module", "balkonkraftwerk"]),
            Investition.aktiv.is_(True),
        )
    )
    return [i for i in res.scalars().all() if i.ist_aktiv_im_zeitraum(von, bis)]


def _tages_gewichte(
    invs: list[Investition],
    gruppen: list[Orientierungsgruppe],
    tage: list[date],
) -> Optional[list[list[float]]]:
    """kWp-Anteil je (Tag, Orientierungsgruppe) — ``None``, wenn durchgehend 1.

    Hintergrund (N31): OpenMeteo wird EINMAL je Orientierungsgruppe über den
    ganzen Horizont abgerufen; wechselt der Bestand innerhalb des Horizonts
    (Anschaffung/Stilllegung), muss der Ertrag dieser Gruppe pro Tag auf die an
    diesem Tag aktive kWp heruntergewichtet werden. Das ist exakt äquivalent zu
    einem eigenen Abruf mit kleinerer kWp: ``berechne_pv_ertrag`` ist strikt
    linear in kWp (kWp ist reiner Multiplikator; Temperatur-/Schnee-Korrektur
    hängen nicht davon ab).

    ``None`` heißt „kein Bestandswechsel im Horizont" — der Normalfall läuft
    dann rechnerisch unverändert (keine zusätzliche Multiplikation, keine
    Rundungsdrift gegenüber vorher).
    """
    if not invs or not gruppen:
        return None
    if not any(
        (i.anschaffungsdatum and i.anschaffungsdatum > tage[0])
        or (i.stilllegungsdatum and i.stilllegungsdatum < tage[-1])
        for i in invs
    ):
        return None

    keys = [(g.neigung, g.ausrichtung) for g in gruppen]
    gewichte: list[list[float]] = []
    for tag in tage:
        # Bewusst über die SoT-Gruppierung, damit die kWp-Ermittlung (Spalte →
        # parameter-JSON → Default) dieselbe ist wie beim Fan-out.
        kwp_am_tag = {
            (g.neigung, g.ausrichtung): g.kwp
            for g in orientierungs_gruppen([i for i in invs if i.ist_aktiv_an(tag)])
        }
        gewichte.append([
            (kwp_am_tag.get(k, 0.0) / g.kwp) if g.kwp else 0.0
            for k, g in zip(keys, gruppen)
        ])
    return gewichte


def _kappungs_mitglieder(
    invs: list[Investition], gruppen: list[Orientierungsgruppe], tag: date,
) -> list[list[tuple[float, Optional[float]]]]:
    """(kWp, AC-Grenze) je Gruppe für die an `tag` aktiven Komponenten.

    Nur nötig, wenn überhaupt eine AC-Grenze gepflegt ist (#347) — sonst nimmt
    der Aufrufer den unveränderten Pfad mit den kWp-Tagesgewichten, und die
    Rechnung bleibt für alle anderen Anlagen bitgleich.

    Die Gruppenzuordnung läuft über dieselben Helper wie
    ``orientierungs_gruppen``, damit ein Mitglied nicht in einer anderen Gruppe
    landet als beim Fan-out.
    """
    index = {(g.neigung, g.ausrichtung): i for i, g in enumerate(gruppen)}
    mitglieder: list[list[tuple[float, Optional[float]]]] = [[] for _ in gruppen]
    for inv in invs:
        if not inv.ist_aktiv_an(tag):
            continue
        kwp = get_erzeuger_kwp(inv)
        if kwp <= 0:
            continue
        pos = index.get((int(get_pv_neigung(inv)), int(get_pv_azimut(inv))))
        if pos is None:
            continue
        mitglieder[pos].append((kwp, get_wr_grenze_kw(inv)))
    return mitglieder


async def kanon_tagesprognose(
    db,
    anlage,
    days: int = 4,
    skip_jitter: bool = False,
) -> Optional[KanonPrognose]:
    """Berechnet die kanonische PV-Tagesprognose einer Anlage.

    Quelle ist IMMER die eedc-eigene Prognose (OpenMeteo-Basis × Korrektur) —
    Solcast/SFML sind eigene Pfade. Als OpenMeteo-Basis dient das in der Anlage
    gewählte ``wetter_modell`` (A30/N16, s. u.). ``None`` bei fehlenden
    Koordinaten, fehlender PV-Leistung oder fehlgeschlagenem OpenMeteo-Abruf.
    """
    if not anlage.latitude or not anlage.longitude:
        return None

    heute = date.today()
    tagesdaten = [heute + timedelta(days=o) for o in range(days)]
    invs = await _pv_invs_im_horizont(db, anlage, tagesdaten[0], tagesdaten[-1])
    gruppen = orientierungs_gruppen(invs)
    # N31: kWp-Gewicht je (Tag, Gruppe); None = Bestand ändert sich im Horizont
    # nicht (Normalfall → Rechnung bleibt bitgleich zu vorher).
    gewichte = _tages_gewichte(invs, gruppen, tagesdaten)

    if not gruppen:
        # Keine Modul-Orientierung gepflegt → eine Default-Gruppe aus der
        # Anlage-Gesamtleistung (Süd/35°), damit Bestandsanlagen ohne
        # Orientierungs-Pflege weiter eine Prognose erhalten.
        kwp = anlage.leistung_kwp or 0.0
        if kwp <= 0:
            return None
        gruppen = [Orientierungsgruppe(neigung=35, ausrichtung=0, kwp=kwp)]

    system_losses = resolve_system_losses(await lade_aktive_prognose(db, anlage.id))

    # A30/N16: das in der Anlage gewählte Wettermodell — in derselben Form wie
    # `prefetch_service` und `/solar-prognose` (WETTER_MODELLE-Key; die Kaskade
    # „bevorzugtes Modell + best_match für die Tage jenseits seines Horizonts"
    # steckt in `get_solar_prognose`, hier wird nichts nachgebaut).
    #
    # Bis dahin rechnete der Kanon IMMER mit best_match, während Live-Wetter,
    # 14-Tage-Wettertabelle und die OpenMeteo-Spalte in `/solar-prognose` das
    # gewählte Modell schon nutzten: dieselbe Seite zeigte für denselben Tag
    # OM-Balken aus Modell A und den eedc-Wert aus Modell B, und der MQTT-/HA-
    # Export folgte dem Kanon (= best_match). Für `wetter_modell="auto"` — den
    # Default — ändert sich dadurch nichts.
    wetter_modell = getattr(anlage, "wetter_modell", None) or "auto"

    # Fan-out: pro Orientierungsgruppe ein get_solar_prognose (eigener Cache-
    # Eintrag, parallel). Aufruf über das Modul (sfs.) — Monkeypatch-fähig.
    coros = [
        sfs.get_solar_prognose(
            latitude=anlage.latitude,
            longitude=anlage.longitude,
            kwp=g.kwp,
            neigung=g.neigung,
            ausrichtung=g.ausrichtung,
            days=days,
            system_losses=system_losses,
            wetter_modell=wetter_modell,
            skip_jitter=skip_jitter,
        )
        for g in gruppen
    ]
    ergebnisse = await asyncio.gather(*coros)
    if all(r is None or not getattr(r, "tageswerte", None) for r in ergebnisse):
        return None

    # Pro Gruppe: Tag-Index nach Datum.
    by_datum: list[dict] = []
    for r in ergebnisse:
        if r is None or not getattr(r, "tageswerte", None):
            by_datum.append({})
        else:
            by_datum.append({t.datum: t for t in r.tageswerte})

    # Legacy-Skalar (Kaskaden-Miss-Fallback). Function-local Import =
    # Monkeypatch-fähig (Tests patchen live_wetter._get_lernfaktor).
    from backend.api.routes.live_wetter import _get_lernfaktor
    skalar = await _get_lernfaktor(anlage.id, db)

    # #347: AC-Grenze eines Wechselrichters. Nur wenn überhaupt eine gepflegt
    # ist, wird je Komponente gerechnet — sonst bleibt der Pfad unverändert.
    kappung_aktiv = any(get_wr_grenze_kw(i) for i in invs)

    tage: list[Optional[KanonTag]] = []
    for offset in range(days):
        datum = tagesdaten[offset]
        datum_iso = datum.isoformat()
        mitglieder = (
            _kappungs_mitglieder(invs, gruppen, datum) if kappung_aktiv else None
        )

        om_slots = [0.0] * 24
        pv_ertrag_sum = 0.0
        groups_present = 0
        has_hourly = False
        wetter_bew = wetter_nieder = wetter_code = None

        for grp_idx in range(len(gruppen)):
            tag = by_datum[grp_idx].get(datum_iso)
            if tag is None:
                continue
            groups_present += 1
            # N31: Anteil der an DIESEM Tag aktiven kWp der Gruppe (1.0, wenn
            # sich im Horizont nichts ändert). Ein Faktor 0 ist kein fehlender
            # Tag — die Gruppe hat an diesem Tag legitim keinen Ertrag.
            gew = gewichte[offset][grp_idx] if gewichte is not None else 1.0
            stunden_kw = getattr(tag, "stunden_kw", None)
            tages_kwh = getattr(tag, "pv_ertrag_kwh", 0.0) or 0.0

            # #347: gepflegte AC-Grenze ⇒ je Komponente rechnen und stündlich
            # kappen. Das ersetzt das kWp-Tagesgewicht (`gew`) — die Mitglieder
            # sind bereits die an DIESEM Tag aktiven, die Gewichtung steckt
            # also in der Mitgliederliste statt in einem Skalar.
            grp_mitglieder = mitglieder[grp_idx] if mitglieder is not None else None
            if grp_mitglieder and hat_kappung(grp_mitglieder) and stunden_kw:
                gekappt = kappe_profil(stunden_kw, gruppen[grp_idx].kwp, grp_mitglieder)
                pv_ertrag_sum += tages_kwh * kappungs_faktor(
                    stunden_kw, gruppen[grp_idx].kwp, grp_mitglieder
                )
                if any(gekappt):
                    has_hourly = True
                    for h in range(min(24, len(gekappt))):
                        om_slots[h] += gekappt[h]
            else:
                pv_ertrag_sum += tages_kwh * gew
                if stunden_kw and any(v for v in stunden_kw):
                    has_hourly = True
                    for h in range(min(24, len(stunden_kw))):
                        om_slots[h] += (stunden_kw[h] or 0.0) * gew
            # Wetter ist standort- (nicht orientierungs-)abhängig → erste
            # liefernde Gruppe genügt für die Kaskaden-Klassifikation.
            if wetter_bew is None:
                wetter_bew = getattr(tag, "stunden_bewoelkung", None)
                wetter_nieder = getattr(tag, "stunden_niederschlag", None)
                wetter_code = getattr(tag, "stunden_wetter_code", None)

        # #306: untergewichtet, wenn nicht alle Gruppen den Tag lieferten.
        om_vollstaendig = groups_present == len(gruppen)

        if groups_present == 0:
            tage.append(None)
            continue

        if has_hourly:
            faktoren = await korrekturfaktoren_fuer_tag(
                db,
                anlage_id=anlage.id,
                lat=anlage.latitude,
                lon=anlage.longitude,
                datum=datum,
                stunden_bewoelkung=wetter_bew,
                stunden_niederschlag=wetter_nieder,
                stunden_wetter_code=wetter_code,
            )
            profil = korrigiere_tagesprofil(om_slots, faktoren, fallback_faktor=skalar)
            eedc_kwh = profil.tageswert_kwh
            om_kwh = round(sum(om_slots), 1)
            vm_kwh, nm_kwh = _vm_nm_split(
                profil.stundenprofil_export_kwh, datum_iso, anlage.longitude
            )
        else:
            # OpenMeteo-Schätzpfad (Tagessumme ohne Hourly): Tages-Ertrag ×
            # Skalar, kein Profil (bisheriges Verhalten, eedc_prognose_service).
            profil = None
            eedc_kwh = (
                round(pv_ertrag_sum * (skalar or 1.0), 1) if pv_ertrag_sum else None
            )
            om_kwh = round(pv_ertrag_sum, 1) if pv_ertrag_sum else None
            vm_kwh = nm_kwh = None

        tage.append(KanonTag(
            datum=datum_iso,
            om_kwh=om_kwh,
            eedc_kwh=eedc_kwh,
            vm_kwh=vm_kwh,
            nm_kwh=nm_kwh,
            profil=profil,
            om_stundenprofil_kwh=[round(v, 3) for v in om_slots] if has_hourly else None,
            om_vollstaendig=om_vollstaendig,
        ))

    # Rollende „heute"-Größen aus den korrigierten Slots + IST.
    rest_heute = ist_bisher = heute_rollend = None
    heute_tag = tage[0] if tage else None
    if heute_tag is not None and heute_tag.profil is not None:
        from backend.services.prognose_adapter import ist_profil
        now = datetime.now(_BERLIN_TZ)
        slots = heute_tag.profil.stunden_kwh
        # #339: laufende Stunde anteilig nach verstrichenen Minuten. Backward-
        # Konvention (#144): Slot N = Energie [N-1, N), also ist slots[now.hour]
        # bereits abgelaufen und slots[now.hour + 1] die laufende Stunde. Ohne den
        # frac-Term sinkt der Rest nur einmal je Stunde in EINEM Sprung (bei
        # kleinen Anlagen 5–8 kWh) statt gleichmäßig.
        frac = 1.0 - now.minute / 60.0
        laufend = frac * slots[now.hour + 1] if now.hour + 1 < len(slots) else 0.0
        rest_heute = round(
            laufend + sum(slots[h] for h in range(now.hour + 2, len(slots))), 1
        )
        ist_res = await db.execute(
            select(TagesEnergieProfil).where(
                TagesEnergieProfil.anlage_id == anlage.id,
                TagesEnergieProfil.datum == heute,
            ).order_by(TagesEnergieProfil.stunde)
        )
        ist_p = ist_profil(ist_res.scalars().all(), jetzt_stunde=now.hour, datum=heute)
        ist_bisher = round(ist_p.tageswert_kwh or 0.0, 1)
        heute_rollend = round(ist_bisher + rest_heute, 1)

    return KanonPrognose(
        tage=tage,
        rest_heute_kwh=rest_heute,
        ist_bisher_kwh=ist_bisher,
        heute_rollend_kwh=heute_rollend,
        skalar_fallback=skalar,
    )


def _vm_nm_split(
    export_slots, datum_iso: str, longitude: Optional[float]
) -> tuple[Optional[float], Optional[float]]:
    """Splittet die korrigierten Export-Slots am Solar-Noon (Backward-Slots).

    Slot ``h`` = Energie im Intervall ``[h-1, h)``. Konsistent zur
    ``_berechne_tageshaelfte``-Logik im Prognosen-Vergleich.
    """
    if longitude is None:
        return None, None
    noon = sfs._solar_noon_hour(datum_iso, longitude)
    vm = 0.0
    nm = 0.0
    for h in range(24):
        wert = export_slots[h] if h < len(export_slots) else 0.0
        slot_start = h - 1
        if h <= noon:
            vm += wert
        elif slot_start >= noon:
            nm += wert
        else:
            frac_vm = max(0.0, min(1.0, noon - slot_start))
            vm += wert * frac_vm
            nm += wert * (1 - frac_vm)
    return round(vm, 1), round(nm, 1)
