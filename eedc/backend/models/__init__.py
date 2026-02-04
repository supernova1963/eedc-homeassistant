# EEDC Models
from backend.models.anlage import Anlage
from backend.models.monatsdaten import Monatsdaten
from backend.models.investition import Investition, InvestitionMonatsdaten, InvestitionTyp
from backend.models.strompreis import Strompreis
from backend.models.settings import Settings
from backend.models.pvgis_prognose import PVGISPrognose, PVGISMonatsprognose

__all__ = [
    "Anlage",
    "Monatsdaten",
    "Investition",
    "InvestitionMonatsdaten",
    "InvestitionTyp",
    "Strompreis",
    "Settings",
    "PVGISPrognose",
    "PVGISMonatsprognose",
]
