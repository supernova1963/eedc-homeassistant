"""Werkbank-Operation «Werte vor dem Sensorbeginn verwerfen» (HA-Bauform S3, E-S3-5; Bauplan §7, Entscheid S3-E2).

**Was sie tut.** Für **ein** zugeordnetes Feld (einen Zählerkanal ``basis:<feld>`` bzw. ``inv:<id>:<feld>``) und einen
Zeitpunkt ``t`` (Vorbelegung: Beginn der jüngsten Quelle = des neuen Sensors) verwirft sie die Werte des alten Sensors
in **beiden Schichten, feldgenau, ohne eine Zeile zu löschen** (außer den Kanalzeilen der älteren Quellen):

* **Kanalschicht** (``services/kanal/verwerfen.py``): ``kanal_statistik``-Zeilen der älteren Quellen mit ``start_ts < t``
  löschen; die ``kanal_quelle``-Zeilen bleiben als Herkunft mit Marke ``verworfen_ts``.
* **Bestand** (hier): für die Tage, deren Tagesfenster ganz vor ``t`` liegt, in ``TagesEnergieProfil`` (Stunden) und
  ``TagesZusammenfassung`` (Tag) **nur die Schlüssel dieses Feldes** leeren, über die Provenance-Schreiber mit Quelle
  ``verworfen:werkbank``: den ``komponenten_kwh``-Eintrag (Beitragsschicht ``komponenten_beitraege``: genau die Ziel-Schlüssel,
  in die dieses Feld schreibt), bei ``basis:einspeisung``/``basis:netzbezug`` dazu die Achsenspalte der Stunde und den
  ``spannen``-Eintrag der Achse; bei ``basis:pv_gesamt`` statt der geteilten Spalte ``pv_kw`` die aus dem Anlagenwert
  zerlegten Geräte-Einträge (#406-Marke ``kwp_anteil``; ⛔ H-5 im Bericht E-S3-5).
  **Monate mit Abschluss bleiben unberührt** — eedc erkennt den Abschluss an der ``Monatsdaten``-Zeile des Monats
  (``monats_fakten/laden.py``: ``monatsdaten_by_ym``; ohne Zeile rechnet der Monat aus den Tagen, Lesart 1).
* **Bleibt stehen:** Wetter, Prognose, Preise, Betriebsart, SoC, andere Geräte, die abgeleiteten Stundengrößen
  (``verbrauch_kw``, ``ueberschuss_kw``, ``defizit_kw``) und die Tagesgrößen daraus, die Marken ``verworfen``/``nachtrag``
  der Tageszeile — und ``TagesEnergieProfil.komponenten``: diese Spalte ist der **Leistungspfad** (Stundenmittel der
  Leistungssensoren, Bauplan S3-R6 / E-S3-1 H-1), nicht der Wert dieses Zählers (⛔ H-3 im Bericht E-S3-5; die Vorschau
  nennt, wie viele Stunden des Geräts er trägt).

**Ein Lauf, idempotent:** der zweite Lauf findet keine Kanalzeile und keinen Schlüssel mehr und sagt «nichts zu
verwerfen». **Kein Rückweg:** die Vorschau sagt, dass die Werte danach weg sind. Aktivität in derselben Sitzung (N-532).

Schwesterdateien: ``services/kanal/verwerfen.py``, ``services/repair_orchestrator.py`` (``_plan_/_execute_verwerfen_…``),
Tests ``test_werkbank_verwerfen_vor_quellbeginn.py``, ``test_werkbank_verwerfen_kommt_nicht_zurueck.py``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.zahlenformat import fmt_datum, fmt_zahl
from backend.models.anlage import Anlage
from backend.models.investition import Investition
from backend.models.kanal import Kanal
from backend.models.monatsdaten import Monatsdaten
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.services.kanal import verwerfen as kv

logger = logging.getLogger(__name__)

QUELLE = "verworfen:werkbank"
WRITER = "repair_orchestrator:verwerfen_vor_quellbeginn"
_GRUND = "Werkbank «Werte vor dem Sensorbeginn verwerfen»"
#: #406: ein ``komponenten_kwh``-Sub-Key, der aus dem Anlagenwert ``pv_gesamt`` zerlegt wurde (``provenance.ABGELEITET_KWP_ANTEIL``).
_PV_AGGREGAT_MARKE = "kwp_anteil"


# ── Was «dieses Feld» im Bestand ist ────────────────────────────────────────


@dataclass(frozen=True)
class BestandZiele:
    """Die Schlüssel des Bestands, die zu EINEM Feld gehören."""

    #: Achsenspalte der Stundenzeile (nur ``basis:*``), z. B. ``einspeisung_kw``.
    spalte: Optional[str] = None
    #: ``spannen``-Eintrag der Achse (nur ``basis:*``).
    spannen_achse: Optional[str] = None
    #: ``komponenten_kwh``-Schlüssel, in die dieses Feld schreibt (Beitragsschicht).
    tz_keys: frozenset[str] = frozenset()
    #: ``basis:pv_gesamt``: dazu die aus dem Anlagenwert zerlegten Sub-Keys (#406-Marke).
    pv_aggregat: bool = False
    #: Andere Felder, die in dieselben ``komponenten_kwh``-Schlüssel schreiben (der Eintrag wird als Ganzes geleert).
    mitbetroffen: tuple[str, ...] = ()
    #: Investition (für die Zählung des Leistungspfads, der stehen bleibt — H-3).
    inv_id: Optional[int] = None


def _basis_ziele(feld: str) -> BestandZiele:
    """Einspeisung/Netzbezug: die Achsenspalte und ihr ``spannen``-Eintrag gehören dem Feld allein. ``pv_gesamt``: die Achse
    ``pv`` ist geteilt (``pv_kw`` = Σ aller PV-/Erzeuger-Zähler der Stunde, #406 wählt je Tag Anlagen- ODER Geräte-Zähler) —
    Spalte und Spanne bleiben; geleert werden die aus dem Anlagenwert zerlegten Tageswerte (⛔ H-5 im Bericht E-S3-5)."""
    from backend.core.berechnungen.spannen import _SPALTE_JE_ACHSE, achse_der_kategorie
    from backend.services.snapshot.keys import BASIS_ZAEHLER_FELDER, _categorize_counter

    if feld not in BASIS_ZAEHLER_FELDER:
        return BestandZiele()
    if feld == "pv_gesamt":
        return BestandZiele(tz_keys=frozenset({feld}), pv_aggregat=True)
    achse = achse_der_kategorie(_categorize_counter(feld, None, None))
    return BestandZiele(spalte=_SPALTE_JE_ACHSE.get(achse or ""), spannen_achse=achse, tz_keys=frozenset({feld}))


def _inv_ziele(inv: Investition, mapping_inv: dict, feld: str, kanal_keys: set[str]) -> BestandZiele:
    """Ziel-Schlüssel über ``investition_beitraege`` — mit der Verfügbarkeit, die die Anlage heute hat (Feld mit Kanal
    oder HA-Sensor), damit Stufen- und Ersatzregeln (Wärmepumpe K3, E-Auto, Sonstiges) wie im Lauf entscheiden."""
    from backend.services.snapshot.komponenten_beitraege import _is_sensor_mapping, investition_beitraege

    felder = (mapping_inv or {}).get("felder", {}) or {}

    def verfuegbar(f: str) -> bool:
        return f == feld or f"inv:{inv.id}:{f}" in kanal_keys or _is_sensor_mapping(felder.get(f))

    beitraege = investition_beitraege(inv, mapping_inv or {}, ist_verfuegbar=verfuegbar)
    ziele = frozenset(b.target_key for b in beitraege if b.feld == feld)
    mit = tuple(sorted({f"inv:{inv.id}:{b.feld}" for b in beitraege if b.feld != feld and b.target_key in ziele}))
    return BestandZiele(tz_keys=ziele, mitbetroffen=mit, inv_id=inv.id)


async def bestand_ziele(db: AsyncSession, anlage: Anlage, key: str) -> BestandZiele:
    teile = key.split(":")
    if teile[0] == "basis":
        return _basis_ziele(teile[1])
    inv = (await db.execute(select(Investition).where(and_(
        Investition.anlage_id == anlage.id, Investition.id == int(teile[1]))))).scalar_one_or_none()
    if inv is None:
        return BestandZiele()
    kanal_keys = set((await db.execute(select(Kanal.key).where(Kanal.anlage_id == anlage.id))).scalars().all())
    mapping_inv = ((anlage.sensor_mapping or {}).get("investitionen") or {}).get(str(inv.id)) or {}
    return _inv_ziele(inv, mapping_inv, teile[2], kanal_keys)


def feld_label(key: str, invs: dict[int, Investition]) -> str:
    """«Süddach · Erzeugung» bzw. «Anlage · Einspeisung» — der Name des Feldes für Vorschau und Auswahl."""
    from backend.core.field_definitions import FELD_LABELS

    teile = key.split(":")
    feld = teile[-1]
    if teile[0] == "basis":
        return f"Anlage · {FELD_LABELS.get(feld, feld)}"
    inv = invs.get(int(teile[1]))
    name = inv.bezeichnung if inv is not None else f"Gerät {teile[1]}"
    return f"{name} · {FELD_LABELS.get(feld, feld)}"


async def _investitionen(db: AsyncSession, anlage_id: int) -> dict[int, Investition]:
    return {i.id: i for i in (await db.execute(
        select(Investition).where(Investition.anlage_id == anlage_id))).scalars().all()}


async def abschluss_monate(db: AsyncSession, anlage_id: int) -> frozenset[tuple[int, int]]:
    """Monate mit Abschluss = Monate mit ``Monatsdaten``-Zeile (dieselbe Weiche wie ``monats_fakten/laden.py``)."""
    return frozenset((int(j), int(m)) for j, m in (await db.execute(
        select(Monatsdaten.jahr, Monatsdaten.monat).where(Monatsdaten.anlage_id == anlage_id))).all())


def _im_abschluss(tag: date, abschluss: frozenset[tuple[int, int]]) -> bool:
    return (tag.year, tag.month) in abschluss


# ── Bestand: zählen ─────────────────────────────────────────────────────────


def _hat(spalte, key: str):
    return func.json_type(spalte, f'$."{key}"').is_not(None)


def _tep_bedingung(ziele: BestandZiele):
    teile = []
    if ziele.spalte:
        teile.append(getattr(TagesEnergieProfil, ziele.spalte).is_not(None))
    if ziele.spannen_achse:
        teile.append(_hat(TagesEnergieProfil.spannen, ziele.spannen_achse))
    return or_(*teile) if teile else None


def _tz_bedingung(ziele: BestandZiele):
    teile = [_hat(TagesZusammenfassung.komponenten_kwh, k) for k in sorted(ziele.tz_keys)]
    if ziele.pv_aggregat:
        teile.append(TagesZusammenfassung.source_provenance.like(f"%{_PV_AGGREGAT_MARKE}%"))
    return or_(*teile) if teile else None


def _pv_aggregat_keys(row: TagesZusammenfassung) -> list[str]:
    """Sub-Keys von ``komponenten_kwh``, die die #406-Marke tragen (aus dem Anlagenwert zerlegt)."""
    prov = row.source_provenance or {}
    werte = row.komponenten_kwh or {}
    return [k for k in werte if (prov.get(f"komponenten_kwh.{k}") or {}).get("abgeleitet") == _PV_AGGREGAT_MARKE]


def tz_keys_der_zeile(row: TagesZusammenfassung, ziele: BestandZiele) -> list[str]:
    werte = row.komponenten_kwh or {}
    keys = [k for k in sorted(ziele.tz_keys) if k in werte]
    if ziele.pv_aggregat:
        keys += [k for k in _pv_aggregat_keys(row) if k not in keys]
    return keys


@dataclass
class BestandZaehlung:
    """Was der Bestand vor ``t`` von diesem Feld trägt (Monate mit Abschluss getrennt gezählt)."""

    tage: set[date] = field(default_factory=set)
    stundenzeilen: int = 0
    tageszeilen: int = 0
    abschluss_tage: set[date] = field(default_factory=set)
    #: Stunden, in denen der Leistungspfad (``komponenten``) einen Eintrag des Geräts trägt — bleibt stehen (H-3).
    leistungspfad_stunden: int = 0


async def _tep_daten(db: AsyncSession, anlage_id: int, bis_tag: date, ziele: BestandZiele) -> list[date]:
    bed = _tep_bedingung(ziele)
    if bed is None:
        return []
    return [d for (d,) in (await db.execute(select(TagesEnergieProfil.datum).where(and_(
        TagesEnergieProfil.anlage_id == anlage_id, TagesEnergieProfil.datum <= bis_tag, bed)))).all()]


async def _tz_zeilen(db: AsyncSession, anlage_id: int, bis_tag: date, ziele: BestandZiele) -> list[TagesZusammenfassung]:
    bed = _tz_bedingung(ziele)
    if bed is None:
        return []
    return list((await db.execute(select(TagesZusammenfassung).where(and_(
        TagesZusammenfassung.anlage_id == anlage_id, TagesZusammenfassung.datum <= bis_tag, bed))
        .order_by(TagesZusammenfassung.datum))).scalars().all())


async def _leistungspfad_stunden(db: AsyncSession, anlage_id: int, bis_tag: date, inv_id: Optional[int]) -> int:
    """Stunden vor ``bis_tag`` mit einem ``komponenten``-Eintrag des Geräts (``<kategorie>_<id>``, ohne ``soc_``)."""
    if inv_id is None:
        return 0
    from sqlalchemy import text

    return int((await db.execute(text(
        "SELECT count(*) FROM tages_energie_profil t WHERE t.anlage_id = :a AND t.datum <= :d AND EXISTS ("
        "SELECT 1 FROM json_each(t.komponenten) j WHERE j.key LIKE :muster ESCAPE '!' AND j.key NOT LIKE 'soc!_%' ESCAPE '!')"
    ), {"a": anlage_id, "d": bis_tag.isoformat(), "muster": f"%!_{inv_id}"})).scalar_one())


async def zaehle_bestand(db: AsyncSession, anlage_id: int, ziele: BestandZiele, bis_tag: date,
                         abschluss: frozenset[tuple[int, int]]) -> BestandZaehlung:
    z = BestandZaehlung()
    for d in await _tep_daten(db, anlage_id, bis_tag, ziele):
        if _im_abschluss(d, abschluss):
            z.abschluss_tage.add(d)
            continue
        z.tage.add(d)
        z.stundenzeilen += 1
    for row in await _tz_zeilen(db, anlage_id, bis_tag, ziele):
        if not tz_keys_der_zeile(row, ziele):
            continue
        if _im_abschluss(row.datum, abschluss):
            z.abschluss_tage.add(row.datum)
            continue
        z.tage.add(row.datum)
        z.tageszeilen += 1
    z.leistungspfad_stunden = await _leistungspfad_stunden(db, anlage_id, bis_tag, ziele.inv_id)
    return z


# ── Bestand: leeren (Provenance-Schreiber, Quelle `verworfen:werkbank`) ─────


async def _leere_tep_zeile(db: AsyncSession, row: TagesEnergieProfil, ziele: BestandZiele) -> int:
    from backend.services.provenance import remove_json_subkey_with_provenance, write_with_provenance

    n = 0
    if ziele.spalte and getattr(row, ziele.spalte) is not None:
        res = await write_with_provenance(db, row, ziele.spalte, None, source=QUELLE, writer=WRITER)
        n += bool(res.applied)
    if ziele.spannen_achse and ziele.spannen_achse in (row.spannen or {}):
        await remove_json_subkey_with_provenance(db, row, "spannen", ziele.spannen_achse, source=QUELLE,
                                                 writer=WRITER, decision_reason=_GRUND)
        n += 1
    return n


async def _leere_tz_zeile(db: AsyncSession, row: TagesZusammenfassung, ziele: BestandZiele) -> int:
    from backend.services.provenance import remove_json_subkey_with_provenance

    n = 0
    for key in tz_keys_der_zeile(row, ziele):
        await remove_json_subkey_with_provenance(db, row, "komponenten_kwh", key, source=QUELLE, writer=WRITER,
                                                 decision_reason=_GRUND)
        n += 1
    return n


async def leere_bestand(db: AsyncSession, anlage_id: int, ziele: BestandZiele, bis_tag: date,
                        abschluss: frozenset[tuple[int, int]]) -> dict[str, int]:
    """Die Schlüssel dieses Feldes in Stunden- und Tageszeilen bis ``bis_tag`` leeren — Monate mit Abschluss ausgenommen."""
    out = {"stundenzeilen_geleert": 0, "tageszeilen_geleert": 0, "felder_geleert": 0}
    bed = _tep_bedingung(ziele)
    if bed is not None:
        for row in (await db.execute(select(TagesEnergieProfil).where(and_(
            TagesEnergieProfil.anlage_id == anlage_id, TagesEnergieProfil.datum <= bis_tag, bed)))).scalars().all():
            if _im_abschluss(row.datum, abschluss):
                continue
            n = await _leere_tep_zeile(db, row, ziele)
            out["stundenzeilen_geleert"] += bool(n)
            out["felder_geleert"] += n
    for row in await _tz_zeilen(db, anlage_id, bis_tag, ziele):
        if _im_abschluss(row.datum, abschluss):
            continue
        n = await _leere_tz_zeile(db, row, ziele)
        out["tageszeilen_geleert"] += bool(n)
        out["felder_geleert"] += n
    return out


# ── Vorschau ────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Lage:
    """Alles, was Vorschau und Ausführung über EINEN Plan wissen."""

    anlage: Anlage
    key: str
    label: str
    t: int
    kanal: kv.KanalVorschau
    ziele: BestandZiele
    bestand: BestandZaehlung
    abschluss: frozenset[tuple[int, int]]

    @property
    def bis_tag(self) -> date:
        return self.kanal.letzter_ganzer_tag

    def lesart1_ohne_werte(self) -> list[date]:
        """Tage, die danach weder eine Kanalzeile noch einen Bestandswert dieses Feldes haben."""
        kanal_tage = {d for d in self.kanal.tage if d <= self.bis_tag and not _im_abschluss(d, self.abschluss)}
        return sorted(kanal_tage | self.bestand.tage)

    def lesart1_mit_bestand(self) -> list[date]:
        """Tage, die ihre Kanalzeilen (oder den Anker) verlieren, deren Bestand aber stehen bleibt."""
        betroffen = set(self.kanal.tage) | ({self.kanal.tag_von_t} if self.kanal.zeilen else set())
        return sorted(betroffen - set(self.lesart1_ohne_werte()))

    def abschluss_monate_betroffen(self) -> list[tuple[int, int]]:
        tage = set(self.kanal.tage) | self.bestand.abschluss_tage
        return sorted({(d.year, d.month) for d in tage if _im_abschluss(d, self.abschluss)})

    @property
    def nichts_zu_tun(self) -> bool:
        return not self.kanal.zeilen and not self.bestand.tage


async def lage(db: AsyncSession, anlage_id: int, params: dict[str, Any]) -> Lage:
    """Eingaben prüfen und beide Schichten zählen (kein Schreiben)."""
    key = params.get("kanal")
    if not key or not isinstance(key, str):
        raise ValueError("Verwerfen braucht params.kanal (das zugeordnete Feld, z. B. basis:einspeisung)")
    if not params.get("zeitpunkt"):
        raise ValueError("Verwerfen braucht params.zeitpunkt (JJJJ-MM-TTTHH:MM, volle Stunde)")
    t = kv.zeitpunkt_aus_text(str(params["zeitpunkt"]))
    anlage = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one_or_none()
    if anlage is None:
        raise LookupError(f"Anlage {anlage_id} nicht gefunden")
    kanal, quellen = await kv.lade_kanal(db, anlage_id, key)
    kv.pruefe_zeitpunkt(key, quellen, t)
    kanal_v = await kv.vorschau(db, kanal, quellen, t)
    ziele = await bestand_ziele(db, anlage, key)
    abschluss = await abschluss_monate(db, anlage_id)
    bestand = await zaehle_bestand(db, anlage_id, ziele, kanal_v.letzter_ganzer_tag, abschluss)
    return Lage(anlage, key, feld_label(key, await _investitionen(db, anlage_id)), t, kanal_v, ziele, bestand, abschluss)


def _zeit(ts: Optional[int]) -> str:
    return datetime.fromtimestamp(ts).strftime("%d.%m.%Y %H:%M") if ts is not None else ""


def _quelle_satz(q: kv.QuelleInfo, t: int) -> str:
    art = "alter Sensor" if q.familie == "spiegel" else "alte Mitschrift" if q.familie == "mitschrift" else "alte Quelle"
    name = f" {q.statistic_id}" if q.statistic_id else ""
    ende = min(q.bis, t) if q.bis is not None else t
    marke = f" (schon verworfen am {_zeit(q.verworfen_ts)})" if q.verworfen_ts is not None else ""
    return (f"{art}{name} von {_zeit(q.gueltig_ab)} bis {_zeit(ende)}: {fmt_zahl(q.zeilen)} Stunden im Kanal"
            f"{marke}.")


def _spanne(tage: list[date]) -> str:
    return f"{fmt_datum(tage[0])} … {fmt_datum(tage[-1])}" if tage else ""


def _monate_text(monate: list[tuple[int, int]]) -> str:
    """Bis sechs Monate einzeln, sonst «erster … letzter» — die Liste steht vollständig in ``operation_preview``."""
    namen = [f"{m:02d}/{j}" for j, m in monate]
    return ", ".join(namen) if len(namen) <= 6 else f"{namen[0]} … {namen[-1]}"


def _saetze_kanal(la: Lage) -> list[str]:
    s = [f"Verworfen werden die Werte von «{la.label}» ({la.key}) vor {_zeit(la.t)} — Beginn der jüngsten Quelle "
         f"{la.kanal.juengste.statistic_id or ''} am {_zeit(la.kanal.juengste.gueltig_ab)}."]
    s += [_quelle_satz(q, la.t) for q in la.kanal.aeltere]
    if la.kanal.zeilen:
        s.append(f"Kanal: {fmt_zahl(la.kanal.zeilen)} Stundenzeilen an {fmt_zahl(len(la.kanal.tage))} Tagen "
                 f"({_spanne(list(la.kanal.tage))}) werden gelöscht; die Quellen bleiben als Herkunft mit Marke "
                 "«verworfen am» stehen.")
    return s


def _saetze_bestand(la: Lage) -> list[str]:
    b, s = la.bestand, []
    if b.tage:
        s.append(f"Bestand: an {fmt_zahl(len(b.tage))} Tagen ({_spanne(sorted(b.tage))}) werden nur die Werte dieses "
                 f"Feldes geleert ({fmt_zahl(b.stundenzeilen)} Stundenzeilen, {fmt_zahl(b.tageszeilen)} Tageszeilen) "
                 "— Wetter, Prognose, Preise, Betriebsart, SoC und andere Geräte bleiben.")
    monate = la.abschluss_monate_betroffen()
    if monate:
        s.append(f"{fmt_zahl(len(monate))} Monat(e) mit Abschluss bleiben im Bestand unberührt: {_monate_text(monate)}.")
    if la.ziele.mitbetroffen:
        s.append(f"Der Tageswert {', '.join(sorted(la.ziele.tz_keys))} trägt auch {', '.join(la.ziele.mitbetroffen)} "
                 "— er wird als Ganzes geleert.")
    if b.leistungspfad_stunden:
        s.append(f"Die Leistungswerte des Geräts in {fmt_zahl(b.leistungspfad_stunden)} Stundenzeilen kommen von seinem "
                 "Leistungssensor, nicht von diesem Zähler — sie bleiben stehen.")
    return s


def _saetze_danach(la: Lage) -> list[str]:
    s = []
    ohne = la.lesart1_ohne_werte()
    if ohne:
        s.append(f"Danach haben {fmt_zahl(len(ohne))} Tage ({_spanne(ohne)}) keinen Wert dieses Feldes mehr: kein "
                 "Kanal, und der Bestand trägt das Feld nicht mehr.")
    mit = la.lesart1_mit_bestand()
    if mit:
        s.append(f"{fmt_zahl(len(mit))} Tag(e) ({_spanne(mit)}) verlieren ihre Kanalzeilen, ihr Bestand bleibt "
                 "unverändert (Monate mit Abschluss, der angebrochene Tag des Sensorwechsels).")
    s.append("Kein Rückweg: die verworfenen Werte sind danach weg. «Tag neu aggregieren» für einen Tag davor holt die "
             "Werte aus den gespeicherten Zählerständen zurück.")
    return s


def klartext(la: Lage) -> list[str]:
    if la.nichts_zu_tun:
        return [f"Nichts zu verwerfen — vor {_zeit(la.t)} tragen weder der Kanal noch der Bestand (außerhalb von Monaten "
                f"mit Abschluss) Werte von «{la.label}» ({la.key})."]
    return _saetze_kanal(la) + _saetze_bestand(la) + _saetze_danach(la)


def geschaetzt(la: Lage) -> dict[str, int]:
    return {
        "kanalzeilen": la.kanal.zeilen,
        "bestand_tage": len(la.bestand.tage),
        "stundenzeilen": la.bestand.stundenzeilen,
        "tageszeilen": la.bestand.tageszeilen,
        "abschluss_monate": len(la.abschluss_monate_betroffen()),
        "tage_ohne_werte": len(la.lesart1_ohne_werte()),
    }


def vorschau_daten(la: Lage) -> dict[str, Any]:
    return {
        "kanal": la.key, "label": la.label, "zeitpunkt": kv.text_aus_zeitpunkt(la.t),
        "quellen": [{"statistic_id": q.statistic_id, "familie": q.familie, "gueltig_ab": kv.text_aus_zeitpunkt(q.gueltig_ab),
                     "zeilen": q.zeilen, "verworfen_ts": q.verworfen_ts} for q in la.kanal.aeltere],
        "letzter_ganzer_tag": la.bis_tag.isoformat(),
        "abschluss_monate": [f"{j}-{m:02d}" for j, m in la.abschluss_monate_betroffen()],
        "tage_ohne_werte": [d.isoformat() for d in la.lesart1_ohne_werte()],
        "tage_mit_bestand": [d.isoformat() for d in la.lesart1_mit_bestand()],
        "bestand_ziele": {"spalte": la.ziele.spalte, "spannen": la.ziele.spannen_achse,
                          "komponenten_kwh": sorted(la.ziele.tz_keys), "pv_aggregat": la.ziele.pv_aggregat},
    }


# ── Ausführung ──────────────────────────────────────────────────────────────


async def fuehre_aus(db: AsyncSession, anlage_id: int, params: dict[str, Any]) -> dict[str, Any]:
    """Beide Schichten in EINER Sitzung, ein Commit. Aktivität in derselben Sitzung (N-532)."""
    from backend.services.activity_service import log_activity

    la = await lage(db, anlage_id, params)
    bestand = await leere_bestand(db, anlage_id, la.ziele, la.bis_tag, la.abschluss)
    geloescht = await kv.loesche_zeilen(db, la.kanal.kanal_id, la.t)
    markiert = await kv.markiere_quellen(db, la.kanal.kanal_id, la.t, int(datetime.now().timestamp())) if geloescht else 0
    summary = {"kanal": la.key, "zeitpunkt": kv.text_aus_zeitpunkt(la.t), "kanalzeilen_geloescht": geloescht,
               "quellen_markiert": markiert, **bestand}
    if geloescht or bestand["felder_geleert"]:
        await log_activity(
            kategorie="repair", aktion=f"Werte vor dem Sensorbeginn verworfen: {la.label}", erfolg=True,
            details=(f"{la.key} vor {_zeit(la.t)}: {fmt_zahl(geloescht)} Kanalzeilen gelöscht, "
                     f"{fmt_zahl(bestand['stundenzeilen_geleert'])} Stunden- und "
                     f"{fmt_zahl(bestand['tageszeilen_geleert'])} Tageszeilen feldgenau geleert."),
            details_json=summary, anlage_id=anlage_id, db=db,
        )
    await db.commit()
    return summary


# ── Auswahl für die Werkbank (lesende Route) ────────────────────────────────


async def auswahl(db: AsyncSession, anlage_id: int) -> list[dict[str, Any]]:
    """Die Zählerkanäle zugeordneter Felder mit mindestens zwei Quellen (Sensortausch) — mit Vorbelegung."""
    invs = await _investitionen(db, anlage_id)
    out = []
    for kanal, quellen in await kv.kanaele_mit_quellen(db, anlage_id):
        if len(quellen) < 2:
            continue
        teile = kanal.key.split(":")
        inv = invs.get(int(teile[1])) if teile[0] == "inv" else None
        out.append({
            "key": kanal.key, "label": feld_label(kanal.key, invs),
            "investition_id": inv.id if inv is not None else None, "typ": inv.typ if inv is not None else None,
            "quellen": [{"gueltig_ab": kv.text_aus_zeitpunkt(q.gueltig_ab), "familie": q.familie,
                         "statistic_id": q.statistic_id,
                         "verworfen_am": kv.text_aus_zeitpunkt(q.verworfen_ts) if q.verworfen_ts is not None else None}
                        for q in quellen],
            "vorbelegung": kv.text_aus_zeitpunkt(quellen[-1].gueltig_ab),
        })
    return out
