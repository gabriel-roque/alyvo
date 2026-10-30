"""Generate the synthetic documents used by OCR and ingestion validation."""

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).parent / "synthetic-documents"


def font(size: int):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def document(title: str, lines: list[str]) -> Image.Image:
    image = Image.new("RGB", (1400, 900), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, 1400, 112), fill="#2457ff")
    draw.text((70, 30), title, fill="white", font=font(46))
    y = 180
    for line in lines:
        draw.text((85, y), line, fill="#101828", font=font(38))
        y += 92
    draw.text((85, 820), "DOCUMENTO SINTÉTICO — SEM VALIDADE", fill="#667085", font=font(24))
    return image


def noisy(image: Image.Image) -> Image.Image:
    result = image.copy()
    pixels = result.load()
    random.seed(42)
    for _ in range(36_000):
        x = random.randrange(result.width)
        y = random.randrange(result.height)
        value = random.randrange(185, 256)
        pixels[x, y] = (value, value, value)
    return result


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    documents = {
        "identidade": ["NOME: Juliana Silva", "CPF: 123.456.789-09", "RG: 12.345.678-9"],
        "carteirinha": ["NOME: Juliana Silva", "CONVÊNIO: Vida+", "NÚMERO: VIDA-102938", "VALIDADE: 12/2027"],
        "pedido-medico": ["PACIENTE: Juliana Silva", "EXAME: Hemograma completo", "SOLICITANTE: Dra. Ana Costa"],
    }
    for name, lines in documents.items():
        image = document(name.replace("-", " ").upper(), lines)
        image.save(ROOT / f"{name}-limpo.png")
        image.rotate(4, expand=True, fillcolor="white").save(ROOT / f"{name}-rotacionado.png")
        image.filter(ImageFilter.GaussianBlur(1.2)).save(ROOT / f"{name}-desfocado.png")
        noisy(image).save(ROOT / f"{name}-ruido.png")
    institutional = document(
        "GUIA ADMINISTRATIVO ALYVO",
        [
            "A Unidade Centro aceita Vida+ e Amil.",
            "Cardiologia: Dra. Marina Lopes e Dr. Lucas Ferreira.",
            "Leve documento com foto e carteirinha do convênio.",
        ],
    )
    institutional.save(ROOT / "guia-institucional.pdf", "PDF", resolution=150)


if __name__ == "__main__":
    main()
