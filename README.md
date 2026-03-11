# Market Comparator

Comparador de preços de supermercados — Curitiba/PR.

## Mercados suportados

| Mercado | Plataforma | API | Status |
|---------|-----------|-----|--------|
| Condor | O Super (Sense) | JSON REST pública | ✅ Validado |
| Muffato | VTEX | Intelligent Search + Legacy | 🧪 Implementado |
| Carrefour | VTEX | Legacy Search + Regions | 🧪 Implementado |

## Setup

```bash
# Instalar dependências com uv
uv sync

# Copiar configuração
cp .env.example .env
```

## Uso — CLI de teste

```bash
# Buscar em um mercado específico
uv run python -m src.scrapers.run search condor "leite integral"
uv run python -m src.scrapers.run search muffato "coca cola"
uv run python -m src.scrapers.run search carrefour "arroz"

# Buscar em TODOS os mercados (comparação lado a lado)
uv run python -m src.scrapers.run search-all "leite integral"

# Listar categorias
uv run python -m src.scrapers.run categories condor
```

## Arquitetura

```
src/
├── models/
│   └── product.py          # ScrapedProduct, ScrapedCategory (contratos)
├── scrapers/
│   ├── base.py              # BaseScraper (ABC) + ScraperRegistry
│   ├── condor.py            # API Sense (osuper.com.br)
│   ├── muffato.py           # VTEX Intelligent Search
│   ├── carrefour.py         # VTEX Legacy + Regions (CEP-based)
│   └── run.py               # CLI de teste
├── matching/                # (próximo passo)
├── db/                      # (próximo passo)
└── api/                     # (próximo passo)
```

## Adicionar novo mercado

1. Crie `src/scrapers/novo_mercado.py`
2. Implemente a classe herdando `BaseScraper`
3. Decore com `@ScraperRegistry.register`
4. Importe em `src/scrapers/__init__.py`

O orquestrador descobre automaticamente.