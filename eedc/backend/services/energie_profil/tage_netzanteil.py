"""Tag und Stunde mit gemessenem Netzbezug zum WP-/Wallbox-Tarif (N-770/N-771 E3, Bauplan F5 mit F9 = A, F6).

Der Monat rechnet die Stromrechnung ``(Netzbezug − Σ N) × Haushalt + Σ N × Komponenten-Tarif`` und die
Eigenverbrauchs-Ersparnis mit dem PV-Anteil der WP P = S − N zum WP-Tarif (``monats_fakten.komponenten_anteile``,
E2). Die Tagessicht (``tage_werte.py``, auch PDF-Monatsbericht) rechnet dieselbe Formel **je Stunde** — mit den
Stunden des Kanals des Felds (``kanal/netzanteil_leser.py``, der einzigen Stundenquelle des Felds, F9 = A):

* **Wann:** in einem Monat, in dem die Monats-Fakten den Anteil der Verwendung ansetzen (eigener Tarif, gemessen, F3)
  UND die Kanäle des Felds den Kalendermonat voll decken. Sonst rechnen die Tage wie bisher — benannte Grenze F9:
  ein Netzbezug zum WP-Tarif, der nur als Monatswert vorliegt (Hand, CSV, kein Kanal), teilt den Tag nicht, Σ Tage ≠
  Monat.
* **Menge je Stunde:** der Zuwachs des Kanals in dieser Stunde. Hat der Monat geklemmt (F7: N > S oder N > Netzbezug),
  tragen die Stunden die Klemme im selben Verhältnis (``angesetzt ÷ gemessen``), damit Σ Stunden der Monatsmenge folgt.
* **Preis je Stunde:** mit Zeitfenster-Tarif (F6, der Monat gewichtet ihn über N) der Slot-Preis des Komponenten-Tarifs
  zur Uhr-Stunde, sonst der Monatspreis des Anteils (``NetzanteilZumTarif.cent``). Der Haushaltspreis der Stunde bleibt
  der Slot-Preis der Kaskade P-6 (``strompreis_aggregator.slot_kosten_aus_zeilen``) — er bewertet den Rest der Stunde.
* **EV-Ersparnis je Tag:** P_d = WP-Strom des Tages − N_wp des Tages zum WP-Tarif des Monats (``wp_cent``), der Rest zum
  EV-Preis des Tages (``finanz_aggregat.bewerte_eigenverbrauch`` — dieselbe Layer-Formel wie der Monat).
* **F12 gemeinsamer Zähler WP + Wallbox (E6):** die Stunde rechnet N_g,h × W_g,h + Rest × H_h (Stunden des Felds an der
  WP, Σ Tage = Monat in voll gedeckten Monaten); die EV-Ersparnis des Tages teilt NICHT — ohne Stundenwerte der Wallbox
  ist N_wp des Tages nicht bekannt, der Monat trägt den Wert (benannte Grenze analog F9, Auftrag §3.4).

Nichts wird geschrieben (``TagesEnergieProfil`` bleibt, aggregate-day unverändert).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Iterable, Mapping

from sqlalchemy.ext.asyncio import AsyncSession

MonatsSchluessel = tuple[int, int]


@dataclass
class TageNetzanteil:
    """Was die Tagessicht braucht: die Anteile je Stunde und der WP-Tarif des PV-Anteils je Monat."""

    #: ``start_ts → [(verwendung, kWh, ct), …]`` — Eingang von ``slot_kosten_aus_zeilen(netzanteile=…)``.
    stunden: dict[int, list[tuple[str, float, float]]] = field(default_factory=dict)
    #: ``(jahr, monat) → ct`` — Preis des PV-Anteils der WP (nur Monate, in denen die WP-Stunden angesetzt sind).
    wp_cent: dict[MonatsSchluessel, float] = field(default_factory=dict)

    def __bool__(self) -> bool:
        return bool(self.stunden)


async def netzanteile_der_tage(
    db: AsyncSession, anlage_id: int, tage: Iterable[date], tarife_je_stichtag: Mapping[date, dict],
) -> TageNetzanteil:
    """Die Anteile zum Komponenten-Tarif je Stunde für die Monate der ``tage``. Leer (und ohne weitere Abfrage nach dem
    Vorfilter), wenn kein Monat einen eigenen Komponenten-Tarif hat oder die Anlage keinen Kanal des Felds führt."""
    from backend.services.kanal.netzanteil_leser import hat_netzanteil_kanaele, netzanteil_des_monats
    from backend.services.monats_fakten.tarif import eigene_tarif_verwendungen

    out = TageNetzanteil()
    monate = sorted({(t.year, t.month) for t in tage})
    relevant = [m for m in monate if eigene_tarif_verwendungen(tarife_je_stichtag.get(date(*m, 1)) or {})]
    if not relevant or not await hat_netzanteil_kanaele(db, anlage_id):
        return out
    netz = {m: await netzanteil_des_monats(db, anlage_id, *m) for m in relevant}
    relevant = [m for m in relevant if netz[m]]
    if not relevant:
        return out
    from backend.services.monats_fakten import komponenten_anteile_des_fakts, lade_monats_fakten

    fakten = {(f.jahr, f.monat): f for f in await lade_monats_fakten(
        db, anlage_id, von=relevant[0], bis=relevant[-1], inkl_nur_tageswerte=True,
    )}
    for m in relevant:
        anteile = komponenten_anteile_des_fakts(fakten.get(m))
        if anteile is None:
            continue
        tarife = tarife_je_stichtag.get(date(*m, 1)) or {}
        for a in anteile.netz:
            stunden = netz[m].get(_kanal_verwendung(a.verwendung))
            if stunden is None:
                continue
            _stunden_eintragen(out.stunden, a, stunden.werte, tarife)
            if a.verwendung == "waermepumpe" and anteile.wp_cent is not None:
                out.wp_cent[m] = anteile.wp_cent
    return out


def _kanal_verwendung(verwendung: str) -> str:
    """F12 (E6): der Anteil ``waermepumpe_wallbox`` (gemeinsamer Zähler) liest die Stunden des Felds an der Wärmepumpe
    (dort trägt es N_g) und den Tarif über die Verwendung ``waermepumpe`` (derselbe Datensatz). Die EV-Ersparnis des
    Tages teilt er NICHT: ohne Stundenwerte der Wallbox ist N_wp des Tages unbekannt — der Tag rechnet sie wie bisher,
    der Monat trägt den Wert (benannte Grenze analog F9, Auftrag §3.4; ``wp_cent`` bleibt ohne Eintrag)."""
    from backend.services.monats_fakten.tarif import GEMEINSAM

    return "waermepumpe" if verwendung == GEMEINSAM else verwendung


def _stunden_eintragen(ziel: dict, anteil, werte: Mapping[int, float], tarife: Mapping[str, object]) -> None:
    """Die Stunden EINES angesetzten Anteils (``NetzanteilZumTarif``) in ``ziel`` — Klemme im Verhältnis, Preis je
    Stunde (F6: Slot-Preis des Komponenten-Tarifs, sonst der Monatspreis des Anteils)."""
    from backend.api.routes.strompreise import resolve_tarif_for_komponente
    from backend.core.berechnungen.zeittarif import preis_je_uhrzeit

    faktor = (anteil.kwh / anteil.gemessen_kwh) if anteil.gemessen_kwh > 0 else 0.0
    tarif = resolve_tarif_for_komponente(tarife, _kanal_verwendung(anteil.verwendung)) if anteil.zeitfenster else None
    for ts, kwh in werte.items():
        cent = preis_je_uhrzeit(tarif, datetime.fromtimestamp(ts)) if tarif is not None else anteil.cent
        ziel.setdefault(ts, []).append((anteil.verwendung, kwh * faktor, cent))


__all__ = ["TageNetzanteil", "netzanteile_der_tage"]
