from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import io
import base64
import uuid
import os
from PIL import Image, ImageDraw, ImageFont
from rembg import remove

app = FastAPI(title="Figurinha Copa 2026 API")

# Libera CORS para o seu frontend (Lovable/Vercel)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Troque pelo domínio do seu Lovable em produção
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── CONFIGURAÇÕES DO TEMPLATE ─────────────────────────────────────────────────
# Ajuste essas posições conforme o SEU template PNG
TEMPLATE_PATH = "template.png"       # coloque seu template na mesma pasta

CONFIG = {
    # Posição e tamanho do rosto no template (x, y, largura, altura)
    "face": {
        "x": 90,
        "y": 60,
        "width": 280,
        "height": 280,
    },
    # Textos — ajuste x, y, tamanho e cor conforme seu template
    "texts": {
        "nome": {
            "x": 230,   # centro horizontal
            "y": 375,
            "size": 22,
            "color": (255, 255, 255),
            "bold": True,
            "uppercase": True,
            "align": "center",
        },
        "clube": {
            "x": 230,
            "y": 415,
            "size": 16,
            "color": (255, 220, 0),
            "bold": False,
            "uppercase": True,
            "align": "center",
        },
        "stats": {  # Ex: "12-10-2015 | 1,50 m | 52 kg"
            "x": 230,
            "y": 395,
            "size": 13,
            "color": (220, 220, 220),
            "bold": False,
            "uppercase": False,
            "align": "center",
        },
    },
    # Watermark (PREVIEW diagonal)
    "watermark": {
        "text": "PREVIEW",
        "color": (255, 255, 255, 60),  # RGBA — 60 = transparência
        "size": 55,
        "angle": 35,
        "repeat": True,  # repete em grade
    },
}

# ─── FONTES ───────────────────────────────────────────────────────────────────
# Se não tiver as fontes, baixe e coloque na pasta /fonts
FONT_BOLD = "fonts/Anton-Regular.ttf"      # estilo Panini bold
FONT_REGULAR = "fonts/Roboto-Regular.ttf"  # texto normal


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if bold else FONT_REGULAR
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


# ─── REMOÇÃO DE FUNDO ─────────────────────────────────────────────────────────
def remove_background(image_bytes: bytes) -> Image.Image:
    """Remove o fundo da foto usando rembg (gratuito, local)."""
    output = remove(image_bytes)
    return Image.open(io.BytesIO(output)).convert("RGBA")


