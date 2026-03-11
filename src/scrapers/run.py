"""
CLI para testar os scrapers individualmente.

Uso:
    uv run python -m src.scrapers.run search condor "leite integral"
    uv run python -m src.scrapers.run search muffato "coca cola"
    uv run python -m src.scrapers.run search carrefour "arroz"
    uv run python -m src.scrapers.run categories condor
    uv run python -m src.scrapers.run search-all "leite integral"   # busca em TODOS
"""

from __future__ import annotations

import asyncio
import json
import sys
from datetime import datetime

from loguru import logger

# Configura loguru
logger.remove()
logger.add(sys.stderr, level="INFO", format="<level>{level: <8}</level> | {message}")

# Import registra todos os scrapers
# Funciona tanto com `python -m src.scrapers.run` quanto via entrypoint
try:
    from src.scrapers import ScraperRegistry
    from src.models import MarketSlug
except ImportError:
    from . import ScraperRegistry
    from ..models import MarketSlug


async def cmd_search(market_slug: str, query: str) -> None:
    """Busca produtos em um mercado específico."""
    slug = MarketSlug(market_slug)
    scraper = ScraperRegistry.get(slug)

    print(f"\n🔍 Buscando '{query}' no {scraper.get_name()}...\n")

    async with scraper:
        products = await scraper.search(query, limit=10)

    if not products:
        print("❌ Nenhum produto encontrado.")
        return

    print(f"✅ {len(products)} produtos encontrados:\n")
    print(f"{'#':<3} {'Produto':<50} {'Preço':>10} {'GTIN':<15} {'Marca':<20}")
    print("─" * 100)

    for i, p in enumerate(products, 1):
        name = p.name[:48] if len(p.name) > 48 else p.name
        price_str = f"R$ {p.price:.2f}"
        promo = " 🏷️" if p.is_promotion else ""
        gtin = p.gtin or "—"
        print(f"{i:<3} {name:<50} {price_str:>10}{promo} {gtin:<15} {p.brand:<20}")

    # Exporta JSON para debug
    print(f"\n📦 Primeiro produto (JSON completo):")
    print(json.dumps(products[0].model_dump(mode="json"), indent=2, ensure_ascii=False, default=str))


async def cmd_search_all(query: str) -> None:
    """Busca em TODOS os mercados registrados."""
    scrapers = ScraperRegistry.all()
    print(f"\n🔍 Buscando '{query}' em {len(scrapers)} mercados...\n")

    results: dict[str, list] = {}

    for scraper in scrapers:
        name = scraper.get_name()
        print(f"  ⏳ {name}...", end=" ", flush=True)
        start = datetime.now()

        async with scraper:
            try:
                products = await scraper.search(query, limit=5)
                elapsed = (datetime.now() - start).total_seconds()
                results[name] = products
                print(f"✅ {len(products)} produtos ({elapsed:.1f}s)")
            except Exception as e:
                elapsed = (datetime.now() - start).total_seconds()
                results[name] = []
                print(f"❌ {e} ({elapsed:.1f}s)")

    # Comparação lado a lado
    print(f"\n{'─' * 90}")
    print(f"📊 COMPARAÇÃO: '{query}'\n")
    print(f"{'Mercado':<20} {'Produto':<40} {'Preço':>10} {'GTIN':<15}")
    print("─" * 90)

    for market, products in results.items():
        if products:
            p = products[0]
            name = p.name[:38] if len(p.name) > 38 else p.name
            gtin = p.gtin or "—"
            print(f"{market:<20} {name:<40} R$ {p.price:>7.2f} {gtin:<15}")
        else:
            print(f"{market:<20} {'(sem resultado)':<40}")


async def cmd_categories(market_slug: str) -> None:
    """Lista categorias de um mercado."""
    slug = MarketSlug(market_slug)
    scraper = ScraperRegistry.get(slug)

    print(f"\n📁 Categorias do {scraper.get_name()}...\n")

    async with scraper:
        categories = await scraper.get_categories()

    if not categories:
        print("❌ Nenhuma categoria encontrada.")
        return

    print(f"✅ {len(categories)} categorias:\n")
    for cat in categories[:30]:  # Limita a 30 para não poluir o terminal
        indent = "  └─ " if cat.parent_id else "📂 "
        count = f" ({cat.product_count} produtos)" if cat.product_count else ""
        print(f"{indent}{cat.name} [id: {cat.id}]{count}")

    if len(categories) > 30:
        print(f"\n  ... e mais {len(categories) - 30} categorias")


def main() -> None:
    if len(sys.argv) < 2:
        print(
            "Uso:\n"
            "  python -m src.scrapers.run search <mercado> <query>\n"
            "  python -m src.scrapers.run search-all <query>\n"
            "  python -m src.scrapers.run categories <mercado>\n"
            f"\nMercados disponíveis: {', '.join(s.value for s in ScraperRegistry.slugs())}"
        )
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "search" and len(sys.argv) >= 4:
        asyncio.run(cmd_search(sys.argv[2], " ".join(sys.argv[3:])))
    elif cmd == "search-all" and len(sys.argv) >= 3:
        asyncio.run(cmd_search_all(" ".join(sys.argv[2:])))
    elif cmd == "categories" and len(sys.argv) >= 3:
        asyncio.run(cmd_categories(sys.argv[2]))
    else:
        print(f"Comando desconhecido: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()