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

**F12 — gemeinsamer Zähler WP + Wallbox (E6, Verwendung ``waermepumpe_wallbox``):** das Feld an der WP trägt N_g
(``monats_fakten.tarif._anteile_gemeinsam``, F12a = A). Dann statt der beiden Komponenten:

* **WARNING — Vorrang:** ein eigener WP- bzw. Wallbox-Tarif gilt am selben Stichtag wie der gemeinsame — er hat Vorrang
  für seine Verwendung (``strompreise.tarife_zum_stichtag``), der gemeinsame gilt nur noch für die andere.
* **WARNING — Feld an der Wallbox:** unter dem gemeinsamen Tarif zählt ein «Netzbezug zum Wallbox-Tarif» nicht in der
  Stromrechnung (N_g steht an der WP, sonst doppelt).
* **INFO — Feld fehlt** (Obergrenze wie oben mit S_wp + L_wb) · **WARNING — geklemmt:** N_g > S_wp + L_wb (2 %) bzw.
  > Netzbezug · **WARNING — N_wb > N_g:** die Netzladung der Wallbox nach der bisherigen Regel übersteigt den
  gemeinsamen Netzbezug, N_wb wird auf N_g geklemmt.
* **INFO — Tage teilen nicht** (Auftrag §3.4): Monate mit gemeinsamem Zähler und Ladung > 0 — ohne Stundenwerte der
  Wallbox teilt der Tag die Eigenverbrauchs-Ersparnis nicht, der Monat trägt den Wert (benannte Grenze analog F9).
* G1 (paralleler Zähler) gilt an der WP sinngemäß.

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
from .ziele import ziel_datenquelle, ziel_tarif

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
#: F12 (E6): der gemeinsame Zähler WP + Wallbox — Anwenderwort, Feld-Label (an der WP), Mengenwort.
GEMEINSAM = "waermepumpe_wallbox"
_GEMEINSAM_TEXTE = ("Wärmepumpen-/Wallbox", "Netzbezug zum WP-/Wallbox-Tarif (gemeinsamer Zähler)", None,
                    "WP-Strom und Ladung", None)


def _monat_minus(jahr: int, monat: int, n: int) -> tuple[int, int]:
    """``(jahr, monat)`` minus ``n`` Monate."""
    idx = jahr * 12 + (monat - 1) - n
    return idx // 12, idx % 12 + 1


def _monate_text(monate) -> str:
    return ", ".join(f"{m:02d}/{j}" for j, m in sorted(monate))


def _texte(verwendung: str) -> tuple:
    return _GEMEINSAM_TEXTE if verwendung == GEMEINSAM else _KOMPONENTEN[verwendung]


