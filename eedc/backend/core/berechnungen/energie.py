"""Energie-Aggregate aus den zentralen Tabellen.

Single Source of Truth für:
- Whitelist-Prefixe für PV-Erzeugungs-Komponenten in komponenten_kwh
- Tages-Summen aus dem komponenten_kwh-JSON

Konsumenten importieren ausschließlich aus diesem Modul, NICHT inline
re-implementieren. Konformitäts-Test prüft, dass die Prefix-Tuple bzw.
Inline-`startswith("pv_")`-Patterns außerhalb dieses Layers nicht auftauchen.
"""

from __future__ import annotations

from typing import NamedTuple, Optional


# ─── Whitelist-Konstante (SoT) ──────────────────────────────────────────────

# Komponenten-Keys in TagesZusammenfassung.komponenten_kwh, die zur PV-
# Tageserzeugung beitragen. Ein neues PV-Präfix (z. B. `wr_`) muss hier
# ergänzt werden — sonst zählen Daten-Checker, Drift-Check, Genauigkeits-
# Tracking und Reparatur-Werkbank ihn nicht mit.
#
# Spiegel im Frontend: `frontend/src/lib/constants.ts:PV_KOMPONENTEN_PREFIXE`
# (TypeScript kann nicht aus diesem Layer importieren) — dort ebenfalls ergänzen.
#
# Vor Hinzufügen eines neuen Präfixes prüfen:
# - Wird der Boundary-Pfad (lts_aggregator.py:237+ oder snapshot/aggregator.py)
#   diesen Präfix tatsächlich schreiben?
# - Ist das Naming-Schema zwischen Live-Tagesverlauf-Service
#   (live_sensor_config.TV_SERIE_CONFIG → live_tagesverlauf_service:148) und
#   Boundary-Aggregator identisch? Bei Mismatch entsteht Doppelzählung
#   (BKW-Bug 2026-05-19, Rainer-PN).
PV_KOMPONENTEN_PREFIXE: tuple[str, ...] = ("pv_", "bkw_")


# Pro Kategorie der Per-Stunde-TEP-Felder die zugehörigen komponenten_kwh-
# Präfixe, damit die Invariante (siehe core/berechnungen/invarianten.py) für
# jede Kategorie symmetrisch laufen kann (v3.33.0, Issue #290).
WAERMEPUMPE_KOMPONENTEN_PREFIXE: tuple[str, ...] = ("waermepumpe_",)
WALLBOX_KOMPONENTEN_PREFIXE: tuple[str, ...] = ("wallbox_", "eauto_")
BATTERIE_KOMPONENTEN_PREFIXE: tuple[str, ...] = ("batterie_",)
SONSTIGES_KOMPONENTEN_PREFIX: str = "sonstige_"


# ─── Σ-Helper ───────────────────────────────────────────────────────────────


def _summe_prefix(
    komponenten_kwh: Optional[dict],
    prefixe: tuple[str, ...],
    nur_positiv: bool = False,
) -> float:
    """Σ aller komponenten_kwh-Werte deren Key mit einem der Präfixe beginnt."""
    if not komponenten_kwh:
        return 0.0
    return sum(
        float(v)
        for k, v in komponenten_kwh.items()
        if isinstance(v, (int, float))
        and (not nur_positiv or v > 0)
        and any(k.startswith(p) for p in prefixe)
    )


def summe_pv_bkw_kwh(komponenten_kwh: Optional[dict]) -> float:
    """Tages-PV-Σ aus dem JSON-Feld `TagesZusammenfassung.komponenten_kwh`.

    Whitelist auf `PV_KOMPONENTEN_PREFIXE`, nur positive Werte
    (Verbraucher-Sub-Keys mit negativem Vorzeichen werden ignoriert).
    """
    return _summe_prefix(komponenten_kwh, PV_KOMPONENTEN_PREFIXE, nur_positiv=True)


