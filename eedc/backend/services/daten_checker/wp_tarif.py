"""
Daten-Checker — eigener Wärmepumpen- und Wallbox-Tarif (`WpTarifChecks`, N-767 24.10.2026; N-770/N-771 E4 31.10.2026).

**Was die Meldungen benennen.** Mit einem eigenen WP- bzw. Wallbox-Tarif rechnet der Versorger einen Teil des
Netzbezugs zu diesem Tarif ab. eedc rechnet das genau, wo der **Netzbezug zum WP-/Wallbox-Tarif** gemessen ist (Feld
``netzbezug_eigener_tarif_kwh``, Bauplan N-770 §1): Stromrechnung ``(Netzbezug − N) × Haushalt + N × Komponenten-Tarif``,
Eigenverbrauchs-Ersparnis mit dem PV-Anteil der WP P = S − N zum WP-Tarif, an der Wallbox die Netzladung = N (F11).
Ohne das Feld bleibt die Grenze: Ersparnis UND Stromrechnung stehen zusammen um bis zu (Haushalt − WP-Tarif) × S zu
hoch bzw. zu niedrig — die Obergrenze, die die INFO nennt (``F7``: «die Obergrenze gilt Ersparnis + Stromrechnung
zusammen»; S = P + N, jeder Teil steht mit der Tarifdifferenz in genau einer der beiden Zahlen).

Eine Kategorie für beide Komponenten (``wp_eigener_tarif``, Label «Strompreise – eigener WP-/Wallbox-Tarif»):
dieselbe Ursache (ein zweiter Tarif am selben Netzanschluss), dasselbe Feld, dieselbe Seite (Strompreise,
Datenquellen), dieselbe Klemme (``monats_fakten.komponenten_anteile``). Je Komponente:

* **INFO — Feld fehlt:** ein Monat der letzten 12 abgeschlossenen mit WP-Strom bzw. Ladung > 0 ohne gemessenes N
  (F3: Monat nicht gemessen) ⇒ Obergrenze und Rat «Netzbezug zum WP-/Wallbox-Tarif zuordnen». Still, wenn jeder solche
  Monat gemessen ist.
* **WARNING — geklemmt (F7):** N > Gerätemenge (Toleranz 2 %) oder N > Netzbezug (Wallbox: > Netzbezug − N_WP) — der
  Monat rechnet begrenzt; die Herleitung sagt es.
* **WARNING — evcc weicht ab (F11):** trägt eine Wallbox-Zeile neben N einen gepflegten PV-/Netz-Anteil (evcc), und
  weichen Netz (evcc) und N ab, gilt N (Zähler des Versorgers) — der Checker nennt die Monate.
* **INFO — paralleler Zähler (G1):** steht derselbe Sensor in «Stromverbrauch» bzw. «Ladung» und im Feld, misst ein
  paralleler Zähler (das Gerät hängt nicht hinter dem PV-Messpunkt, P = 0) — dann muss der Netzbezug der Anlage diesen
  Zähler enthalten (Netzbezug der Anlage = Summe beider Zähler), sonst fehlt N im Netzbezug und die Klemme greift.

**Eng gefasst (P-6):** nur wenn zum Monatsersten des Prüfmonats (P8-Stichtag) ein Tarif der Verwendung mit eigenem
Arbeitspreis gilt, der vom allgemeinen abweicht; Mengen über die Monats-Fakten (ADR-002/P10). Verglichen wird der Preis
des Monats, wie ``_lade_tarif`` ihn bildet (``tarif_des_monats``) — keine zweite Kaskade.
"""

from datetime import date
from typing import Optional

from sqlalchemy import and_, select

from backend.api.routes.strompreise import resolve_tarif_for_komponente, tarife_zum_stichtag
from backend.core.zahlenformat import fmt_zahl
from backend.models.anlage import Anlage

from .kategorien import CheckErgebnis, CheckKategorie, CheckSeverity

#: Das Fenster: die letzten zwölf abgeschlossenen Monate vor dem Prüfmonat.
FENSTER_MONATE = 12
#: F7: Toleranz der Probe «N > Gerätemenge» (zwei Zähler, zeitversetzt gelesen).
TOLERANZ = 0.02
#: F11: Abweichung evcc ↔ N, ab der der Checker warnt (kWh bzw. Anteil der Ladung).
ABWEICHUNG_KWH = 0.5
FELD = "netzbezug_eigener_tarif_kwh"
_KAT = CheckKategorie.WP_EIGENER_TARIF.value
#: Je Komponente: Verwendung, Anwenderwort, Feld-Label, Mengenfeld (G1) und Mengenwort.
_KOMPONENTEN = {
    "waermepumpe": ("Wärmepumpen", "Netzbezug zum WP-Tarif", "stromverbrauch_kwh", "WP-Strom", "Stromverbrauch"),
    "wallbox": ("Wallbox", "Netzbezug zum Wallbox-Tarif", "ladung_kwh", "Ladung", "Ladung"),
}


