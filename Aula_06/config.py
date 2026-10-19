"""Ambiente comum e limites didáticos da Aula 06."""
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT.parent / ".env", override=False)
DATA = ROOT / "dados"
RUNTIME = ROOT / "runtime"
MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 8_000_000
MAX_SECONDS = 15
MAX_FRAMES = 8
MAX_IMAGES = 12
PORT = 5003


def configured_model() -> str:
    """Permite um modelo visual específico sem alterar as outras aulas."""
    return os.getenv("OPENAI_VISION_MODEL") or os.getenv("OPENAI_MODEL", "gpt-5.6-luna")