def summe_pv_anlage_kwh(komponenten_kwh: Optional[dict]) -> float:
    """Tages-Σ NUR der PV-Anlagen-Module (`pv_`-Keys), ohne BKW (R17/Verlauf-Split).

    Zusammen mit {@link summe_bkw_kwh} == {@link summe_pv_bkw_kwh}: die beiden
    Präfixe partitionieren `PV_KOMPONENTEN_PREFIXE` (`("pv_", "bkw_")`) disjunkt.
    """
    return _summe_prefix(komponenten_kwh, ("pv_",), nur_positiv=True)


def summe_bkw_kwh(komponenten_kwh: Optional[dict]) -> float:
    """Tages-Σ NUR der Balkonkraftwerk-Erzeugung (`bkw_`-Keys). Siehe {@link summe_pv_anlage_kwh}."""
    return _summe_prefix(komponenten_kwh, ("bkw_",), nur_positiv=True)


def erzeuger_kwh_je_investition(komponenten_kwh: Optional[dict]) -> dict[str, float]:
    """Erzeugung **je Erzeuger-Investition** aus einem Komponenten-JSON (#350).

    Schlüssel ist die **Investitions-ID als String**, nicht der Roh-Key — und das
    ist der ganze Zweck der Funktion. Dieselbe Investition trägt je nach
    Schreibpfad zwei verschiedene Präfixe: der Live-Keyspace führt *alle*
    Erzeuger unter `pv_<id>` (auch ein Balkonkraftwerk,
    `live_komponenten_builder`/`live_history_service`), der Boundary-Keyspace
    unterscheidet `pv_<id>` und `bkw_<id>`
    (`snapshot/komponenten_beitraege._TYP_KEY_PREFIX`). Wer je Roh-Key gruppiert,
    bekommt für **ein** Balkonkraftwerk zwei Spalten, deren Belegung vom
    Schreibpfad des jeweiligen Tages abhängt — dieselbe Mismatch-Klasse, aus der
    der BKW-Doppelzählungs-Bug vom 2026-05-19 entstand (s. Kommentar an
    {@link PV_KOMPONENTEN_PREFIXE}).

    Werte werden je ID summiert und wie in {@link summe_pv_bkw_kwh} auf positive
    Beiträge beschränkt. Keys ohne numerische ID (`pv_gesamt`) fallen heraus:
    sie benennen keine Investition und wären in einer Spalte je Gerät eine
    Summe neben ihren eigenen Summanden.
    """
    if not komponenten_kwh:
        return {}
    je_inv: dict[str, float] = {}
    for key, wert in komponenten_kwh.items():
        if not isinstance(wert, (int, float)) or wert <= 0:
            continue
        praefix, _, rest = str(key).rpartition("_")
        if f"{praefix}_" not in PV_KOMPONENTEN_PREFIXE or not rest.isdigit():
            continue
        je_inv[rest] = je_inv.get(rest, 0.0) + float(wert)
    return je_inv


class SonstigesTagesSummen(NamedTuple):
    """Sonstiges-Mengen EINES Tages, nach Richtung getrennt.

    ``None`` heißt „kein Gerät dieser Richtung hat für den Tag etwas geliefert" —
    nicht 0 (``docs/KONZEPT-UNVOLLSTAENDIGE-WERTE.md``).
    """

    erzeugung_kwh: Optional[float]
    verbrauch_kwh: Optional[float]


def sonstiges_richtung(kategorie: Optional[str], hat_erzeugung: bool) -> str:
    """Zählt dieses *Sonstiges*-Gerät als ``"erzeuger"`` oder ``"verbraucher"``?

    Eine gepflegte Kategorie schlägt alles. Ist keine gepflegt, entscheidet der
    **Wert** — genau wie ``monats_fakten``, das ohne Kategorie beide Felder
    mitnimmt, und wie der Tages-Client, der die Richtung am Vorzeichen ablesen
    kann.

    **Warum es diese Funktion gibt (N-250).** Dieselbe Frage wurde im Baum
    viermal verschieden beantwortet: die beiden Tages-Schreibpfade und
    ``sonstiges_kwh_je_richtung`` unten lesen eine leere Kategorie als
    *Verbraucher*, ``aktueller_monat`` las sie als *Erzeuger* — und filterte
    denselben Zweig anschließend mit ``erzeugung > 0``. Ein ungepflegtes
    Verbrauchsgerät fiel dadurch aus dem Block „Sonstige Geräte" heraus,
    während seine Zahlen in den Summen darüber weiterliefen.

    ⚠ **Kein Default-Ersatz für die untenstehende Summenfunktion.** Dort bleibt
    „leer = Verbraucher" richtig: Sie summiert Beträge, deren Richtung feststehen
    muss, bevor ein Wert vorliegt. Hier geht es um die **Einordnung eines
    Geräts**, für die der Wert bereits bekannt ist.
    """
    if kategorie in ("erzeuger", "verbraucher"):
        return kategorie
    return "erzeuger" if hat_erzeugung else "verbraucher"