def _monat_minus(jahr: int, monat: int, n: int) -> tuple[int, int]:
    """``(jahr, monat)`` minus ``n`` Monate."""
    idx = jahr * 12 + (monat - 1) - n
    return idx // 12, idx % 12 + 1


def _monate_text(monate) -> str:
    return ", ".join(f"{m:02d}/{j}" for j, m in sorted(monate))


def _menge_und_n(fakt, verwendung: str) -> tuple[float, Optional[float]]:
    if verwendung == "waermepumpe":
        return fakt.wp.strom_kwh, fakt.wp.netz_eigener_tarif_kwh
    return fakt.emob.wallbox_ladung_alle_kwh, fakt.emob.wallbox_netz_eigener_tarif_kwh


class WpTarifChecks:
    """N-767 / N-770 / N-771: eigener WP- und Wallbox-Tarif — Feld fehlt, Klemme, evcc-Abweichung, paralleler Zähler."""

    async def _check_wp_eigener_tarif(
        self, anlage: Anlage, *, heute: Optional[date] = None,
    ) -> list[CheckErgebnis]:
        """Die Meldungen der Kategorie (Modul-Docstring). ``heute`` für Proben (keine echte Uhr in Tests)."""
        tag = heute or date.today()
        stichtag = date(tag.year, tag.month, 1)
        zeilen = sorted(
            (t for t in anlage.strompreise if t.gilt_am(stichtag)),
            key=lambda t: t.gueltig_ab, reverse=True,
        )
        tarife = tarife_zum_stichtag(zeilen, stichtag)
        allgemein = resolve_tarif_for_komponente(tarife, "allgemein")
        if allgemein is None:
            return []
        verwendungen = [
            v for v in _KOMPONENTEN
            if (t := resolve_tarif_for_komponente(tarife, v)) is not None and t is not allgemein
            and t.netzbezug_arbeitspreis_cent_kwh != allgemein.netzbezug_arbeitspreis_cent_kwh
        ]
        if not verwendungen:
            return []

        from backend.services.monats_fakten import lade_monats_fakten, tarif_des_monats

        tarif = await tarif_des_monats(self.db, anlage.id, stichtag.year, stichtag.month)
        fenster = (_monat_minus(stichtag.year, stichtag.month, FENSTER_MONATE),
                   _monat_minus(stichtag.year, stichtag.month, 1))
        fakten = await lade_monats_fakten(self.db, anlage.id, von=fenster[0], bis=fenster[1], inkl_nur_tageswerte=True)
        out: list[CheckErgebnis] = []
        for v in verwendungen:
            komp_cent = tarif.wp_preis_cent if v == "waermepumpe" else tarif.wallbox_preis_effektiv_cent
            out += _feld_fehlt(v, fakten, komp_cent, tarif.netzbezug_stammpreis_cent)
            out += _geklemmt(v, fakten)
        out += await self._parallele_zaehler(anlage, verwendungen)
        if "wallbox" in verwendungen:
            out += await self._evcc_weicht_ab(anlage, fenster)
        return out

    async def _parallele_zaehler(self, anlage: Anlage, verwendungen) -> list[CheckErgebnis]:
        """G1: derselbe Sensor in der Gerätemenge und im Feld ⇒ paralleler Zähler — der Netzbezug der Anlage muss ihn
        enthalten (Summe beider Zähler)."""
        from backend.models.investition import Investition

        invs = (await self.db.execute(select(Investition).where(and_(
            Investition.anlage_id == anlage.id, Investition.typ.in_(list(verwendungen)),
        )))).scalars().all()
        mapping = ((anlage.sensor_mapping or {}).get("investitionen") or {})
        out = []
        for inv in invs:
            felder = (mapping.get(str(inv.id)) or {}).get("felder") or {}
            _, label, mengen_feld, _, mengen_label = _KOMPONENTEN[inv.typ]
            n_sensor = (felder.get(FELD) or {}).get("sensor_id")
            if n_sensor and n_sensor == (felder.get(mengen_feld) or {}).get("sensor_id"):
                out.append(CheckErgebnis(
                    kategorie=_KAT, schwere=CheckSeverity.INFO.value, investition_id=inv.id,
                    meldung=f"{inv.bezeichnung}: paralleler Zähler — derselbe Sensor in «{mengen_label}» und «{label}»",
                    details=(
                        f"{inv.bezeichnung} misst «{label}» mit demselben Sensor wie «{mengen_label}» ({n_sensor}): ein "
                        f"eigener Zähler parallel zum Hauszähler, das Gerät bezieht keinen PV-Strom. Dann muss der "
                        f"Netzbezug der Anlage diesen Zähler enthalten — Netzbezug der Anlage = Summe beider Zähler "
                        f"(Hauszähler + Zähler des Geräts). Fehlt er dort, ist der Netzbezug zu klein, und eedc begrenzt "
                        f"den Anteil zum Komponenten-Tarif auf den Netzbezug. Erklärt im Handbuch „Wärme & Klima“, "
                        f"Schritt 6b, und „Einstellungen“ (Netzbezug)."
                    ),
                ))
        return out

    async def _evcc_weicht_ab(self, anlage: Anlage, fenster) -> list[CheckErgebnis]:
        """F11: eine Wallbox-Zeile trägt neben dem gemessenen N einen gepflegten PV-/Netz-Anteil (evcc), und beide
        weichen ab ⇒ WARNING mit den Monaten (es gilt N, der Zähler des Versorgers)."""
        from backend.core.field_definitions import get_eauto_ladung_kwh
        from backend.models.investition import Investition, InvestitionMonatsdaten

        (von_j, von_m), (bis_j, bis_m) = fenster
        zeilen = (await self.db.execute(
            select(Investition.id, Investition.bezeichnung, InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat,
                   InvestitionMonatsdaten.verbrauch_daten)
            .join(InvestitionMonatsdaten, InvestitionMonatsdaten.investition_id == Investition.id)
            .where(and_(Investition.anlage_id == anlage.id, Investition.typ == "wallbox"))
        )).all()
        je_inv: dict[int, tuple[str, list]] = {}
        for inv_id, name, j, m, vd in zeilen:
            if not (von_j * 12 + von_m <= j * 12 + m <= bis_j * 12 + bis_m):
                continue
            d = vd or {}
            if d.get(FELD) is None or (d.get("ladung_pv_kwh") is None and d.get("ladung_netz_kwh") is None):
                continue
            ladung = get_eauto_ladung_kwh(d)
            evcc_netz = (float(d["ladung_netz_kwh"]) if d.get("ladung_netz_kwh") is not None
                         else max(0.0, ladung - float(d.get("ladung_pv_kwh") or 0)))
            if abs(evcc_netz - float(d[FELD])) > max(ABWEICHUNG_KWH, TOLERANZ * ladung):
                je_inv.setdefault(inv_id, (name, []))[1].append((j, m))
        return [CheckErgebnis(
            kategorie=_KAT, schwere=CheckSeverity.WARNING.value, investition_id=inv_id,
            meldung=f"{name}: Netzladung aus evcc weicht vom Netzbezug zum Wallbox-Tarif ab ({_monate_text(monate)})",
            details=(
                f"In {_monate_text(monate)} trägt {name} neben dem «Netzbezug zum Wallbox-Tarif» einen PV-/Netz-Anteil "
                f"(z. B. aus evcc), und beide nennen eine andere Netzladung. eedc rechnet mit dem Zähler des Versorgers: "
                f"Netzladung = Netzbezug zum Wallbox-Tarif, PV-Ladung = Ladung − Netzladung (E-Mob-Ersparnis, "
                f"Heimladekosten, Stromrechnung). Prüfe, ob beide Sensoren dieselbe Wallbox messen; erklärt im Handbuch "
                f"„E-Mobilität“ (Netzbezug zum Wallbox-Tarif)."
            ),
        ) for inv_id, (name, monate) in je_inv.items()]


