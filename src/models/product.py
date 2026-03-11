"""
Modelos de dados compartilhados entre todos os scrapers.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MarketSlug(str, Enum):
    """Identificadores únicos para cada mercado suportado."""

    CONDOR = "condor"
    MUFFATO = "muffato"
    CARREFOUR = "carrefour"


class ScrapedProduct(BaseModel):
    """
    Produto padronizado retornado por QUALQUER scraper.

    Este é o contrato: não importa se o mercado usa VTEX, API própria
    ou HTML puro — todo scraper deve retornar uma lista de ScrapedProduct.
    """

    # Identificação
    sku: str = Field(..., description="SKU interno do mercado")
    gtin: Optional[str] = Field(None, description="Código de barras EAN/GTIN-13 (chave para matching)")
    name: str = Field(..., description="Nome do produto como exibido no site")
    brand: str = Field("", description="Marca do produto")
    description: str = Field("", description="Descrição longa")

    # Preço
    price: Decimal = Field(..., description="Preço atual (pode ser o promocional)")
    original_price: Optional[Decimal] = Field(None, description="Preço original se em promoção")
    is_promotion: bool = Field(False, description="Se está em promoção")

    # Categorização
    category: str = Field("", description="Categoria principal")
    subcategory: str = Field("", description="Subcategoria")

    # Unidade / Gramatura
    unit: str = Field("", description="Unidade: 'kg', 'un', 'L', 'ml', 'g'")
    unit_value: Optional[Decimal] = Field(None, description="Valor da unidade (ex: 998 para 998ml)")

    # Mídia
    image_url: str = Field("", description="URL da imagem principal")
    product_url: str = Field("", description="URL do produto no site do mercado")

    # Disponibilidade
    is_available: bool = Field(True, description="Se está disponível para compra")

    # Metadata do scraping
    market: MarketSlug = Field(..., description="De qual mercado veio")
    scraped_at: datetime = Field(default_factory=datetime.utcnow)


class ScrapedCategory(BaseModel):
    """Categoria descoberta no catálogo de um mercado."""

    id: str = Field(..., description="ID da categoria no mercado")
    name: str = Field(..., description="Nome da categoria")
    parent_id: Optional[str] = Field(None, description="ID da categoria pai")
    product_count: Optional[int] = Field(None, description="Quantidade de produtos estimada")
    url: Optional[str] = Field(None, description="URL da categoria no site")


class ScrapeResult(BaseModel):
    """Resultado de uma operação de scraping."""

    market: MarketSlug
    products: list[ScrapedProduct] = Field(default_factory=list)
    total_found: int = 0
    pages_scraped: int = 0
    errors: list[str] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=datetime.utcnow)
    finished_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None