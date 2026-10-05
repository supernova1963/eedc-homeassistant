"""Kanal-Katalog — die EINE Zuweisung Feld → Kanal-Art und Familie (HA-Bauform E1, Bauplan §3 und §3a).

**Abgeleitet, nicht gepflegt.** Jede Zuweisung entsteht aus einer Regel über die Eigenschaften
des Registry-Eintrags (Einheit, ``stand``, ``zustand``, ``nur_manuell``, ``gruppe``,
``bedingung_basis``) bzw. aus der Snapshot-Liste, in der ein Feld steht — nie aus einer zweiten
Aufzählung von Feldnamen. Dieselbe Bauform wie ``kumulative_zaehler_felder_je_typ`` (N-259): eine
handgepflegte zweite Liste ist die Wette darauf, dass jemand sie beim nächsten Feld mitzieht.

Ein Feld, auf das keine Regel passt, bekommt **keine** Zuweisung — der Wächter
``tests/test_kanal_feld_deckung.py`` meldet es dann beim Namen. „Bewusst kein Kanal" ist damit
von „vergessen" unterscheidbar: es steht als Ausnahme mit Grund im Katalog.

Regeln (Bauplan §3, §3a; Reihenfolge = Vorrang):

======  ==========================================================  ==============================
Klasse  Regel                                                       Ergebnis
======  ==========================================================  ==============================
A-S     ``(typ, feld)`` in ``_SNAPSHOT_AUSNAHMEN``                   kein Kanal (Grund von dort)
O1      Basis-Feld ``gruppe == "wetter"``                           kein Kanal
O2      bedingtes Basis-Feld, Bedingung Tarif-Pflege                kein Kanal
O3      bedingtes Basis-Feld, Bedingung Fremdpreis (E-Auto, WP)     kein Kanal
O4      ``OPTIONALE_FELDER``                                        kein Kanal
O6      Investitionsfeld mit Einheit ``€``                          kein Kanal
O5      Investitionsfeld ``nur_manuell``                            kein Kanal
—       Stand-Feld (``stand: True``)                                ``stand`` · Spiegel/Mitschrift
O7      Feld in ``MQTT_STAND_ZAEHLER_FELDER``                       ``stand`` · Mitschrift
O9      Feld in ``KUMULATIVE_COUNTER_FELDER``                       ``stand`` · Spiegel/Mitschrift
—       Energie-Einheit (kWh, Wh, MWh)                              ``sum`` · Spiegel/Mitschrift
—       Live-Feld ``zustand`` (Betriebsart)                         ``mean`` „Anteil der Stunde je
                                                                    Betriebsart" · Mitschrift
—       Live-/Preis-Feld mit Einheit W · kW · % · °C · ct/kWh       ``mean`` · Spiegel/Mitschrift
======  ==========================================================  ==============================

**Stand E1 — was geschrieben wird** (``e1_schreiber``): ``sum`` und ``stand`` als Spiegel (HA) und
als eigene Summe aus MQTT-Rohständen; ``mean`` als Spiegel, wo der Sensor eine HA-Langzeitstatistik hat
(``mean/min/max`` wörtlich, Kanal-Einheit = HAs Einheit beim Anlegen); die Betriebsart-Mitschrift.
**Nicht** geschrieben: die Mittelwert-**Mitschrift** (``mitschrift_offen``: Sensoren ohne
Langzeitstatistik — die Quelle je Feld ist offen, eigener Punkt vor E3; Entscheid Master 05.10.) und die
abgeleiteten Kanäle (``ABGELEITETE_KANAELE``, im Auftrag E1 ausgeschlossen).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Sequence

from backend.core.field_definitions import (
    BASIS_FELDER,
    BASIS_LIVE_FELDER,
    BASIS_PREIS_FELDER,
    BEDINGTE_BASIS_FELDER,
    INVESTITION_FELDER,
    LIVE_FELDER_INV,
    OPTIONALE_FELDER,
    STAND_FELDER,
    _SNAPSHOT_AUSNAHMEN,
    _SNAPSHOT_KOMPATIBILITAET,
    basis_feld_key,
    einheit_klasse,
)
from backend.models.kanal import (
    ART_MEAN,
    ART_STAND,
    ART_SUM,
    FAMILIE_ABGELEITET,
    FAMILIE_MITSCHRIFT,
    FAMILIE_SPIEGEL,
)
from backend.services.snapshot.keys import (
    BASIS_ZAEHLER_FELDER,
    KUMULATIVE_COUNTER_FELDER,
    KUMULATIVE_ZAEHLER_FELDER,
    MQTT_STAND_ZAEHLER_FELDER,
)

# ── Ausnahme-Klassen ────────────────────────────────────────────────────────

#: Die zehn Felder aus ``field_definitions._SNAPSHOT_AUSNAHMEN`` — Abschluss-Felder, Grund dort.
AUSNAHME_SNAPSHOT = "snapshot_ausnahme"
#: Bauplan §3a O1–O6 — „Abschluss-Feld ohne Sensor".
AUSNAHME_ABSCHLUSS = "abschluss_ohne_sensor"
AUSNAHME_KLASSEN: frozenset[str] = frozenset({AUSNAHME_SNAPSHOT, AUSNAHME_ABSCHLUSS})

#: Gründe der Klasse „Abschluss-Feld ohne Sensor" — wörtlich nach Bauplan §3a.
_GRUND_O: dict[str, str] = {
    "O1": "O1: Fremdquelle (Open-Meteo), kein Sensor, kein Stundenwert; die Stunden-Wetterwerte "
          "sind eigene mean-Kanäle",
    "O2": "O2: Stufe „gepflegt“ der Preis-Kaskade — eine Korrekturschicht je Monat (P8), kein Messwert",
    "O3": "O3: Monatspreis aus Fremdquelle/Pflege; der Tageswert bleibt in der Tageszeile (Konzept §4.5)",
    "O4": "O4: Geld und Freitext der Abschluss-Schicht",
    "O5": "O5: nur_manuell, nicht zuordenbar",
    "O6": "O6: Geldbetrag je Monat, gepflegt",
}

#: Bedingungen der bedingten Basis-Felder → O-Klasse. Eine Bedingung ist eine Eigenschaft des
#: Registry-Eintrags, kein Feldname; ein neues bedingtes Feld mit einer neuen Bedingung bleibt
#: ohne Zuweisung, bis jemand seine Klasse entscheidet (der Wächter meldet es).
_BEDINGUNG_ZU_O: dict[str, str] = {
    "dynamischer_tarif": "O2",
    "variable_einspeisung": "O2",
    "hat_eauto": "O3",
    "hat_waermepumpe": "O3",
}

#: Einheiten, die Bauplan §3 auf ``mean`` legt: Leistung, Ladestand, Temperatur, Preis.
_MEAN_EINHEITEN: frozenset[str] = frozenset({"W", "kW", "%", "°C", "ct/kWh"})

#: Geplante abgeleitete Kanäle (Bauplan §2, §3a O8) — im Katalog benannt, in E1 nicht geschrieben.
ABGELEITETE_KANAELE: dict[str, str] = {
    "kosten:*": "Kosten je Stunde bei Stundenpreis (stundengepaartes Produkt, G1)",
    "kwh_betriebsart:inv:{id}:{betriebsart}": "kWh je Betriebsart aus Anteil × Strom der Stunde",
    "leistung_summe:inv:{id}": "O8: Summenkanal aus Leistung (Stundenmittel × 1 h) für Geräte ohne kWh-Zähler",
    "ueberschuss": "Überschuss je Stunde",
    "defizit": "Defizit je Stunde",
}

# Listen-Namen (Herkunft einer Zuweisung)
L_BASIS = "BASIS_FELDER"
L_BEDINGT = "BEDINGTE_BASIS_FELDER"
L_OPTIONAL = "OPTIONALE_FELDER"
L_INV = "INVESTITION_FELDER"
L_LIVE_INV = "LIVE_FELDER_INV"
L_LIVE_BASIS = "BASIS_LIVE_FELDER"
L_PREIS = "BASIS_PREIS_FELDER"
L_ZAEHLER = "KUMULATIVE_ZAEHLER_FELDER"
L_COUNTER = "KUMULATIVE_COUNTER_FELDER"
L_BASIS_ZAEHLER = "BASIS_ZAEHLER_FELDER"
L_MQTT_STAND = "MQTT_STAND_ZAEHLER_FELDER"


@dataclass(frozen=True)
class KanalZuweisung:
    """Ein Feld einer Liste und was der Katalog daraus macht.

    Genau eines von ``art`` und ``ausnahme`` ist gesetzt. ``familien`` nennt die Roh-Familien, aus
    denen der Kanal geschrieben werden darf (Spiegel = HA wörtlich, Mitschrift = eedc schreibt
    selbst mit); ``bestand`` ist hier nicht aufgeführt — die Familie bleibt unbelegt (Bauplan §3b, 06.10.).
    """

    liste: str
    typ: Optional[str]        # Investitionstyp; ``None`` = Anlagen-Ebene
    feld: str
    art: Optional[str]
    familien: tuple[str, ...]
    ausnahme: Optional[str]
    grund: str
    #: Kanal-Schlüssel-Muster (``basis:einspeisung``, ``inv:{id}:ladung_kwh``,
    #: ``modus:inv:{id}:{betriebsart}``).
    schluessel: str
    #: Schreibt E1 diesen Kanal?
    e1_schreiber: bool
    #: ``mean`` ohne Langzeitstatistik: Mitschrift vorgesehen, Quelle noch nicht festgelegt (vor E3).
    mitschrift_offen: bool = False


def _zuweisung(
    liste: str, typ: Optional[str], feld: str, *, art: Optional[str] = None,
    familien: tuple[str, ...] = (), ausnahme: Optional[str] = None, grund: str,
    schluessel: str, e1: bool = False, mitschrift_offen: bool = False,
) -> KanalZuweisung:
    return KanalZuweisung(liste, typ, feld, art, familien, ausnahme, grund, schluessel, e1, mitschrift_offen)


_SPIEGEL_ODER_MITSCHRIFT = (FAMILIE_SPIEGEL, FAMILIE_MITSCHRIFT)


def _inv_schluessel(feld: str) -> str:
    return f"inv:{{id}}:{feld}"


# ── Regeln je Liste ─────────────────────────────────────────────────────────


def _regel_investition(
    liste: str, typ: str, eintrag: Mapping, *, stand_mqtt: frozenset[str],
    counter: Mapping[str, Sequence[str]],
) -> Optional[KanalZuweisung]:
    feld = eintrag["feld"]
    einheit = eintrag.get("einheit", "")
    sk = _inv_schluessel(feld)
    if (typ, feld) in _SNAPSHOT_AUSNAHMEN:
        return _zuweisung(liste, typ, feld, ausnahme=AUSNAHME_SNAPSHOT,
                          grund=_SNAPSHOT_AUSNAHMEN[(typ, feld)], schluessel=sk)
    if einheit == "€":
        return _zuweisung(liste, typ, feld, ausnahme=AUSNAHME_ABSCHLUSS, grund=_GRUND_O["O6"], schluessel=sk)
    if eintrag.get("nur_manuell"):
        return _zuweisung(liste, typ, feld, ausnahme=AUSNAHME_ABSCHLUSS, grund=_GRUND_O["O5"], schluessel=sk)
    if eintrag.get("stand"):
        return _zuweisung(liste, typ, feld, art=ART_STAND, familien=_SPIEGEL_ODER_MITSCHRIFT,
                          grund="Stand-Feld (F-58) ⇒ stand: Δ des Standes, ohne Reset-Regel",
                          schluessel=sk, e1=True)
    if feld in stand_mqtt:
        return _zuweisung(liste, typ, feld, art=ART_STAND, familien=(FAMILIE_MITSCHRIFT,),
                          grund="O7: kommt heute nur über MQTT; ein späterer HA-Sensor ist ein "
                                "Spiegel desselben Kanals", schluessel=sk, e1=True)
    if feld in counter.get(typ, ()):
        return _regel_counter(liste, typ, feld)
    if einheit_klasse(einheit) == "energie":
        return _zuweisung(liste, typ, feld, art=ART_SUM, familien=_SPIEGEL_ODER_MITSCHRIFT,
                          grund="kWh-Zähler ⇒ sum (§3): Spiegel HA, ohne HA eigene Summe mit HAs Reset-Regel",
                          schluessel=sk, e1=True)
    return None


def _regel_counter(liste: str, typ: Optional[str], feld: str) -> KanalZuweisung:
    if feld in STAND_FELDER:
        return _zuweisung(liste, typ, feld, art=ART_STAND, familien=_SPIEGEL_ODER_MITSCHRIFT,
                          grund="Stand-Feld (F-58) ⇒ stand: Δ des Standes, ohne Reset-Regel",
                          schluessel=_inv_schluessel(feld), e1=True)
    return _zuweisung(liste, typ, feld, art=ART_STAND, familien=_SPIEGEL_ODER_MITSCHRIFT,
                      grund="O9: Zählwerk (Starts, Betriebsstunden) ist eine Bestandsgröße ⇒ stand; "
                            "ein Rücksprung ist kein Reset mit Gutschrift, sondern verworfen",
                      schluessel=_inv_schluessel(feld), e1=True)


def _regel_mean(liste: str, typ: Optional[str], feld: str, einheit: str, schluessel: str) -> Optional[KanalZuweisung]:
    if einheit in _MEAN_EINHEITEN:
        return _zuweisung(liste, typ, feld, art=ART_MEAN, familien=_SPIEGEL_ODER_MITSCHRIFT,
                          grund="Leistung/Ladestand/Temperatur/Preis ⇒ mean (§3): Spiegel bei "
                                "Langzeitstatistik (E1: mean/min/max wörtlich, Einheit = HA); ohne "
                                "Langzeitstatistik Mitschrift — Quelle offen (vor E3)",
                          schluessel=schluessel, e1=True, mitschrift_offen=True)
    return None


def kanal_katalog(
    *,
    basis_felder: Sequence[Mapping] = BASIS_FELDER,
    bedingte_basis_felder: Sequence[Mapping] = BEDINGTE_BASIS_FELDER,
    optionale_felder: Sequence[Mapping] = OPTIONALE_FELDER,
    investition_felder: Mapping = INVESTITION_FELDER,
    live_felder_inv: Mapping = LIVE_FELDER_INV,
    basis_live_felder: Sequence[Mapping] = BASIS_LIVE_FELDER,
    basis_preis_felder: Sequence[Mapping] = BASIS_PREIS_FELDER,
    kumulative_zaehler_felder: Mapping[str, Sequence[str]] = KUMULATIVE_ZAEHLER_FELDER,
    kumulative_counter_felder: Mapping[str, Sequence[str]] = KUMULATIVE_COUNTER_FELDER,
    basis_zaehler_felder: Sequence[str] = BASIS_ZAEHLER_FELDER,
    mqtt_stand_zaehler_felder: Iterable[str] = MQTT_STAND_ZAEHLER_FELDER,
) -> tuple[list[KanalZuweisung], list[tuple[str, Optional[str], str]]]:
    """Den Katalog aus den Listen ableiten.

    Die Listen sind Parameter mit den Produktiv-Listen als Vorgabe — damit die Gegenprobe des
    Wächters ein künstliches Feld hineinreichen kann, ohne Modulzustand umzubiegen.

    Returns:
        ``(zuweisungen, ohne_regel)`` — ``ohne_regel`` sind ``(liste, typ, feld)``, auf die keine
        Regel passt. Produktiv muss die Liste leer sein (Wächter, Baseline 0).
    """
    stand_mqtt = frozenset(mqtt_stand_zaehler_felder)
    out: list[KanalZuweisung] = []
    ohne: list[tuple[str, Optional[str], str]] = []
    gesehen: set[tuple[str, Optional[str], str]] = set()

    def _nimm(z: Optional[KanalZuweisung], liste: str, typ: Optional[str], feld: str) -> None:
        schl = (liste, typ, feld)
        if schl in gesehen:
            return
        gesehen.add(schl)
        if z is None:
            ohne.append(schl)
        else:
            out.append(z)

    # Basis-Felder (Monatszeile)
    for f in basis_felder:
        feld = f["feld"]
        if f.get("gruppe") == "wetter":
            z = _zuweisung(L_BASIS, None, feld, ausnahme=AUSNAHME_ABSCHLUSS, grund=_GRUND_O["O1"],
                           schluessel=f"basis:{f.get('mapping_key', feld)}")
        elif einheit_klasse(f.get("einheit")) == "energie" and f.get("mapping_key"):
            z = _zuweisung(L_BASIS, None, feld, art=ART_SUM, familien=_SPIEGEL_ODER_MITSCHRIFT,
                           grund="kWh-Zähler ⇒ sum (§3)", schluessel=f"basis:{f['mapping_key']}", e1=True)
        else:
            z = None
        _nimm(z, L_BASIS, None, feld)

    for f in bedingte_basis_felder:
        feld = f["feld"]
        o = _BEDINGUNG_ZU_O.get(f.get("bedingung_basis"))
        z = (_zuweisung(L_BEDINGT, None, feld, ausnahme=AUSNAHME_ABSCHLUSS, grund=_GRUND_O[o],
                        schluessel=f"basis:{feld}") if o else None)
        _nimm(z, L_BEDINGT, None, feld)

    for f in optionale_felder:
        feld = f["feld"]
        _nimm(_zuweisung(L_OPTIONAL, None, feld, ausnahme=AUSNAHME_ABSCHLUSS, grund=_GRUND_O["O4"],
                         schluessel=f"basis:{feld}"), L_OPTIONAL, None, feld)

    # Investitionsfelder (bei `sonstiges` je Kategorie, vereinigt)
    for typ, felder in investition_felder.items():
        listen = list(felder.values()) if isinstance(felder, dict) else [felder]
        for liste in listen:
            for f in liste:
                _nimm(_regel_investition(L_INV, typ, f, stand_mqtt=stand_mqtt,
                                         counter=kumulative_counter_felder), L_INV, typ, f["feld"])

    # Live-Felder je Gerät
    for typ, felder in live_felder_inv.items():
        for f in felder:
            key = f["key"]
            if f.get("zustand"):
                z = _zuweisung(L_LIVE_INV, typ, key, art=ART_MEAN, familien=(FAMILIE_MITSCHRIFT,),
                               grund="Betriebsart ⇒ Mitschrift „Anteil der Stunde je Betriebsart“ "
                                     "(climate hat keine Langzeitstatistik, W2)",
                               schluessel="modus:inv:{id}:{betriebsart}", e1=True)
            else:
                z = _regel_mean(L_LIVE_INV, typ, key, f.get("einheit", ""), f"inv:{{id}}:{key}")
            _nimm(z, L_LIVE_INV, typ, key)

    for f in basis_live_felder:
        key = f["key"]
        _nimm(_regel_mean(L_LIVE_BASIS, None, key, f.get("einheit", ""), f"basis:{key}"), L_LIVE_BASIS, None, key)

    for f in basis_preis_felder:
        key = f["key"]
        _nimm(_regel_mean(L_PREIS, None, key, f.get("einheit", ""), f"basis:{key}"), L_PREIS, None, key)

    # Snapshot-Listen aus `services/snapshot/keys.py`
    kompat = {(t, f) for t, fs in _SNAPSHOT_KOMPATIBILITAET.items() for f in fs}
    for typ, felder in kumulative_zaehler_felder.items():
        for feld in felder:
            if (typ, feld) in kompat:
                z = _zuweisung(L_ZAEHLER, typ, feld, art=ART_SUM, familien=_SPIEGEL_ODER_MITSCHRIFT,
                               grund="Kompatibilitäts-Name aus Altbeständen (_SNAPSHOT_KOMPATIBILITAET) — "
                                     "kWh-Zähler ⇒ sum, Schlüssel wie gemappt",
                               schluessel=_inv_schluessel(feld), e1=True)
            elif einheit_klasse(_einheit_im_register(investition_felder, typ, feld)) == "energie":
                z = _zuweisung(L_ZAEHLER, typ, feld, art=ART_SUM, familien=_SPIEGEL_ODER_MITSCHRIFT,
                               grund="kWh-Zähler ⇒ sum (§3)", schluessel=_inv_schluessel(feld), e1=True)
            else:
                z = None
            _nimm(z, L_ZAEHLER, typ, feld)
    for typ, felder in kumulative_counter_felder.items():
        for feld in felder:
            _nimm(_regel_counter(L_COUNTER, typ, feld), L_COUNTER, typ, feld)
    for feld in basis_zaehler_felder:
        _nimm(_zuweisung(L_BASIS_ZAEHLER, None, feld, art=ART_SUM, familien=_SPIEGEL_ODER_MITSCHRIFT,
                         grund="Anlagen-Zähler ⇒ sum (§3)", schluessel=f"basis:{feld}", e1=True),
              L_BASIS_ZAEHLER, None, feld)
    for feld in sorted(stand_mqtt):
        _nimm(_zuweisung(L_MQTT_STAND, None, feld, art=ART_STAND, familien=(FAMILIE_MITSCHRIFT,),
                         grund="O7: Stand ohne kWh-Semantik, heute nur MQTT", schluessel=_inv_schluessel(feld),
                         e1=True), L_MQTT_STAND, None, feld)
    return out, ohne


def _einheit_im_register(investition_felder: Mapping, typ: str, feld: str) -> Optional[str]:
    felder = investition_felder.get(typ)
    if felder is None:
        return None
    listen = list(felder.values()) if isinstance(felder, dict) else [felder]
    for liste in listen:
        for f in liste:
            if f["feld"] == feld:
                return f.get("einheit")
    return None


# ── Nachschlagen für den Schreiber ──────────────────────────────────────────

_ZUWEISUNGEN, _OHNE_REGEL = kanal_katalog()

#: (typ, feld) → Art für die gesnapshotteten Zähler (sum/stand). Anlagen-Ebene: typ ``None``.
_ART_JE_ZAEHLER: dict[tuple[Optional[str], str], str] = {}
for _z in _ZUWEISUNGEN:
    if _z.art in (ART_SUM, ART_STAND) and _z.liste in (L_INV, L_ZAEHLER, L_COUNTER, L_BASIS_ZAEHLER, L_BASIS):
        _feld = _z.feld if _z.liste != L_BASIS else _z.schluessel.split(":", 1)[1]
        _ART_JE_ZAEHLER.setdefault((_z.typ, _feld), _z.art)
for _z in _ZUWEISUNGEN:
    # O7: km_gefahren/ladevorgaenge stehen typlos in der MQTT-Liste; am Gerät gilt dieselbe Art.
    if _z.liste == L_MQTT_STAND:
        _ART_JE_ZAEHLER.setdefault((None, _z.feld), _z.art)


#: (typ, feld) der Mittelwert-Kanäle mit Spiegel. Anlagen-Ebene (Live-Basis, Preis): typ ``None``.
_MEAN_SPIEGEL: frozenset[tuple[Optional[str], str]] = frozenset(
    (_z.typ, _z.feld) for _z in _ZUWEISUNGEN
    if _z.art == ART_MEAN and _z.liste in (L_LIVE_INV, L_LIVE_BASIS, L_PREIS) and _z.mitschrift_offen
)


def ist_mean_spiegel(sensor_key: str, inv_typ: Optional[str]) -> bool:
    """Ist dieser Schlüssel (``basis:<key>`` / ``inv:<id>:<key>``) ein Mittelwert-Kanal mit Spiegel?
    Innengerät-Suffixe (``leistung_w-3``) tragen die Art ihres Basis-Felds."""
    if sensor_key.startswith("basis:"):
        return (None, sensor_key.split(":", 1)[1]) in _MEAN_SPIEGEL
    if sensor_key.startswith("inv:"):
        return (inv_typ, basis_feld_key(sensor_key.split(":", 2)[2])) in _MEAN_SPIEGEL
    return False


def zuweisungen() -> list[KanalZuweisung]:
    """Der Produktiv-Katalog (einmal abgeleitet)."""
    return list(_ZUWEISUNGEN)


def ohne_regel() -> list[tuple[str, Optional[str], str]]:
    """Felder ohne Zuweisung — produktiv leer (Wächter)."""
    return list(_OHNE_REGEL)


def zaehler_art(sensor_key: str, inv_typ: Optional[str]) -> Optional[str]:
    """Kanal-Art eines Snapshot-Schlüssels (``basis:<feld>`` / ``inv:<id>:<feld>``): ``sum``,
    ``stand`` oder ``None`` (kein Zähler-Kanal — der Schreiber lässt ihn aus und meldet es).

    Innengerät-Suffixe (``…_kwh-3``) tragen die Art ihres Basis-Felds.
    """
    if sensor_key.startswith("basis:"):
        return _ART_JE_ZAEHLER.get((None, sensor_key.split(":", 1)[1]))
    if sensor_key.startswith("inv:"):
        feld = basis_feld_key(sensor_key.split(":", 2)[2])
        return _ART_JE_ZAEHLER.get((inv_typ, feld)) or (
            _ART_JE_ZAEHLER.get((None, feld)) if feld in MQTT_STAND_ZAEHLER_FELDER else None
        )
    return None


def modus_kanal_key(inv_id: int | str, betriebsart: str) -> str:
    """Schlüssel eines Betriebsart-Mitschrift-Kanals (Bauplan §2): ``modus:inv:<id>:<betriebsart>``."""
    return f"modus:inv:{inv_id}:{betriebsart}"
