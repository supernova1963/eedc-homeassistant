"""
Daten-Checker — Ziel-Bauer (Etappe E2 des Vorhabens «Daten-Checker: ein Handgriff je Befund», Konzept §3.1 R2, §3.3).

Jedes Sprung-Ziel eines Befunds entsteht hier, nie als Literal in einem Erzeuger (Wächter W-2,
`tests/test_daten_checker_ziele.py`). **Jeder Bauer prüft `feld` gegen die Registry** und wirft `ValueError` bei
einem unbekannten Schlüssel — ein falscher Schlüssel stirbt im Test, nicht beim Anwender (Gegenprüfung N4).

Registry-Quellen (eine je Ziel-Art):

* Monats- und Datenquellen-Felder (`ziel_monat`, `ziel_datenquelle`): `core/feld_auswertungen.alle_registry_felder()`
  (aus `core/field_definitions/registry.py`), `core/field_definitions/karten.FELD_LABELS` (darin die Basis-Extras wie
  `pv_gesamt`) und die Spalten von `models/monatsdaten.Monatsdaten` (`batterie_ladung_kwh`, `batterie_entladung_kwh` …).
  Ein Innengeräte-Suffix (`betriebsmodus-3`) wird über `basis_feld_key` aufgelöst.
* Komponenten (`ziel_komponente`): Spalten von `models/investition.Investition` (`feld=`) **oder** Parameter des Typs
  aus `core/investition_parameter.py` (`parameter=`, `typ=` Pflicht). Getrennt, weil ein Erzeuger, der die Spalte
  `anschaffungskosten_alternativ` liest, nicht auf den Parameter `alternativ_kosten_euro` zeigen darf (E0 (5)).
* Anlage (`ziel_anlage`): Spalten von `models/anlage.Anlage`.
* Tarife (`ziel_tarif`): Spalten von `models/strompreis.Strompreis`.
* Solarprognose (`ziel_block("stammdaten", "solarprognose", feld=…)`): Spalten von `models/pvgis_prognose.PVGISPrognose`
  (`system_losses`).

`BLOCK_IDS` ist die Block-Tabelle wörtlich aus `frontend/src/config/einstellungenKatalog.tsx` (Kategorie → Block-Ids);
der Vitest `src/test/sprungziele-blockids.test.ts` liest diese Datei und vergleicht — eine Wahrheit.

**`link`** entsteht in `kategorien.link_aus_ziel` aus dem `Ziel` mit allen Parametern des Schemas (E4; das Übergangsfeld
`altlink` aus E2 ist mit E4 entfallen, seine Baseline `tests/daten_checker_altlink_baseline.txt` ist leer). Jede Zielseite liest
jeden Parameter, den ein Bauer hier für sie erzeugt (Wächter W-5, Export `tests/fixtures/sprungziele.json`).
"""

from functools import lru_cache
from typing import Optional

from .kategorien import Ziel

__all__ = [
    "BLOCK_IDS", "WIZARDS", "ziel_anlage", "ziel_block", "ziel_datenquelle", "ziel_komponente", "ziel_monat",
    "ziel_datenquelle_schluessel", "ziel_monat_label", "ziel_tarif", "ziel_werkbank",
]

#: Kategorie → Block-Ids, wörtlich aus `einstellungenKatalog.tsx` (`komponenten` ist datengetrieben, ohne Katalog-Block).
BLOCK_IDS: dict[str, tuple[str, ...]] = {
    "stammdaten": ("community", "anlage", "strompreise", "solarprognose"),
    "komponenten": (),
    "infothek": ("infothek", "berichte"),
    "daten": ("monatsdaten", "energieprofil", "datenchecker", "einrichtung"),
    "integration": ("mqtt-broker", "ha-verbindung", "ha-export", "ha-statistik-import", "import-buendel"),
    "datenquellen": ("datenquellen",),
    "system": ("demo-daten", "allgemein", "backup", "protokolle"),
}

# ─── Registries ───────────────────────────────────────────────────────────────────────────────────────────────
def _spalten(modell) -> frozenset[str]:
    return frozenset(c.name for c in modell.__table__.columns)


@lru_cache(maxsize=1)
def _monats_felder() -> frozenset[str]:
    from backend.core.feld_auswertungen import alle_registry_felder
    from backend.core.field_definitions.karten import FELD_LABELS
    from backend.models.monatsdaten import Monatsdaten
    return frozenset({f for _, f in alle_registry_felder()} | set(FELD_LABELS) | _spalten(Monatsdaten))