def _menge_und_n(fakt, verwendung: str) -> tuple[float, Optional[float]]:
    if verwendung == GEMEINSAM:
        return fakt.wp.strom_kwh + fakt.emob.wallbox_ladung_alle_kwh, fakt.wp.netz_eigener_tarif_kwh
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
        from backend.services.monats_fakten.tarif import komponenten_tarif_gemeinsam

        gemeinsam = komponenten_tarif_gemeinsam(tarife)
        out: list[CheckErgebnis] = _vorrang_vor_gemeinsam(zeilen)
        verwendungen = [
            v for v in _KOMPONENTEN
            if (t := resolve_tarif_for_komponente(tarife, v)) is not None and t is not allgemein
            and t.netzbezug_arbeitspreis_cent_kwh != allgemein.netzbezug_arbeitspreis_cent_kwh
        ]
        if not verwendungen:
            return out
        # F12: unter dem gemeinsamen Tarif EINE Prüfung über den gemeinsamen Netzbezug N_g (Feld an der WP).
        pruefungen = [GEMEINSAM] if gemeinsam else verwendungen

        from backend.services.monats_fakten import lade_monats_fakten, tarif_des_monats

        tarif = await tarif_des_monats(self.db, anlage.id, stichtag.year, stichtag.month)
        fenster = (_monat_minus(stichtag.year, stichtag.month, FENSTER_MONATE),
                   _monat_minus(stichtag.year, stichtag.month, 1))
        fakten = await lade_monats_fakten(self.db, anlage.id, von=fenster[0], bis=fenster[1], inkl_nur_tageswerte=True)
        for v in pruefungen:
            komp_cent = tarif.wallbox_preis_effektiv_cent if v == "wallbox" else tarif.wp_preis_cent
            out += _feld_fehlt(v, fakten, komp_cent, tarif.netzbezug_stammpreis_cent)
            out += _geklemmt(v, fakten, _geraet_mit_feld(anlage, tag, "wallbox" if v == "wallbox" else "waermepumpe"))
        out += await self._parallele_zaehler(anlage, ["waermepumpe"] if gemeinsam else verwendungen)
        if gemeinsam:
            out += _gemeinsam_tage_und_wallbox(fakten, _geraet_mit_feld(anlage, tag, "waermepumpe"))
            out += await self._feld_an_wallbox_unter_gemeinsam(anlage, fenster, tarife["waermepumpe"].id)
        elif "wallbox" in verwendungen:
            out += await self._evcc_weicht_ab(anlage, fenster)
        return out

    async def _feld_an_wallbox_unter_gemeinsam(self, anlage: Anlage, fenster, tarif_id: int) -> list[CheckErgebnis]:
        """F12: ein «Netzbezug zum Wallbox-Tarif» an einer Wallbox (zugeordnet oder in einer Monatszeile des Fensters)
        zählt unter dem gemeinsamen Tarif nicht in der Stromrechnung — sonst stünde N_wb doppelt (N_g steht an der WP)."""
        from backend.models.investition import Investition, InvestitionMonatsdaten

        (von_j, von_m), (bis_j, bis_m) = fenster
        mapping = ((anlage.sensor_mapping or {}).get("investitionen") or {})
        zeilen = (await self.db.execute(
            select(Investition.id, Investition.bezeichnung, InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat,
                   InvestitionMonatsdaten.verbrauch_daten)
            .outerjoin(InvestitionMonatsdaten, InvestitionMonatsdaten.investition_id == Investition.id)
            .where(and_(Investition.anlage_id == anlage.id, Investition.typ == "wallbox"))
        )).all()
        namen: dict[int, str] = {}
        for inv_id, name, j, m, vd in zeilen:
            zugeordnet = bool(((mapping.get(str(inv_id)) or {}).get("felder") or {}).get(FELD))
            im_fenster = j is not None and von_j * 12 + von_m <= j * 12 + m <= bis_j * 12 + bis_m
            if zugeordnet or (im_fenster and (vd or {}).get(FELD) is not None):
                namen[inv_id] = name
        return [CheckErgebnis(
            kategorie=_KAT, schwere=CheckSeverity.WARNING.value, code="wp_tarif_wallbox_netzbezug_zaehlt_nicht", ziel=ziel_tarif(tarif_id), investition_id=inv_id,
            meldung=f"{name}: «Netzbezug zum Wallbox-Tarif» zählt unter dem gemeinsamen Tarif nicht",
            details=(
                f"Für Wärmepumpe und Wallbox gilt ein gemeinsamer Tarif (ein Zähler vor beiden Geräten). Den gemeinsamen "
                f"Netzbezug trägt das Feld «Netzbezug zum WP-/Wallbox-Tarif (gemeinsamer Zähler)» an der Wärmepumpe; ein "
                f"Wert an {name} zählt in der Stromrechnung nicht (er stünde sonst doppelt). Entferne die Zuordnung an der "
                f"Wallbox bzw. ordne den Zähler an der Wärmepumpe zu. Erklärt im Handbuch „Wärme & Klima“, Schritt 6b."
            ),
        ) for inv_id, name in sorted(namen.items())]

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
                    kategorie=_KAT, schwere=CheckSeverity.INFO.value, code="paralleler_zaehler", ziel=ziel_datenquelle(geraet=inv.id, feld=FELD), investition_id=inv.id,
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
        weichen ab ⇒ WARNING mit den Monaten (es gilt N, der Zähler des Versorgers). Der Sprung öffnet die Wallbox ohne
        Feld (E6.D D3, Wächter W-14): ein Feld «Netzladung» gibt es an der Wallbox nicht."""
        from backend.core.field_definitions import get_eauto_ladung_kwh
        from backend.models.investition import Investition, InvestitionMonatsdaten

        from backend.services.kanal.netzanteil_leser import zuordnungsmonate_der_wallboxen

        (von_j, von_m), (bis_j, bis_m) = fenster
        zeilen = (await self.db.execute(
            select(Investition.id, Investition.bezeichnung, InvestitionMonatsdaten.jahr, InvestitionMonatsdaten.monat,
                   InvestitionMonatsdaten.verbrauch_daten)
            .join(InvestitionMonatsdaten, InvestitionMonatsdaten.investition_id == Investition.id)
            .where(and_(Investition.anlage_id == anlage.id, Investition.typ == "wallbox"))
        )).all()
        # N-771 Rest 1 (E6): im Zuordnungsmonat des Felds gilt N nicht als Netzladung — dort gibt es keine Abweichung.
        zuordnung = await zuordnungsmonate_der_wallboxen(self.db, anlage.id, [(z[0], z[4]) for z in zeilen])
        je_inv: dict[int, tuple[str, list]] = {}
        for inv_id, name, j, m, vd in zeilen:
            if not (von_j * 12 + von_m <= j * 12 + m <= bis_j * 12 + bis_m) or zuordnung.get(inv_id) == (j, m):
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
            kategorie=_KAT, schwere=CheckSeverity.WARNING.value, code="evcc_netzladung_abweichung", ziel=ziel_datenquelle(geraet=inv_id), investition_id=inv_id,
            meldung=f"{name}: Netzladung aus evcc weicht vom Netzbezug zum Wallbox-Tarif ab ({_monate_text(monate)})",
            details=(
                f"In {_monate_text(monate)} trägt {name} neben dem «Netzbezug zum Wallbox-Tarif» einen PV-/Netz-Anteil "
                f"(z. B. aus evcc), und beide nennen eine andere Netzladung. eedc rechnet mit dem Zähler des Versorgers: "
                f"Netzladung = Netzbezug zum Wallbox-Tarif, PV-Ladung = Ladung − Netzladung (E-Mob-Ersparnis, "
                f"Heimladekosten, Stromrechnung). Prüfe, ob beide Sensoren dieselbe Wallbox messen; erklärt im Handbuch "
                f"„E-Mobilität“ (Netzbezug zum Wallbox-Tarif)."
            ),
        ) for inv_id, (name, monate) in je_inv.items()]


def _vorrang_vor_gemeinsam(zeilen) -> list[CheckErgebnis]:
    """F12: gilt am Stichtag neben dem gemeinsamen Tarif ein eigener WP- bzw. Wallbox-Tarif, hat er Vorrang für seine
    Verwendung (``strompreise.tarife_zum_stichtag``) — WARNING, wer Vorrang hat."""
    verwendungen = {t.verwendung or "allgemein" for t in zeilen}
    if GEMEINSAM not in verwendungen:
        return []
    return [CheckErgebnis(
        kategorie=_KAT, schwere=CheckSeverity.WARNING.value, code="eigener_tarif_vorrang", ziel=ziel_tarif(next(t.id for t in zeilen if t.verwendung == v)),
        meldung=f"Eigener {_KOMPONENTEN[v][0]}-Tarif hat Vorrang vor dem gemeinsamen Tarif «Wärmepumpe und Wallbox»",
        details=(
            f"Zum selben Stichtag gelten ein Tarif «{ 'Wärmepumpe' if v == 'waermepumpe' else 'Wallbox' }» und ein "
            f"gemeinsamer Tarif «Wärmepumpe und Wallbox». eedc rechnet die {_KOMPONENTEN[v][0]} mit dem eigenen Tarif, "
            f"der gemeinsame gilt nur noch für das andere Gerät — dann ist es kein gemeinsamer Zähler mehr. Hängen beide "
            f"Geräte hinter einem Zähler, beende den eigenen Tarif; erklärt im Handbuch „Einstellungen“ (Strompreise)."
        ),
    ) for v in ("waermepumpe", "wallbox") if v in verwendungen]


def _geraet_mit_feld(anlage: Anlage, tag: date, typ: str) -> Optional[int]:
    """Das Gerät des Typs ``typ`` (Wärmepumpe bzw. Wallbox), das «Netzbezug zum …-Tarif» trägt — Sprungziel der
    Meldungen ohne eigenes Gerät (E6.D D3 und H-E6-11 Option A, Wächter W-14): unter den heute aktiven das mit
    zugeordnetem Feld, sonst das einzige; mehrdeutig ⇒ ``None`` (der Sprung öffnet dann die Zuordnung ohne Gerät und ohne
    Feld). Beim gemeinsamen Zähler (F12) trägt die Wärmepumpe das Feld. Aus ``anlage.investitionen`` (vom Checker
    geladen), keine eigene Abfrage."""
    geraete = sorted(i.id for i in anlage.investitionen if i.typ == typ and i.ist_aktiv_an(tag))
    mapping = ((anlage.sensor_mapping or {}).get("investitionen") or {})
    mit_feld = [i for i in geraete if ((mapping.get(str(i)) or {}).get("felder") or {}).get(FELD)]
    if len(mit_feld) == 1:
        return mit_feld[0]
    return geraete[0] if len(geraete) == 1 else None



def _gemeinsam_tage_und_wallbox(fakten, wp_id: Optional[int] = None) -> list[CheckErgebnis]:
    """F12: INFO «Tage teilen nicht» (Monate mit gemeinsamem Zähler und Ladung > 0, Auftrag §3.4) und WARNING «N_wb > N_g»
    (die Netzladung der Wallbox nach der bisherigen Regel übersteigt den gemeinsamen Netzbezug, §3.3). Der Sprung der
    WARNING zeigt auf das Feld des gemeinsamen Zählers an der Wärmepumpe ``wp_id`` (E6.D D3) — nie «erstes Gerät mit dem
    Feld»; ohne eindeutige Wärmepumpe die Zuordnung ohne Feld."""
    from backend.services.monats_fakten import komponenten_anteile_des_fakts

    tage, ueber = [], []
    for f in fakten:
        a = komponenten_anteile_des_fakts(f)
        if a is None or a.gemeinsam_wallbox_kwh is None or f.emob.wallbox_ladung_alle_kwh <= 0:
            continue
        tage.append((f.jahr, f.monat))
        if (a.gemeinsam_wallbox_regel_kwh or 0.0) > a.netz[0].kwh + 0.005:
            ueber.append((f.jahr, f.monat))
    out = []
    if tage:
        out.append(CheckErgebnis(
            kategorie=_KAT, schwere=CheckSeverity.INFO.value, code="gemeinsamer_zaehler_tage_ohne_teilung",
            meldung=f"Gemeinsamer Zähler Wärmepumpe + Wallbox: Tage teilen die Ersparnis nicht ({_monate_text(tage)})",
            details=(f"In {_monate_text(tage)} rechnet eedc die Stromrechnung mit dem gemeinsamen Netzbezug je Stunde. "
                     f"Die Eigenverbrauchs-Ersparnis teilt der einzelne Tag aber nicht in Wärmepumpe und Wallbox: dafür "
                     f"fehlen Stundenwerte der Netzladung der Wallbox. Der Tag rechnet sie wie ohne gemeinsamen Zähler, "
                     f"der Monat trägt den genauen Wert — die Summe der Tage weicht bei der Ersparnis vom Monat ab. Kein "
                     f"Handlungsbedarf; erklärt unter „Berechnungen“ und im Handbuch „Wärme & Klima“, Schritt 6b."),
        ))
    if ueber:
        out.append(CheckErgebnis(
            kategorie=_KAT, schwere=CheckSeverity.WARNING.value, code="wallbox_netzladung_groesser_gemeinsamer_netzbezug",
            ziel=ziel_datenquelle(geraet=wp_id, feld=FELD) if wp_id is not None else ziel_datenquelle(),
            meldung=f"Netzladung der Wallbox größer als der gemeinsame Netzbezug ({_monate_text(ueber)})",
            details=(f"In {_monate_text(ueber)} ist die Netzladung der Wallbox (evcc-Wert bzw. Tagesquote) größer als der "
                     f"«Netzbezug zum WP-/Wallbox-Tarif (gemeinsamer Zähler)». eedc setzt den Wallbox-Teil auf den "
                     f"gemeinsamen Netzbezug, der Wärmepumpe bleibt kein Netzanteil. Prüfe den Zähler («Zähler vor beiden "
                     f"Geräten minus Zähler danach») und die Netzladung der Wallbox."),
        ))
    return out


def _feld_fehlt(verwendung: str, fakten, komp_cent: float, haushalt_cent: float) -> list[CheckErgebnis]:
    """INFO, wenn ein Monat mit Gerätemenge > 0 das Feld nicht misst — mit der Obergrenze für Ersparnis UND
    Stromrechnung (F7); still, wenn jeder solche Monat gemessen ist. F12: beim gemeinsamen Zähler mit S_wp + L_wb."""
    wort, label, _feld, mengen_wort, _ = _texte(verwendung)
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
    elif verwendung == GEMEINSAM:
        wirkung = (f"eedc rechnet den Netzbezug von Wärmepumpe und Wallbox in der Stromrechnung dann zum Haushaltstarif "
                   f"({fmt_zahl(haushalt_cent, 2)} ct) statt zum gemeinsamen Tarif ({fmt_zahl(komp_cent, 2)} ct) und "
                   f"bewertet den PV-Anteil der Wärmepumpe zum Haushaltstarif")
    else:
        wirkung = (f"eedc rechnet die Netzladung der Wallbox in der Stromrechnung dann zum Haushaltstarif "
                   f"({fmt_zahl(haushalt_cent, 2)} ct) statt zum Wallbox-Tarif ({fmt_zahl(komp_cent, 2)} ct), und die "
                   f"Netzladung selbst ist eedcs Aufteilung (evcc bzw. Tagesquote), keine Messung")
    return [CheckErgebnis(
        kategorie=_KAT, schwere=CheckSeverity.INFO.value, code="wp_eigener_tarif_obergrenze",
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


def _geklemmt(verwendung: str, fakten, geraet_id: Optional[int] = None) -> list[CheckErgebnis]:
    """WARNING je Komponente: Monate, deren gemessenes N über der Gerätemenge (Toleranz 2 %) oder über dem Netzbezug
    (Wallbox: über dem Rest nach der WP) liegt — der Monat rechnet begrenzt (``komponenten_anteile``, F7)."""
    from backend.services.monats_fakten import komponenten_anteile_des_fakts

    wort, label, _feld, mengen_wort, _ = _texte(verwendung)
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
            kategorie=_KAT, schwere=CheckSeverity.WARNING.value, code="tarif_mengenfeld_groesser_als_menge", ziel=ziel_datenquelle(geraet=geraet_id, feld=FELD) if geraet_id is not None else ziel_datenquelle(),
            meldung=f"«{label}» größer als der {mengen_wort} ({_monate_text(ueber_menge)})",
            details=(f"In {_monate_text(ueber_menge)} ist «{label}» größer als der {mengen_wort} des Geräts (Toleranz "
                     f"2 %). Mehr, als das Gerät verbraucht, kann der Versorger nicht zum {wort}-Tarif abgerechnet "
                     f"haben — eedc begrenzt den Monat auf den {mengen_wort}, die Herleitung sagt es. Prüfe den Sensor "
                     f"(«Zähler vor dem Gerät minus Zähler nach dem Gerät»)."),
        ))
    if ueber_netz:
        rest = "den Netzbezug der Anlage" if verwendung != "wallbox" else "den Netzbezug nach dem WP-Anteil"
        out.append(CheckErgebnis(
            kategorie=_KAT, schwere=CheckSeverity.WARNING.value, code="tarif_mengenfeld_groesser_als_rest", ziel=ziel_datenquelle(geraet=geraet_id, feld=FELD) if geraet_id is not None else ziel_datenquelle(),
            meldung=f"«{label}» größer als {rest} ({_monate_text(ueber_netz)})",
            details=(f"In {_monate_text(ueber_netz)} ist «{label}» größer als {rest}. Die Stromrechnung begrenzt den "
                     f"Anteil zum {wort}-Tarif darauf, die Herleitung sagt es"
                     + (" (die E-Mob-Zeile behält die Netzladung bis zur Ladung)" if verwendung == "wallbox" else "")
                     + ". Häufige Ursache: ein paralleler Zähler, der nicht im Netzbezug der Anlage steht "
                       "(Netzbezug der Anlage = Summe beider Zähler)."),
        ))
    return out
