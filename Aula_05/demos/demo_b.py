"""Demo B: resultado adulterado sintético. Nenhuma escrita ou exfiltração."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mcp_server import build_server

if __name__ == "__main__":
    build_server(demo="b").run()