# ─── COMPOSIÇÃO DA FIGURINHA ──────────────────────────────────────────────────
def compose_figurinha(
    face_img: Image.Image,
    nome: str,
    clube: str,
    peso: str,
    altura: str,
    data_nascimento: str,
    watermark: bool = True,
) -> Image.Image:
    """Compõe a figurinha final sobre o template."""

    # Carrega o template
    if not os.path.exists(TEMPLATE_PATH):
        raise FileNotFoundError(f"Template não encontrado: {TEMPLATE_PATH}")

    template = Image.open(TEMPLATE_PATH).convert("RGBA")
    result = template.copy()

    # 1. Posiciona o rosto
    fc = CONFIG["face"]
    face_resized = face_img.resize((fc["width"], fc["height"]), Image.LANCZOS)

    # Cria máscara circular para o rosto
    mask = Image.new("L", (fc["width"], fc["height"]), 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.ellipse((0, 0, fc["width"], fc["height"]), fill=255)

    face_layer = Image.new("RGBA", result.size, (0, 0, 0, 0))
    face_layer.paste(face_resized, (fc["x"], fc["y"]), mask)
    result = Image.alpha_composite(result, face_layer)

    # 2. Escreve os textos
    draw = ImageDraw.Draw(result)

    # Nome
    t = CONFIG["texts"]["nome"]
    nome_txt = nome.upper() if t["uppercase"] else nome
    font = get_font(t["size"], t["bold"])
    draw.text((t["x"], t["y"]), nome_txt, font=font, fill=t["color"], anchor="mm")

    # Stats (data | altura | peso)
    t = CONFIG["texts"]["stats"]
    stats_txt = f"{data_nascimento} | {altura} m | {peso} kg"
    font = get_font(t["size"], t["bold"])
    draw.text((t["x"], t["y"]), stats_txt, font=font, fill=t["color"], anchor="mm")

    # Clube
    t = CONFIG["texts"]["clube"]
    clube_txt = clube.upper() if t["uppercase"] else clube
    font = get_font(t["size"], t["bold"])
    draw.text((t["x"], t["y"]), clube_txt, font=font, fill=t["color"], anchor="mm")

    # 3. Watermark (só no preview)
    if watermark:
        result = add_watermark(result)

    return result


def add_watermark(img: Image.Image) -> Image.Image:
    """Adiciona watermark diagonal em grade na imagem."""
    wm_cfg = CONFIG["watermark"]
    overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
    draw = ImageDraw.Draw(overlay)
    font = get_font(wm_cfg["size"], bold=True)

    step_x, step_y = 140, 100
    for y in range(-50, img.height + 50, step_y):
        for x in range(-50, img.width + 50, step_x):
            draw.text((x, y), wm_cfg["text"], font=font, fill=wm_cfg["color"])

    # Rotaciona o overlay
    rotated = overlay.rotate(wm_cfg["angle"], expand=False)
    rotated = rotated.crop((0, 0, img.width, img.height))
    return Image.alpha_composite(img.convert("RGBA"), rotated)


def image_to_base64(img: Image.Image, format: str = "PNG") -> str:
    buffer = io.BytesIO()
    img.convert("RGB").save(buffer, format=format, quality=95)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


# ─── ENDPOINTS ────────────────────────────────────────────────────────────────

@app.post("/gerar-figurinha")
async def gerar_figurinha(
    foto: UploadFile = File(...),
    nome: str = Form(...),
    clube: str = Form(...),
    peso: str = Form(...),
    altura: str = Form(...),
    data_nascimento: str = Form(...),
):
    """
    Recebe os dados do quiz e retorna:
    - preview_base64: figurinha COM watermark (para mostrar antes do pagamento)
    - figurinha_id: ID único para recuperar a versão limpa após pagamento
    """
    try:
        # Lê a foto enviada
        foto_bytes = await foto.read()

        # Remove o fundo
        face_img = remove_background(foto_bytes)

        # Gera preview (com watermark)
        preview = compose_figurinha(
            face_img=face_img,
            nome=nome,
            clube=clube,
            peso=peso,
            altura=altura,
            data_nascimento=data_nascimento,
            watermark=True,
        )

        # Gera versão limpa e salva em disco (entregue após pagamento)
        figurinha_id = str(uuid.uuid4())
        os.makedirs("figurinhas_geradas", exist_ok=True)

        clean = compose_figurinha(
            face_img=face_img,
            nome=nome,
            clube=clube,
            peso=peso,
            altura=altura,
            data_nascimento=data_nascimento,
            watermark=False,
        )
        clean.convert("RGB").save(f"figurinhas_geradas/{figurinha_id}.png")

        return JSONResponse({
            "success": True,
            "figurinha_id": figurinha_id,
            "preview_base64": image_to_base64(preview),
        })

    except FileNotFoundError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao gerar figurinha: {str(e)}")


@app.get("/figurinha/{figurinha_id}")
async def get_figurinha(figurinha_id: str):
    """
    Retorna a figurinha LIMPA (sem watermark) após confirmação de pagamento.
    Chame este endpoint só depois de confirmar o pagamento via webhook.
    """
    path = f"figurinhas_geradas/{figurinha_id}.png"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Figurinha não encontrada")

    with open(path, "rb") as f:
        img_base64 = base64.b64encode(f.read()).decode("utf-8")

    return JSONResponse({
        "success": True,
        "figurinha_base64": img_base64,
    })


@app.get("/health")
async def health():
    return {"status": "ok"}