def sonstiges_kwh_je_richtung(
    komponenten_kwh: Optional[dict],
    kategorie_je_investition: dict[str, str],
) -> SonstigesTagesSummen:
    """Tages-Σ der ``sonstiges``-Geräte, getrennt in Erzeugung und Verbrauch.

    Gegenstück zur Monatsgröße aus ``SonstigesFakten`` — dieselbe Trennung, aber
    aus dem Komponenten-JSON eines Tages. Die Richtung kommt aus der **gepflegten
    Kategorie** der Investition (``parameter.kategorie``), nicht aus dem
    Vorzeichen des Werts, und das ist der Kern dieser Funktion:

    * Der **Leistungspfad** (``TagesEnergieProfil.komponenten``) trägt das
      Vorzeichen der Seite — ein Verbraucher steht dort negativ
      (gemessen: ``sonstige_10 = +0,97``/Erzeuger, ``sonstige_12 = −0,6``/Verbraucher).
    * Der **Boundary-/LTS-Pfad** (``TagesZusammenfassung.komponenten_kwh``)
      schreibt je Gerät **einen positiven** Wert, dessen Bedeutung erst die
      Kategorie ergibt (``snapshot/komponenten_beitraege.py``, Either-Or
      ``verbrauch_kwh``/``erzeugung_kwh``).

    Eine Vorzeichen-Regel lieferte für denselben Tag je nach Schreibpfad ein
    anderes Ergebnis — genau die Asymmetrie-Klasse aus
    [[feedback_aggregator_symmetrie]]. Deshalb: Richtung aus der Kategorie,
    Menge als Betrag.

    ``kategorie_je_investition`` bildet die **Investitions-ID als String** auf
    die Kategorie ab und trägt damit zugleich den Laufzeit-Filter: wer nicht
    darin steht (am Tag nicht aktiv, gelöscht, kein ``sonstiges``), zählt nicht.

    **Bewusste Lücke, sie gehört benannt:** Kategorie ``speicher`` bleibt außen
    vor. Auf Tagesebene gibt es je Gerät genau **eine** Zahl; bei einem
    bidirektionalen Gerät ist sie ein Netto-Wert und lässt sich weder der
    Erzeugung noch dem Verbrauch zuschlagen. Der Monat kann das, weil dort zwei
    getrennte Felder gepflegt werden.
    """
    # Lokaler Import: dieses Layer-Modul bleibt frei von Top-Level-Abhängigkeiten
    # zur Feld-Registry (ADR-001 — der Layer rechnet, er lädt nicht).
    from backend.core.field_definitions import ist_zaehler_kategorie

    if not komponenten_kwh or not kategorie_je_investition:
        return SonstigesTagesSummen(None, None)
    erzeugung: Optional[float] = None
    verbrauch: Optional[float] = None
    for key, wert in komponenten_kwh.items():
        if not isinstance(wert, (int, float)):
            continue
        praefix, _, rest = str(key).rpartition("_")
        if f"{praefix}_" != SONSTIGES_KOMPONENTEN_PREFIX or not rest.isdigit():
            continue
        kategorie = kategorie_je_investition.get(rest)
        if kategorie is None or kategorie == "speicher":
            continue
        # #377 — ein Verbrauchszähler (Gas/Wasser/Öl) hat gar keine
        # Stromrichtung und gehört in keine der beiden Summen.
        #
        # ⚠ **Er fiele sonst in den `else`-Zweig unten und würde als
        # VERBRAUCHER gezählt** — mit m³ in einer kWh-Summe. Neu angelegte
        # Zähler erzeugen zwar gar keinen `sonstige_<id>`-Eintrag mehr
        # (`sonstiges_feld_reihenfolge` liefert für sie `()`), aber wer ein
        # BESTEHENDES Gerät auf „Zähler" umstellt, hat die alten Einträge
        # weiterhin in seinen Tageszeilen stehen. Dieselbe Stelle, dieselbe
        # Begründung wie in `imd_monatsaggregat` für den Monat.
        if ist_zaehler_kategorie(kategorie):
            continue
        betrag = abs(float(wert))
        if kategorie == "erzeuger":
            erzeugung = (erzeugung or 0.0) + betrag
        else:
            # Leere Kategorie zählt als Verbraucher — dieselbe Vorgabe, mit der
            # **beide** Tages-Schreibpfade den Wert überhaupt erst erzeugt haben
            # (`live_sensor_config.baue_investitions_serien`,
            # `snapshot/komponenten_beitraege`). Der Monat nimmt bei leerer
            # Kategorie beide Felder mit (`imd_typ_beitrag`) — dort stehen sie
            # auch beide da.
            verbrauch = (verbrauch or 0.0) + betrag
    return SonstigesTagesSummen(erzeugung, verbrauch)


