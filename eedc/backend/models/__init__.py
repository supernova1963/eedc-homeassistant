# EEDC Models
from backend.models.anlage import Anlage, AnlageFoto
from backend.models.monatsdaten import Monatsdaten
from backend.models.investition import Investition, InvestitionMonatsdaten, InvestitionTyp
from backend.models.strompreis import Strompreis
from backend.models.settings import Settings
from backend.models.pvgis_prognose import PVGISPrognose, PVGISMonatsprognose
from backend.models.activity_log import ActivityLog
from backend.models.mqtt_energy_snapshot import MqttEnergySnapshot
from backend.models.tages_energie_profil import TagesEnergieProfil, TagesZusammenfassung
from backend.models.infothek import InfothekEintrag, InfothekDatei

__all__ = [
    "Anlage",
    "AnlageFoto",
    "Monatsdaten",
    "Investition",
    "InvestitionMonatsdaten",
    "InvestitionTyp",
    "Strompreis",
    "Settings",
    "PVGISPrognose",
    "PVGISMonatsprognose",
    "ActivityLog",
    "MqttEnergySnapshot",
    "TagesEnergieProfil",
    "TagesZusammenfassung",
    "InfothekEintrag",
    "InfothekDatei",
]
