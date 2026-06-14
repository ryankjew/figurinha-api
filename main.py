from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import io
import base64
import uuid
import os
import requests
from PIL import Image, ImageDraw, ImageFont

app = FastAPI(title="Figurinha Copa 2026 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

REMOVE_BG_KEY = os.getenv("REMOVE_BG_API_KEY", "")

CONFIG = {
    "face": {"x": 386, "y": 428, "width": 768, "height": 824},
    "texts": {
        "nome":  {"x": 926, "y": 2100, "size": 90,  "color": (255,255,255), "bold": True,  "uppercase": True},
        "stats": {"x": 926, "y": 2210, "size": 58,  "color": (255,255,255), "bold": False, "uppercase": False},
        "clube": {"x": 926, "y": 2362, "size": 58,  "color": (255,255,255), "bold": True,  "uppercase": True},
    },
    "watermark": {"text": "PREVIEW", "color": (255,255,255,70), "size": 160, "angle": 35},
}

FONT_BOLD    = "fonts/Anton-Regular.ttf"
FONT_REGULAR = "fonts/Roboto-Regular.ttf"

def get_font(size, bold=False):
    try:
        return ImageFont.truetype(FONT_BOLD if bold else FONT_REGULAR, size)
    except:
        return ImageFont.load_default()

def remove_background(image_bytes):
    if not REMOVE_BG_KEY:
        raise HTTPException(status_code=500, detail="REMOVE_BG_API_KEY nao configurada")
    resp = requests.post(
        "https://api.remove.bg/v1.0/removebg",
        files={"image_file": ("foto.jpg", image_bytes)},
        data={"size": "auto"},
        headers={"X-Api-Key": REMOVE_BG_KEY},
    )
    if resp.status_code != 200:
        raise HTTPException(status_code=500, detail=f"remove.bg erro: {resp.text}")
    return Image.open(io.BytesIO(resp.content)).convert("RGBA")

def compose_figurinha(face_img, nome, clube, peso, altura, data_nascimento, watermark=True):
    if not os.path.exists("template.png"):
        raise FileNotFoundError("template.png nao encontrado")
    result = Image.open("template.png").convert("RGBA")
    fc = CONFIG["face"]
    face_resized = face_img.resize((fc["width"], fc["height"]), Image.LANCZOS)
    mask = Image.new("L", (fc["width"], fc["height"]), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, fc["width"], fc["height"]], radius=50, fill=255)
    layer = Image.new("RGBA", result.size, (0,0,0,0))
    layer.paste(face_resized, (fc["x"], fc["y"]), mask)
    result = Image.alpha_composite(result, layer)
    draw = ImageDraw.Draw(result)
    t = CONFIG["texts"]["nome"]
    draw.text((t["x"], t["y"]), nome.upper(), font=get_font(t["size"], t["bold"]), fill=t["color"], anchor="mm")
    t = CONFIG["texts"]["stats"]
    draw.text((t["x"], t["y"]), f"{data_nascimento} | {altura}m | {peso}kg", font=get_font(t["size"], t["bold"]), fill=t["color"], anchor="mm")
    t = CONFIG["texts"]["clube"]
    draw.text((t["x"], t["y"]), clube.upper(), font=get_font(t["size"], t["bold"]), fill=t["color"], anchor="mm")
    if watermark:
        wm = CONFIG["watermark"]
        ov = Image.new("RGBA", result.size, (255,255,255,0))
        d = ImageDraw.Draw(ov)
        f = get_font(wm["size"], bold=True)
        for y in range(-100, result.height+100, 280):
            for x in range(-100, result.width+100, 420):
                d.text((x,y), wm["text"], font=f, fill=wm["color"])
        rot = ov.rotate(wm["angle"], expand=False).crop((0,0,result.width,result.height))
        result = Image.alpha_composite(result.convert("RGBA"), rot)
    return result

def to_b64(img):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", quality=95)
    return base64.b64encode(buf.getvalue()).decode()

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
        face = remove_background(await foto.read())
        preview = compose_figurinha(face, nome, clube, peso, altura, data_nascimento, watermark=True)
        fid = str(uuid.uuid4())
        os.makedirs("figurinhas_geradas", exist_ok=True)
        compose_figurinha(face, nome, clube, peso, altura, data_nascimento, watermark=False).convert("RGB").save(f"figurinhas_geradas/{fid}.png")
        return JSONResponse({"success": True, "figurinha_id": fid, "preview_base64": to_b64(preview)})
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/figurinha/{fid}")
async def get_figurinha(fid: str):
    path = f"figurinhas_geradas/{fid}.png"
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Nao encontrada")
    return JSONResponse({"success": True, "figurinha_base64": base64.b64encode(open(path,"rb").read()).decode()})

@app.get("/health")
async def health():
    return {"status": "ok"}
