"""Wächter: die Snapshot-Zählerfelder sind aus der Feld-Registry ABGELEITET.

**Anlass N-259 (Melder rapahl, 16.08.2026).** `snapshot/keys.py` führte eine
**zweite, handgepflegte** Liste derselben Feldnamen, die `field_definitions.py`
ohnehin als Registry hält. Die beiden liefen auseinander, und es gab keine
Stelle, an der das auffallen konnte:

* Ein *Sonstiges*-**Verbraucher** heißt in der Registry ``verbrauch_sonstig_kwh``
  — die Zuordnungsfläche schreibt diesen Key ins ``sensor_mapping``,
  ``mqtt_topic_registry`` baut daraus das Topic. Die Snapshot-Liste kannte
  ``verbrauch_kwh``, einen Namen, den es für diesen Typ nicht gibt.
* Folge: eedc **publizierte ein Topic, das es selbst nicht wieder einlesen
  konnte** (``_mqtt_key_to_sensor_key`` filtert gegen dieselbe Liste), und
  ``_add("verbrauch_kwh")`` fand nie ein Mapping. Ein Heizstab mit eigenem
  Zähler existierte auf Stunden- und Tagesebene nicht.
* Der Monat kam an, weil ``get_sonstiges_verbrauch_kwh`` **beide** Namen liest —
  deshalb sah es nach „Tageswert fehlt" aus statt nach „Feld wird nirgends
  gefunden".
* Der Sonstiges-**Erzeuger** war nie betroffen (``erzeugung_kwh`` heißt in
  beiden Welten gleich). Genau diese Asymmetrie hat den Fehler versteckt.

Die Proben hier halten die beiden Welten zusammen. Wichtiger als die Gleichheit
ist ``test_jedes_energie_feld_ist_erfasst_oder_begruendet``: Es geht nicht darum,
dass die Liste stimmt, sondern dass **„bewusst nicht" von „vergessen"
unterscheidbar** ist — das fehlte, und deshalb konnte ein Feld durchrutschen.
"""

import pytest

from backend.core.field_definitions import (
    INVESTITION_FELDER,
    FELD_EINHEITEN,
    einheit_klasse,
    kumulative_zaehler_felder_je_typ,
    _SNAPSHOT_AUSNAHMEN,
    _SNAPSHOT_KOMPATIBILITAET,
    _SNAPSHOT_OHNE_KOMPONENTEN_BEITRAG,
)
from backend.services.snapshot.keys import (
    KUMULATIVE_ZAEHLER_FELDER,
    _mqtt_key_to_sensor_key,
    _categorize_counter,
)
from backend.services.snapshot.komponenten_beitraege import (
    investition_beitraege,
    investition_hourly_eintraege,
)


def _energie_felder_je_typ() -> dict[str, set[str]]:
    """{typ: alle kWh-Felder der Registry} — bei `sonstiges` über alle Kategorien."""
    out: dict[str, set[str]] = {}
    for typ, felder in INVESTITION_FELDER.items():
        listen = list(felder.values()) if isinstance(felder, dict) else [felder]
        namen = {
            f["feld"]
            for liste in listen
            for f in liste
            if einheit_klasse(FELD_EINHEITEN.get(f["feld"])) == "energie"
        }
        if namen:
            out[typ] = namen
    return out


class _Inv:
    def __init__(self, typ, parameter=None, inv_id=7):
        self.typ = typ
        self.parameter = parameter or {}
        self.id = inv_id
        self.parent_investition_id = None


# ── 1. Die Liste ist abgeleitet, nicht gepflegt ──────────────────────────────


def test_snapshot_liste_ist_die_ableitung():
    """Wer die Liste in `keys.py` wieder von Hand füllt, fällt hier auf."""
    assert KUMULATIVE_ZAEHLER_FELDER == kumulative_zaehler_felder_je_typ()


# ── 2. Der eigentliche Wächter: keine unbegründete Auslassung ────────────────


