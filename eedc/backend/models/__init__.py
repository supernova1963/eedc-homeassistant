# EEDC Models
from backend.models.anlage import Anlage, AnlageFoto
from backend.models.monatsdaten import Monatsdaten
from backend.models.investition import Investition, InvestitionMonatsdaten, InvestitionTyp
from backend.models.strompreis import Strompreis, StrompreisZeitfenster
from backend.models.settings import Settings
from backend.models.pvgis_prognose import PVGISPrognose, PVGISMonatsprognose
from backend.models.activity_log import ActivityLog
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
# Triage 3.11.2026: registriert, damit `Base.metadata.create_all` (conftest, init_db) die Tabelle immer anlegt —
# bis dahin hing sie an der Import-Reihenfolge (eine Testdatei allein lief ohne Tabelle).
from backend.models.mqtt_live_snapshot import MqttLiveSnapshot
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.models.infothek import InfothekEintrag, InfothekDatei
from backend.models.korrekturprofil import Korrekturprofil
from backend.models.data_provenance_log import DataProvenanceLog
from backend.models.emob_ladeblock import EmobLadeblock
from backend.models.kanal import Kanal, KanalNachfuellung, KanalQuelle, KanalStatistik

__all__ = [
    "Anlage",
    "AnlageFoto",
    "Monatsdaten",
    "Investition",
    "InvestitionMonatsdaten",
    "InvestitionTyp",
    "Strompreis",
    "StrompreisZeitfenster",
    "Settings",
    "PVGISPrognose",
    "PVGISMonatsprognose",
    "ActivityLog",
    "MqttEnergySnapshot",
    "MqttLiveSnapshot",
    "TagesEnergieProfil",
    "TagesZusammenfassung",
    "InfothekEintrag",
    "InfothekDatei",
    "Korrekturprofil",
    "DataProvenanceLog",
    "EmobLadeblock",
    "Kanal",
    "KanalQuelle",
    "KanalStatistik",
    "KanalNachfuellung",
]
