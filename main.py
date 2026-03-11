"""
Entrypoint principal — roda a CLI dos scrapers.

Uso:
    python main.py search condor "leite integral"
    python main.py search-all "arroz"
    python main.py categories muffato
"""

from src.scrapers.run import main

if __name__ == "__main__":
    main()