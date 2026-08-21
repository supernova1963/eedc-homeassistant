"""Betriebsmodus einer Wärmepumpe/Klimaanlage — Kanon und Normalisierung (#263 K-2, S1).

**Warum es diese Datei gibt.** Eine Split-Klimaanlage ist physikalisch eine
Luft-Luft-Wärmepumpe: dasselbe Gerät heizt im Winter und kühlt im Sommer, über
**denselben** Stromzähler (Konzept `docs/KONZEPT-263-klima-split.md`, D4). Die
Aufteilung „was ging ins Heizen, was ins Kühlen" ist aus keinem vorhandenen Feld
rekonstruierbar — sie entsteht nur, wenn eedc den Betriebsmodus **zur Messzeit**
mitschreibt.

**Der Lesepfad ist bewusst eng gehalten** (Konzept §3.3): eine feste Wertemenge,
eine Normalisierungstabelle Hersteller→Kanon, sonst nichts. Ein zweiter
Anwendungsfall für einen generischen Zustandssensor existiert nicht, und die
P-11-Lehre lautet: nicht auf Vorrat bauen.

**Was hier NICHT passiert:** Es wird nichts geraten. `auto`/`heat_cool` und jeder
unbekannte Wert werden zu `unbestimmt` — sie einer Seite zuzuschlagen wäre eine
erfundene Aufteilung (ADR-002/P4). `unbestimmt` fällt später in die abgeleitete
Zeile „nicht aufgeteilt", zusammen mit Entfeuchten, Lüften und Standby.

⚠ **`hvac_action` (der Ist-Betrieb) wird NICHT verlangt** (Konzept D2): in
HA-Core definiert nur `AtwDeviceZoneClimate` (Luft-**Wasser**) die Property;
`AtaDeviceClimate` (Luft-Luft, also genau der Klimaanlagen-Fall) und die
Basisklasse nicht. Wer sie verlangt, baut für Daikin und sperrt den Rest aus.
Wo sie vorhanden ist, **verfeinert** sie — deshalb der optionale zweite
Parameter, nie eine Bedingung.
"""

from typing import Final, Optional

# ── Kanon ────────────────────────────────────────────────────────────────────
#
# Sechs Werte. Gespeichert und ausgewiesen werden später nur die Teilmengen zu
# `heizen` und `kuehlen`; die vier übrigen Klassen fallen in „nicht aufgeteilt"
# (Konzept §3.3, belegt durch D11: in der Praxis fahren die drei Melder nur
# Heizen und Kühlen, der Modus wird saisonal manuell gestellt).
HEIZEN: Final[str] = "heizen"
KUEHLEN: Final[str] = "kuehlen"
ENTFEUCHTEN: Final[str] = "entfeuchten"
LUEFTEN: Final[str] = "lueften"
AUS: Final[str] = "aus"
UNBESTIMMT: Final[str] = "unbestimmt"

BETRIEBSMODUS_KANON: Final[tuple[str, ...]] = (
    HEIZEN, KUEHLEN, ENTFEUCHTEN, LUEFTEN, AUS, UNBESTIMMT,
)

# Die beiden Klassen, für die es eine eigene Teilmenge gibt.
AUFGETEILTE_MODI: Final[frozenset[str]] = frozenset({HEIZEN, KUEHLEN})

#: Kanon → deutscher Klartext für die **Zuordnungs-Fläche** (F-52/F-53).
#:
#: **Warum das hier steht und nicht im Frontend:** Es ist keine Formatierung,
#: sondern die Deutung eines Kanon-Werts — und der Kanon liegt in dieser Datei.
#: Eine zweite Tabelle im Client wäre genau die Drift, gegen die `MODUS_STROM_FELD`
#: einen Wächter hat. Die Zahlen-Labels der Auswertung („davon Heizen") sind
#: davon unberührt: sie beschriften eine **Menge**, nicht einen Zustand.
BETRIEBSMODUS_LABEL: Final[dict[str, str]] = {
    HEIZEN: "Heizen",
    KUEHLEN: "Kühlen",
    ENTFEUCHTEN: "Entfeuchten",
    LUEFTEN: "Lüften",
    AUS: "Aus",
    UNBESTIMMT: "Unbestimmt",
}


