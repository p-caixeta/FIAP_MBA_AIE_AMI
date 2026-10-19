"""Mídia entra como evidência; os metadados não antecipam a resposta."""
import base64
import hashlib
import io
from pathlib import Path

import cv2
from PIL import Image, ImageOps

from config import MAX_BYTES, MAX_FRAMES, MAX_IMAGES, MAX_PIXELS, MAX_SECONDS

Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize_image(source: Path, target: Path) -> dict:
    """Valida bytes/dimensões e remove EXIF antes de produzir um JPEG."""
    if source.stat().st_size > MAX_BYTES:
        raise ValueError("Imagem maior que 10 MB.")
    with Image.open(source) as original:
        if original.format not in {"JPEG", "PNG", "WEBP"}:
            raise ValueError("Use JPEG, PNG ou WEBP.")
        if original.width * original.height > MAX_PIXELS:
            raise ValueError("Imagem maior que 8 megapixels.")
        picture = ImageOps.exif_transpose(original).convert("RGB")
        picture.thumbnail((1280, 1280))
        target.parent.mkdir(parents=True, exist_ok=True)
        picture.save(target, "JPEG", quality=88)
    return {"path": str(target), "width": picture.width, "height": picture.height,
            "sha256": digest(target)}


def sample_frames(source: Path, output: Path, count: int = 8) -> list[dict]:
    """Ex. 1.3: amostra quadros reais, incluindo início e fim do MP4."""
    if type(count) is not int or not 2 <= count <= MAX_FRAMES:
        raise ValueError("Selecione entre 2 e 8 quadros.")
    if source.stat().st_size > MAX_BYTES or source.read_bytes()[4:8] != b"ftyp":
        raise ValueError("Use um MP4 de até 10 MB.")
    capture = cv2.VideoCapture(str(source))
    try:
        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = capture.get(cv2.CAP_PROP_FPS)
        width, height = (int(capture.get(p)) for p in
                         (cv2.CAP_PROP_FRAME_WIDTH, cv2.CAP_PROP_FRAME_HEIGHT))
        if not capture.isOpened() or fps <= 0 or total < 2:
            raise ValueError("Vídeo inválido ou sem quadros suficientes.")
        if total / fps > MAX_SECONDS or width * height > MAX_PIXELS:
            raise ValueError("Vídeo excede 15 s ou 8 megapixels por quadro.")
        indices = sorted({round(i * (total - 1) / (count - 1)) for i in range(count)})
        output.mkdir(parents=True, exist_ok=True)
        frames = []
        for index in indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, pixels = capture.read()
            if not ok:
                raise ValueError(f"Não foi possível decodificar o quadro {index}.")
            path = output / f"frame_{index:04d}.jpg"
            image = Image.fromarray(cv2.cvtColor(pixels, cv2.COLOR_BGR2RGB))
            image.thumbnail((1280, 1280))
            image.save(path, quality=88)
            # Índice/fps é a aproximação temporal para estes clips de taxa constante.
            frames.append({"path": str(path), "index": index, "timestamp": round(index / fps, 3),
                           "duration": round(total / fps, 3), "total_frames": total,
                           "width": image.width, "height": image.height, "sha256": digest(path)})
        return frames
    finally:
        capture.release()


def build_multimodal_input(message: str, evidence: list[dict]) -> list[dict]:
    """Ex. 1.1: intercale identificadores e imagens na entrada real do LMM."""
    if not message.strip() or len(message) > 4000 or len(evidence) > MAX_IMAGES:
        raise ValueError("Informe texto de até 4.000 caracteres e até 12 imagens/quadros.")
    content = [{"type": "input_text", "text": message}]
    for item in evidence:
        path = Path(item["path"])
        if digest(path) != item["sha256"]:
            raise ValueError("A evidência foi alterada; prepare uma nova análise.")
        label = {key: item[key] for key in ("id", "timestamp") if key in item}
        content.append({"type": "input_text", "text": str(label)})
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        content.append({"type": "input_image", "image_url": f"data:image/jpeg;base64,{encoded}",
                        "detail": "auto"})
    return content


def input_summary(content: list[dict]) -> list[dict]:
    """Trace legível: preserva texto e quantidade de bytes, nunca base64."""
    return [{"type": part["type"], "text": part["text"]} if "text" in part else
            {"type": "input_image", "encoded_bytes": len(part["image_url"])}
            for part in content]


def prepare_media(paths: list[Path], directory: Path, frames: int) -> tuple[list, list]:
    """Normaliza cópias privadas e associa IDs a imagens/quadros enviados."""
    evidence, originals = [], []
    for number, path in enumerate(paths, 1):
        asset = directory / f"asset_{number}"
        asset.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() == ".mp4":
            copy = asset / "source.mp4"
            copy.write_bytes(path.read_bytes())
            items = sample_frames(copy, asset, frames)
            originals.append({"path": str(copy), "kind": "video", "id": f"M{number}"})
        else:
            items = [normalize_image(path, asset / "image.jpg")]
            originals.append({"path": items[0]["path"], "kind": "image", "id": f"M{number}"})
        for index, item in enumerate(items):
            evidence.append({**item, "id": f"M{number}-F{index}" if path.suffix.lower() == ".mp4" else f"M{number}"})
    return evidence, originals