def _feld_fehlt(verwendung: str, fakten, komp_cent: float, haushalt_cent: float) -> list[CheckErgebnis]:
    """INFO, wenn ein Monat mit Gerätemenge > 0 das Feld nicht misst — mit der Obergrenze für Ersparnis UND
    Stromrechnung (F7); still, wenn jeder solche Monat gemessen ist."""
    wort, label, _feld, mengen_wort, _ = _KOMPONENTEN[verwendung]
    differenz_cent = abs(haushalt_cent - komp_cent)
    if round(differenz_cent, 2) == 0:
        return []
    mit_menge = [(f, *_menge_und_n(f, verwendung)) for f in fakten]
    mit_menge = [(f, s, n) for f, s, n in mit_menge if s > 0]
    ungemessen = [(f, s) for f, s, n in mit_menge if n is None]
    if not ungemessen:
        return []
    menge = sum(s for _f, s in ungemessen)
    obergrenze = menge * differenz_cent / 100.0
    gemessen = len(mit_menge) - len(ungemessen)
    teil = (f" In {gemessen} der {len(mit_menge)} Monate ist er gemessen; die übrigen rechnen ohne ihn."
            if gemessen else "")
    if verwendung == "waermepumpe":
        wirkung = (f"eedc bewertet den PV-Anteil der Wärmepumpe dann zum Haushaltstarif ({fmt_zahl(haushalt_cent, 2)} ct) "
                   f"und rechnet ihren Netzbezug in der Stromrechnung zum Haushaltstarif statt zum Wärmepumpen-Tarif "
                   f"({fmt_zahl(komp_cent, 2)} ct)")
    else:
        wirkung = (f"eedc rechnet die Netzladung der Wallbox in der Stromrechnung dann zum Haushaltstarif "
                   f"({fmt_zahl(haushalt_cent, 2)} ct) statt zum Wallbox-Tarif ({fmt_zahl(komp_cent, 2)} ct), und die "
                   f"Netzladung selbst ist eedcs Aufteilung (evcc bzw. Tagesquote), keine Messung")
    return [CheckErgebnis(
        kategorie=_KAT, schwere=CheckSeverity.INFO.value,
        meldung=(
            f"Eigener {wort}-Tarif ({fmt_zahl(komp_cent, 2)} ct gegen {fmt_zahl(haushalt_cent, 2)} ct): Ersparnis und "
            f"Stromrechnung der letzten 12 Monate können zusammen um bis zu {fmt_zahl(obergrenze, 0)} € abweichen — "
            f"ordne «{label}» zu"
        ),
        details=(
            f"Für {_monate_text((f.jahr, f.monat) for f, _ in ungemessen)} fehlt «{label}». {wirkung}. Ersparnis und "
            f"Stromrechnung können dadurch zusammen um bis zu {fmt_zahl(obergrenze, 0)} € abweichen — {mengen_wort} "
            f"dieser Monate {fmt_zahl(menge, 0)} kWh × Differenz {fmt_zahl(differenz_cent, 2)} ct.{teil} Ordne den "
            f"Netzbezug zum {wort}-Tarif zu (Datenquellen, Block «Gerät gesamt»; der Zähler des Versorgers: «Zähler vor "
            f"dem Gerät minus Zähler nach dem Gerät»), dann rechnet eedc beide Tarife genau. Erklärt im Handbuch "
            f"„Wärme & Klima“, Schritt 6b, und unter „Berechnungen“."
        ),
    )]


