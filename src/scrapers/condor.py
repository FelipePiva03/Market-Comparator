"""
Scraper do Supermercado Condor.

O Condor usa a plataforma "O Super" com API Sense.
Endpoint: https://sense.osuper.com.br/{company_id}/{store_id}/...

Já validado na POC — a API retorna JSON limpo sem autenticação.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from loguru import logger

from ..models import MarketSlug, ScrapedCategory, ScrapedProduct

from .base import BaseScraper, ScraperRegistry


@ScraperRegistry.register
class CondorScraper(BaseScraper):
    """
    Scraper para o Supermercado Condor via API Sense (osuper.com.br).

    A API é pública e retorna JSON. Não precisa de auth.
    Estrutura: /search, /category/{id}, /categories
    """

    COMPANY_ID = "314"
    STORE_ID = "1441"  # Loja padrão Curitiba — pode ser parametrizado
    BASE_API = f"https://sense.osuper.com.br/{COMPANY_ID}/{STORE_ID}"

    def get_name(self) -> str:
        return "Supermercados Condor"

    def get_slug(self) -> MarketSlug:
        return MarketSlug.CONDOR

    def get_base_url(self) -> str:
        return "https://www.condor.com.br"

    # ── Search ─────────────────────────────────────────────────────

    async def search(self, query: str, limit: int = 50) -> list[ScrapedProduct]:
        """
        Busca textual de produtos.

        Endpoint correto (descoberto via DevTools):
        /search?search=leite&sortField=_score&sortOrder=desc&size=12&from=0
        """
        url = f"{self.BASE_API}/search"
        params = {
            "search": query,
            "size": min(limit, 100),
            "from": 0,
            "sortField": "_score",
            "sortOrder": "desc",
            "brands": "",
            "categories": "",
            "tags": "",
        }

        try:
            data = await self._get_json(url, params=params)
        except Exception as e:
            logger.error(f"[condor] Erro na busca '{query}': {e}")
            return []

        hits = data.get("hits", [])
        return [self._parse_product(h) for h in hits if h]

    # ── Categories ─────────────────────────────────────────────────

    async def get_categories(self) -> list[ScrapedCategory]:
        """Lista categorias do Condor."""
        url = f"{self.BASE_API}/categories"

        try:
            data = await self._get_json(url)
        except Exception as e:
            logger.error(f"[condor] Erro ao buscar categorias: {e}")
            return []

        categories = []
        for cat in data if isinstance(data, list) else data.get("categories", []):
            categories.append(
                ScrapedCategory(
                    id=str(cat.get("id", "")),
                    name=cat.get("name", ""),
                    parent_id=str(cat.get("parentId", "")) if cat.get("parentId") else None,
                    product_count=cat.get("productCount"),
                    url=f"{self.get_base_url()}/categorias/{cat.get('slug', '')}",
                )
            )
        return categories

    # ── Products by category ───────────────────────────────────────

    async def get_products_by_category(
        self,
        category_id: str,
        page: int = 1,
        page_size: int = 50,
    ) -> list[ScrapedProduct]:
        """Lista produtos de uma categoria com paginação."""
        url = f"{self.BASE_API}/category/{category_id}"
        params = {
            "sortField": "sales_count",
            "size": page_size,
            "from": (page - 1) * page_size,
        }

        try:
            data = await self._get_json(url, params=params)
        except Exception as e:
            logger.error(f"[condor] Erro categoria {category_id} page {page}: {e}")
            return []

        hits = data.get("hits", [])
        return [self._parse_product(h) for h in hits if h]

    # ── Parser ─────────────────────────────────────────────────────

    def _parse_product(self, raw: dict) -> ScrapedProduct:
        """Converte um hit da API Sense para ScrapedProduct."""

        # Preço vem dentro do objeto "pricing"
        pricing = raw.get("pricing", {}) if isinstance(raw.get("pricing"), dict) else {}
        price = Decimal(str(pricing.get("price", 0) or 0))
        promo_price = Decimal(str(pricing.get("promotionalPrice", 0) or 0))
        is_promo = bool(pricing.get("promotion", False))

        # Se tem promoção e preço promocional é menor, inverte
        original_price: Optional[Decimal] = None
        if is_promo and promo_price > 0 and promo_price < price:
            original_price = price
            price = promo_price

        # Estoque
        quantity_obj = raw.get("quantity", {})
        is_available = True
        if isinstance(quantity_obj, dict):
            is_available = bool(quantity_obj.get("inStock", True))

        # GTIN (código de barras)
        gtin = raw.get("gtin") or raw.get("ean") or None
        if gtin:
            gtin = str(gtin).strip()

        # Categorias
        categories = raw.get("categories", [])
        category = ""
        subcategory = ""
        if isinstance(categories, list) and categories:
            for i, cat in enumerate(categories):
                cat_clean = cat.split(":", 1)[1] if ":" in str(cat) else str(cat)
                if i == 0:
                    category = cat_clean
                elif i == 1:
                    subcategory = cat_clean

        return ScrapedProduct(
            sku=str(raw.get("id", raw.get("productId", ""))),
            gtin=gtin,
            name=raw.get("name", raw.get("title", raw.get("productName", ""))),
            brand=raw.get("brand", raw.get("brandName", "")) or "",
            description=raw.get("description", "") or "",
            price=price,
            original_price=original_price,
            is_promotion=is_promo,
            category=category,
            subcategory=subcategory,
            unit=raw.get("unit", raw.get("measurementUnit", "")) or "",
            image_url=raw.get("image", raw.get("imageUrl", "")) or "",
            product_url=f"{self.get_base_url()}/produto/{raw.get('slug', raw.get('id', ''))}",
            is_available=is_available,
            market=MarketSlug.CONDOR,
        )