# ─── Netzpunkt-Bilanz: Gesamterzeugung hinter dem Hauszähler ────────────────


def erzeugung_hinter_zaehler_kwh(*erzeuger_kwh: Optional[float]) -> float:
    """Σ aller Erzeuger-Beiträge *hinter dem Hauszähler* — Eingang der Netzpunkt-Bilanz.

    PV-Module + Balkonkraftwerk + **sonstige Erzeuger** (z. B. Mini-BHKW/KWK).
    An EINEM Netzanschluss messen die Zähler (`einspeisung_kwh`/`netzbezug_kwh`)
    die Summe ALLER dahinter liegenden Erzeuger. Deshalb MUSS die Eigenverbrauchs-/
    Autarkie-Ableitung (`berechne_verbrauchs_kennzahlen`) diese Gesamtsumme als
    „Erzeugung" bekommen — sonst wird die Bilanz still verfälscht: ein ignorierter
    Erzeuger drückt `direktverbrauch = max(0, Erzeugung − Einspeisung − …)` zu
    niedrig (auf 0 geklemmt), und Autarkie/EV-Quote werden unterschätzt
    (Konzept „Sonstiger Erzeuger", 2026-06-22).

    Achsen-Trennung (bewusst): PV-EIGENE Kennzahlen (spez. Ertrag, Performance-
    Ratio, SOLL/IST, kWp) nutzen NUR die PV-Erzeugung, NICHT diese Summe — ein
    sonstiger Erzeuger ist energetisch Erzeuger, aber kein PV-Modul. CO₂-/
    Wirtschaftlichkeits-Bewertung bleibt ebenfalls quellenspezifisch (ein BHKW
    spart kein CO₂, sondern emittiert; Brennstoffkosten sind ein eigener Posten).
    Insel-Anlagen (kein Netzanschluss, kein Bezug/keine Einspeisung) fallen nicht
    unter diesen Begriff — das ist ein Anlagen-Merkmal (eigenes KZ, geplant).

    None-tolerant (None → 0.0). Aufrufer übergeben i. d. R. die schon
    zusammengefasste PV-(inkl. BKW-)Erzeugung + die Sonstiges-Erzeugung.
    """
    return sum(float(x or 0.0) for x in erzeuger_kwh)


def summe_waermepumpe_kwh(komponenten_kwh: Optional[dict]) -> float:
    """Σ aller `waermepumpe_<id>`-Keys (immer ≥ 0, elektrischer Verbrauch)."""
    return _summe_prefix(komponenten_kwh, WAERMEPUMPE_KOMPONENTEN_PREFIXE)


