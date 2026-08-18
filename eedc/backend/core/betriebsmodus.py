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

# Die beiden Klassen, für die es später eine eigene Teilmenge gibt.
AUFGETEILTE_MODI: Final[frozenset[str]] = frozenset({HEIZEN, KUEHLEN})


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
