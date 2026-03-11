"""
Base scraper interface + Registry pattern.

Para adicionar um novo mercado:
  1. Crie um arquivo em src/scrapers/ (ex: angeloni.py)
  2. Implemente a classe herdando de BaseScraper
  3. Decore com @ScraperRegistry.register
  4. Importe no __init__.py do pacote

Pronto — o orquestrador já descobre o novo scraper automaticamente.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, Optional

import httpx
from loguru import logger
from tenacity import retry, stop_after_attempt, wait_exponential

from ..models import MarketSlug, ScrapedCategory, ScrapedProduct, ScrapeResult


class BaseScraper(ABC):
    """
    Contrato que todo scraper de mercado deve seguir.

    Cada mercado tem suas peculiaridades (API JSON, VTEX, HTML puro),
    mas todos devem retornar os mesmos tipos de dados.
    """

    # Timeout padrão para requests HTTP
    DEFAULT_TIMEOUT: ClassVar[float] = 30.0
    # User-Agent para não ser bloqueado
    DEFAULT_HEADERS: ClassVar[dict[str, str]] = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/html, */*",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    }

    def __init__(self) -> None:
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def client(self) -> httpx.AsyncClient:
        """HTTP client lazy-initialized com headers e timeout padrão."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers={**self.DEFAULT_HEADERS, **self.extra_headers()},
                timeout=self.DEFAULT_TIMEOUT,
                follow_redirects=True,
            )
        return self._client

    async def close(self) -> None:
        """Fecha o HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ── Métodos que o scraper DEVE implementar ──────────────────────

    @abstractmethod
    def get_name(self) -> str:
        """Nome legível do mercado (ex: 'Condor', 'Super Muffato')."""
        ...

    @abstractmethod
    def get_slug(self) -> MarketSlug:
        """Identificador único do mercado."""
        ...

    @abstractmethod
    def get_base_url(self) -> str:
        """URL base do site/API do mercado."""
        ...

    @abstractmethod
    async def search(self, query: str, limit: int = 50) -> list[ScrapedProduct]:
        """
        Busca textual de produtos.
        Usado quando o usuário digita algo no comparador.
        """
        ...

    @abstractmethod
    async def get_categories(self) -> list[ScrapedCategory]:
        """Lista todas as categorias disponíveis."""
        ...

    @abstractmethod
    async def get_products_by_category(
        self,
        category_id: str,
        page: int = 1,
        page_size: int = 50,
    ) -> list[ScrapedProduct]:
        """
        Lista produtos de uma categoria (com paginação).
        Usado pelo job de scraping em massa.
        """
        ...

    # ── Métodos opcionais que o scraper pode sobrescrever ───────────

    def extra_headers(self) -> dict[str, str]:
        """Headers adicionais específicos do mercado."""
        return {}

    async def get_product_by_sku(self, sku: str) -> Optional[ScrapedProduct]:
        """Busca um produto específico por SKU. Nem todo mercado suporta."""
        return None

    async def get_product_by_gtin(self, gtin: str) -> Optional[ScrapedProduct]:
        """Busca um produto por código de barras. Ideal para matching."""
        results = await self.search(gtin, limit=5)
        # Tenta achar match exato pelo GTIN
        for p in results:
            if p.gtin == gtin:
                return p
        return None

    # ── Helpers HTTP com retry ──────────────────────────────────────

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _get_json(self, url: str, params: Optional[dict] = None) -> dict:
        """GET request que retorna JSON, com retry automático."""
        logger.debug(f"[{self.get_slug()}] GET {url} params={params}")
        resp = await self.client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def _get_html(self, url: str, params: Optional[dict] = None) -> str:
        """GET request que retorna HTML, com retry automático."""
        logger.debug(f"[{self.get_slug()}] GET (html) {url}")
        resp = await self.client.get(url, params=params)
        resp.raise_for_status()
        return resp.text

    # ── Context Manager ────────────────────────────────────────────

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()


class ScraperRegistry:
    """
    Registry pattern para scrapers.

    Uso:
        @ScraperRegistry.register
        class CondorScraper(BaseScraper):
            ...

        # Depois, em qualquer lugar:
        all_scrapers = ScraperRegistry.all()
        condor = ScraperRegistry.get(MarketSlug.CONDOR)
    """

    _registry: ClassVar[dict[MarketSlug, type[BaseScraper]]] = {}

    @classmethod
    def register(cls, scraper_cls: type[BaseScraper]) -> type[BaseScraper]:
        """Decorator para registrar um scraper."""
        instance = scraper_cls()
        slug = instance.get_slug()
        cls._registry[slug] = scraper_cls
        logger.info(f"Scraper registrado: {instance.get_name()} ({slug})")
        return scraper_cls

    @classmethod
    def get(cls, slug: MarketSlug) -> BaseScraper:
        """Retorna uma instância do scraper pelo slug."""
        if slug not in cls._registry:
            available = ", ".join(s.value for s in cls._registry)
            raise KeyError(f"Scraper '{slug}' não encontrado. Disponíveis: {available}")
        return cls._registry[slug]()

    @classmethod
    def all(cls) -> list[BaseScraper]:
        """Retorna instâncias de todos os scrapers registrados."""
        return [scraper_cls() for scraper_cls in cls._registry.values()]

    @classmethod
    def slugs(cls) -> list[MarketSlug]:
        """Lista os slugs de todos os scrapers registrados."""
        return list(cls._registry.keys())