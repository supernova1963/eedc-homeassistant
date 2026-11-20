"""Korrektur eines Sensorwechsels als **ein** Lauf (Sensorwechsel mit Grund, Bauplan B-6, Konzept S-4/S-9; Sitzung 3).

Der Anwender sagt: «bisher war der falsche Sensor zugeordnet, seit ``falsch_seit``». Für das Intervall ``[falsch_seit, ab)``
gilt danach die richtige (heutige) Quelle; was die falsche dort hinterlassen hat, wird verworfen und — soweit Home Assistant
die Geschichte des richtigen Sensors führt — aus ihr neu gefüllt. Fünf Schritte:

1. **Wechsel-Zeile** (``zuordnung_wechsel``: ``grund = korrektur``, ``falsch_seit_ts``, ``ab_ts``) — mit ihr liefert
   ``zeitpunkt.quelle_am`` im Intervall ``nachher`` (B-0). Eine frühere Zeile ohne Grund, die denselben Wechsel beschreibt
   (gleiche neue Quelle, ``ab_ts`` im Intervall oder höchstens eine Stunde danach), wird aufgehoben (``aufgehoben_durch``),
   ebenso jede Zeile ohne Grund oder mit «Fortsetzung», deren ``ab_ts`` im Intervall liegt, und die Zeile am Rand
   «falsch seit», deren ``vorher`` die richtige Quelle ist (Bauplan §13 Nr. 67; ``_im_intervall``). Korrektur-Zeilen bleiben.
2. **Im Intervall verwerfen:** Kanalzeilen nur in Abschnitten, deren Quelle nicht die richtige ist (``kanal/korrektur.py``) ·
   Zählerstände (``sensor_snapshots`` des Schlüssels) · MQTT-Rohstände des Schlüssels · Feldschlüssel der Tageszeilen nach den
   Regeln der Werkbank (``verwerfen_vor_quellbeginn.leere_bestand``; Tage, deren Fenster ganz im Intervall liegt; Monate mit
   Abschluss bleiben). Für die Reihe heißt Korrektur «verwerfen, dann füllt B-0 aus der richtigen Quelle» (§8 Nr. 16).
3. **Kanal:** die richtige Quelle beginnt mit ihrer ersten Zeile im Intervall, ein Versatz nach R2, gefüllt mit dem
   Blockleser von ``neu_spiegeln``.
4. **Tageszeilen** der Tage, deren Fenster das Intervall schneidet und deren Tageszeile einen Schlüssel des Felds trägt
   (§7 Nr. 10, ohne Blick auf seine Herkunft: §10 Nr. 35), im Hintergrund neu bilden — mit Fortschritt, fortsetzbar nach einem Neustart
   (``korrektur_lauf.py``); Wetter und Börsenpreis bleiben, wie sie gespeichert sind (kein Abruf, §10 Nr. 32).
5. **Merker** verwerfen (gemerkte Kanal-Tage, Wechsel-Merkliste der Sitzung).

**Stände speichern** (Sitzung 4b-1-K2, Bauplan «Zu §14» Nr. 111): füllt die Korrektur aus Home Assistant, liest der Nachlauf die
Zählerstände der Zeit neu und speichert sie (``fuelle_staende``) — sonst stünde die Reihe leer und bildete jeder Leser ohne
lesbare HA-Statistik die Differenz über das ganze Intervall. Bis dahin gilt das Intervall als gesperrt (Nr. 106); ist Home
Assistant erreichbar und führt dort nichts, endet das (U1 Punkt 2, ``_luecke_nach_dem_lesen``).
**Leere Zeit wie Zählerlücke** (Nr. 119, Nr. 127 Option A, Zielbild Nr. 133 (4); U1): was nichts füllt, bekommt in jeder Lage
eine Lücken-Zeile (nicht heilen, nicht füllen); ihre Ränder sind Nähte nur bei einem Höhenwechsel
(``zeitpunkt.ohne_hoehenwechsel``) — sonst rechnen die Leser über sie wie über jede Zählerlücke (``_wie_zaehlerluecke``: die
Vorschau fragt dieselbe Regel). Leer bleibt nur die Zeit, für die Home Assistant nichts führt (``_luecke``).

**Home Assistant:** eingerichtet, aber nicht erreichbar ⇒ der Lauf startet nicht (``KorrekturNichtStartbar``). Ohne Home
Assistant (Standalone) laufen die Schritte 1, 2 und 5 — nichts wird gefüllt, kein Tag neu gebildet.
**Endgültig** (Bauplan G-2): der Rückweg ist eine Sicherung von Home Assistant bzw. ohne Home Assistant der
eedc-Datenbank; die Vorschau sagt es.

Aufrufer: die Werkbank-Operation «Werte vor dem Sensorbeginn verwerfen» (``services/verwerfen_vor_quellbeginn.fuehre_aus``,
S-9: ``falsch_seit`` offen = von Beginn an, ``ab`` = Beginn des jüngsten Sensors) und seit Sitzung 3b der Dialog beim
Sensorwechsel (``abfrage.vollziehe``: Feld-Route, Preset; ``ab`` = nächste volle Stunde, richtig ist die neue Quelle).

**Robust (Sitzung 3b, Bauplan §10 Nr. 40):** eine wiederholte gleiche Korrektur (gleicher Schlüssel, gleiche richtige Quelle,
Intervall schon von einer Korrektur-Zeile gedeckt) legt keine zweite Zeile an. Der Nachlauf nach dem Commit (Füllen, abhängige
abgeleitete Kanäle) steht als Auftrag im Zustand des Laufs (``nachlauf_auftrag``); scheitert er, holt ihn der Lauf nach.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, Optional

from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.zuordnung_wechsel import (
    ANSATZ_HOEHE_UNGEPRUEFT,
    GRUND_KORREKTUR,
    HERKUNFT_NACHTRAG,
    ZuordnungWechsel,
)

logger = logging.getLogger(__name__)

_STUNDE = 3600


class KorrekturNichtStartbar(ValueError):
    """Home Assistant ist eingerichtet, aber nicht erreichbar — der Lauf startet nicht."""


SATZ_NICHT_ERREICHBAR = ("Home Assistant ist nicht erreichbar — die Korrektur startet erst, wenn eedc die Langzeitstatistik "
                         "lesen kann.")


@dataclass(frozen=True)
class Auftrag:
    anlage_id: int
    sensor_key: str
    #: Erste falsche Stunde (örtlich ohne Zone, volle Stunde); ``None`` = von Beginn an (Werkbank, S-9).
    falsch_seit: Optional[datetime]
    #: Erste Stunde der richtigen Quelle (``ab_ts``).
    ab: datetime
    vorher: Optional[dict]
    nachher: Optional[dict]
    herkunft: str = HERKUNFT_NACHTRAG
    erklaert: Optional[datetime] = None
    #: Korrektur über ein **abgeschlossenes Stück** (Bauplan «Zu §14» Nr. 97, ``stueck.py``): ``falsch_seit`` = Sprung,
    #: ``ab`` = Rückgang, ``vorher`` = ``nachher`` = die Quelle außerhalb des Stücks. Gefüllt wird nur, wenn beide Rand-Stände
    #: HAs Rohsumme dieser Quelle sind (``stueck.ist_fuellbar``); sonst bleibt das Stück eine Lücke.
    stueck: bool = False


def richtige_entitaet(nachher: Optional[dict]) -> Optional[str]:
    return nachher.get("entity_id") if isinstance(nachher, dict) and nachher.get("art") == "ha" else None


def _ts(dt: Optional[datetime]) -> Optional[int]:
    return None if dt is None else int(dt.timestamp())


def _kanal_beginn(a: Auftrag) -> Optional[int]:
    """Der Beginn des Intervalls im Kanal: **die Zeile ``t − 1 h`` trägt den Stand um ``t``** — der erste falsche Stand
    (``falsch_seit``) steht in der Kanalzeile eine Stunde davor (U1 Punkt 4, Gegenprüfung Zeile 10; dieselbe Regel wie am Ende,
    ``kanal/korrektur._spaetere_richtige``). Sonst bliebe die Stunde vor ``falsch_seit`` mit dem Stand des fremden Zählers im
    Kanal (gemessen 4b-1-K, Fall ``h4``: 10.06. 12,05 statt 12,0). ``None`` = von Beginn an (Werkbank). Mit einer
    Home-Assistant-Entität als richtiger Quelle (Spiegel) und — U3 b, G7 (a) — am Stück einer MQTT-Reihe: dessen «Falsch seit»
    ist der erste versetzte Stand der Reihe, der Sprung liegt in der Kanal-Stunde davor."""
    if a.falsch_seit is None:
        return None
    mqtt_stueck = a.stueck and (a.nachher or {}).get("art") == "mqtt"
    return int(a.falsch_seit.timestamp()) - (_STUNDE if richtige_entitaet(a.nachher) is not None or mqtt_stueck else 0)


async def kanal_beginn(db: AsyncSession, a: Auftrag, ha_svc=None) -> Optional[int]:
    """``_kanal_beginn`` mit dem **linken Rand** (U3-K3, B2): auf einer vollen Stunde «Falsch seit» trägt die Zeile
    ``Falsch seit − 1 h`` die Stunde davor. Führt Home Assistant für sie **keine** Zeile des richtigen Sensors (er beginnt erst
    später), zählt sie der bis dahin geltende Sensor, dessen Zeile der Kanal trägt — sie bleibt stehen (der Tag davor zählt
    seine letzte Stunde). Sonst wie bisher eine Stunde davor: führt HA den richtigen Sensor dort, zählt die Stunde mit ihm
    (U2 a2, P-1: Schnitt an «Falsch seit − 1 h»); beginnt an der Zeile eine Quelle des Kanals (die falsche wurde zu «Falsch
    seit» zugeordnet — gemessen 4b-1-K, Fall ``h4``); ein Stück (dessen Sprung liegt in der Kanal-Stunde davor); ohne Home
    Assistant."""
    k = _kanal_beginn(a)
    eid = richtige_entitaet(a.nachher)
    if (k is None or a.stueck or eid is None or ha_svc is None or a.falsch_seit.minute or a.falsch_seit.second
            or k + _STUNDE != int(a.falsch_seit.timestamp())):
        return k
    from backend.services.kanal.korrektur import erste_ha_zeile

    if await ha_abruf(erste_ha_zeile(ha_svc, eid, k, k)) is not None:
        return k                                # HA führt den richtigen Sensor in dieser Stunde (P-1)
    from backend.models.kanal import Kanal, KanalQuelle

    beginnt = (await db.execute(select(func.count()).select_from(KanalQuelle).join(Kanal, Kanal.id == KanalQuelle.kanal_id)
                                .where(and_(Kanal.anlage_id == a.anlage_id, Kanal.key == a.sensor_key,
                                            KanalQuelle.gueltig_ab == k)))).scalar_one()
    return k if beginnt else k + _STUNDE


# ── Home Assistant ──────────────────────────────────────────────────────────


def ha_eingerichtet() -> bool:
    """Ist Home Assistant für eedc eingerichtet (Add-on, Recorder-Adresse oder API-Verbindung)? Ohne: Standalone."""
    from backend.core.config import HA_INTEGRATION_AVAILABLE, settings
    from backend.services.ha_statistics_service import get_ha_statistics_service

    return bool(HA_INTEGRATION_AVAILABLE or settings.ha_recorder_db_url
                or getattr(get_ha_statistics_service(), "_ws_client", None) is not None)


def ha_dienst(ha_svc=None):
    """Der HA-Dienst des Laufs: ``ha_svc`` (Proben) oder — wenn eingerichtet — der Dienst des Prozesses; ``None`` = ohne HA.
    Eingerichtet, aber nicht erreichbar ⇒ ``KorrekturNichtStartbar``."""
    if ha_svc is None:
        if not ha_eingerichtet():
            return None
        from backend.services.ha_statistics_service import get_ha_statistics_service

        ha_svc = get_ha_statistics_service()
    if not ha_svc.is_available:
        raise KorrekturNichtStartbar(SATZ_NICHT_ERREICHBAR)
    return ha_svc


async def ha_abruf(abruf):
    """Ein Abruf aus Home Assistant in der Lage einer Korrektur (Bauplan «Zu §14» Nr. 116 E-K6): scheitert er, ist die Korrektur
    in diesem Augenblick nicht startbar (``KorrekturNichtStartbar`` mit dem Satz «nicht erreichbar») — die Prüf-Route antwortet
    damit wie bei «nicht erreichbar», die Route des Eintrags lehnt ab (422), nichts wird geschrieben."""
    try:
        return await abruf
    except KorrekturNichtStartbar:
        raise
    except Exception as e:  # noqa: BLE001 — jeder Abruf-Fehler von Home Assistant
        logger.warning("Korrektur: Abruf aus Home Assistant gescheitert: %s: %s", type(e).__name__, e)
        raise KorrekturNichtStartbar(SATZ_NICHT_ERREICHBAR) from e


# ── Lage (lesend) ───────────────────────────────────────────────────────────


@dataclass
class Lage:
    auftrag: Auftrag
    label: str
    kanal: Any                     # kanal/korrektur.KanalLage
    zaehlerstaende: int
    rohstaende: int
    bestand: Any                   # verwerfen_vor_quellbeginn.BestandZaehlung
    ziele: Any
    abschluss: frozenset
    tage_neu: list[date] = field(default_factory=list)
    mit_ha: bool = False
    nicht_startbar: Optional[str] = None
    von2: Optional[date] = None
    bis2: Optional[date] = None
    #: Der Teil des Intervalls, den nichts füllt (``[von, bis)``) — eine Lücken-Zeile; ihre Ränder sind Nähte nur bei einem
    #: Höhenwechsel (``zaehlerluecke``, U1); ``None`` = alles wird aus Home Assistant gefüllt.
    luecke: Optional[tuple[datetime, datetime]] = None
    #: Tage, die die Lücke trifft (Vorschau): ganz darin bzw. nur teilweise (Rand-Tage) — im Tagesfenster der Tagesansicht.
    luecke_tage: list[date] = field(default_factory=list)
    luecke_rand: list[date] = field(default_factory=list)
    #: Die Zeit, deren Zählerstände der Lauf aus Home Assistant neu liest und **speichert** (Bauplan «Zu §14» Nr. 111,
    #: ``fuelle_staende``) — die gefüllte Zeit (seit U1 auch hinter einer Lücke bis zum Beginn der HA-Geschichte); ``None`` =
    #: nichts zu speichern.
    staende_neu: Optional[tuple[datetime, datetime]] = None
    #: Ältere Lücken, die diese Korrektur ganz oder teilweise überdeckt (Bauplan «Zu §14» Nr. 113): je ``(von, bis, Rest)`` —
    #: ihr Rest bleibt Lücke (``_rest_der_luecke``), die überdeckte Zeit liest danach aus der richtigen Quelle.
    ueberdeckt: list[tuple[datetime, datetime, list[tuple[datetime, datetime]]]] = field(default_factory=list)
    #: «Wie jede Zählerlücke» (Bauplan Nr. 119, Nr. 127, U1, ``_wie_zaehlerluecke``): die Ränder der Lücke sind keine Nähte —
    #: davor, in der Zeit und danach gilt dieselbe Quelle, kein Zählertausch dazwischen; die Menge steht am ersten Stand danach.
    zaehlerluecke: bool = False
    #: Der Tag, an dem die Menge einer Zählerlücke steht (das Tagesfenster mit dem ersten Stand danach).
    zaehlerluecke_tag: Optional[date] = None
    #: Das Intervall ``[falsch_seit, ab)`` dieses Auftrags (Vorschau und Lauf; Korrekturrunde U1-K (e): eine wiederholte
    #: Korrektur über einen Teil nimmt ihre Zeile wieder, kürzt ältere Lücken aber nur um diesen Teil).
    intervall: Optional[tuple[datetime, datetime]] = None
    #: Pflichtpunkt P-2 (Halt H-1 aus U1-K, Option A): die Korrektur füllt erst nach der Lücke aus Home Assistant, und kein
    #: Rand-Stand war prüfbar — die Lücken-Zeile trägt das Merkmal «Höhe ungeprüft» (``ANSATZ_HOEHE_UNGEPRUEFT``), ihr Rand ist
    #: ein Höhenwechsel (``zeitpunkt.ohne_hoehenwechsel``).
    hoehe_ungeprueft: bool = False
    #: U3-K3 «Regel 2» (``nullpunkt.py``): die Lücke endet an der ersten Zeile einer neuen Statistik des richtigen Sensors
    #: (HA führt davor keine) — ihr Rand-Stand dort ist HAs Nullpunkt (``None`` = nicht so).
    nullpunkt: Optional[float] = None
    #: U3-K3: der Kanal des Felds trägt vor der verworfenen Zeit Werte (und die richtige Quelle aus Home Assistant setzt danach
    #: an) — die Tagesansicht liest dort den Kanal; die Tage der Lücke nennt die Vorschau nach seinen Rändern (``_tage``).
    kanal_traegt: bool = False

    @property
    def nichts_zu_tun(self) -> bool:
        return not (self.kanal.zeilen or self.kanal.offen or self.zaehlerstaende or self.rohstaende or self.bestand.tage)

    def abschluss_monate(self) -> list[tuple[int, int]]:
        tage = set(self.tage_neu) | set(self.bestand.abschluss_tage)
        return sorted({(d.year, d.month) for d in tage if (d.year, d.month) in self.abschluss})


def _ganze_tage(f: Optional[datetime], ab: datetime) -> tuple[Optional[date], date]:
    """Die Bestandstage (Fenster ``[Vortag 23:00, 23:00)``), deren Fenster ganz in ``[f, ab)`` liegt."""
    from backend.services.kanal.abgeleitet import tag_der_stunde

    bis = tag_der_stunde(int(ab.timestamp())) - timedelta(days=1)
    if f is None:
        return None, bis
    von = tag_der_stunde(int(f.timestamp()))
    if datetime.combine(von - timedelta(days=1), datetime.min.time()).replace(hour=23) < f:
        von += timedelta(days=1)
    return von, bis


async def _zaehle(db, modell, spalte_key, key, spalte_zeit, f, ab, anlage_id) -> int:
    bed = [modell.anlage_id == anlage_id, spalte_key == key, spalte_zeit < ab]
    if f is not None:
        bed.append(spalte_zeit >= f)
    return int((await db.execute(select(func.count()).select_from(modell).where(and_(*bed)))).scalar_one())


async def tage_neu_bilden_liste(db: AsyncSession, a: Auftrag, ziele) -> list[date]:
    """§7 Nr. 10, §10 Nr. 35: Tage, deren Fenster ``[f, ab)`` schneidet und deren Tageszeile einen Schlüssel des Felds trägt
    — **ohne Blick auf seine Herkunft**: die Marke ``auto:kanal_tag`` gilt je Zeile, nicht je Schlüssel
    (``energie_profil/mengen_weiche``), und der gespeicherte Wert wird gelesen; auch ein schon einmal neu gebildeter Tag
    gehört dazu. Auch in Monaten mit Abschluss (ihre gespeicherten Monatswerte bleiben)."""
    from backend.services.kanal.abgeleitet import tag_der_stunde
    from backend.services.verwerfen_vor_quellbeginn import _tz_zeilen, tz_keys_der_zeile

    bis = tag_der_stunde(int(a.ab.timestamp()) - _STUNDE)
    von = tag_der_stunde(int(a.falsch_seit.timestamp())) if a.falsch_seit is not None else None
    return sorted({row.datum for row in await _tz_zeilen(db, a.anlage_id, bis, ziele, von) if tz_keys_der_zeile(row, ziele)})


async def lage(db: AsyncSession, a: Auftrag, *, ha_svc=None) -> Lage:
    """Beide Schichten zählen, nichts schreiben. ``ha_svc``: der Dienst des Laufs (``ha_dienst``) oder ``None``."""
    from backend.models.anlage import Anlage
    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
    from backend.models.sensor_snapshot import SensorSnapshot
    from backend.services import verwerfen_vor_quellbeginn as vq
    from backend.services.kanal.korrektur import kanal_lage
    from backend.services.snapshot.keys import _sensor_key_to_mqtt_key

    anlage = (await db.execute(select(Anlage).where(Anlage.id == a.anlage_id))).scalar_one_or_none()
    if anlage is None:
        raise LookupError(f"Anlage {a.anlage_id} nicht gefunden")
    k = await kanal_lage(db, a.anlage_id, a.sensor_key, await kanal_beginn(db, a, ha_svc), int(a.ab.timestamp()),
                         richtige_entitaet(a.nachher))
    ab_staende = await wirksames_ab(db, a, k.w0)
    zs = await _zaehle(db, SensorSnapshot, SensorSnapshot.sensor_key, a.sensor_key, SensorSnapshot.zeitpunkt,
                       a.falsch_seit, ab_staende, a.anlage_id)
    mk = _sensor_key_to_mqtt_key(a.sensor_key)
    rs = await _zaehle(db, MqttEnergySnapshot, MqttEnergySnapshot.energy_key, mk, MqttEnergySnapshot.timestamp,
                       a.falsch_seit, ab_staende, a.anlage_id) if mk else 0
    ziele = await vq.bestand_ziele(db, anlage, a.sensor_key)
    abschluss = await vq.abschluss_monate(db, a.anlage_id)
    von2, bis2 = _ganze_tage(a.falsch_seit, a.ab)
    bestand = await vq.zaehle_bestand(db, a.anlage_id, ziele, bis2, abschluss, von2) if (von2 is None or von2 <= bis2) \
        else vq.BestandZaehlung()
    la = Lage(a, vq.feld_label(a.sensor_key, await vq._investitionen(db, a.anlage_id)), k, zs, rs, bestand, ziele,
              abschluss, mit_ha=ha_svc is not None, von2=von2, bis2=bis2)
    if ha_svc is not None:
        la.tage_neu = await tage_neu_bilden_liste(db, a, ziele)
    la.intervall = (_beginn(a, k.w0), ab_staende)
    la.luecke, la.nullpunkt = await _luecke(db, a, k.w0, ab_staende, ha_svc)
    if la.luecke is not None:
        from backend.services.zuordnung_wechsel.stueck import tragtag_der_luecke

        la.hoehe_ungeprueft = await _hoehe_ungeprueft(db, a, la.luecke, ab_staende, ha_svc)
        la.zaehlerluecke = await _wie_zaehlerluecke(db, a, *la.luecke, ab_staende, hoehe_ungeprueft=la.hoehe_ungeprueft)
        la.luecke_tage, la.luecke_rand = await _tage(db, anlage, a, k, la, ha_svc)
        if la.zaehlerluecke:
            la.zaehlerluecke_tag = await tragtag_der_luecke(db, anlage, a.sensor_key, la.luecke[1])
            la.luecke_tage = [d for d in la.luecke_tage if d != la.zaehlerluecke_tag]
            la.luecke_rand = [d for d in la.luecke_rand if d != la.zaehlerluecke_tag]
    if ha_svc is not None and richtige_entitaet(a.nachher) is not None and (la.luecke is None or la.luecke[1] < ab_staende):
        # U1 Punkt 3 (Gegenprüfung Zeile 5): führt Home Assistant den richtigen Sensor erst ab einem späteren Zeitpunkt, bleibt
        # nur die Zeit davor leer — ab dort liest der Lauf die Stände neu und speichert sie.
        await _fuellt_aus_ha(db, la, _erster_neuer_stand(la), ab_staende)
    if la.luecke is None and la.nullpunkt is not None:
        la.kanal_traegt = await _kanal_traegt(db, a, k, la)
    return la


async def _tage(db: AsyncSession, anlage, a: Auftrag, k, la: Lage, ha_svc=None) -> tuple[list[date], list[date]]:
    """Die Tage der Lücke (Vorschau): nach den gespeicherten Zählerständen (``stueck.tage_der_luecke``) — oder, trägt der Kanal
    des Felds davor Werte und setzt die richtige Quelle aus Home Assistant danach an, nach den Rändern des Kanals
    (``stueck.tage_im_kanal``, U3-K3) an Kanal-Tagen: verworfen ab ``w0`` bis zur ersten Zeile, die Home Assistant für den
    richtigen Sensor führt — dort setzt der Lauf seine Quelle an (``kanal/korrektur.erste_ha_zeile``; dieselbe Grenze, die die
    Auskunft «Zeit verworfen» danach im Kanal liest, ``raender_der_verworfenen_zeit``, U3-K4 K3-B7 Nr. 2); führt HA sie noch
    nicht und liegt das Ende der Lücke noch vor uns (der Dialog), ab der Stunde davor — der Stundenlauf übernimmt die erste
    Zeile des richtigen Sensors; an den übrigen Tagen nach der Reihe."""
    from backend.services.kanal.korrektur import erste_ha_zeile
    from backend.services.zuordnung_wechsel.stueck import reihe_raender, tage_der_luecke, tage_im_kanal

    la.kanal_traegt = await _kanal_traegt(db, a, k, la)
    if not la.kanal_traegt:
        # bis zum ersten Stand, den der Lauf hinter der Lücke speichert (die Stände davor verwirft er)
        return await tage_der_luecke(db, anlage, a.sensor_key, la.luecke[0], _erster_neuer_stand(la))
    ende = la.luecke[1]
    h0 = await ha_abruf(erste_ha_zeile(ha_svc, richtige_entitaet(a.nachher), k.w0, int(ende.timestamp()))) \
        if ha_svc is not None else None
    if h0 is not None and h0 < int(ende.timestamp()):
        ende = datetime.fromtimestamp(h0)
    elif h0 is None and la.nullpunkt is None and ende > (a.erklaert or datetime.now()):
        ende -= timedelta(hours=1)
    return await tage_im_kanal(db, anlage, a.sensor_key, datetime.fromtimestamp(k.w0), ende,
                               reihe=await reihe_raender(db, a.anlage_id, a.sensor_key, la.luecke[0], _erster_neuer_stand(la)))


async def _kanal_traegt(db: AsyncSession, a: Auftrag, k, la: Lage) -> bool:
    """U3-K3: trägt der Kanal des Felds vor der verworfenen Zeit Werte (und setzt die richtige Quelle aus Home Assistant
    danach an)? Nicht bei einer Zählerlücke."""
    from backend.services.kanal.korrektur import _referenz

    return bool(richtige_entitaet(a.nachher) and k.kanal is not None and k.w0 is not None and not la.zaehlerluecke
                and await _referenz(db, k.kanal, k.w0) is not None)


def _erste_zeile(la: Lage) -> datetime:
    """Wo die richtige Quelle zu zählen beginnt: das Ende der Lücke — ohne Lücke «Falsch seit» (``la.intervall``)."""
    return la.luecke[1] if la.luecke is not None else la.intervall[0]


def _erster_neuer_stand(la: Lage) -> datetime:
    """Ab wann der Lauf die Stände neu liest: das Ende der Lücke bzw. ohne Lücke «Falsch seit» — mit «Regel 2» (U3-K3/U3-K4,
    ``la.nullpunkt``) eine Stunde später, am Stand nach HAs erster Zeile (vor ihr führt HA keinen Stand; der Leser fände um
    die erste Zeile mit seiner Toleranz den Stand eine Stunde später)."""
    return _erste_zeile(la) + (timedelta(hours=1) if la.nullpunkt is not None else timedelta(0))


async def _fuellt_aus_ha(db: AsyncSession, la: Lage, f: datetime, ab: datetime) -> None:
    """Die Korrektur füllt ``[f, ab)`` aus Home Assistant (keine Lücke): ältere Lücken darin werden auf ihren Rest gekürzt
    (Nr. 113), und der Lauf liest die Zählerstände der Zeit neu und speichert sie (Nr. 111) — wenn die Korrektur dort Stände
    verwirft oder eine ältere Lücke überdeckt (deren Stände sind schon verworfen)."""
    la.ueberdeckt = [(w.falsch_seit_ts, w.ab_ts, _rest_der_luecke(w.falsch_seit_ts, w.ab_ts, f, ab))
                     for w in await _aeltere_luecken(db, la.auftrag, f, ab)]
    if f < ab and (la.ueberdeckt or await _erster_stand(db, la.auftrag, f, ab) is not None):
        la.staende_neu = (f, ab)


#: Zeilen-Nummern der gedachten Zeilen, mit denen die Vorschau die Lage nach der Korrektur nachbildet (``_zeilen_danach``).
_GEDACHT = 10 ** 12


async def _zeilen_danach(db: AsyncSession, a: Auftrag, f: datetime, ab: datetime, luecke: tuple[datetime, datetime], *,
                         hoehe_ungeprueft: bool = False) -> list:
    """Die Wechsel-Zeilen des Schlüssels, wie sie **nach** dieser Korrektur stehen werden (``zeitpunkt.Wechsel``, nichts
    geschrieben): die Zeilen, die sie aufhebt (``_ersetzte``) und die älteren Lücken, die sie überdeckt
    (``_aeltere_luecken``), als aufgehoben; dazu die Korrektur-Zeile und — bei einer Home-Assistant-Entität — die
    Lücken-Zeile (``_luecken_zeile``, mit dem Merkmal «Höhe ungeprüft», wenn der Lauf es setzt — P-2). Eine wiederholte
    gleiche Korrektur legt keine neue Zeile an (``_gleiche_korrektur``)."""
    from dataclasses import replace

    from backend.services.zuordnung_wechsel.zeitpunkt import Wechsel, lade_wechsel

    weg = {w.id for w in await _ersetzte(db, a, f)} | {w.id for w in await _aeltere_luecken(db, a, f, ab)}
    gleich = await _gleiche_korrektur(db, a, f, ab)
    durch = _GEDACHT if gleich is None else gleich.id          # wie der Lauf: die Zeile, die sie aufhebt
    zeilen = [replace(w, aufgehoben_durch=durch) if w.id in weg else w
              for w in (await lade_wechsel(db, a.anlage_id)).get(a.sensor_key, [])]
    if gleich is None:
        zeilen.append(Wechsel(a.sensor_key, ab, a.vorher, a.nachher, GRUND_KORREKTUR, f, None, None, _GEDACHT))
    if richtige_entitaet(a.nachher) is not None:
        zeilen.append(Wechsel(a.sensor_key, luecke[1], a.vorher, None, GRUND_KORREKTUR, luecke[0], None, None, _GEDACHT + 1,
                              ansatz=ANSATZ_HOEHE_UNGEPRUEFT if hoehe_ungeprueft else None))
    return zeilen


async def _wie_zaehlerluecke(db: AsyncSession, a: Auftrag, f: datetime, bis: datetime, ab: datetime, *,
                             hoehe_ungeprueft: bool = False) -> bool:
    """**Wie jede Zählerlücke** (Entscheid Gernot 19.11.2026, Bauplan Nr. 119; Halt H-K2-1 Option A, Nr. 127; Zielbild Nr. 133
    (4)): die verworfene, nicht gefüllte Zeit ``[f, bis)`` bekommt eine Lücken-Zeile (Merkmal «hier nicht aus Home Assistant
    heilen und nicht füllen»), und ihre Ränder sind **keine Nähte**, wenn zwischen dem letzten Stand davor und dem ersten Stand
    danach kein erklärter Höhenwechsel liegt (``zeitpunkt.ohne_hoehenwechsel``: dieselbe Quelle an beiden Ständen, keine
    Fortsetzung dazwischen) — in jeder Lage, mit und ohne Home Assistant, auch für MQTT. Die Vorschau fragt dieselbe Regel wie
    die Leser, an den Zeilen, wie sie nach der Korrektur stehen (``_zeilen_danach``). Endet die Lücke vor ``ab`` (Home
    Assistant führt den richtigen Sensor ab ``bis``), ist der Stand danach der, den der Lauf um ``bis`` neu speichert."""
    from backend.services.zuordnung_wechsel.zeitpunkt import ohne_hoehenwechsel, staende_um

    vor, nach = await staende_um(db, a.anlage_id, a.sensor_key, f, bis)
    if bis < ab or nach is None:
        # Der Stand danach ist der, den der Lauf um ``bis`` speichert, bzw. — endet die Zeit jetzt (Dialog: ``ab`` = nächste
        # volle Stunde) — der erste, den eedc danach schreibt; dort gilt die richtige Quelle der Korrektur.
        nach = bis
    return ohne_hoehenwechsel(await _zeilen_danach(db, a, f, ab, (f, bis), hoehe_ungeprueft=hoehe_ungeprueft), vor, nach,
                              (f, bis))


async def _aeltere_luecken(db: AsyncSession, a: Auftrag, f: datetime, ab: datetime, ohne_id: Optional[int] = None
                           ) -> list[ZuordnungWechsel]:
    """Die nicht aufgehobenen älteren Lücken des Schlüssels (``zeitpunkt.ist_luecke``: Lücken-Zeilen und Korrektur-Zeilen ohne
    Home-Assistant-Entität, etwa MQTT), die ``[f, ab)`` schneiden — die Korrektur kürzt sie auf ihren Rest (Bauplan «Zu §14»
    Nr. 102, Nr. 113). Vorschau und Lauf fragen dieselbe Liste."""
    from backend.services.zuordnung_wechsel.zeitpunkt import ist_luecke

    alte = (await db.execute(select(ZuordnungWechsel).where(and_(
        ZuordnungWechsel.anlage_id == a.anlage_id, ZuordnungWechsel.sensor_key == a.sensor_key,
        ZuordnungWechsel.grund == GRUND_KORREKTUR, ZuordnungWechsel.aufgehoben_durch.is_(None),
        ZuordnungWechsel.falsch_seit_ts < ab, ZuordnungWechsel.ab_ts > f)).order_by(ZuordnungWechsel.id))).scalars().all()
    return [w for w in alte if w.id != ohne_id and ist_luecke(w)]


async def _luecke(db: AsyncSession, a: Auftrag, w0: Optional[int], ab: datetime,
                  ha_svc) -> tuple[Optional[tuple[datetime, datetime]], Optional[float]]:
    """Der Teil von ``[falsch_seit, ab)``, den nichts füllt (Bauplan «Zu §14» Nr. 97): «Zuordnung zum Zeitpunkt» (B-0) füllt
    die Reihe nur aus einer Home-Assistant-Entität mit Geschichte — ohne Home Assistant oder mit einer MQTT-Quelle bleibt das
    ganze Intervall leer (``None`` = gefüllt); ein Stück füllt nur, wenn beide Rand-Stände HAs Rohsumme der Quelle sind
    (``stueck.ist_fuellbar``). **Leer bleibt nur die Zeit, für die Home Assistant nichts führt** (U1 Punkt 3, Gegenprüfung
    Zeile 5): beginnt HAs Geschichte des richtigen Sensors erst im Intervall, ist die Lücke ``[falsch_seit, erster Stand aus
    HA)``; ab dort liest der Lauf die Stände neu und speichert sie (``_fuellt_aus_ha``, ``fuelle_staende``). **U3-K3 «Regel 2»**
    (``nullpunkt.py``): ist HAs erste Zeile ``h`` die erste ihrer Statistik überhaupt, endet die Lücke an ``h`` (statt am Stand
    ``h + 1 h``) — die erste Zeile zählt ab HAs Nullpunkt; Rückgabe ``(Lücke, Nullpunkt der Reihe)``. **U3-K4 (K3-B4):** liegt
    «Falsch seit» genau auf ``h``, gilt dieselbe Regel ohne Lücke (``(None, Nullpunkt)``)."""
    from backend.services.kanal.korrektur import erste_ha_zeile, ha_beginnt_bei

    f = _beginn(a, w0)
    if f >= ab:
        return None, None
    eid = richtige_entitaet(a.nachher)
    if eid is None or ha_svc is None:
        return (f, ab), None
    if a.stueck:
        from backend.services.zuordnung_wechsel.stueck import ist_fuellbar

        if not await ist_fuellbar(db, a, ha_svc):
            return (f, ab), None
    # Der Stand um ``z`` steht in HAs Zeile ``z − 1 h`` (``get_value_at``). Gemessen wird ab dem ersten Stand, den die
    # Korrektur in der Reihe verwirft (davor gibt es nichts zu füllen — Werkbank «von Beginn an»: «falsch seit» liegt eine
    # Stunde vor dem ersten Wert). Beginnt HAs Geschichte später, ist ihr erster Stand ``h + 1 h`` — die Zeit davor bleibt
    # eine Lücke (ihre Ränder sind Nähte nur bei Höhenwechsel, ``_wie_zaehlerluecke``).
    z1 = await _erster_stand(db, a, f, ab)
    if z1 is None:
        return None, None
    if not a.stueck and not await _hoehe_passt(db, a, f, ab, ha_svc):
        return (f, ab), None                # U1-K (d): Füllen nur auf geprüfter Höhe
    h = await ha_abruf(erste_ha_zeile(ha_svc, eid, int(z1.timestamp()) - _STUNDE, int(ab.timestamp())))
    if h is not None and h <= int(z1.timestamp()) - _STUNDE:
        return None, None
    # «Regel 2» nur, wo kein Rand-Stand die Höhe prüft: liegt HAs Statistik auf der Höhe der gespeicherten Stände (geprüft), beginnt
    # sie dort nicht am Nullpunkt (U1-K (d), Fall «gleiche Höhe, ab später»).
    if (h is not None and not a.stueck and f <= datetime.fromtimestamp(h) < ab
            and await ha_abruf(ha_beginnt_bei(ha_svc, eid, h)) and await _hoehe_pruefung(db, a, f, ab, ha_svc) is None):
        from backend.services.zuordnung_wechsel.nullpunkt import nullpunkt_der_reihe

        null = await nullpunkt_der_reihe(db, a.anlage_id, ha_svc, eid, a.sensor_key, datetime.fromtimestamp(h))
        if null is not None:
            return ((f, datetime.fromtimestamp(h)) if f < datetime.fromtimestamp(h) else None), null
    if h is None or datetime.fromtimestamp(h + _STUNDE) >= ab:
        return (f, ab), None
    return (f, datetime.fromtimestamp(h + _STUNDE)), None


async def _hoehe_passt(db: AsyncSession, a: Auftrag, f: datetime, ab: datetime, ha_svc) -> bool:
    """``_hoehe_pruefung`` ohne «nicht prüfbar»: füllen, außer ein prüfbarer Rand passt nicht."""
    return await _hoehe_pruefung(db, a, f, ab, ha_svc) is not False


async def _hoehe_ungeprueft(db: AsyncSession, a: Auftrag, luecke: tuple[datetime, datetime], ab: datetime, ha_svc) -> bool:
    """Pflichtpunkt P-2 (Halt H-1 aus U1-K, Option A): füllt die Korrektur aus Home Assistant erst **nach** der Lücke
    (``luecke`` endet vor ``ab``) und ist kein Rand-Stand prüfbar (``_hoehe_pruefung`` ⇒ ``None``)? Nicht am Stück-Weg (dort
    prüft ``stueck.ist_fuellbar`` beide Ränder)."""
    if a.stueck or ha_svc is None or luecke[1] >= ab:
        return False
    return await _hoehe_pruefung(db, a, luecke[0], ab, ha_svc) is None      # dieselben Ränder wie ``_luecke``


async def _hoehe_pruefung(db: AsyncSession, a: Auftrag, f: datetime, ab: datetime, ha_svc) -> Optional[bool]:
    """**Füllen aus Home Assistant nur auf geprüfter Höhe** (Korrekturrunde U1-K (d), Bauplan Nr. 141; dieselbe Prüfung wie am
    Stück, ``stueck.ist_fuellbar``): ein prüfbarer Rand-Stand — der letzte gespeicherte Stand vor ``f`` bzw. der erste ab ``ab``,
    gespeichert aus der richtigen Quelle, und Home Assistant führt sie dort — muss HAs heutige Summe der richtigen Quelle sein
    (``SPIEGEL_TOLERANZ_KWH``). Passt einer nicht (etwa: die Summe wurde in Home Assistant seither berichtigt), füllt eedc nicht;
    die Zeit bleibt leer und folgt der Regel der Zählerlücke. Ein Rand aus einer anderen Quelle prüft die Höhe der richtigen
    nicht (Wechsel A → C). ``None``: kein Rand-Stand prüfbar (P-2), ``True``: alle prüfbaren passen."""
    from backend.core.berechnungen.zaehler_versatz import stand_passt_zum_spiegel
    from backend.services.zuordnung_wechsel.stueck import _ha_rohsumme, _rand_ab, _rand_vor
    from backend.services.zuordnung_wechsel.zeitpunkt import HEUTE, gleiche_quelle, lade_wechsel, quelle_am

    zeilen = (await lade_wechsel(db, a.anlage_id)).get(a.sensor_key)
    geprueft: Optional[bool] = None
    for rand in (await _rand_vor(db, a.anlage_id, a.sensor_key, f), await _rand_ab(db, a.anlage_id, a.sensor_key, ab)):
        if rand is None:
            continue
        q = quelle_am(zeilen, rand.zeitpunkt)
        if q is HEUTE:                     # kein Wechsel danach: davor die bisherige, danach die neue Zuordnung
            q = a.vorher if rand.zeitpunkt < ab else a.nachher
        if not (isinstance(q, dict) and gleiche_quelle(q, a.nachher)):
            continue
        summe = await _ha_rohsumme(ha_svc, richtige_entitaet(a.nachher), a.sensor_key, rand.zeitpunkt)
        if summe is None:
            continue
        if not stand_passt_zum_spiegel(rand.stand, summe, 0.0):
            return False
        geprueft = True
    return geprueft


async def _erster_stand(db: AsyncSession, a: Auftrag, f: datetime, ab: datetime) -> Optional[datetime]:
    from backend.models.sensor_snapshot import SensorSnapshot

    return (await db.execute(select(func.min(SensorSnapshot.zeitpunkt)).where(and_(
        SensorSnapshot.anlage_id == a.anlage_id, SensorSnapshot.sensor_key == a.sensor_key,
        SensorSnapshot.zeitpunkt >= f, SensorSnapshot.zeitpunkt < ab)))).scalar_one_or_none()


def _monate(monate: list[tuple[int, int]]) -> str:
    from backend.services.verwerfen_vor_quellbeginn import _monate_text

    return _monate_text(monate)


#: Die Wortlaute der Vorschau (Bauplan B-6 «Vorschau nennt», §10 Nr. 37; mit und ohne Home Assistant).
SATZ_TAGE = ("{n} Tage werden im Hintergrund neu gebildet: alle Zähler dieser Tage werden neu aus Home Assistant gelesen; "
             "Wetter und Börsenpreis bleiben.")
SATZ_STUNDENMITTEL = ("Bei älteren Tagen kommt die Leistung je Stunde danach aus der Langzeitstatistik von Home Assistant "
                      "(Stundenmittel), nicht mehr aus dem damaligen Verlauf.")
SATZ_KEIN_TAG = "Kein Tag muss neu gebildet werden; der Wert dieses Felds kommt danach aus dem richtigen Sensor."
SATZ_OHNE_HA = "Ohne Home Assistant werden die Werte nur verworfen — kein Tag wird neu gebildet."
SATZ_MONATE_NEU = ("Abgeschlossene Monate {liste}: die gespeicherten Monatswerte bleiben aus dem bisherigen Sensor; was eedc "
                   "im Monat aus den Tagen rechnet, folgt den neu gebildeten Tagen.")
SATZ_MONATE = "Abgeschlossene Monate {liste}: die gespeicherten Monatswerte bleiben aus dem bisherigen Sensor."
SATZ_RUECKWEG_HA = ("Die Korrektur lässt sich in eedc nicht rückgängig machen — der Rückweg ist eine Sicherung von Home "
                    "Assistant.")
SATZ_RUECKWEG_OHNE = ("Die Korrektur lässt sich in eedc nicht rückgängig machen — der Rückweg ist eine Sicherung der "
                      "eedc-Datenbank.")


def _saetze_monate(la: Lage) -> list[str]:
    """Abgeschlossene Monate: mit neu gebildeten Tagen folgt, was eedc im Monat aus den Tagen rechnet, den neuen Tagen."""
    neu = {(d.year, d.month) for d in la.tage_neu} if la.mit_ha else set()
    monate = la.abschluss_monate()
    s = []
    if [m for m in monate if m in neu]:
        s.append(SATZ_MONATE_NEU.format(liste=_monate([m for m in monate if m in neu])))
    if [m for m in monate if m not in neu]:
        s.append(SATZ_MONATE.format(liste=_monate([m for m in monate if m not in neu])))
    return s


def saetze(la: Lage) -> list[str]:
    """Die Vorschau in Anwender-Sprache (Bauplan B-6 «Vorschau nennt», §10 Nr. 37)."""
    from backend.core.zahlenformat import fmt_zahl

    if la.nicht_startbar:
        return [la.nicht_startbar]
    s = []
    if la.zaehlerstaende or la.rohstaende:
        s.append(f"Zählerstände dieses Felds im Zeitraum werden verworfen ({fmt_zahl(la.zaehlerstaende + la.rohstaende)}).")
    if not la.mit_ha:
        s.append(SATZ_OHNE_HA)
    elif la.tage_neu:
        s += [SATZ_TAGE.format(n=fmt_zahl(len(la.tage_neu))), SATZ_STUNDENMITTEL]
    elif la.luecke is None:                 # mit einer Lücke kommt der Wert nicht aus dem richtigen Sensor (``saetze_luecke``)
        s.append(SATZ_KEIN_TAG)
    s += saetze_luecke(la)
    s += saetze_ueberdeckt(la)
    s += _saetze_monate(la)
    s.append(SATZ_RUECKWEG_HA if la.mit_ha else SATZ_RUECKWEG_OHNE)
    return s


#: Lücke bei einem Höhenwechsel (Bauplan «Zu §14» Nr. 95 (1), seit Nr. 119/U1 nur noch dort): die Vorschau nennt, was ohne
#: Füllen gilt.
SATZ_LUECKE = ("Vom {von} bis {bis} Uhr füllt nichts die verworfenen Zählerstände wieder auf. Davor, in dieser Zeit und danach "
               "gilt nicht erkennbar dieselbe Quelle (eine andere oder unbekannte Quelle), oder dazwischen ist ein Zählertausch "
               "eingetragen — wo eedc einen Wert aus den gespeicherten Zählerständen bildet, bildet es über diese Zeit keine "
               "Differenz: die Menge dieser Zeit, gerechnet ab dem letzten Zählerstand davor, fehlt dort.")
#: Pflichtpunkt P-2 (Halt H-1 aus U1-K, Option A): dieselbe Quelle, aber das Gefüllte nach der Zeit liegt auf ungeprüfter Höhe.
#: U2 Lauf b (Punkt 5): wahr gefasst — Home Assistant führt den richtigen Sensor erst nach der Zeit (``_hoehe_ungeprueft``:
#: die Lücke endet vor ``ab``, weil HAs Geschichte dort beginnt), dazu der Handgriff, wo «Falsch seit» wählbar ist.
SATZ_LUECKE_HOEHE = ("Vom {von} bis {bis} Uhr füllt nichts die verworfenen Zählerstände wieder auf: Home Assistant führt den "
                     "richtigen Sensor erst ab dann. Ob seine Zählerstände auf der Höhe der gespeicherten davor liegen, lässt "
                     "sich nicht prüfen — wo eedc einen Wert aus den gespeicherten Zählerständen bildet, bildet es über diese "
                     "Zeit keine Differenz: die Menge dieser Zeit, gerechnet ab dem letzten Zählerstand davor, fehlt dort.")
SATZ_LUECKE_HOEHE_HANDGRIFF = ("Sollen die bisherigen Werte dieser Zeit lieber bleiben, setze «Falsch seit» auf {bis} Uhr — "
                               "dann verwirft eedc erst ab dort.")
SATZ_LUECKE_TAGE = "Wo die Tagesansicht den Wert aus den gespeicherten Zählerständen bildet, zeigt sie {teile}."
#: U3-K3: trägt der Kanal des Felds davor Werte, liest die Tagesansicht ihn — die Tage nach seinen Rändern (``_tage``).
SATZ_LUECKE_TAGE_KANAL = "Die Tagesansicht zeigt {teile}."
#: Lab-K W5/W9, U3-K3 (Nachmessung Satz B: «bis jetzt», die Zeit reichte bis zur nächsten vollen Stunde): der Beginn der
#: Lücken-Sätze, wenn ihr Ende noch nicht erreicht ist.
SATZ_BIS_JETZT = "Vom {von} Uhr bis zum Ende der laufenden Stunde"
SATZ_LUECKE_INNEN = "{tage} keinen Wert"
SATZ_LUECKE_RAND = "{tage} nur den Teil außerhalb dieser Zeit"


def _tage_bereich(tage: list[date]) -> str:
    """Zusammenhängende Tage als «am …» bzw. «vom … bis …»."""
    if len(tage) == 1:
        return f"am {tage[0].strftime('%d.%m.%Y')}"
    return f"vom {tage[0].strftime('%d.%m.%Y')} bis {tage[-1].strftime('%d.%m.%Y')}"


#: «Wie jede Zählerlücke» (Bauplan «Zu §14» Nr. 119/120; U1-K S1: eedc prüft die Quelle und den eingetragenen Zählertausch,
#: nicht die Höhe).
SATZ_ZAEHLERLUECKE = ("Vom {von} bis {bis} Uhr füllt nichts die verworfenen Zählerstände wieder auf. Davor, in dieser Zeit und "
                      "danach gilt dieselbe Quelle, und dazwischen ist kein Zählertausch eingetragen — eedc rechnet über diese "
                      "Zeit wie über jede Zählerlücke: die Menge dieser Zeit steht an dem Tag, an dem sie endet; die Tage davor "
                      "zeigen für diese Zeit keinen Wert.")
SATZ_ZAEHLERLUECKE_TAG = "am {tag} die Menge seit dem letzten Zählerstand davor"
#: U1 Punkt 3: führt Home Assistant den richtigen Sensor ab einem Zeitpunkt in der Zeit, liest eedc ab dort neu. U3-K4
#: (K3-B7 Nr. 1): die Zeit ist der erste neu gelesene Stand — Home Assistant kann den Sensor schon eine Stunde früher führen.
SATZ_STAENDE_AB = "Ab {zeit} Uhr liest eedc die Zählerstände des richtigen Sensors neu und speichert sie."
#: U3-K3 «Regel 2» (``la.nullpunkt``): die erste Zeile einer neuen Statistik zählt ab HAs Nullpunkt — im Kanal, wenn er davor
#: Werte trägt (``la.kanal_traegt``), sonst nur im Monat (Leseregel (a) in ``kanal/lesen.py``: ein Zeitraum, dessen erste Zeile
#: nach seinem Beginn liegt, ist nie voll).
SATZ_STAENDE_AB_KANAL = ("Ab {zeit} Uhr führt Home Assistant den richtigen Sensor; von dort an zählt eedc ihn wie Home "
                         "Assistant und liest seine Zählerstände neu.")
SATZ_STAENDE_AB_MONAT = ("Ab {zeit} Uhr führt Home Assistant den richtigen Sensor; eedc liest seine Zählerstände neu. Diese "
                         "erste Stunde zählt eedc im Monatsabschluss und bei „Aus HA laden“ wie Home Assistant, in "
                         "Tagesansicht, Stundenwerten und Monatsübersicht des Energieprofils nicht — dieses Feld hat davor "
                         "keinen Wert.")


def saetze_luecke(la: Lage) -> list[str]:
    """Die Sätze zur Lücke (``la.luecke``): Zeit, ohne Spitze, Tage ohne Wert und Rand-Tage mit Teilwert — bzw. bei einer
    Zählerlücke (``la.zaehlerluecke``) der Tag, an dem die Menge der Zeit steht."""
    if la.luecke is None:
        intervall = getattr(la, "intervall", None)
        if getattr(la, "nullpunkt", None) is not None and not getattr(la, "kanal_traegt", False) and intervall is not None:
            # U3-K4 (K3-B4): «Regel 2» ohne Lücke — ohne Werte davor zählt die erste Stunde nur der Monat
            return [SATZ_STAENDE_AB_MONAT.format(zeit=intervall[0].strftime("%d.%m.%Y %H:%M"))]
        return []
    von, bis = la.luecke
    satz = SATZ_ZAEHLERLUECKE if la.zaehlerluecke else (SATZ_LUECKE_HOEHE if la.hoehe_ungeprueft else SATZ_LUECKE)
    if bis > (getattr(la.auftrag, "erklaert", None) or datetime.now()):
        # Lab-K W5/W9: das Ende der Zeit liegt noch vor uns (``ab`` = nächste volle Stunde) — die Vorschau nennt «jetzt».
        satz = satz.replace("Vom {von} bis {bis} Uhr", SATZ_BIS_JETZT)
    s = [satz.format(von=von.strftime("%d.%m.%Y %H:%M"), bis=bis.strftime("%d.%m.%Y %H:%M"))]
    if satz is SATZ_LUECKE_HOEHE and la.auftrag.falsch_seit is not None and not getattr(la.auftrag, "stueck", False):
        s.append(SATZ_LUECKE_HOEHE_HANDGRIFF.format(bis=bis.strftime("%d.%m.%Y %H:%M")))
    teile = []
    if la.luecke_tage:
        teile.append(SATZ_LUECKE_INNEN.format(tage=_tage_bereich(la.luecke_tage)))
    if la.luecke_rand:
        teile.append(SATZ_LUECKE_RAND.format(tage=" und ".join(f"am {d.strftime('%d.%m.%Y')}" for d in la.luecke_rand)))
    if la.zaehlerluecke_tag is not None:
        teile.append(SATZ_ZAEHLERLUECKE_TAG.format(tag=la.zaehlerluecke_tag.strftime("%d.%m.%Y")))
    if teile:
        s.append((SATZ_LUECKE_TAGE_KANAL if getattr(la, "kanal_traegt", False) else SATZ_LUECKE_TAGE).format(
            teile=" und ".join(teile)))
    if _staende_ab(la):
        satz = SATZ_STAENDE_AB
        if getattr(la, "nullpunkt", None) is not None:
            satz = SATZ_STAENDE_AB_KANAL if getattr(la, "kanal_traegt", False) else SATZ_STAENDE_AB_MONAT
        s.append(satz.format(zeit=_staende_ab_zeit(la).strftime("%d.%m.%Y %H:%M")))
    return s


def _staende_ab(la: Lage) -> bool:
    """Liest der Lauf die Stände ab dem Ende der Lücke neu (Home Assistant führt den richtigen Sensor erst ab dort)?"""
    luecke, neu = getattr(la, "luecke", None), getattr(la, "staende_neu", None)
    return luecke is not None and neu is not None and neu[0] == _erster_neuer_stand(la)


def _staende_ab_zeit(la: Lage) -> datetime:
    """Ab wann eedc den richtigen Sensor zählt — **eine** Zeit für ``SATZ_STAENDE_AB`` und den Lücken-Satz (Korrekturrunde
    U1-K S5; U3-K3: dieselbe Zeit wie «bis» der Lücke): das Ende der Lücke. Mit «Regel 2» (``la.nullpunkt``) ist das HAs erste
    Zeile, und der Kanal zählt sie ab HAs Nullpunkt; sonst der erste neu gelesene Stand (gemessen U3-K2-Nachmessung: die
    Stunde davor zählte kein Leser)."""
    return la.luecke[1]


#: Eine Korrektur, die eine ältere Lücke überdeckt (Bauplan «Zu §14» Nr. 113): die Vorschau nennt, was mit ihr geschieht.
SATZ_LUECKE_GEKUERZT = ("Eine frühere Korrektur hat die Zeit vom {von} bis {bis} Uhr ohne Wert gelassen; für die Zeit dieser "
                        "Korrektur liest eedc die Zählerstände danach aus dem richtigen Sensor{rest}.")
SATZ_LUECKE_REST = " — ohne Wert bleibt {teile}"
SATZ_LUECKE_REST_TEIL = "die Zeit vom {von} bis {bis} Uhr"


def _uhr(t: datetime) -> str:
    return t.strftime("%d.%m.%Y %H:%M")


def saetze_ueberdeckt(la: Lage) -> list[str]:
    """Je ältere Lücke, die die Korrektur überdeckt: was danach aus dem richtigen Sensor kommt und was ohne Wert bleibt."""
    s = []
    for von, bis, rest in la.ueberdeckt:
        teile = " und ".join(SATZ_LUECKE_REST_TEIL.format(von=_uhr(x), bis=_uhr(y)) for x, y in rest)
        s.append(SATZ_LUECKE_GEKUERZT.format(von=_uhr(von), bis=_uhr(bis),
                                             rest=SATZ_LUECKE_REST.format(teile=teile) if teile else ""))
    return s


#: Der Kanal in der Dialog-Vorschau (Bauplan §11 Nr. 48; an der Werkbank-Vorschau ausgerichtet).
#: U1 (Punkt 6): was die leere Zeit für die Tageswerte heißt, sagen die Lücken-Sätze (``saetze_luecke``) — diese Sätze nennen
#: nur, was eedc nicht neu liest (wahr mit und ohne Höhenwechsel).
SATZ_KANAL_AB = ("Home Assistant führt die Geschichte des richtigen Sensors erst ab {zeit} Uhr — für die Zeit davor liest eedc "
                 "nichts neu.")
SATZ_KANAL_OHNE_GESCHICHTE = ("Home Assistant führt für den richtigen Sensor in diesem Zeitraum noch keine Stundenwerte — eedc "
                              "liest dort nichts neu.")
#: U3-K3 (Regel 1 nicht gebaut, gemessen ``vorlauf_2344``/``w5_2344``): endet die Zeit erst mit der laufenden Stunde, und Home
#: Assistant beginnt den richtigen Sensor in ihr, übernimmt der Stundenlauf seine erste Zeile; die Monatswerte aus Home
#: Assistant zählen sie nicht (Anker = erste Zeile).
SATZ_KANAL_ERSTE_STUNDE_OFFEN = ("Beginnt Home Assistant den richtigen Sensor in der laufenden Stunde, zählen Monatsabschluss und "
                                 "„Aus HA laden“ diese erste Stunde nicht; Home Assistant zählt sie.")
SATZ_KANAL_MQTT = ("Eine MQTT-Quelle hat keine Geschichte, die eedc nachholen könnte — für die Zeit von «Falsch seit» bis jetzt "
                   "liest eedc nichts neu.")
#: Dasselbe im Nachtrag (Bauplan §13 Nr. 69): dort endet das verworfene Intervall am Wechsel, nicht jetzt.
SATZ_KANAL_MQTT_NACHTRAG = ("Eine MQTT-Quelle hat keine Geschichte, die eedc nachholen könnte — für die Zeit von «Falsch seit» "
                            "bis zum Wechsel liest eedc nichts neu.")


async def kanal_saetze(la: Lage, ha_svc, *, bis_zum_wechsel: bool = False) -> list[str]:
    """Die Dialog-Vorschau nennt den Kanal (Bauplan §11 Nr. 48): ab wann Home Assistant die Geschichte des richtigen Sensors
    führt, wenn das nach dem Beginn des verworfenen Teils (``w0``) liegt, und dass eine MQTT-Quelle keine Geschichte
    nachholt. Derselbe Beginn ``h0`` wie im Lauf (``kanal/korrektur.erste_ha_zeile`` ab ``w0`` bis zum Soll-Ende) —
    Vorschau = Lauf. Ohne Home Assistant sagt ``SATZ_OHNE_HA`` genug. ``bis_zum_wechsel``: «Grund nachtragen» — das
    Intervall endet am Wechsel (``SATZ_KANAL_MQTT_NACHTRAG``)."""
    from backend.services.kanal.korrektur import erste_ha_zeile, fuell_ende

    if la.nicht_startbar:
        return []
    eid = richtige_entitaet(la.auftrag.nachher)
    if eid is None:
        if getattr(la.auftrag, "stueck", False):
            return []                       # das Stück endet am Rückgang — der Lücken-Satz sagt es (``saetze_luecke``)
        satz = SATZ_KANAL_MQTT_NACHTRAG if bis_zum_wechsel else SATZ_KANAL_MQTT
        return [satz] if (la.kanal.zeilen or la.zaehlerstaende or la.rohstaende) else []
    if ha_svc is None or la.kanal.w0 is None:
        return []
    h0 = await erste_ha_zeile(ha_svc, eid, la.kanal.w0, fuell_ende(int(datetime.now().timestamp())))
    if h0 is None:
        luecke = getattr(la, "luecke", None)
        offen = luecke is not None and luecke[1] > (getattr(la.auftrag, "erklaert", None) or datetime.now())
        return [SATZ_KANAL_OHNE_GESCHICHTE] + ([SATZ_KANAL_ERSTE_STUNDE_OFFEN] if offen else [])
    if _staende_ab(la) and datetime.fromtimestamp(h0) == _staende_ab_zeit(la):
        return []                           # derselbe Sachverhalt steht schon in ``SATZ_STAENDE_AB`` (U1-K S5)
    return [SATZ_KANAL_AB.format(zeit=datetime.fromtimestamp(h0).strftime("%d.%m.%Y %H:%M"))] if h0 > la.kanal.w0 else []


def vorschau_daten(la: Lage) -> dict[str, Any]:
    return {
        "zaehlerstaende": la.zaehlerstaende, "rohstaende": la.rohstaende,
        "tage_neu": [d.isoformat() for d in la.tage_neu], "mit_home_assistant": la.mit_ha,
        "abschluss_monate": [f"{j}-{m:02d}" for j, m in la.abschluss_monate()], "startbar": la.nicht_startbar is None,
        "luecke": None if la.luecke is None else {
            "von": la.luecke[0].isoformat(), "bis": la.luecke[1].isoformat(),
            "tage_ohne_wert": [d.isoformat() for d in la.luecke_tage], "tage_teilwert": [d.isoformat() for d in la.luecke_rand],
            "wie_zaehlerluecke": la.zaehlerluecke,
            "tag_der_menge": None if la.zaehlerluecke_tag is None else la.zaehlerluecke_tag.isoformat()},
        "staende_neu": None if la.staende_neu is None else {
            "von": la.staende_neu[0].isoformat(), "bis": la.staende_neu[1].isoformat()},
        "luecken_gekuerzt": [{"von": v.isoformat(), "bis": b.isoformat(),
                              "rest": [{"von": x.isoformat(), "bis": y.isoformat()} for x, y in r]} for v, b, r in la.ueberdeckt],
    }


# ── Ausführung ──────────────────────────────────────────────────────────────


def _beginn(a: Auftrag, w0: Optional[int]) -> datetime:
    """``falsch_seit`` der Wechsel-Zeile: wie angegeben, «von Beginn an» = Beginn des falschen Teils im Kanal (``w0``)."""
    return a.falsch_seit or (datetime.fromtimestamp(w0) if w0 is not None else a.ab)


def _im_intervall(a: Auftrag, w: ZuordnungWechsel) -> bool:
    """Bauplan §13 Nr. 67: eine Zeile, die die Korrektur gegenstandslos macht — ``ab_ts`` **im** verworfenen Intervall
    (``falsch_seit < ab_ts < ab``; ohne ``falsch_seit`` von Beginn an), oder am Rand ``ab_ts = falsch_seit``, wenn ihr
    ``vorher`` die richtige Quelle ist (der Wechsel ist rückgängig gemacht; mit anderem ``vorher`` wechselt dort weiter etwas)."""
    if not w.ab_ts < a.ab:
        return False
    if a.falsch_seit is None or w.ab_ts > a.falsch_seit:
        return True
    return w.ab_ts == a.falsch_seit and (w.vorher or {}) == (a.nachher or {})


async def _ersetzte(db: AsyncSession, a: Auftrag, f: datetime) -> list[ZuordnungWechsel]:
    """Die Zeilen, die die Korrektur aufhebt (nie eine Korrektur-Zeile): frühere Zeilen ohne Grund oder mit «Fortsetzung»
    für denselben Wechsel (gleiche neue Quelle, ``ab_ts`` in ``[f, ab + 1 h]``) und — Bauplan §13 Nr. 67 — jede Zeile ihres
    Intervalls (``_im_intervall``: beide Seiten oder ihre neue Quelle sind verworfen). Ein Dienst für Dialog, Nachtrag und
    Werkbank; Vorschau und Lauf zählen über dieselbe Liste (``wirksames_ab``)."""
    alle = (await db.execute(select(ZuordnungWechsel).where(and_(
        ZuordnungWechsel.anlage_id == a.anlage_id, ZuordnungWechsel.sensor_key == a.sensor_key,
        ZuordnungWechsel.aufgehoben_durch.is_(None), ZuordnungWechsel.ab_ts <= a.ab + timedelta(hours=1),
    )).order_by(ZuordnungWechsel.id))).scalars().all()
    return [w for w in alle if w.grund != GRUND_KORREKTUR and (
        (w.ab_ts >= f and (w.nachher or {}) == (a.nachher or {})) or _im_intervall(a, w))]


async def wirksames_ab(db: AsyncSession, a: Auftrag, w0: Optional[int]) -> datetime:
    """Das ``ab_ts`` der Wechsel-Zeile: ``ab`` oder später, wenn eine aufgehobene Zeile später beginnt (§10 Nr. 36 — Vorschau
    und Lauf verwerfen die Zählerstände bis hierher)."""
    return max([a.ab] + [w.ab_ts for w in await _ersetzte(db, a, _beginn(a, w0))])


async def _gleiche_korrektur(db: AsyncSession, a: Auftrag, f: datetime, ab: datetime) -> Optional[ZuordnungWechsel]:
    """Eine Korrektur-Zeile, die dieselbe Korrektur schon trägt (gleiche richtige Quelle, Intervall ``[f, ab)`` gedeckt)."""
    zeilen = (await db.execute(select(ZuordnungWechsel).where(and_(
        ZuordnungWechsel.anlage_id == a.anlage_id, ZuordnungWechsel.sensor_key == a.sensor_key,
        ZuordnungWechsel.grund == GRUND_KORREKTUR, ZuordnungWechsel.aufgehoben_durch.is_(None),
        ZuordnungWechsel.falsch_seit_ts <= f, ZuordnungWechsel.ab_ts >= ab)).order_by(ZuordnungWechsel.id))).scalars().all()
    return next((w for w in reversed(zeilen) if (w.nachher or {}) == (a.nachher or {})), None)


async def _wechsel_zeile(db: AsyncSession, a: Auftrag, jetzt: datetime, lauf: str, w0: Optional[int]) -> ZuordnungWechsel:
    """Schritt 1 — mit Aufheben einer früheren Zeile ohne Grund für denselben Wechsel; eine wiederholte gleiche Korrektur
    nimmt ihre Zeile wieder (``lauf`` = der neue Lauf), statt eine zweite anzulegen."""
    from backend.services.zuordnung_wechsel.zeitpunkt import merke_neu, vergiss

    f = _beginn(a, w0)
    ersetzt = await _ersetzte(db, a, f)
    ab = max([a.ab] + [w.ab_ts for w in ersetzt])
    gleich = await _gleiche_korrektur(db, a, f, ab)
    if gleich is not None:
        gleich.lauf = lauf
        await db.flush()
        return gleich
    row = ZuordnungWechsel(anlage_id=a.anlage_id, sensor_key=a.sensor_key, erklaert_ts=(a.erklaert or jetzt),
                           ab_ts=ab, vorher=a.vorher, nachher=a.nachher, grund=GRUND_KORREKTUR, falsch_seit_ts=f,
                           herkunft=a.herkunft, lauf=lauf)
    db.add(row)
    await db.flush()
    for w in ersetzt:
        w.aufgehoben_durch = row.id
    vergiss(db, a.anlage_id)
    merke_neu(db, row)
    return row


async def _luecken_zeile(db: AsyncSession, a: Auftrag, row: ZuordnungWechsel, luecke: Optional[tuple[datetime, datetime]],
                         lauf: str, intervall: Optional[tuple[datetime, datetime]] = None, *,
                         hoehe_ungeprueft: bool = False) -> Optional[ZuordnungWechsel]:
    """Die Lücken-Zeile (Bauplan «Zu §14» Nr. 95 (1), Nr. 97; seit U1 in jeder Lage): bleibt ein Teil des Intervalls ungefüllt,
    obwohl die Korrektur-Zeile eine Home-Assistant-Entität nennt (ohne Home Assistant, ohne Geschichte, ein Stück, dessen Ränder
    nicht zu HAs Rohsumme passen), steht für diesen Teil eine zweite Korrektur-Zeile mit ``nachher`` leer — sie ist jünger,
    gilt dort also vor der ersten (``zeitpunkt.quelle_am``: unbekannt ⇒ kein Schreiber füllt, kein Leser heilt), und ihre
    Ränder sind Nähte nur bei einem Höhenwechsel (``zeitpunkt.ohne_hoehenwechsel``). Nennt die Korrektur-Zeile selbst keine Entität (MQTT), ist sie die Lücke. Eine frühere
    Lücken-Zeile im neuen Intervall wird aufgehoben (dort gilt jetzt die neue Erklärung); **überdeckt die neue Korrektur sie
    nur teilweise, bleibt ihr Rest eine Lücke** (``_rest_der_luecke``, Bauplan «Zu §14» Nr. 102 — sonst stünden ihre Ränder als
    Nähte mitten in gefüllter Zeit). Ebenso eine ältere Korrektur-Zeile ohne Home-Assistant-Entität (MQTT, selbst eine Lücke):
    sie wird aufgehoben, ihr Rest steht als Lücken-Zeile (Nr. 113, ``_aeltere_luecken``). Gekürzt wird nur um das Intervall
    dieses Auftrags (``intervall``) — nimmt eine wiederholte Korrektur über einen Teil die Zeile der älteren wieder, behält der
    Rest der älteren Lücke «nicht heilen» (Korrekturrunde U1-K (e))."""
    from backend.services.zuordnung_wechsel.zeitpunkt import ist_luecken_zeile, merke_neu, vergiss

    f, ab = intervall or (row.falsch_seit_ts, row.ab_ts)
    soll = None if luecke is None else (luecke[0], min(luecke[1], ab))
    gleich = None
    reste: list[tuple[ZuordnungWechsel, datetime, datetime]] = []
    for w in await _aeltere_luecken(db, a, f, ab, ohne_id=row.id):
        if soll is not None and ist_luecken_zeile(w) and (w.falsch_seit_ts, w.ab_ts) == soll:
            gleich = w
            continue
        w.aufgehoben_durch = row.id
        reste += [(w, von, bis) for von, bis in _rest_der_luecke(w.falsch_seit_ts, w.ab_ts, f, ab)]
    for w, von, bis in reste:
        db.add(ZuordnungWechsel(anlage_id=w.anlage_id, sensor_key=w.sensor_key, erklaert_ts=w.erklaert_ts, ab_ts=bis,
                                vorher=w.vorher, nachher=None, grund=GRUND_KORREKTUR, falsch_seit_ts=von,
                                herkunft=w.herkunft, lauf=w.lauf,
                                ansatz=w.ansatz if bis == w.ab_ts else None))     # P-2: der Rest mit dem alten Ende
    if reste:
        await db.flush()
    vergiss(db, a.anlage_id)
    if soll is None or richtige_entitaet(row.nachher) is None or gleich is not None:
        return gleich
    neu = ZuordnungWechsel(anlage_id=a.anlage_id, sensor_key=a.sensor_key, erklaert_ts=row.erklaert_ts, ab_ts=soll[1],
                           vorher=row.vorher, nachher=None, grund=GRUND_KORREKTUR, falsch_seit_ts=soll[0],
                           herkunft=row.herkunft, lauf=lauf, ansatz=ANSATZ_HOEHE_UNGEPRUEFT if hoehe_ungeprueft else None)
    db.add(neu)
    await db.flush()
    vergiss(db, a.anlage_id)
    merke_neu(db, neu)
    return neu


def _rest_der_luecke(von: datetime, bis: datetime, f: datetime, ab: datetime) -> list[tuple[datetime, datetime]]:
    """Was von der Lücke ``[von, bis)`` außerhalb des neuen Intervalls ``[f, ab)`` bleibt (null, ein oder zwei Teile)."""
    return [(x, y) for x, y in ((von, min(bis, f)), (max(von, ab), bis)) if x < y]


async def _verwerfe_staende(db: AsyncSession, a: Auftrag, ab: datetime) -> tuple[int, int]:
    from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
    from backend.models.sensor_snapshot import SensorSnapshot
    from backend.services.snapshot.keys import _sensor_key_to_mqtt_key

    bed = [SensorSnapshot.anlage_id == a.anlage_id, SensorSnapshot.sensor_key == a.sensor_key, SensorSnapshot.zeitpunkt < ab]
    if a.falsch_seit is not None:
        bed.append(SensorSnapshot.zeitpunkt >= a.falsch_seit)
    zs = int((await db.execute(delete(SensorSnapshot).where(and_(*bed)))).rowcount or 0)
    mk = _sensor_key_to_mqtt_key(a.sensor_key)
    rs = 0
    if mk:
        bed = [MqttEnergySnapshot.anlage_id == a.anlage_id, MqttEnergySnapshot.energy_key == mk,
               MqttEnergySnapshot.timestamp < ab]
        if a.falsch_seit is not None:
            bed.append(MqttEnergySnapshot.timestamp >= a.falsch_seit)
        rs = int((await db.execute(delete(MqttEnergySnapshot).where(and_(*bed)))).rowcount or 0)
    return zs, rs


async def fuehre_aus(db: AsyncSession, a: Auftrag, *, ha_svc=None, jetzt: Optional[datetime] = None,
                     bestand_leeren: bool = True) -> dict[str, Any]:
    """Schritte 1, 2, 3 (ohne Füllen) und 5 in der Sitzung des Aufrufers, ein Commit; danach Füllen des Kanals und der
    Auftrag für Schritt 4 (``korrektur_lauf``). ``ha_svc`` = ``ha_dienst(...)`` (``None`` = ohne HA). Die Aktivität schreibt
    der Aufrufer (N-532: in dieser Sitzung, vor dem Commit — Rückgabe ``aktivitaet`` hilft ihm)."""
    from backend.core.database import get_session
    from backend.services import verwerfen_vor_quellbeginn as vq
    from backend.services.kanal import merken
    from backend.services.kanal.korrektur import fuell_ende, korrigiere_kanal
    from backend.services.zuordnung_wechsel import korrektur_lauf

    jetzt = (jetzt or datetime.now()).replace(microsecond=0)
    la = await lage(db, a, ha_svc=ha_svc)
    lauf = uuid.uuid4().hex[:12]
    bis_ts = fuell_ende(int(jetzt.timestamp()))
    kk = await korrigiere_kanal(db, a.anlage_id, a.sensor_key, await kanal_beginn(db, a, ha_svc), int(a.ab.timestamp()),
                                richtige_entitaet(a.nachher), ha_svc=ha_svc, jetzt_ts=int(jetzt.timestamp()), bis_ts=bis_ts,
                                bruecke=la.zaehlerluecke, nullpunkt=la.nullpunkt is not None)
    row = await _wechsel_zeile(db, a, jetzt, lauf, kk.w0)
    luecke = await _luecken_zeile(db, a, row, la.luecke, lauf, la.intervall, hoehe_ungeprueft=la.hoehe_ungeprueft)
    if luecke is not None and la.nullpunkt is not None and luecke.ab_ts == la.luecke[1]:
        luecke.stand_neu_null = la.nullpunkt            # U3-K3 «Regel 2»: das Merkmal für die Hülle des Monats
    if ha_svc is not None and la.luecke is None and la.nullpunkt is not None:
        row.stand_neu_null = la.nullpunkt               # U3-K4 (K3-B4): «Regel 2» ohne Lücke — das Merkmal trägt die Zeile
        await db.flush()
    elif ha_svc is not None and la.luecke is None:
        await _rand_an_falsch_seit(db, row, ha_svc)
    zs, rs = await _verwerfe_staende(db, a, row.ab_ts)
    bestand = {"stundenzeilen_geleert": 0, "tageszeilen_geleert": 0, "felder_geleert": 0}
    if bestand_leeren and (la.von2 is None or la.von2 <= la.bis2):
        bestand = await vq.leere_bestand(db, a.anlage_id, la.ziele, la.bis2, la.abschluss, la.von2)
    tage = la.tage_neu if ha_svc is not None else []
    nach = nachlauf_auftrag(kk, ha_svc, bis_ts, jetzt, staende=_staende_auftrag(a, la, ha_svc))
    if tage or nach is not None:
        await korrektur_lauf.anlegen(db, lauf, a.anlage_id, a.sensor_key, tage, fuellen=nach)
    merken.invalidiere(a.anlage_id, db=db)                         # Schritt 5
    summary = {"lauf": lauf, "wechsel_id": row.id, "kanalzeilen_geloescht": kk.geloescht,
               "abgeleitet_verworfen": kk.abgeleitet_verworfen,
               "quellen_markiert": kk.markiert, "kanal_beginn": kk.h0, "versatz": kk.versatz,
               "zaehlerstaende_geloescht": zs, "rohstaende_geloescht": rs, "tage_neu": len(tage),
               "luecke_id": None if luecke is None else luecke.id, **bestand}
    return {"summary": summary, "kanal": kk, "lage": la, "bis_ts": bis_ts, "jetzt": jetzt, "nachlauf": nach,
            "sitzungen": sitzungen_wie(db, get_session)}


async def _rand_an_falsch_seit(db: AsyncSession, row: ZuordnungWechsel, ha_svc) -> None:
    """P-1 mit Rand-Ständen (U2 a2): wechselt an «Falsch seit» die Entität (Home Assistant → Home Assistant) und füllt die
    Korrektur die Zeit ganz aus Home Assistant, trägt ihre Zeile die Rand-Stände nach der Regel eines Wechsels «bleiben» mit
    Schnitt an ``G = falsch_seit − 1 h``: der gespeicherte Stand des bisherigen Sensors um G und der Stand des richtigen dort
    aus Home Assistant (``ansatz = schnitt``). Dann zählt die Reihe die Stunde vor «Falsch seit» mit dem richtigen Sensor wie
    der Kanal. Fehlt einer der beiden Stände, bleibt die Naht ohne Rand-Stände (sie teilt)."""
    from backend.models.zuordnung_wechsel import ANSATZ_SCHNITT
    from backend.services.zuordnung_wechsel.stueck import _ha_rohsumme, _rand_vor
    from backend.services.zuordnung_wechsel.zeitpunkt import _falsch_seit_zwischen_zwei_sensoren, _als_wechsel, lade_wechsel

    eid, fs = richtige_entitaet(row.nachher), row.falsch_seit_ts
    if eid is None or fs is None:
        return
    zeilen = (await lade_wechsel(db, row.anlage_id)).get(row.sensor_key) or [_als_wechsel(row)]
    if not any(w.id == row.id for w in _falsch_seit_zwischen_zwei_sensoren(zeilen)):
        return
    g = fs - timedelta(hours=1)
    alt = await _rand_vor(db, row.anlage_id, row.sensor_key, fs)
    neu = await _ha_rohsumme(ha_svc, eid, row.sensor_key, g)
    if alt is None or alt.zeitpunkt != g or neu is None:
        return
    row.ansatz, row.stand_alt_ende, row.stand_neu_null = ANSATZ_SCHNITT, alt.stand, neu
    await db.flush()


def _staende_auftrag(a: Auftrag, la: Lage, ha_svc) -> Optional[dict]:
    """Der Schritt «Zählerstände neu lesen und speichern» im Auftrag des Nachlaufs (Bauplan «Zu §14» Nr. 111): die Zeit
    ``la.staende_neu`` (Vorschau = Lauf), nur mit Home Assistant."""
    if ha_svc is None or la.staende_neu is None:
        return None
    von, bis = la.staende_neu
    auftrag = {"key": a.sensor_key, "von": von.isoformat(), "bis": bis.isoformat()}
    if la.hoehe_ungeprueft:                         # P-2: eine Lücke, die der Lauf erst beim Lesen findet, trägt es auch
        auftrag["hoehe_ungeprueft"] = True
    return auftrag


def sitzungen_wie(db: AsyncSession, rueckfall):
    """Sitzungen an derselben Datenbank wie ``db`` (Füllen und Hintergrund-Lauf brauchen eigene, kurze Transaktionen)."""
    from contextlib import asynccontextmanager

    from sqlalchemy.ext.asyncio import async_sessionmaker

    bind = getattr(db, "bind", None)
    if bind is None:
        return rueckfall
    macher = async_sessionmaker(bind, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def sitzungen():
        async with macher() as s:
            yield s
            await s.commit()

    return sitzungen


def nachlauf_auftrag(kk, ha_svc, bis_ts: int, jetzt: datetime, *, staende: Optional[dict] = None) -> Optional[dict]:
    """Der Nachlauf nach dem Commit als Auftrag im Zustand des Laufs (``None`` = nichts zu tun): Kanal füllen (mit Home
    Assistant und einem Beginn der richtigen Quelle), die verworfenen abhängigen abgeleiteten Kanäle neu schreiben und —
    Bauplan «Zu §14» Nr. 111 — die Zählerstände der gefüllten Zeit aus Home Assistant neu lesen und speichern
    (``staende``, ``_staende_auftrag``). Solange der Auftrag offen ist, gilt das Intervall der Korrektur als Lücke (Nr. 106)."""
    fuellen = ha_svc is not None and kk.h0 is not None and kk.kanal_id is not None
    if not fuellen and not kk.abgeleitet_verworfen and staende is None:
        return None
    return {"kanal_id": kk.kanal_id, "key": kk.key, "w0": kk.w0, "h0": kk.h0 if fuellen else None, "bis_ts": bis_ts,
            "familien": None if kk.abgeleitet_familien is None else sorted(kk.abgeleitet_familien),
            "abgeleitet_verworfen": kk.abgeleitet_verworfen, "jetzt": jetzt.isoformat(), "staende": staende,
            "erledigt": False}


async def nachlauf_aus_auftrag(sitzungen, anlage_id: int, f: dict, *, ha_svc=None) -> dict[str, int]:
    """Den Nachlauf aus dem Auftrag ausführen (nach dem Commit oder nachgeholt vom Lauf; ``ha_svc`` = der Dienst des
    Aufrufers, sonst der des Prozesses). Wiederholbar: das Füllen des Kanals spiegelt neu, das Speichern der Stände füllt nur
    fehlende Zeilen. Returns: die Mengen."""
    from backend.services.kanal.korrektur import KanalKorrektur, fuelle_kanal, schreibe_abgeleitete_nach

    kk = KanalKorrektur(f["key"], kanal_id=f.get("kanal_id"), w0=f.get("w0"), h0=f.get("h0"),
                        abgeleitet_familien=None if f.get("familien") is None else frozenset(f["familien"]),
                        abgeleitet_verworfen=int(f.get("abgeleitet_verworfen") or 0))
    n: dict[str, int] = {}
    if not f.get("kanal_erledigt"):            # nach dem Commit schon gelaufen, nur die Stände stehen aus (Nr. 111)
        n = {"kanal_neu_gespiegelt": 0, "abgeleitet_neu": 0}
        svc = (ha_svc or ha_dienst(None)) if kk.h0 is not None else None
        if svc is not None:
            n["kanal_neu_gespiegelt"] = await fuelle_kanal(sitzungen, anlage_id, kk, ha_svc=svc, bis_ts=int(f["bis_ts"]))
            if isinstance(f.get("mitruecken"), dict):       # Ansetzen eines Wechsels «bleiben» (a-K N3): F4 nachholen
                from backend.services.zuordnung_wechsel.ansatz import mitruecken

                n["verschiebung"] = await mitruecken(sitzungen, kk.kanal_id, f["mitruecken"])
        n["abgeleitet_neu"] = await schreibe_abgeleitete_nach(sitzungen, anlage_id, kk, datetime.fromisoformat(f["jetzt"]),
                                                              immer=bool(f.get("abgeleitet_immer"))) or 0
    if isinstance(f.get("staende"), dict):
        n["staende_neu"] = await fuelle_staende(sitzungen, anlage_id, f["staende"], ha_svc=ha_svc)
    return n


async def fuelle_staende(sitzungen, anlage_id: int, auftrag: dict, *, ha_svc=None) -> int:
    """Bauplan «Zu §14» Nr. 111: die Zählerstände der gefüllten Zeit ``[von, bis)`` aus Home Assistant neu lesen und
    **speichern** — der bestehende Schreiber der Stunde (``snapshot/writer.snapshot_anlage``, nur dieser Schlüssel) mit der
    Zuordnung zum Zeitpunkt: in der Zeit gilt die richtige Quelle der Korrektur-Zeile, gefüllt werden nur fehlende Zeilen. Ein
    Tag je Transaktion. **Zwei Lagen** (U1 Punkt 2, ändert E-K2-3 der Runde 4b-1-K2):

    * Home Assistant **nicht erreichbar** (vorher, mittendrin oder danach) ⇒ die Funktion wirft — der Auftrag bleibt offen, die
      Zeit bleibt gesperrt (zeigt nichts), der Lauf holt es stündlich und nach dem Start nach (``korrektur_lauf``).
    * Home Assistant **nicht (mehr) eingerichtet** ⇒ wie ohne Home Assistant: Lücken-Zeile, der Auftrag endet (U1-K (b)).
    * Home Assistant **erreichbar, führt für die Quelle in der Zeit nichts** (kein Stand gespeichert) ⇒ der Auftrag endet; die
      Zeit bekommt eine Lücken-Zeile (``_luecke_nach_dem_lesen``: hier nicht heilen, nicht füllen) und die Leser rechnen über
      sie nach der Regel der Zählerlücke (``zeitpunkt.ohne_hoehenwechsel``). Führt Home Assistant die Quelle erst ab einem
      späteren Stand der Zeit, bleibt nur die Zeit davor leer.

    Returns: Zahl der geschriebenen Stände."""
    from backend.models.anlage import Anlage
    from backend.services.kanal import merken
    from backend.services.snapshot.writer import snapshot_anlage

    svc = ha_svc or ha_dienst(None)
    von, bis = datetime.fromisoformat(auftrag["von"]), datetime.fromisoformat(auftrag["bis"])
    if svc is None:
        # Korrekturrunde U1-K (b): Home Assistant ist nicht mehr eingerichtet — die Lage «ohne Home Assistant»: die Zeit
        # bekommt eine Lücken-Zeile, der Auftrag endet, die Leser folgen der Regel der Zählerlücke.
        await _luecke_nach_dem_lesen(sitzungen, anlage_id, auftrag["key"], von, bis, "Home Assistant ist nicht eingerichtet")
        merken.invalidiere(anlage_id)
        return 0
    zp = ab_ts_volle_stunde(von)
    nur = frozenset({auftrag["key"]})
    n = 0
    while zp < bis:
        _erreichbar(svc)
        async with sitzungen() as db:
            anlage = (await db.execute(select(Anlage).where(Anlage.id == anlage_id))).scalar_one()
            ende = min(bis, zp + timedelta(days=1))
            while zp < ende:
                n += await snapshot_anlage(db, anlage, zeitpunkt=zp, nur_schluessel=nur, ha_svc=svc)
                zp += timedelta(hours=1)
    _erreichbar(svc)
    erster = await _erster_stand_da(sitzungen, anlage_id, auftrag["key"], von, bis)
    if erster is None or erster > von:
        await _luecke_nach_dem_lesen(sitzungen, anlage_id, auftrag["key"], von, bis if erster is None else erster,
                                     ansatz=ANSATZ_HOEHE_UNGEPRUEFT if erster is not None and auftrag.get("hoehe_ungeprueft")
                                     else None)
    merken.invalidiere(anlage_id)
    return n


async def _luecke_nach_dem_lesen(sitzungen, anlage_id: int, key: str, von: datetime, bis: datetime,
                                 anlass: str = "Home Assistant führt nichts", *, ansatz: Optional[str] = None) -> None:
    """Home Assistant ist erreichbar und führt für ``[von, bis)`` nichts (U1 Punkt 2): eine Lücken-Zeile zur Korrektur-Zeile,
    deren Zeit das Füllen trägt (gleiche Felder wie ``_luecken_zeile``, ihr Lauf) — sonst heilte «Zuordnung zum Zeitpunkt» dort
    aus Home Assistant. Ihre Ränder sind Nähte nur bei Höhenwechsel (``zeitpunkt.ohne_hoehenwechsel``)."""
    from backend.services.zuordnung_wechsel.zeitpunkt import ist_luecken_zeile

    async with sitzungen() as db:
        zeilen = (await db.execute(select(ZuordnungWechsel).where(and_(
            ZuordnungWechsel.anlage_id == anlage_id, ZuordnungWechsel.sensor_key == key,
            ZuordnungWechsel.grund == GRUND_KORREKTUR, ZuordnungWechsel.aufgehoben_durch.is_(None),
            ZuordnungWechsel.falsch_seit_ts <= von, ZuordnungWechsel.ab_ts >= bis)).order_by(ZuordnungWechsel.id))).scalars().all()
        if any(ist_luecken_zeile(w) and w.falsch_seit_ts <= von and w.ab_ts >= bis for w in zeilen):
            return                                          # ein früherer Versuch hat sie schon geschrieben
        k = next((w for w in reversed(zeilen) if richtige_entitaet(w.nachher) is not None), None)
        if k is None:
            return
        db.add(ZuordnungWechsel(anlage_id=anlage_id, sensor_key=key, erklaert_ts=k.erklaert_ts, ab_ts=bis, vorher=k.vorher,
                                nachher=None, grund=GRUND_KORREKTUR, falsch_seit_ts=von, herkunft=k.herkunft, lauf=k.lauf,
                                ansatz=ansatz))
    logger.info("Korrektur: %s für %s vom %s bis %s — die Zeit bleibt leer", anlass, key, von, bis)


async def _erster_stand_da(sitzungen, anlage_id: int, key: str, von: datetime, bis: datetime) -> Optional[datetime]:
    """Der erste gespeicherte Stand in ``[von, bis)`` (auch aus einem früheren Versuch); ``None`` = keiner."""
    from backend.models.sensor_snapshot import SensorSnapshot

    async with sitzungen() as db:
        return (await db.execute(select(func.min(SensorSnapshot.zeitpunkt)).where(and_(
            SensorSnapshot.anlage_id == anlage_id, SensorSnapshot.sensor_key == key, SensorSnapshot.zeitpunkt >= von,
            SensorSnapshot.zeitpunkt < bis, SensorSnapshot.wert_kwh.is_not(None))))).scalar_one_or_none()


def ab_ts_volle_stunde(t: datetime) -> datetime:
    from backend.services.zuordnung_wechsel.zeitpunkt import ab_ts_aus

    return ab_ts_aus(t.replace(microsecond=0))


def _erreichbar(svc) -> None:
    if not svc.is_available:
        raise KorrekturNichtStartbar(SATZ_NICHT_ERREICHBAR)


async def nach_dem_commit(ergebnis: dict, *, ha_svc=None, sitzungen=None, starten: bool = True) -> dict[str, Any]:
    """Nach dem Commit des Aufrufers: Kanal füllen (Schritt 3), die abhängigen abgeleiteten Kanäle neu schreiben (§10
    Nr. 34) und den Hintergrund-Lauf starten — er speichert die Stände (Nr. 111, ``fuelle_staende``; über Monate tausende
    Stunden-Abrufe, deshalb nicht in der Anfrage) und bildet die Tage neu (Schritt 4). Scheitert der Nachlauf, holt ihn der Lauf
    nach (er steht als ``fuellen`` im Zustand); ``fuellen_offen`` in der Zusammenfassung sagt es dem Aufrufer, ``staende_offen``,
    dass der Lauf die Stände noch speichert."""
    from backend.services.kanal.korrektur import fuelle_kanal, schreibe_abgeleitete_nach
    from backend.services.zuordnung_wechsel import korrektur_lauf

    s = ergebnis["summary"]
    sitzungen = sitzungen or ergebnis["sitzungen"]
    anlage_id = ergebnis["lage"].auftrag.anlage_id
    nach = ergebnis["nachlauf"] if "nachlauf" in ergebnis else nachlauf_auftrag(
        ergebnis["kanal"], ha_svc, ergebnis["bis_ts"], ergebnis["jetzt"])
    hat_zustand = bool(s["tage_neu"]) or nach is not None
    staende = nach is not None and isinstance(nach.get("staende"), dict)
    try:
        if ha_svc is not None:
            s["kanal_neu_gespiegelt"] = await fuelle_kanal(sitzungen, anlage_id, ergebnis["kanal"], ha_svc=ha_svc,
                                                           bis_ts=ergebnis["bis_ts"])
        s["abgeleitet_neu"] = await schreibe_abgeleitete_nach(sitzungen, anlage_id, ergebnis["kanal"], ergebnis["jetzt"])
    except Exception as e:  # noqa: BLE001 — der Lauf holt den Nachlauf nach (Zustand ``fuellen``)
        logger.warning("Korrektur %s: Füllen nach dem Commit gescheitert, der Lauf holt es nach: %s: %s",
                       s["lauf"], type(e).__name__, e)
        s["fuellen_offen"] = True
    else:
        if hat_zustand:
            await korrektur_lauf.nachlauf_erledigt(sitzungen, s["lauf"], s.get("kanal_neu_gespiegelt", 0),
                                                   s.get("abgeleitet_neu", 0), staende_offen=staende)
        s["staende_offen"] = staende
    if hat_zustand and starten and (s["tage_neu"] or s.get("fuellen_offen") or staende):
        korrektur_lauf.starten(s["lauf"], sitzungen=sitzungen)
    return s
