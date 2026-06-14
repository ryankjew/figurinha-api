from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import io
import base64
import uuid
import os
from PIL import Image, ImageDraw, ImageFont
import requests

app = FastAPI(title="Figurinha Copa 2026 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Troque pelo dominio do seu Lovable em producao
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── COORDENADAS CALIBRADAS (template 1852x2457px) ────────────────────────────
CONFIG = {
    "template_size": (1852, 2457),

    "face": {
        "x": 382,
        "y": 354,
        "width": 769,
        "height": 770,
    },

    "texts": {
        "nome": {
            "x": 771,
            "y": 2134,
            "size": 95,
            "color": (255, 255, 255),
            "bold": True,
            "uppercase": True,
        },
        "stats": {
            "x": 771,
            "y": 2234,
            "size": 65,
            "color": (255, 255, 255),
            "bold": False,
            "uppercase": False,
        },
        "clube": {
            "x": 771,
            "y": 2364,
            "size": 65,
            "color": (255, 255, 255),
            "bold": True,
            "uppercase": True,
        },
    },

    "watermark": {
        "text": "PREVIEW",
        "color": (255, 255, 255, 70),
        "size": 160,
        "angle": 35,
    },
}

FONT_BOLD    = "fonts/Anton-Regular.ttf"
FONT_REGULAR = "fonts/Roboto-Regular.ttf"


def get_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_BOLD if bold else FONT_REGULAR
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def remove_background(image_bytes: bytes) -> Image.Image:
    output = remove(image_bytes)
    return Image.open(io.BytesIO(output)).convert("RGBA")


def compose_figurinha(
    face_img: Image.Image,
    nome: str,
    clube: str,
    peso: str,
    altura: str,
    data_nascimento: str,
    watermark: bool = True,
) -> Image.Image:

    if not os.path.exists("template.png"):
        raise FileNotFoundError("template.png nao encontrado na raiz do projeto")

    template = Image.open("template.png").convert("RGBA")
    result   = template.copy()

    # 1. Cola o rosto no placeholder
    fc = CONFIG["face"]
    face_resized = face_img.resize((fc["width"], fc["height"]), Image.LANCZOS)

    # Mascara retangular com cantos arredondados
    mask = Image.new("L", (fc["width"], fc["height"]), 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.rounded_rectangle(
        [0, 0, fc["width"], fc["height"]],
        radius=60,
        fill=255
    )

    face_layer = Image.new("RGBA", result.size, (0, 0, 0, 0))
    face_layer.paste(face_resized, (fc["x"], fc["y"]), mask)
    result = Image.alpha_composite(result, face_layer)

    # 2. Escreve os textos
    draw = ImageDraw.Draw(result)

    # Nome
    t = CONFIG["texts"]["nome"]
    txt = nome.upper() if t["uppercase"] else nome
    draw.text((t["x"], t["y"]), txt,
              font=get_font(t["size"], t["bold"]),
              fill=t["color"], anchor="mm")

    # Stats: data | altura m | peso kg
    t = CONFIG["texts"]["stats"]
    stats = f"{data_nascimento} | {altura}m | {peso}kg"
    draw.text((t["x"], t["y"]), stats,
              font=get_font(t["size"], t["bold"]),
              fill=t["color"], anchor="mm")

    # Clube
    t = CONFIG["texts"]["clube"]
    txt = clube.upper() if t["uppercase"] else clube
    draw.text((t["x"], t["y"]), txt,
              font=get_font(t["size"], t["bold"]),
              fill=t["color"], anchor="mm")

    # 3. Watermark
    if watermark:
        result = add_watermark(result)

    return result


def add_watermark(img: Image.Image) -> Image.Image:
    wm = CONFIG["watermark"]
    overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
    draw    = ImageDraw.Draw(overlay)
    font    = get_font(wm["size"], bold=True)

    step_x, step_y = 420, 280
    for y in range(-100, img.height + 100, step_y):
        for x in range(-100, img.width + 100, step_x):
            draw.text((x, y), wm["text"], font=font, fill=wm["color"])

    rotated = overlay.rotate(wm["angle"], expand=False)
    rotated = rotated.crop((0, 0, img.width, img.height))
    return Image.alpha_composite(img.convert("RGBA"), rotated)


def image_to_base64(img: Image.Image) -> str:
    buffer = io.BytesIO()
    img.convert("RGB").save(buffer, format="PNG", quality=95)
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
    try:
        foto_bytes = await foto.read()
        face_img   = remove_background(foto_bytes)

        # Preview com watermark (para mostrar antes do pagamento)
        preview = compose_figurinha(
            face_img, nome, clube, peso, altura, data_nascimento,
            watermark=True
        )

        # Versao limpa salva em disco (entregue apos pagamento)
        figurinha_id = str(uuid.uuid4())
        os.makedirs("figurinhas_geradas", exist_ok=True)

        clean = compose_figurinha(
            face_img, nome, clube, peso, altura, data_nascimento,
            watermark=False
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
        raise HTTPException(status_code=500, detail=f"Erro: {str(e)}")


@app.get("/figurinha/{figurinha_id}")
async def get_figurinha(figurinha_id: str):
    path = f"figurinhas_geradas/{figurinha_id}.png"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Figurinha nao encontrada")
    with open(path, "rb") as f:
        img_b64 = base64.b64encode(f.read()).decode("utf-8")
    return JSONResponse({"success": True, "figurinha_base64": img_b64})


@app.get("/health")
async def health():
    return {"status": "ok"}