def test_jedes_energie_feld_ist_erfasst_oder_begruendet():
    """Jedes kWh-Feld der Registry ist entweder im Snapshot-Pfad **oder** trägt
    einen Ausnahme-Grund. Eine dritte Möglichkeit — stilles Fehlen — war der
    Zustand, in dem N-259 vierzehn Monate unentdeckt lag.
    """
    unbegruendet: list[str] = []
    for typ, felder in _energie_felder_je_typ().items():
        erfasst = set(KUMULATIVE_ZAEHLER_FELDER.get(typ, ()))
        for feld in sorted(felder):
            if feld in erfasst:
                continue
            if (typ, feld) in _SNAPSHOT_AUSNAHMEN:
                continue
            unbegruendet.append(f"{typ}/{feld}")
    assert not unbegruendet, (
        "kWh-Felder ohne Snapshot-Erfassung und ohne Begründung: "
        f"{unbegruendet}. Entweder in KUMULATIVE_ZAEHLER_FELDER aufnehmen "
        "(dann entsteht ein Stunden-/Tageswert) oder mit Grund in "
        "field_definitions._SNAPSHOT_AUSNAHMEN eintragen."
    )


def test_jede_ausnahme_zeigt_auf_ein_existierendes_feld():
    """Eine Ausnahme für ein Feld, das es nicht (mehr) gibt, ist tote Begründung
    — und sie täuscht Vollständigkeit vor, weil der Wächter oben sie akzeptiert.
    """
    registry = _energie_felder_je_typ()
    tot = [
        f"{typ}/{feld}"
        for (typ, feld) in _SNAPSHOT_AUSNAHMEN
        if feld not in registry.get(typ, set())
    ]
    assert not tot, f"Ausnahmen ohne Feld in der Registry: {tot}"


def test_jede_ausnahme_hat_einen_grund():
    leer = [k for k, v in _SNAPSHOT_AUSNAHMEN.items() if not (v or "").strip()]
    assert not leer, f"Ausnahmen ohne Begründung: {leer}"


def test_kompatibilitaets_namen_stehen_NICHT_in_der_registry():
    """Die Kompatibilitäts-Liste ist für Namen aus Altbeständen. Steht einer
    davon in der Registry, gehört er dorthin und nicht hierher — sonst wird eine
    echte Zuordnung als „Legacy" geführt.
    """
    registry = _energie_felder_je_typ()
    falsch = [
        f"{typ}/{feld}"
        for typ, felder in _SNAPSHOT_KOMPATIBILITAET.items()
        for feld in felder
        if feld in registry.get(typ, set())
    ]
    assert not falsch, f"Registry-Felder in der Kompatibilitäts-Liste: {falsch}"


# ── 2b. Deckung: jedes gesnapshottete Feld hat auch einen Konsumenten ───────