def waermepumpe_kwh_je_investition(komponenten: Optional[dict]) -> dict[str, float]:
    """Wärmepumpen-Strom **je Investition** aus einem Komponenten-JSON (#263 K-2).

    Schlüssel ist die **Investitions-ID als String**, Wert der **Betrag** der
    Energie (kWh). Zwei Fallen, die diese Funktion abfängt und die beide schon
    einmal Fehler erzeugt haben:

    1. **Die ID ist kein Präfix.** ``waermepumpe_1`` und ``waermepumpe_12`` sind
       verschiedene Geräte; ein ``startswith("waermepumpe_1")`` faltet sie
       zusammen. Hier wird die ID **exakt** getrennt.
    2. **Ein Gerät kann mehrere Keys haben.** Bei getrennter Strommessung führt
       der Live-Pfad zusätzlich ``waermepumpe_<id>_heizen`` und
       ``waermepumpe_<id>_warmwasser`` (``live_tagesverlauf_service``); beide
       gehören derselben Investition und werden summiert.

    ⚠ **Vorzeichen:** ``TagesEnergieProfil.komponenten`` führt die Wärmepumpe
    **negativ** (Leistungspfad, ``seite: "senke"`` ⇒ ``-abs(...)``),
    ``TagesZusammenfassung.komponenten_kwh`` **positiv** (Zählerpfad, s.
    {@link summe_waermepumpe_kwh}). Diese Funktion liefert für **beide**
    Eingänge den Betrag — sie ist damit die eine Stelle, an der die zwei
    Vorzeichen-Welten zusammenkommen.
    """
    if not komponenten:
        return {}
    praefix = WAERMEPUMPE_KOMPONENTEN_PREFIXE[0]
    je_inv: dict[str, float] = {}
    for key, wert in komponenten.items():
        if not isinstance(wert, (int, float)):
            continue
        name = str(key)
        if not name.startswith(praefix):
            continue
        rest = name[len(praefix):]
        # `waermepumpe_7` → "7"; `waermepumpe_7_heizen` → "7" (Suffix verworfen).
        inv_id, _, _suffix = rest.partition("_")
        if not inv_id.isdigit():
            continue
        je_inv[inv_id] = je_inv.get(inv_id, 0.0) + abs(float(wert))
    return je_inv


def summe_wallbox_eauto_kwh(komponenten_kwh: Optional[dict]) -> float:
    """Σ aller `wallbox_<id>` + `eauto_<id>`-Keys.

    Spiegelt das TEP-Feld `wallbox_kw`, das im Aggregator als
    `snap_h.get("wallbox") + snap_h.get("eauto")` zusammengesetzt wird.
    """
    return _summe_prefix(komponenten_kwh, WALLBOX_KOMPONENTEN_PREFIXE)


