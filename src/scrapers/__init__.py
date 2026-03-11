"""
Pacote de scrapers — importar este módulo registra todos os scrapers automaticamente.
"""

from .base import BaseScraper, ScraperRegistry
from .carrefour import CarrefourScraper
from .condor import CondorScraper
from .muffato import MuffatoScraper

__all__ = [
    "BaseScraper",
    "ScraperRegistry",
    "CondorScraper",
    "MuffatoScraper",
    "CarrefourScraper",
]