"""
Scraper do Super Muffato.

O Muffato roda na plataforma VTEX, que tem uma API pública de busca:
  - Intelligent Search: /api/io/_v/api/intelligent-search/product_search/{facets}
  - Legacy Search: /api/catalog_system/pub/products/search/{category}

A Intelligent Search NÃO requer autenticação para leitura.
A accountName VTEX do Muffato é "muffatosupermercados".
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from loguru import logger

from ..models import MarketSlug, ScrapedCategory, ScrapedProduct

from .base import BaseScraper, ScraperRegistry


@ScraperRegistry.register
class MuffatoScraper(BaseScraper):
    """
    Scraper para o Super Muffato via VTEX API.

    Usa a Intelligent Search API que é pública:
    https://www.supermuffato.com.br/api/io/_v/api/intelligent-search/product_search/{facets}

    Fallback para Legacy Search se necessário:
    https://www.supermuffato.com.br/api/catalog_system/pub/products/search/
    """

    ACCOUNT_NAME = "muffatosupermercados"
    BASE_URL = "https://www.supermuffato.com.br"
    SEARCH_API = f"{BASE_URL}/api/io/_v/api/intelligent-search"
    LEGACY_API = f"{BASE_URL}/api/catalog_system/pub"

    def get_name(self) -> str:
        return "Super Muffato"

    def get_slug(self) -> MarketSlug:
        return MarketSlug.MUFFATO

    def get_base_url(self) -> str:
        return self.BASE_URL

    def extra_headers(self) -> dict[str, str]:
        """VTEX precisa desses headers para retornar dados corretos."""
        return {
            "Accept": "application/json",
            # O cookie de região/seller pode ser necessário para preços locais
            # Vamos começar sem e ajustar se necessário
        }

    # ── Search (Intelligent Search) ────────────────────────────────

    async def search(self, query: str, limit: int = 50) -> list[ScrapedProduct]:
        """
        Busca via VTEX Intelligent Search.
        GET /api/io/_v/api/intelligent-search/product_search/?query={q}&count={n}
        """
        url = f"{self.SEARCH_API}/product_search/"
        params = {
            "query": query,
            "count": min(limit, 50),
            "page": 1,
            "locale": "pt-BR",
        }

        try:
            data = await self._get_json(url, params=params)
        except Exception:
            # Fallback para Legacy Search
            logger.warning(f"[muffato] Intelligent Search falhou para '{query}', tentando Legacy")
            return await self._search_legacy(query, limit)

        products = data.get("products", [])
        return [self._parse_product(p) for p in products if p]

    async def _search_legacy(self, query: str, limit: int = 50) -> list[ScrapedProduct]:
        """Fallback: Legacy Search API."""
        url = f"{self.LEGACY_API}/products/search/"
        params = {
            "ft": query,
            "_from": 0,
            "_to": min(limit - 1, 49),
        }

        try:
            data = await self._get_json(url, params=params)
        except Exception as e:
            logger.error(f"[muffato] Legacy search também falhou para '{query}': {e}")
            return []

        if isinstance(data, list):
            return [self._parse_legacy_product(p) for p in data if p]
        return []

    # ── Categories ─────────────────────────────────────────────────

    async def get_categories(self) -> list[ScrapedCategory]:
        """
        Lista categorias via VTEX Category Tree API.
        GET /api/catalog_system/pub/category/tree/{levels}
        """
        url = f"{self.LEGACY_API}/category/tree/3"

        try:
            data = await self._get_json(url)
        except Exception as e:
            logger.error(f"[muffato] Erro ao buscar categorias: {e}")
            return []

        categories = []
        self._flatten_categories(data if isinstance(data, list) else [], categories)
        return categories

    def _flatten_categories(
        self,
        tree: list[dict],
        result: list[ScrapedCategory],
        parent_id: Optional[str] = None,
    ) -> None:
        """Achata a árvore de categorias VTEX em lista plana."""
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
            children = node.get("children", [])
            if children:
                self._flatten_categories(children, result, parent_id=cat_id)

    # ── Products by category ───────────────────────────────────────

    async def get_products_by_category(
        self,
        category_id: str,
        page: int = 1,
        page_size: int = 50,
    ) -> list[ScrapedProduct]:
        """
        Lista produtos de uma categoria.

        VTEX Intelligent Search: GET /product_search/{category_slug}
        VTEX Legacy: GET /products/search/?fq=C:/{category_id}/
        """
        # Tenta Intelligent Search primeiro
        url = f"{self.SEARCH_API}/product_search/"
        params = {
            "count": page_size,
            "page": page,
            "locale": "pt-BR",
            "query": "",
            # Filtro por categoria via facets
        }

        # Fallback para legacy que é mais confiável para categorias
        legacy_url = f"{self.LEGACY_API}/products/search/"
        from_idx = (page - 1) * page_size
        to_idx = from_idx + page_size - 1
        legacy_params = {
            "fq": f"C:/{category_id}/",
            "_from": from_idx,
            "_to": to_idx,
        }

        try:
            data = await self._get_json(legacy_url, params=legacy_params)
            if isinstance(data, list):
                return [self._parse_legacy_product(p) for p in data if p]
        except Exception as e:
            logger.error(f"[muffato] Erro categoria {category_id} page {page}: {e}")

        return []

    # ── Parsers ────────────────────────────────────────────────────

    def _parse_product(self, raw: dict) -> ScrapedProduct:
        """Parse de produto da Intelligent Search API."""

        # Pega o primeiro item/SKU
        items = raw.get("items", [])
        first_item = items[0] if items else {}
        sellers = first_item.get("sellers", [])
        first_seller = sellers[0] if sellers else {}
        offer = first_seller.get("commertialOffer", {}) or first_seller.get("commercialOffer", {})

        # Preço
        price = Decimal(str(offer.get("Price", 0) or 0))
        list_price = Decimal(str(offer.get("ListPrice", 0) or 0))
        original_price = list_price if list_price > price else None
        is_available = offer.get("IsAvailable", True)

        # GTIN
        gtin = None
        ean_field = first_item.get("ean", "") or first_item.get("referenceId", "")
        if ean_field:
            gtin = str(ean_field).strip()
        # Tenta pegar do campo alternativo
        if not gtin:
            ref_ids = first_item.get("referenceId", [])
            if isinstance(ref_ids, list) and ref_ids:
                gtin = str(ref_ids[0].get("Value", "")).strip() or None

        # Imagem
        images = first_item.get("images", [])
        image_url = images[0].get("imageUrl", "") if images else ""

        # Categoria
        categories = raw.get("categories", [])
        category = categories[0].strip("/") if categories else ""
        subcategory = categories[1].strip("/") if len(categories) > 1 else ""

        # SKU
        sku = str(first_item.get("itemId", raw.get("productId", "")))

        # URL
        link = raw.get("link", raw.get("linkText", ""))
        product_url = f"{self.BASE_URL}{link}" if link.startswith("/") else f"{self.BASE_URL}/{link}"

        return ScrapedProduct(
            sku=sku,
            gtin=gtin,
            name=raw.get("productName", raw.get("name", "")),
            brand=raw.get("brand", ""),
            description=raw.get("description", "") or "",
            price=price,
            original_price=original_price,
            is_promotion=original_price is not None and original_price > price,
            category=category,
            subcategory=subcategory,
            unit=first_item.get("measurementUnit", "") or "",
            unit_value=(
                Decimal(str(first_item.get("unitMultiplier", 1)))
                if first_item.get("unitMultiplier")
                else None
            ),
            image_url=image_url,
            product_url=product_url,
            is_available=is_available,
            market=MarketSlug.MUFFATO,
        )

    def _parse_legacy_product(self, raw: dict) -> ScrapedProduct:
        """
        Parse de produto da Legacy Search API.
        Estrutura é similar mas com diferenças nos campos.
        """
        # Na Legacy, items é uma lista de SKUs
        items = raw.get("items", [])
        first_item = items[0] if items else {}
        sellers = first_item.get("sellers", [])
        first_seller = sellers[0] if sellers else {}
        offer = first_seller.get("commertialOffer", {})

        price = Decimal(str(offer.get("Price", 0) or 0))
        list_price = Decimal(str(offer.get("ListPrice", 0) or 0))
        original_price = list_price if list_price > price and list_price > 0 else None

        # GTIN
        gtin = first_item.get("ean", None)
        if gtin:
            gtin = str(gtin).strip()

        # Imagem
        images = first_item.get("images", [])
        image_url = images[0].get("imageUrl", "") if images else ""

        # Categorias
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
            market=MarketSlug.MUFFATO,
        )