# ── Feldnamen der Teilmengen (#263 K-2, S3) ──────────────────────────────────
#
# **Warum eigene Namen und nicht `strom_heizen_kwh`** (Entscheid E-G, gemessen
# 2026-08-18; das Konzept empfahl in §3.2 noch die Wiederverwendung): Dieses
# Feld gibt es bereits, aber es trägt dort eine **andere** Bedeutung — bei
# `getrennte_strommessung=True` ist es ein **Summand**
# (`Gesamt = strom_heizen + strom_warmwasser`), hier wäre es eine **Teilmenge**
# von `stromverbrauch_kwh`. Drei Stellen schließen aus seiner bloßen
# **Anwesenheit** auf die getrennte Messung und würden mitkippen:
# `investitionen/dashboards.py` (`if 'strom_heizen_kwh' in d`) → daran hängt
# `cop_heizen`, und daran wiederum `WaermepumpeHubBloecke.tsx`
# (`hatGetrennteStrom`). Mit abgeleiteter Wärme (§3.4) käme dort als „JAZ"
# exakt die gepflegte JAZ heraus — der §3.5-Verstoß, gegen den S3 gebaut ist.
# Eigene Namen machen die Kollision **strukturell** unmöglich, statt sie an
# vier Stellen abzufangen; und eine WP mit getrennter Messung **und**
# Modus-Sensor behält beide Angaben nebeneinander.
#
# ⚑ **Die Namen sind an den Kanon gebunden, nicht frei gewählt.** Sie stehen
# hier ausgeschrieben (nicht generiert), weil dieses Projekt von der
# Grep-Barkeit lebt — aber `test_263_k2_modus_split.py::test_feldnamen_folgen_dem_kanon`
# hält sie gegen `AUFGETEILTE_MODI`: für jeden aufgeteilten Modus genau ein
# Feld, und jeder Name genau `modus_strom_<modus>_kwh`. Eine siebte
# Betriebsart kostet damit **einen Eintrag oben** — und der Wächter sagt
# sofort, was dazu fehlt. Ohne ihn wäre „eine spätere Betriebsart kostet ein
# Feld, keine Migration" (Konzept §3.1, Folge 4) eine Behauptung.
MODUS_STROM_FELD: Final[dict[str, str]] = {
    HEIZEN: "modus_strom_heizen_kwh",
    KUEHLEN: "modus_strom_kuehlen_kwh",
}


# ── GEMESSENE Betriebsart-Felder (#263, Fassung 2026-08-21) ──────────────────
#
# **Der Unterschied zu `MODUS_STROM_FELD` ist die Herkunft, nicht die Größe.**
# Dort steht, was eedc aus dem Betriebsmodus **abgeleitet** hat; hier steht,
# was ein Zähler **gemessen** hat. Beides nebeneinander zu führen ist kein
# Doppel, sondern dieselbe Unterscheidung, die eedc bei der Heizwärme längst
# macht (`waerme_abgeleitet`): eine gerechnete Zahl darf nie wie eine gemessene
# aussehen. Der Vorrang liegt an genau einer Stelle
# (`core/berechnungen/imd_monatsaggregat.py`): **gemessen schlägt abgeleitet**,
# nie beides addiert.
#
# **Warum eigene Namen und nicht `strom_heizen_kwh`.** Das gibt es schon und
# bedeutet etwas anderes — bei `getrennte_strommessung=True` ist es ein
# **Summand** (Gesamt = Heizen + Warmwasser), hier wäre es eine **Teilmenge**
# des Gesamtverbrauchs. Drei Stellen schließen aus seiner bloßen Anwesenheit
# auf die getrennte Messung. Dieselbe Begründung wie oben bei
# `MODUS_STROM_FELD`, nur eine Ebene weiter.
#
# **Alle vier Betriebsarten, nicht nur die zwei aufgeteilten.** Der abgeleitete
# Split kann nur Heizen und Kühlen (mehr gibt ein Modus-Signal nicht her, D11);
# ein Zähler kann jede Betriebsart messen, und wer sich per Utility-Meter vier
# Tarife baut, hat vier Zahlen. `AUFGETEILTE_MODI` bleibt davon **unberührt** —
# die abgeleitete Aufteilung ändert sich nicht.
#
# Ausgeschrieben statt generiert, aus demselben Grund wie oben (Grep-Barkeit);
# `test_263_betriebsart_felder.py` hält beide Tabellen gegen den Kanon.

#: Betriebsarten, für die es einen **messbaren** Verbrauch geben kann.
MESSBARE_MODI: Final[tuple[str, ...]] = (HEIZEN, KUEHLEN, LUEFTEN, ENTFEUCHTEN)

#: Gemessener **Strom**verbrauch je Betriebsart (Teilmenge des Gesamtverbrauchs).
BETRIEBSART_STROM_FELD: Final[dict[str, str]] = {
    HEIZEN: "betriebsart_strom_heizen_kwh",
    KUEHLEN: "betriebsart_strom_kuehlen_kwh",
    LUEFTEN: "betriebsart_strom_lueften_kwh",
    ENTFEUCHTEN: "betriebsart_strom_entfeuchten_kwh",
}