@lru_cache(maxsize=1)
def _parameter_je_typ() -> dict[str, frozenset[str]]:
    from backend.core import investition_parameter as ip
    return {
        "e-auto": frozenset(ip.PARAM_E_AUTO.values()), "waermepumpe": frozenset(ip.PARAM_WAERMEPUMPE.values()),
        "speicher": frozenset(ip.PARAM_SPEICHER.values()), "wallbox": frozenset(ip.PARAM_WALLBOX.values()),
        "wechselrichter": frozenset(ip.PARAM_WECHSELRICHTER.values()), "pv-module": frozenset(ip.PARAM_PV_MODULE.values()),
        "balkonkraftwerk": frozenset(ip.PARAM_BALKONKRAFTWERK.values()), "sonstiges": frozenset(ip.PARAM_SONSTIGES.values()),
    }


@lru_cache(maxsize=1)
def _modell_spalten() -> dict[str, frozenset[str]]:
    from backend.models.anlage import Anlage
    from backend.models.investition import Investition
    from backend.models.pvgis_prognose import PVGISPrognose
    from backend.models.strompreis import Strompreis
    return {"investition": _spalten(Investition), "anlage": _spalten(Anlage), "strompreis": _spalten(Strompreis),
            "solarprognose": _spalten(PVGISPrognose)}


def _pruefe(feld: Optional[str], erlaubt: frozenset[str], wo: str) -> None:
    if feld is not None and feld not in erlaubt:
        raise ValueError(f"Daten-Checker-Ziel: Feld {feld!r} steht in keiner Registry für {wo}")


def _monatsfeld(feld: Optional[str]) -> None:
    if feld is not None:
        from backend.core.field_definitions.keys import basis_feld_key
        _pruefe(basis_feld_key(feld), _monats_felder(), "Monats-/Datenquellen-Felder")


def _ohne_none(**params) -> dict:
    return {k: v for k, v in params.items() if v is not None}


# ─── Bauer ────────────────────────────────────────────────────────────────────────────────────────────────────
def ziel_monat(jahr: int, monat: int, geraet: Optional[int] = None, feld: Optional[str] = None) -> Ziel:
    """Monat erfassen oder bearbeiten (`?erfassen=JJJJ-MM`), optional Gerät und Feld."""
    _monatsfeld(feld)
    return Ziel("daten", "monatsdaten", _ohne_none(erfassen=f"{int(jahr)}-{int(monat):02d}", geraet=geraet, feld=feld),
                anker=feld)


def ziel_monat_label(label: str, geraet: Optional[int] = None, feld: Optional[str] = None) -> Ziel:
    """Wie `ziel_monat`, aus dem Anzeige-Label `"MM/YYYY"`; eine andere Form fällt auf den Monatsdaten-Block zurück
    (Laufzeit-Rohwert, H-E2-1: dieselbe Regel wie `kategorien.link_monat_erfassen`)."""
    teile = (label or "").split("/")
    if len(teile) == 2 and teile[0].isdigit() and teile[1].isdigit():
        return ziel_monat(int(teile[1]), int(teile[0]), geraet=geraet, feld=feld)
    _monatsfeld(feld)
    return Ziel("daten", "monatsdaten", _ohne_none(geraet=geraet, feld=feld), anker=feld)


def ziel_komponente(inv_id: Optional[int] = None, feld: Optional[str] = None, neu: Optional[str] = None, *,
                    typ: Optional[str] = None, parameter: Optional[str] = None, jahresbilanz: bool = False) -> Ziel:
    """Komponente bearbeiten (`bearbeiten=<id>`) und dort ein Feld: `feld=` Spalte der Investition, `parameter=`
    Parameter des Typs (`typ=` Pflicht); `neu=<typ>` legt an; `jahresbilanz=True` öffnet den Komponenten-Hub des Typs."""
    _pruefe(feld, _modell_spalten()["investition"], "Investitions-Spalten")
    if parameter is not None:
        if typ not in _parameter_je_typ():
            raise ValueError(f"Daten-Checker-Ziel: Parameter {parameter!r} braucht einen bekannten Typ, nicht {typ!r}")
        _pruefe(parameter, _parameter_je_typ()[typ], f"Parameter des Typs {typ}")
    if neu is not None and neu not in _parameter_je_typ():
        raise ValueError(f"Daten-Checker-Ziel: unbekannter Komponenten-Typ {neu!r}")
    if jahresbilanz:
        if typ not in _parameter_je_typ() or inv_id is None:
            raise ValueError("Daten-Checker-Ziel: Jahresbilanz braucht Typ und Gerät")
        return Ziel("komponenten-hub", typ, {"geraet": inv_id})
    if inv_id is None and (feld is not None or parameter is not None):
        raise ValueError("Daten-Checker-Ziel: ein Komponenten-Feld braucht das Gerät (`bearbeiten=`), sonst gibt es kein Formular")
    name = f"param_{parameter}" if parameter is not None else feld
    return Ziel("komponenten", None, _ohne_none(bearbeiten=inv_id, feld=parameter or feld, neu=neu), anker=name)