def geraete_spalte_kw(
    zaehler_wert: Optional[float],
    komponenten: Optional[dict],
    praefixe: tuple[str, ...],
) -> Optional[float]:
    """Geräte-Sammelspalte einer Stundenzeile — Zähler schlägt Leistungspfad.

    **Warum es diese Funktion gibt** (#263, T1; gemeldet von OB73-gif am
    2026-08-20): Dieselbe Größe liegt in `TagesEnergieProfil` an **zwei**
    Stellen, und die Sammelspalten der Tagesansicht kannten nur eine davon.

    * ``waermepumpe_kw`` / ``wallbox_kw`` kommen aus dem **Zähler-Snapshot**
      (`snap_h["wp"]`) — sie brauchen einen zugeordneten **kWh-Zählersensor**.
    * ``komponenten['waermepumpe_<id>']`` kommt aus dem **Leistungspfad** — und
      **daraus** rechnet der Monats-Modus-Split seine Aufteilung.

    Wer eine Wärmepumpe oder Klimaanlage **ohne kWh-Zähler, aber mit
    Leistungssensor** betreibt — bei Split-Klimaanlagen der Normalfall —, sah
    deshalb im Monat eine Aufteilung und im Tag eine **leere Spalte**, während
    der Wert in der gerätebenannten Spalte danebenstand.

    ⚠ **Der Fallback greift nur, wenn der Zähler fehlt.** Wo beides vorliegt,
    bleibt der Zähler die Wahrheit — sonst stünden zwei Zahlen für dieselbe
    Größe nebeneinander, und die können abweichen (Achse-2-Drift, #356).

    ⚠ **Vorzeichen:** ``TagesEnergieProfil.komponenten`` führt Senken **negativ**
    (Leistungspfad, ``seite: "senke"`` ⇒ ``-abs(...)``, N-261). Die Sammelspalte
    ist ein Betrag ⇒ hier wird der Betrag der Σ genommen.

    ⛔ **Kein Key heißt None, nicht 0.** Ein Gerät ohne jede Spur darf keine
    erfundene Null bekommen (die F-42-Klasse) — nur „hingesehen und nichts
    gefunden" wäre eine Aussage, und die haben wir hier nicht. Ein **vorhandener**
    Key mit Wert 0 ist dagegen eine echte 0 und bleibt es.

    Args:
        zaehler_wert: die Spalte aus dem Zählerpfad (``r.waermepumpe_kw`` …).
        komponenten: ``TagesEnergieProfil.komponenten`` derselben Stunde.
        praefixe: die Key-Präfixe des Geräts, z. B.
            {@link WAERMEPUMPE_KOMPONENTEN_PREFIXE}.

    Returns:
        Den Zählerwert, sonst den Betrag der Leistungspfad-Σ, sonst ``None``.
    """
    if zaehler_wert is not None:
        return zaehler_wert
    if not komponenten:
        return None
    treffer = [
        float(v) for k, v in komponenten.items()
        if isinstance(v, (int, float)) and any(str(k).startswith(p) for p in praefixe)
    ]
    if not treffer:
        return None
    return abs(sum(treffer))


def summe_batterie_netto_kwh(komponenten_kwh: Optional[dict]) -> float:
    """Σ aller `batterie_<id>`-Keys, signed in Spalten-Konvention:
    ENTLADUNG positiv (Quelle), LADUNG negativ (Senke) — identisch zur
    `TagesEnergieProfil.batterie_kw`-Spalte (s. ``batterie_kw_spalte``)."""
    return _summe_prefix(komponenten_kwh, BATTERIE_KOMPONENTEN_PREFIXE)


def batterie_kw_spalte(batt_netto_kwh: Optional[float]) -> Optional[float]:
    """Vorzeichen-SoT der Batterie-Energiewerte: **ENTLADUNG positiv** (Quelle),
    **LADUNG negativ** (Senke).

    Eingang ist das Bilanz-Netto ``ladung − entladung`` (Ladung positiv, z. B.
    ``snap_h['batterie_netto']``) — die gespeicherte Spalte/der Komponenten-Wert
    ist dessen **Negation**. Die lokale Bilanz-Formel
    ``verbrauch = pv + bezug − einspeisung − batt_netto`` nutzt weiterhin das
    Netto (Ladung positiv); nur die *gespeicherte Spalte* folgt dieser Konvention.

    Vertrag gilt für ``TagesEnergieProfil.batterie_kw`` UND
    ``komponenten[batterie_*]``/``komponenten_kwh[batterie_*]``. Consumer:
    ``tagesbilanz`` (speicher_ladung/-entladung), ``TagVerlaufChart``/
    ``TagWerteTabelle`` (bat_pos = Entladung → Quelle), ``EnergieprofilTab``-KPI,
    ``speicher_wirtschaftlichkeit`` (``batterie_kw < 0`` = Ladestunde), Achse-2-
    und TZ-Komponenten-Invarianten. Durchgängigkeit:
    ``tests/test_batterie_vorzeichen_durchgaengig.py``.
    """
    return None if batt_netto_kwh is None else -batt_netto_kwh


def wert_basis_kwh(komponenten_kwh: Optional[dict], feld: str) -> Optional[float]:
    """Liest `einspeisung` / `netzbezug` aus dem Basis-Slot — None wenn nicht gemappt."""
    if not komponenten_kwh:
        return None
    v = komponenten_kwh.get(feld)
    return float(v) if isinstance(v, (int, float)) else None