#: Gemessene **abgegebene Nutzenergie** je Betriebsart (Wärme bzw. Kälte).
#: Bewusst nicht „waerme": im Kühlbetrieb ist die Nutzenergie Kälte, und ein
#: Feldname, der etwas anderes behauptet als er trägt, ist die Klasse, an der
#: `heizenergie_kwh` schon einmal missverstanden wurde (#120).
BETRIEBSART_NUTZENERGIE_FELD: Final[dict[str, str]] = {
    HEIZEN: "betriebsart_nutzenergie_heizen_kwh",
    KUEHLEN: "betriebsart_nutzenergie_kuehlen_kwh",
    LUEFTEN: "betriebsart_nutzenergie_lueften_kwh",
    ENTFEUCHTEN: "betriebsart_nutzenergie_entfeuchten_kwh",
}

#: Deutsche Bezeichnung der Betriebsart für Feld-Labels. Getrennt von
#: `BETRIEBSMODUS_LABEL`, weil das dort ein **Zustand** ist („Kühlen") und hier
#: eine **Betriebsphase** benannt wird („Kühlbetrieb") — dieselbe Trennung, die
#: `betriebsmodus_klartext` von den Mengen-Labels trennt.
BETRIEBSART_LABEL: Final[dict[str, str]] = {
    HEIZEN: "Heizbetrieb",
    KUEHLEN: "Kühlbetrieb",
    LUEFTEN: "Lüftbetrieb",
    ENTFEUCHTEN: "Entfeuchtungsbetrieb",
}

#: Stunden des Monats mit **gültigem Modus-Signal** — das Qualitätsmaß neben
#: den zwei Mengen (Konzept §3.3). Es trennt die zwei Fälle, die der Anwender
#: unterscheiden können muss: „lief in anderen Betriebsarten" (Abdeckung hoch,
#: Rest > 0) gegen „eedc hat nicht hingesehen" (Abdeckung niedrig).
#: Zugleich die Zeitbasis, die K-1 (SEER) ohnehin braucht.
MODUS_ABDECKUNG_FELD: Final[str] = "modus_abdeckung_h"

#: Alle drei Felder, die der Modus-Split in `verbrauch_daten` schreibt — für
#: Schreibpfad, Wächter und die Stellen, die sie **nicht** als Bilanzgröße
#: behandeln dürfen.
MODUS_SPLIT_FELDER: Final[tuple[str, ...]] = (
    *sorted(MODUS_STROM_FELD.values()), MODUS_ABDECKUNG_FELD,
)


# ── Normalisierung Hersteller → Kanon ────────────────────────────────────────
#
# Grundlage ist `HVACMode` aus HA-Core: HA normalisiert die Herstellerwerte
# bereits auf diese sieben Zeichenketten, bevor sie im State stehen. Die
# deutschen Schreibweisen daneben fangen Template-Sensoren ab, mit denen sich
# Anwender den Modus heute selbst bauen (der Weg, den kingcap1 und dietmar1968
# im Forum beschrieben haben).
#
# ⚠ `auto` und `heat_cool` stehen bewusst auf `unbestimmt` und nicht auf einer
# der beiden Seiten: das Gerät entscheidet dort selbst, und ohne `hvac_action`
# weiß eedc nicht, was es gerade tut (D1/D2).
_ZUSTAND_ZU_KANON: Final[dict[str, str]] = {
    # HVACMode (HA-Core)
    "heat": HEIZEN,
    "cool": KUEHLEN,
    "dry": ENTFEUCHTEN,
    "fan_only": LUEFTEN,
    "off": AUS,
    "auto": UNBESTIMMT,
    "heat_cool": UNBESTIMMT,
    # Deutsche Schreibweisen aus selbstgebauten Template-Sensoren
    "heizen": HEIZEN,
    "kuehlen": KUEHLEN,
    "kühlen": KUEHLEN,
    "entfeuchten": ENTFEUCHTEN,
    "lueften": LUEFTEN,
    "lüften": LUEFTEN,
    "aus": AUS,
    "automatik": UNBESTIMMT,
}

# `HVACAction` (HA-Core) — nur wo die Integration sie überhaupt liefert.
# Sie beschreibt den **Ist**-Betrieb und schlägt deshalb den eingestellten
# Modus, wenn beide da sind. `idle` ist ausdrücklich KEIN `aus`: das Gerät ist
# an und wartet (Standby-Verbrauch, D6 — 10 W, weil das Außengerät drei
# Innengeräte samt WLAN versorgt). Es einer Heiz- oder Kühlseite zuzuschlagen
# wäre falsch, „aus" zu nennen ebenfalls ⇒ `unbestimmt`.
_AKTION_ZU_KANON: Final[dict[str, str]] = {
    "heating": HEIZEN,
    "preheating": HEIZEN,
    "defrosting": HEIZEN,
    "cooling": KUEHLEN,
    "drying": ENTFEUCHTEN,
    "fan": LUEFTEN,
    "off": AUS,
    "idle": UNBESTIMMT,
}