def ziel_datenquelle(feld: Optional[str] = None, geraet: Optional[int] = None) -> Ziel:
    """Datenquellen-Zuordnung, optional das Gerät aufgeklappt und das Feld markiert (gelesen seit E4)."""
    _monatsfeld(feld)
    return Ziel("datenquellen", None, _ohne_none(geraet=geraet, feld=feld), anker=feld)


def ziel_datenquelle_schluessel(schluessel: str) -> Ziel:
    """Wie `ziel_datenquelle`, aus einem gespeicherten Sensor-Schlüssel `inv:<id>:<feld>` bzw. `<präfix>:<feld>`
    (Laufzeit-Rohwert, H-E2-1). Ein Basis-Zähler heißt im Mapping `pv_gesamt`/`einspeisung`/`netzbezug`, auf der
    Datenquellen-Fläche `pv_gesamt_kwh` … (`datenquellen_mapping_sync.BASIS_ENERGY_FELD`, E4: der Anker der Fläche).
    Ein Feld, das die Registry nicht kennt (Alt-Name), fällt weg — der Befund bleibt."""
    from backend.services.datenquellen_mapping_sync import BASIS_ENERGY_FELD
    teile = (schluessel or "").split(":")
    geraet = int(teile[1]) if len(teile) == 3 and teile[0] == "inv" and teile[1].isdigit() else None
    feld = teile[-1] or None
    if geraet is None and feld is not None:
        feld = {basis: fid for fid, basis in BASIS_ENERGY_FELD.items()}.get(feld, feld)
    try:
        return ziel_datenquelle(feld=feld, geraet=geraet)
    except ValueError:
        return ziel_datenquelle(geraet=geraet)


def ziel_tarif(id: Optional[int] = None, feld: Optional[str] = None, neu_art: Optional[str] = None,
               ab: Optional[str] = None, *, neu: bool = False) -> Ziel:
    """Strompreise: Tarif `id` bearbeiten, oder neu anlegen (`neu=True`/`neu_art=<verwendung>`, optional `ab=<datum>`)."""
    _pruefe(feld, _modell_spalten()["strompreis"], "Tarif-Spalten")
    tarif = "neu" if (neu or neu_art is not None) else id
    return Ziel("stammdaten", "strompreise", _ohne_none(tarif=tarif, feld=feld, art=neu_art, ab=ab), anker=feld)


def ziel_anlage(feld: str) -> Ziel:
    """Anlage-Formular, Feld der Anlage."""
    _pruefe(feld, _modell_spalten()["anlage"], "Anlage-Spalten")
    return Ziel("stammdaten", "anlage", {"feld": feld}, anker=feld)


def ziel_werkbank(karte: str = "werkbank", plan: Optional[str] = None) -> Ziel:
    """Energieprofil-Pflege, zur Reparatur-Werkbank gesprungen (`karte=werkbank`); `plan=<id>` liest die Werkbank ab E3."""
    return Ziel("daten", "energieprofil", _ohne_none(karte=karte, plan=plan), anker=karte)


#: Assistenten, die ein Ziel öffnen darf (`wizard=`, E4): Schlüssel aus `frontend/src/v4/wizardHost.ts::WizardKey`, je
#: nur in ihrem Block (Import-Assistenten-Bündel, `einstellungenKatalog.tsx::ImportBuendelInhalt`).
WIZARDS = {"connector": ("integration", "import-buendel")}


def ziel_block(bereich: str, block: str, karte: Optional[str] = None, feld: Optional[str] = None,
               wizard: Optional[str] = None) -> Ziel:
    """Reines Block-Ziel (Protokolle, Integration, Solarprognose …); `feld=` nur an der Solarprognose, `wizard=` öffnet
    einen Assistenten des Blocks (`WIZARDS`)."""
    if block not in BLOCK_IDS.get(bereich, ()):
        raise ValueError(f"Daten-Checker-Ziel: Block {bereich}/{block} steht nicht im Einstellungs-Katalog")
    if wizard is not None and WIZARDS.get(wizard) != (bereich, block):
        raise ValueError(f"Daten-Checker-Ziel: Assistent {wizard!r} gehört nicht zu {bereich}/{block}")
    if feld is not None:
        if (bereich, block) != ("stammdaten", "solarprognose"):
            raise ValueError(f"Daten-Checker-Ziel: Block {bereich}/{block} kennt kein Feld")
        _pruefe(feld, _modell_spalten()["solarprognose"], "Solarprognose-Spalten")
    return Ziel(bereich, block, _ohne_none(karte=karte, feld=feld, wizard=wizard), anker=feld or karte or wizard)