def test_jedes_zaehlerfeld_erzeugt_einen_beitrag_oder_ist_begruendet():
    """**Der Prüfer, der N-259 gefangen hätte.**

    Ein Feld in `KUMULATIVE_ZAEHLER_FELDER` wird als Zählerstand
    mitgeschnitten. Ob daraus auch ein Wert in `komponenten_kwh` entsteht,
    entscheidet ein **anderer** Ort: die `if typ ==`-Zweige in
    `investition_beitraege`. Zwischen beiden gab es keinen Abgleich — genau
    deshalb konnte `verbrauch_sonstig_kwh` in beiden fehlen, ohne dass es
    auffiel.

    ⚠ **Warum dieser Test und nicht die Registry-Deckung darüber:** Seit die
    Liste abgeleitet ist, kann „in der Registry, nicht in der Liste" gar nicht
    mehr entstehen — jener Prüfer vergleicht die Ableitung mit sich selbst und
    war bei der Sprengsatz-Probe **stumm**. Dieser hier misst zwei wirklich
    unabhängige Orte.
    """
    ohne: list[str] = []
    for typ, felder in KUMULATIVE_ZAEHLER_FELDER.items():
        # Parameter-Varianten, die eigene Zweige öffnen (getrennte WP-Messung,
        # Sonstiges-Kategorie) — ein Feld gilt als gedeckt, wenn EINE davon es
        # aufgreift.
        varianten = (
            [{"kategorie": "verbraucher"}, {"kategorie": "erzeuger"}] if typ == "sonstiges"
            else [{"getrennte_strommessung": True}, {}] if typ == "waermepumpe"
            else [{}]
        )
        for feld in felder:
            gedeckt = any(
                any(b.feld == feld for b in investition_beitraege(
                    _Inv(typ, p),
                    {"felder": {feld: {"strategie": "sensor", "sensor_id": "sensor.x"}}},
                ))
                for p in varianten
            )
            if gedeckt or (typ, feld) in _SNAPSHOT_OHNE_KOMPONENTEN_BEITRAG:
                continue
            ohne.append(f"{typ}/{feld}")
    assert not ohne, (
        "Zählerfelder ohne Konsumenten in investition_beitraege: "
        f"{ohne}. Entweder den Typ-Zweig dort ergänzen (dann entsteht ein "
        "Komponenten-/Tageswert) oder mit Grund in "
        "field_definitions._SNAPSHOT_OHNE_KOMPONENTEN_BEITRAG eintragen."
    )


def test_jede_beitrags_ausnahme_zeigt_auf_ein_gesnapshottetes_feld():
    tot = [
        f"{typ}/{feld}"
        for (typ, feld) in _SNAPSHOT_OHNE_KOMPONENTEN_BEITRAG
        if feld not in KUMULATIVE_ZAEHLER_FELDER.get(typ, ())
    ]
    assert not tot, f"Beitrags-Ausnahmen ohne Zählerfeld: {tot}"


# ── 3. Der Rundlauf: was wir publizieren, müssen wir lesen können ────────────


def test_publizierte_mqtt_topics_sind_wieder_einlesbar():
    """**Der Beweis gegen N-259 in seiner ursprünglichen Form.**

    `mqtt_topic_registry` baut die Energie-Topics aus `feld["feld"]` der
    Registry; `_mqtt_key_to_sensor_key` erkennt nur, was in
    KUMULATIVE_ZAEHLER_FELDER steht. Vor dem Fix verwarf eedc damit sein
    **eigenes** Topic `…/inv/<id>/verbrauch_sonstig_kwh`.
    """
    for typ, felder in KUMULATIVE_ZAEHLER_FELDER.items():
        for feld in felder:
            key = _mqtt_key_to_sensor_key(f"inv/12/{feld}")
            assert key == f"inv:12:{feld}", (
                f"{typ}/{feld}: publiziertes Energie-Topic wird beim Einlesen "
                f"verworfen (ergab {key!r})"
            )


def test_sonstiges_verbraucher_topic_wird_erkannt():
    """Rainers Fall, an genau dem Namen, den seine Box publiziert."""
    assert _mqtt_key_to_sensor_key("inv/12/verbrauch_sonstig_kwh") == (
        "inv:12:verbrauch_sonstig_kwh"
    )


# ── 4. Rainers Fall auf beiden Wegen: HA-Mapping und MQTT ───────────────────


def test_sonstiges_verbraucher_erzeugt_einen_komponenten_beitrag():
    """Heizstab mit zugeordnetem kWh-Zähler → Beitrag auf `sonstige_<id>`.

    Vor dem Fix war die Liste leer: `_add("verbrauch_kwh")` prüfte auf ein Feld,
    das die Zuordnungsfläche nie schreibt.
    """
    inv = _Inv("sonstiges", {"kategorie": "verbraucher"}, inv_id=12)
    mapping = {"felder": {
        "verbrauch_sonstig_kwh": {"strategie": "sensor", "sensor_id": "sensor.heizstab_kwh"},
    }}
    # Tagespfad: der Beitrag auf `komponenten_kwh` — hier entstand die Lücke.
    beitraege = investition_beitraege(inv, mapping)
    assert [b.feld for b in beitraege] == ["verbrauch_sonstig_kwh"]
    assert beitraege[0].target_key == "sonstige_12"
    assert beitraege[0].vorzeichen == 1
    # Stundenpfad: derselbe Feldname, richtig kategorisiert.
    stunden = investition_hourly_eintraege(inv, mapping)
    assert [(e.feld, e.kategorie) for e in stunden] == [
        ("verbrauch_sonstig_kwh", "verbrauch_sonstiges")
    ]