# States, die HA für „gerade nichts zu sagen" benutzt. Sie sind **kein**
# Betriebsmodus und dürfen nicht zu `unbestimmt` werden: `unbestimmt` heißt
# „das Gerät lief, eedc kann die Seite nicht zuordnen", diese hier heißen
# „eedc hat gar nicht hingesehen". Der Unterschied trägt später die
# Abdeckungs-Kennzahl (Konzept §3.3).
_KEIN_ZUSTAND: Final[frozenset[str]] = frozenset({"unknown", "unavailable", "none", ""})


def normalisiere_betriebsmodus(
    zustand: Optional[str],
    hvac_action: Optional[str] = None,
) -> Optional[str]:
    """Roher HA-State → Kanon-Wert, oder ``None`` wenn es keinen Modus gibt.

    Args:
        zustand: der State der `climate`-Entität (bzw. eines Template-Sensors),
            z. B. ``"heat"``. Groß-/Kleinschreibung und Randleerzeichen sind egal.
        hvac_action: optional der Ist-Betrieb (Attribut ``hvac_action``). Wo
            vorhanden, **schlägt er** den eingestellten Modus — aber er wird nie
            verlangt (D2). Ein `hvac_action`, das eedc nicht kennt, wird
            ignoriert statt den vorhandenen Modus zu verwerfen.

    Returns:
        Einen Wert aus {@link BETRIEBSMODUS_KANON}, oder ``None`` für
        „kein verwertbarer Zustand" (Entity fehlt, `unknown`, `unavailable`).

        ⚠ ``None`` und ``"unbestimmt"`` sind **nicht** dasselbe und dürfen nie
        ineinander übersetzt werden: ``None`` heißt „nicht hingesehen",
        ``unbestimmt`` heißt „hingesehen, Seite nicht zuordenbar". Genau diese
        zwei Fälle muss der Anwender später unterscheiden können.
    """
    if hvac_action is not None:
        aktion = str(hvac_action).strip().lower()
        if aktion in _AKTION_ZU_KANON:
            return _AKTION_ZU_KANON[aktion]

    if zustand is None:
        return None
    roh = str(zustand).strip().lower()
    if roh in _KEIN_ZUSTAND:
        return None

    # Unbekannter, aber vorhandener Wert: das Gerät hat etwas gemeldet, eedc
    # kann es nur nicht einordnen. Das ist `unbestimmt`, nicht `None` — sonst
    # sähe die Abdeckungs-Kennzahl aus wie ein Sensor-Ausfall.
    return _ZUSTAND_ZU_KANON.get(roh, UNBESTIMMT)


def betriebsmodus_klartext(zustand: Optional[str]) -> Optional[str]:
    """Roher HA-State → deutscher Klartext für die Zuordnungs-Fläche (F-53).

    Args:
        zustand: der State der zugeordneten Entität, z. B. ``"cool"``.

    Returns:
        Den Klartext aus {@link BETRIEBSMODUS_LABEL}, oder ``None``, wenn es
        keinen verwertbaren Zustand gibt (`unknown`, `unavailable`, leer).

    ⚑ **Warum der Klartext und nicht der Rohwert allein:** Die Fläche soll
    nicht nur zeigen, dass *etwas* ankommt, sondern ob eedc es **versteht**.
    Eine unbekannte Herstellerschreibweise erscheint hier als „Unbestimmt" —
    und genau die landet später in der Zeile „nicht aufgeteilt", statt einer
    Seite zugeschlagen zu werden. Wer nur ``cool`` läse, sähe den Unterschied
    zwischen „verstanden" und „durchgewinkt" nicht.

    ⚠ Bewusst **ohne** ``hvac_action``: die Fläche zeigt, was an *diesem* Feld
    zugeordnet ist. Die Verfeinerung durch den Ist-Betrieb passiert im
    Aggregator, nicht in der Anzeige.
    """
    kanon = normalisiere_betriebsmodus(zustand)
    if kanon is None:
        return None
    # ⚑ **Direkt indiziert, kein `.get(..., fallback)`.** Der erste Entwurf
    # hatte einen — und ein Sprengsatz darauf blieb STUMM: `normalisiere_…`
    # liefert ausschließlich Kanon-Werte, und die stehen vollzählig in
    # `BETRIEBSMODUS_LABEL`. Der Fallback war damit unerreichbarer Code, der
    # aussah wie eine Absicherung. Die echte Gefahr ist eine **siebte
    # Betriebsart ohne Label**, und die fängt kein Fallback, sondern der
    # Wächter `test_jeder_kanon_wert_hat_ein_label` — hier knallt sie dann
    # sichtbar statt still ein falsches Wort anzuzeigen.
    return BETRIEBSMODUS_LABEL[kanon]
