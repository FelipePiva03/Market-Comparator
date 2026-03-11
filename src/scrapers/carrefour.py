"""
Scraper do Carrefour (que absorveu o Big).

O Carrefour Mercado também roda VTEX, similar ao Muffato.
Domínio: mercado.carrefour.com.br
Account VTEX: "caraborahomolog" ou "carreflourbr" (varia)

APIs principais:
  - Legacy Search: /api/catalog_system/pub/products/search/
  - Regions (por CEP): /api/checkout/pub/regions?country=BRA&postalCode={cep}

Diferença do Muffato: o Carrefour exige um CEP para mostrar preços e
disponibilidade da loja mais próxima (seller regional).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from loguru import logger

from ..models import MarketSlug, ScrapedCategory, ScrapedProduct

from .base import BaseScraper, ScraperRegistry


@ScraperRegistry.register
class CarrefourScraper(BaseScraper):
    """
    Scraper para o Carrefour Mercado via VTEX Legacy Search API.

    O Carrefour exige um CEP para definir a região/seller, o que afeta
    preços e disponibilidade. Default: CEP de Curitiba.
    """

    BASE_URL = "https://mercado.carrefour.com.br"
    LEGACY_API = f"{BASE_URL}/api/catalog_system/pub"
    SEARCH_API = f"{BASE_URL}/api/io/_v/api/intelligent-search"

    # CEP padrão — Curitiba, PR (pode ser configurável)
    DEFAULT_CEP = "80250-060"

    def __init__(self, cep: str = DEFAULT_CEP) -> None:
        super().__init__()
        self.cep = cep
        self._seller_id: Optional[str] = None
        self._region_id: Optional[str] = None

    def get_name(self) -> str:
        return "Carrefour"

    def get_slug(self) -> MarketSlug:
        return MarketSlug.CARREFOUR

    def get_base_url(self) -> str:
        return self.BASE_URL

    def extra_headers(self) -> dict[str, str]:
        """
        Headers completos para simular um browser real.
        O Carrefour tem proteção anti-bot (provavelmente Cloudflare/Fastly)
        que bloqueia requests com headers incompletos.
        """
        return {
            "Accept": "application/json, text/plain, */*",
            "Accept-Encoding": "gzip, deflate, br",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
            "Sec-Ch-Ua": '"Chromium";v="120", "Google Chrome";v="120", "Not?A_Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Referer": "https://mercado.carrefour.com.br/",
            "Origin": "https://mercado.carrefour.com.br",
        }

    # ── Region setup (necessário para preços corretos) ─────────────

    async def _ensure_region(self) -> None:
        """
        Descobre o seller/região com base no CEP.
        Necessário para obter preços corretos da loja mais próxima.
        """
        if self._seller_id:
            return

        url = f"{self.BASE_URL}/api/checkout/pub/regions"
        params = {"country": "BRA", "postalCode": self.cep.replace("-", "")}

        try:
            data = await self._get_json(url, params=params)
            if data and isinstance(data, list) and data[0].get("sellers"):
                sellers = data[0]["sellers"]
                # Pega o primeiro seller ativo
                for seller in sellers:
                    if seller.get("id"):
                        self._seller_id = seller["id"]
                        self._region_id = data[0].get("id")
                        logger.info(
                            f"[carrefour] Região: {self._region_id}, "
                            f"Seller: {self._seller_id} (CEP: {self.cep})"
                        )
                        return
        except Exception as e:
            logger.warning(f"[carrefour] Não conseguiu resolver região para CEP {self.cep}: {e}")

    # ── Search ─────────────────────────────────────────────────────

    async def search(self, query: str, limit: int = 50) -> list[ScrapedProduct]:
        """
        Busca produtos no Carrefour.
        Tenta Intelligent Search primeiro, fallback para Legacy.
        """
        await self._ensure_region()

        # Tenta Intelligent Search
        url = f"{self.SEARCH_API}/product_search/"
        params = {
            "query": query,
            "count": min(limit, 50),
            "page": 1,
            "locale": "pt-BR",
        }

        try:
            data = await self._get_json(url, params=params)
            products = data.get("products", [])
            if products:
                return [self._parse_intelligent_product(p) for p in products if p]
        except Exception:
            logger.debug("[carrefour] Intelligent Search indisponível, usando Legacy")

        # Fallback para Legacy
        return await self._search_legacy(query, limit)

    async def _search_legacy(self, query: str, limit: int = 50) -> list[ScrapedProduct]:
        """Busca via Legacy Search API."""
        url = f"{self.LEGACY_API}/products/search/"
        params = {
            "ft": query,
            "_from": 0,
            "_to": min(limit - 1, 49),
        }
        if self._seller_id:
            params["fq"] = f"seller:{self._seller_id}"

        try:
            data = await self._get_json(url, params=params)
            if isinstance(data, list):
                return [self._parse_legacy_product(p) for p in data if p]
        except Exception as e:
            logger.error(f"[carrefour] Erro na busca '{query}': {e}")

        return []

    # ── Categories ─────────────────────────────────────────────────

    async def get_categories(self) -> list[ScrapedCategory]:
        """Lista categorias via VTEX Category Tree."""
        url = f"{self.LEGACY_API}/category/tree/3"

        try:
            data = await self._get_json(url)
        except Exception as e:
            logger.error(f"[carrefour] Erro ao buscar categorias: {e}")
            return []

        categories: list[ScrapedCategory] = []
        self._flatten_categories(data if isinstance(data, list) else [], categories)
        return categories

    def _flatten_categories(
        self,
        tree: list[dict],
        result: list[ScrapedCategory],
        parent_id: Optional[str] = None,
    ) -> None:
        for node in tree:
            cat_id = str(node.get("id", ""))
            result.append(
                ScrapedCategory(
                    id=cat_id,
                    name=node.get("name", ""),
                    parent_id=parent_id,
                    url=node.get("url", ""),
                )
            )
            for child in node.get("children", []):
                self._flatten_categories([child], result, parent_id=cat_id)

    # ── Products by category ───────────────────────────────────────

    async def get_products_by_category(
        self,
        category_id: str,
        page: int = 1,
        page_size: int = 50,
    ) -> list[ScrapedProduct]:
        """Lista produtos de uma categoria."""
        await self._ensure_region()

        url = f"{self.LEGACY_API}/products/search/"
        from_idx = (page - 1) * page_size
        to_idx = from_idx + page_size - 1
        params: dict = {
            "fq": f"C:/{category_id}/",
            "_from": from_idx,
            "_to": to_idx,
        }

        try:
            data = await self._get_json(url, params=params)
            if isinstance(data, list):
                return [self._parse_legacy_product(p) for p in data if p]
        except Exception as e:
            logger.error(f"[carrefour] Erro categoria {category_id} page {page}: {e}")

        return []

    # ── Parsers ────────────────────────────────────────────────────

    def _parse_intelligent_product(self, raw: dict) -> ScrapedProduct:
        """Parse de produto da Intelligent Search API (VTEX)."""
        items = raw.get("items", [])
        first_item = items[0] if items else {}
        sellers = first_item.get("sellers", [])
        first_seller = sellers[0] if sellers else {}
        offer = first_seller.get("commertialOffer", {}) or first_seller.get("commercialOffer", {})

        price = Decimal(str(offer.get("Price", 0) or 0))
        list_price = Decimal(str(offer.get("ListPrice", 0) or 0))
        original_price = list_price if list_price > price else None

        gtin = first_item.get("ean", None)
        if gtin:
            gtin = str(gtin).strip()

        images = first_item.get("images", [])
        image_url = images[0].get("imageUrl", "") if images else ""

        categories = raw.get("categories", [])
        category = categories[0].strip("/") if categories else ""

        link = raw.get("link", raw.get("linkText", ""))
        product_url = f"{self.BASE_URL}{link}" if link.startswith("/") else f"{self.BASE_URL}/{link}"

        return ScrapedProduct(
            sku=str(first_item.get("itemId", raw.get("productId", ""))),
            gtin=gtin,
            name=raw.get("productName", raw.get("name", "")),
            brand=raw.get("brand", ""),
            description=raw.get("description", "") or "",
            price=price,
            original_price=original_price,
            is_promotion=original_price is not None and original_price > price,
            category=category,
            unit=first_item.get("measurementUnit", "") or "",
            image_url=image_url,
            product_url=product_url,
            is_available=offer.get("IsAvailable", True),
            market=MarketSlug.CARREFOUR,
        )

    def _parse_legacy_product(self, raw: dict) -> ScrapedProduct:
        """Parse de produto da Legacy Search API (VTEX)."""
        items = raw.get("items", [])
        first_item = items[0] if items else {}
        sellers = first_item.get("sellers", [])
        first_seller = sellers[0] if sellers else {}
        offer = first_seller.get("commertialOffer", {})

        price = Decimal(str(offer.get("Price", 0) or 0))
        list_price = Decimal(str(offer.get("ListPrice", 0) or 0))
        original_price = list_price if list_price > price and list_price > 0 else None

        gtin = first_item.get("ean", None)
        if gtin:
            gtin = str(gtin).strip()

        images = first_item.get("images", [])
        image_url = images[0].get("imageUrl", "") if images else ""

        cat_list = raw.get("categories", [])
        category = cat_list[0].strip("/") if cat_list else ""

        link = raw.get("link", "")
        product_url = f"{self.BASE_URL}{link}" if link.startswith("/") else link

        return ScrapedProduct(
            sku=str(first_item.get("itemId", raw.get("productId", ""))),
            gtin=gtin,
            name=raw.get("productName", ""),
            brand=raw.get("brand", ""),
            description=raw.get("description", "") or "",
            price=price,
            original_price=original_price,
            is_promotion=original_price is not None,
            category=category,
            unit=first_item.get("measurementUnit", "") or "",
            image_url=image_url,
            product_url=product_url,
            is_available=offer.get("IsAvailable", True),
            market=MarketSlug.CARREFOUR,
        )