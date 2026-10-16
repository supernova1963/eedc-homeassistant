"""Kanal-Schicht der Werkbank-Operation «Werte vor dem Sensorbeginn verwerfen» (HA-Bauform S3, E-S3-5; Bauplan §7).

**Wozu.** Ein Sensortausch legt eine neue ``kanal_quelle`` an; die Zeilen der alten Quelle bleiben stehen
(``nachfuellen.py`` füllt nur die Vorgeschichte DERSELBEN Quelle). Trägt der alte Sensor falsche Werte, kam bisher kein
Werkzeug an sie heran. Diese Schicht liefert die Vorschau und das Löschen **eines Kanals** (= eines zugeordneten Feldes)
vor einem Zeitpunkt ``t``:

* **Ältere Quellen** sind die ``kanal_quelle``-Zeilen mit ``gueltig_ab < t``. ``t`` liegt auf einer vollen Stunde,
  nach dem Beginn der ersten Quelle und **höchstens** am Beginn der jüngsten (Vorbelegung: ihr ``gueltig_ab``) — die
  jüngste Quelle ist nie eine ältere, ein Kanal ohne Sensortausch hat nichts zu verwerfen. Weil eine Zeile zu der Quelle
  mit dem größten ``gueltig_ab ≤ start_ts`` gehört, sind die Zeilen mit ``start_ts < t`` genau die Zeilen der älteren
  Quellen vor ``t`` (dazu Zeilen vor dem ersten ``gueltig_ab``, falls es sie gibt — sie gehören zu keiner jüngeren Quelle).
* **Gelöscht** werden nur diese ``kanal_statistik``-Zeilen; die ``kanal_quelle``-Zeilen bleiben als Herkunft und
  bekommen die Marke ``verworfen_ts`` (einmal, beim ersten Lauf, der etwas löscht). Ein zweiter Lauf findet keine Zeile
  mehr und ändert nichts.
* **Tage.** Eine Zeile gehört zu dem Kalendertag ihres Beginns (``fenster.kalendertag_der_stunde``, seit HA-Bauform S4
  E-S4-1 — der Kanal-Tag ist der Kalendertag, R-3). Der Tag, in dem ``t`` liegt (``tag_von_t``), braucht als Anker die
  letzte Zeile vor seinem Fenster — sie liegt vor ``t``; er verliert also seine Kanal-Deckung, ist aber nicht ganz vor
  ``t``. ``letzter_ganzer_tag`` ist der Tag davor: sein Fenster endet spätestens bei ``t``. Für die **Bestandstage**
  (Stunden- und Tageszeilen, Fenster ``[Vortag 23:00, 23:00)``) gilt ihr eigenes Fenster: ``tag_von_t_bestand``
  (``abgeleitet.tag_der_stunde``) und ``letzter_ganzer_bestandstag`` — beide verschieden nur, wenn ``t`` auf 23:00 fällt.

Keine Bestandstabelle wird hier gelesen oder geschrieben (das tut ``services/verwerfen_vor_quellbeginn.py``); kein
HA-Abruf. Schwesterdateien: ``nachfuellen.py`` (Marke je Kanal), ``konsistenz.py`` (Neu-Laden nur Spiegel-Abschnitte),
``fenster.py``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import and_, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.kanal import ART_STAND, ART_SUM, Kanal, KanalQuelle, KanalStatistik
from backend.services.kanal.abgeleitet import tag_der_stunde
from backend.services.kanal.fenster import kalendertag_der_stunde

_STUNDE = 3600
#: Kanäle, die die Operation anbietet: Zähler eines zugeordneten Feldes (``basis:<feld>``, ``inv:<id>:<feld>``).
VERWERFBARE_ARTEN = (ART_SUM, ART_STAND)
_PRAEFIXE = ("basis:", "inv:")


@dataclass(frozen=True)
class QuelleInfo:
    """Eine ``kanal_quelle``-Zeile mit ihrem Abschnitt ``[gueltig_ab, bis)`` (``bis`` = Beginn der nächsten Quelle)."""

    gueltig_ab: int
    bis: Optional[int]
    familie: str
    statistic_id: Optional[str]
    verworfen_ts: Optional[int]
    #: Zeilen dieser Quelle vor ``t`` (nur für ältere Quellen in der Vorschau gezählt).
    zeilen: int = 0


@dataclass(frozen=True)
class KanalVorschau:
    """Was die Kanal-Schicht verwerfen würde."""

    kanal_id: int
    key: str
    t: int
    aeltere: tuple[QuelleInfo, ...]
    juengste: QuelleInfo
    zeilen: int
    erste_ts: Optional[int]
    letzte_ts: Optional[int]
    #: Kalendertage mit Kanalzeilen vor ``t`` (``fenster.kalendertag_der_stunde``), aufsteigend.
    tage: tuple[date, ...]
    #: Der Kalendertag, in dem ``t`` liegt — verliert seinen Anker, ist aber nicht ganz vor ``t``.
    tag_von_t: date
    #: Der Bestandstag (``[Vortag 23:00, 23:00)``), in dem ``t`` liegt (``abgeleitet.tag_der_stunde``).
    tag_von_t_bestand: Optional[date] = None

    @property
    def letzter_ganzer_tag(self) -> date:
        return self.tag_von_t - timedelta(days=1)

    @property
    def letzter_ganzer_bestandstag(self) -> date:
        """Der letzte Bestandstag, dessen Fenster ``[Vortag 23:00, 23:00)`` ganz vor ``t`` liegt."""
        return (self.tag_von_t_bestand or self.tag_von_t) - timedelta(days=1)


def ist_verwerfbarer_key(key: str) -> bool:
    return key.startswith(_PRAEFIXE)


def zeitpunkt_aus_text(text: str) -> int:
    """``YYYY-MM-DDTHH:MM`` (Ortszeit der Prozesszone, wie die Tagesfenster) → Unix-Sekunden; nur volle Stunden."""
    try:
        dt = datetime.fromisoformat(text)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Zeitpunkt «{text}» ist kein Datum mit Uhrzeit (JJJJ-MM-TTTHH:MM)") from e
    if dt.tzinfo is not None:
        raise ValueError("Zeitpunkt ohne Zeitzone angeben — eedc rechnet in der Zeitzone von Home Assistant")
    if dt.minute or dt.second or dt.microsecond:
        raise ValueError("Zeitpunkt muss auf einer vollen Stunde liegen — die Kanalzeilen sind Stunden")
    return int(round(dt.timestamp()))


def text_aus_zeitpunkt(ts: int) -> str:
    """Unix-Sekunden → ``YYYY-MM-DDTHH:MM`` in der Prozesszone (Vorbelegung der Oberfläche)."""
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%dT%H:%M")


async def lade_kanal(db: AsyncSession, anlage_id: int, key: str) -> tuple[Kanal, list[KanalQuelle]]:
    """Kanal und seine Quellen (nach ``gueltig_ab``). ``LookupError``/``ValueError``, wenn er nicht taugt."""
    if not ist_verwerfbarer_key(key):
        raise ValueError(f"«{key}» ist kein zugeordnetes Feld (basis:… oder inv:…)")
    kanal = (await db.execute(
        select(Kanal).where(and_(Kanal.anlage_id == anlage_id, Kanal.key == key))
    )).scalar_one_or_none()
    if kanal is None:
        raise LookupError(f"Für «{key}» führt eedc keinen Kanal")
    if kanal.art not in VERWERFBARE_ARTEN:
        raise ValueError(f"«{key}» ist kein Zähler — verworfen werden nur Zählerkanäle")
    quellen = list((await db.execute(
        select(KanalQuelle).where(KanalQuelle.kanal_id == kanal.id).order_by(KanalQuelle.gueltig_ab)
    )).scalars().all())
    return kanal, quellen


def pruefe_zeitpunkt(key: str, quellen: list[KanalQuelle], t: int) -> None:
    """``t`` muss nach dem Beginn der ersten und höchstens am Beginn der jüngsten Quelle liegen."""
    if len(quellen) < 2:
        raise ValueError(
            f"«{key}» hat nur eine Quelle (kein Sensortausch) — vor ihrem Beginn gibt es keine Werte eines anderen "
            "Sensors zu verwerfen")
    if t <= quellen[0].gueltig_ab:
        raise ValueError(
            f"Der Zeitpunkt liegt nicht nach dem Beginn der ersten Quelle ({text_aus_zeitpunkt(quellen[0].gueltig_ab)})"
            " — davor gibt es nichts zu verwerfen")
    if t > quellen[-1].gueltig_ab:
        raise ValueError(
            f"Der Zeitpunkt liegt nach dem Beginn des jüngsten Sensors ({text_aus_zeitpunkt(quellen[-1].gueltig_ab)})"
            " — verworfen werden nur Werte älterer Quellen, nicht die des jüngsten Sensors")


def _info(quellen: list[KanalQuelle], i: int, zeilen: int = 0) -> QuelleInfo:
    q = quellen[i]
    bis = quellen[i + 1].gueltig_ab if i + 1 < len(quellen) else None
    return QuelleInfo(q.gueltig_ab, bis, q.familie, q.statistic_id, q.verworfen_ts, zeilen)


async def _zeilen_je_quelle(db: AsyncSession, kanal_id: int, quellen: list[KanalQuelle], t: int) -> list[int]:
    """Zeilen vor ``t`` je älterer Quelle; die erste Quelle zählt auch Zeilen vor ihrem ``gueltig_ab``."""
    out = []
    for i, q in enumerate(quellen):
        if q.gueltig_ab >= t:
            break
        oben = min(t, quellen[i + 1].gueltig_ab) if i + 1 < len(quellen) else t
        bed = [KanalStatistik.kanal_id == kanal_id, KanalStatistik.start_ts < oben]
        if i > 0:
            bed.append(KanalStatistik.start_ts >= q.gueltig_ab)
        out.append(int((await db.execute(select(func.count()).select_from(KanalStatistik).where(and_(*bed))))
                       .scalar_one()))
    return out


async def vorschau(db: AsyncSession, kanal: Kanal, quellen: list[KanalQuelle], t: int) -> KanalVorschau:
    """Die Kanal-Schicht ohne Schreiben: ältere Quellen, Zeilen vor ``t``, ihre Tage."""
    je_quelle = await _zeilen_je_quelle(db, kanal.id, quellen, t)
    aeltere = tuple(_info(quellen, i, n) for i, n in enumerate(je_quelle))
    stunden = list((await db.execute(
        select(KanalStatistik.start_ts).where(and_(KanalStatistik.kanal_id == kanal.id, KanalStatistik.start_ts < t))
        .order_by(KanalStatistik.start_ts)
    )).scalars().all())
    tage = tuple(sorted({kalendertag_der_stunde(int(s)) for s in stunden}))
    return KanalVorschau(
        kanal_id=kanal.id, key=kanal.key, t=t, aeltere=aeltere, juengste=_info(quellen, len(quellen) - 1),
        zeilen=len(stunden), erste_ts=int(stunden[0]) if stunden else None,
        letzte_ts=int(stunden[-1]) if stunden else None, tage=tage, tag_von_t=kalendertag_der_stunde(t),
        tag_von_t_bestand=tag_der_stunde(t),
    )


async def loesche_zeilen(db: AsyncSession, kanal_id: int, t: int) -> int:
    """Die Kanalzeilen vor ``t`` löschen (die der älteren Quellen). Returns: Zahl der gelöschten Zeilen."""
    res = await db.execute(delete(KanalStatistik).where(and_(
        KanalStatistik.kanal_id == kanal_id, KanalStatistik.start_ts < t,
    )))
    return int(res.rowcount or 0)


async def markiere_quellen(db: AsyncSession, kanal_id: int, t: int, jetzt_ts: int) -> int:
    """Marke «verworfen am» an den älteren Quellen, die noch keine tragen. Returns: Zahl der markierten Quellen."""
    res = await db.execute(update(KanalQuelle).where(and_(
        KanalQuelle.kanal_id == kanal_id, KanalQuelle.gueltig_ab < t, KanalQuelle.verworfen_ts.is_(None),
    )).values(verworfen_ts=jetzt_ts))
    return int(res.rowcount or 0)


async def kanaele_mit_quellen(db: AsyncSession, anlage_id: int) -> list[tuple[Kanal, list[KanalQuelle]]]:
    """Die Zählerkanäle zugeordneter Felder mit ihren Quellen (für die Auswahl der Werkbank), nach Schlüssel."""
    kanaele = [k for k in (await db.execute(
        select(Kanal).where(and_(Kanal.anlage_id == anlage_id, Kanal.art.in_(VERWERFBARE_ARTEN)))
        .order_by(Kanal.key)
    )).scalars().all() if ist_verwerfbarer_key(k.key)]
    quellen: dict[int, list[KanalQuelle]] = {k.id: [] for k in kanaele}
    if kanaele:
        for q in (await db.execute(
            select(KanalQuelle).where(KanalQuelle.kanal_id.in_(list(quellen))).order_by(KanalQuelle.gueltig_ab)
        )).scalars().all():
            quellen[q.kanal_id].append(q)
    return [(k, quellen[k.id]) for k in kanaele]