def _geklemmt(verwendung: str, fakten) -> list[CheckErgebnis]:
    """WARNING je Komponente: Monate, deren gemessenes N über der Gerätemenge (Toleranz 2 %) oder über dem Netzbezug
    (Wallbox: über dem Rest nach der WP) liegt — der Monat rechnet begrenzt (``komponenten_anteile``, F7)."""
    from backend.services.monats_fakten import komponenten_anteile_des_fakts

    wort, label, _feld, mengen_wort, _ = _KOMPONENTEN[verwendung]
    ueber_menge, ueber_netz = [], []
    for f in fakten:
        a = komponenten_anteile_des_fakts(f)
        teil = next((x for x in (a.netz if a is not None else ()) if x.verwendung == verwendung), None)
        if teil is None or not teil.geklemmt:
            continue
        menge, _n = _menge_und_n(f, verwendung)
        if teil.gemessen_kwh > menge * (1 + TOLERANZ):
            ueber_menge.append((f.jahr, f.monat))
        elif teil.kwh < min(teil.gemessen_kwh, menge):
            ueber_netz.append((f.jahr, f.monat))
    out = []
    if ueber_menge:
        out.append(CheckErgebnis(
            kategorie=_KAT, schwere=CheckSeverity.WARNING.value,
            meldung=f"«{label}» größer als der {mengen_wort} ({_monate_text(ueber_menge)})",
            details=(f"In {_monate_text(ueber_menge)} ist «{label}» größer als der {mengen_wort} des Geräts (Toleranz "
                     f"2 %). Mehr, als das Gerät verbraucht, kann der Versorger nicht zum {wort}-Tarif abgerechnet "
                     f"haben — eedc begrenzt den Monat auf den {mengen_wort}, die Herleitung sagt es. Prüfe den Sensor "
                     f"(«Zähler vor dem Gerät minus Zähler nach dem Gerät»)."),
        ))
    if ueber_netz:
        rest = "den Netzbezug der Anlage" if verwendung == "waermepumpe" else "den Netzbezug nach dem WP-Anteil"
        out.append(CheckErgebnis(
            kategorie=_KAT, schwere=CheckSeverity.WARNING.value,
            meldung=f"«{label}» größer als {rest} ({_monate_text(ueber_netz)})",
            details=(f"In {_monate_text(ueber_netz)} ist «{label}» größer als {rest}. Die Stromrechnung begrenzt den "
                     f"Anteil zum {wort}-Tarif darauf, die Herleitung sagt es"
                     + (" (die E-Mob-Zeile behält die Netzladung bis zur Ladung)" if verwendung == "wallbox" else "")
                     + ". Häufige Ursache: ein paralleler Zähler, der nicht im Netzbezug der Anlage steht "
                       "(Netzbezug der Anlage = Summe beider Zähler)."),
        ))
    return out