def test_sonstiges_verbraucher_ueber_mqtt_ohne_ha_mapping():
    """Standalone-/MQTT-Betrieb: Verfügbarkeit kommt aus den gesehenen Keys."""
    inv = _Inv("sonstiges", {"kategorie": "verbraucher"}, inv_id=12)
    gesehen = {"verbrauch_sonstig_kwh"}
    beitraege = investition_hourly_eintraege(
        inv, {}, ist_verfuegbar=lambda feld: feld in gesehen
    )
    assert [b.feld for b in beitraege] == ["verbrauch_sonstig_kwh"]


def test_legacy_name_zaehlt_nicht_zusaetzlich():
    """Trägt ein Altbestand BEIDE Namen, darf der Verbrauch nicht doppelt in die
    Stunde gehen — sie liegen in derselben Either-Or-Gruppe.
    """
    inv = _Inv("sonstiges", {"kategorie": "verbraucher"}, inv_id=12)
    mapping = {"felder": {
        "verbrauch_sonstig_kwh": {"strategie": "sensor", "sensor_id": "sensor.neu"},
        "verbrauch_kwh": {"strategie": "sensor", "sensor_id": "sensor.alt"},
    }}
    beitraege = investition_hourly_eintraege(inv, mapping)
    gruppen = {b.fallback_gruppe for b in beitraege}
    assert len(gruppen) == 1 and None not in gruppen, (
        "beide Namen müssen in EINER Either-Or-Gruppe liegen, sonst zählt der "
        f"Verbrauch doppelt: {[(b.feld, b.fallback_gruppe) for b in beitraege]}"
    )
    # Der kanonische Name steht vorn — er gewinnt, wenn beide ein Delta liefern.
    assert beitraege[0].feld == "verbrauch_sonstig_kwh"


# ── 5. Kategorisierung: der Wert landet auf der richtigen Seite ─────────────


@pytest.mark.parametrize("feld", ["verbrauch_sonstig_kwh", "verbrauch_kwh"])
def test_kategorie_verbraucher(feld):
    assert _categorize_counter(feld, "sonstiges", {"kategorie": "verbraucher"}) == (
        "verbrauch_sonstiges"
    )


@pytest.mark.parametrize("feld", ["erzeugung_kwh", "verbrauch_sonstig_kwh"])
def test_kategorie_erzeuger(feld):
    """Bei Kategorie *Erzeuger* zählt auch ein Verbrauchs-Feldname als Erzeugung
    — die Richtung kommt aus der gepflegten Kategorie, nicht aus dem Feldnamen
    (dieselbe Regel wie in `core/berechnungen/energie.py`).
    """
    assert _categorize_counter(feld, "sonstiges", {"kategorie": "erzeuger"}) == (
        "erzeugung_sonstiges"
    )


def test_sonstiges_erzeuger_war_nie_betroffen():
    """Gegenprobe zur Fehlersuche: Der Erzeuger funktionierte vorher schon."""
    inv = _Inv("sonstiges", {"kategorie": "erzeuger"}, inv_id=10)
    mapping = {"felder": {
        "erzeugung_kwh": {"strategie": "sensor", "sensor_id": "sensor.bhkw"},
    }}
    beitraege = investition_beitraege(inv, mapping)
    assert [b.feld for b in beitraege] == ["erzeugung_kwh"]
    assert beitraege[0].target_key == "sonstige_10"
