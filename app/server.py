"""
Servidor FastAPI para RAG Histología Qdrant — Fullstack A2UI
============================================================
Wrappea AsistenteHistologiaQdrant y expone endpoints REST.
"""

import base64
import os
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv()

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles

from src.assistant import AsistenteHistologiaQdrant
from src.config import COLLECTION_CHUNKS, DIRECTORIO_PDFS

# ── Estado global ────────────────────────────────────────────────────
asistente: Optional[AsistenteHistologiaQdrant] = None
_init_complete = False
_init_error: Optional[str] = None


# ── Modelos Pydantic ─────────────────────────────────────────────────
class ChatRequest(BaseModel):
    query: str
    image_base64: Optional[str] = None
    image_filename: Optional[str] = None


class ChatResponse(BaseModel):
    respuesta: str
    estructura_identificada: Optional[str] = None
    imagenes_recuperadas: list = []
    imagenes_base64: list = []  # Lista de {filename, base64, mime_type}
    trayectoria: list = []
    imagen_activa: Optional[str] = None
    mostrar_imagenes: bool = False


# ── Lifecycle ────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global asistente, _init_complete, _init_error
    print("🚀 Iniciando servidor RAG Histología Qdrant + A2UI...")

    try:
        asistente = AsistenteHistologiaQdrant()
        await asistente.inicializar_componentes()

        print("📚 Leyendo PDFs...")
        asistente.procesar_contenido_base(DIRECTORIO_PDFS)

        print("📋 Extrayendo temario...")
        await asistente.extraer_y_preparar_temario()
        n_temas = len(asistente.extractor_temario.temas) if asistente.extractor_temario else 0
        print(f"   → {n_temas} temas")

        print("💾 Verificando e indexando base de datos Qdrant (si está vacía)...")
        await asistente.indexar_en_qdrant(DIRECTORIO_PDFS, forzar=False)

        _init_complete = True
        print("✅ Servidor listo")
    except Exception as e:
        import traceback
        traceback.print_exc()
        _init_error = str(e)
        print(f"❌ Error inicializando: {e}")

    yield

    # Shutdown
    if asistente:
        await asistente.cerrar()
    print("👋 Servidor apagado")


# ── App FastAPI ──────────────────────────────────────────────────────
app = FastAPI(
    title="RAG Histología Qdrant + A2UI",
    description="Sistema RAG Multimodal de Histología — Fullstack",
    version="5.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Archivos estáticos del cliente
CLIENT_DIR = Path(__file__).parent / "client"

# Directorio de imágenes extraídas (para servir al frontend)
IMAGENES_DIR = Path(__file__).parent / "imagenes_extraidas"


def _check_ready():
    if not _init_complete:
        raise HTTPException(503, detail=_init_error or "Sistema inicializándose...")


def _prune_chat_images(chat_dir: Path, keep: int = 20, protect: Optional[str] = None):
    """Keep only the most recent uploads so imagenes_chat/ doesn't grow unbounded.

    The currently-active image (reused across turns) is never deleted.
    """
    try:
        files = sorted(
            chat_dir.glob("upload_*"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for p in files[keep:]:
            if protect and os.path.abspath(str(p)) == os.path.abspath(protect):
                continue
            try:
                p.unlink()
            except Exception:
                pass
    except Exception:
        pass


def _friendly_error_message(error: Exception) -> str:
    raw = str(error).lower()
    if any(token in raw for token in ["rate limit", "quota", "429", "resource_exhausted", "sin cuota"]):
        return (
            "El asistente está temporalmente ocupado porque se agotó el cupo diario del modelo. "
            "Probá de nuevo en unos minutos o avisá al equipo docente si el problema continúa."
        )
    if any(token in raw for token in ["503", "temporarily", "ocupado", "connection", "timeout"]):
        return (
            "El asistente no pudo completar la respuesta por una demora del servicio. "
            "Probá nuevamente en unos minutos."
        )
    return (
        "No pude completar la respuesta en este momento. "
        "Probá nuevamente o reformulá la pregunta."
    )


# ── Rutas de archivos del frontend ───────────────────────────────────
@app.get("/")
async def root():
    return FileResponse(str(CLIENT_DIR / "index.html"))


@app.get("/app.js")
async def serve_js():
    return FileResponse(str(CLIENT_DIR / "app.js"), media_type="application/javascript")


@app.get("/style.css")
async def serve_css():
    return FileResponse(str(CLIENT_DIR / "style.css"), media_type="text/css")


# ── API: Estado ──────────────────────────────────────────────────────
@app.get("/api/status")
async def get_status():
    if not _init_complete:
        return {
            "ready": False,
            "error": _init_error,
            "diagnostico": {
                "sistema": "Inicializando",
                "qdrant": "No verificado",
                "modelo": "No disponible",
                "cuota_modelo": "No verificada",
            },
        }

    qdrant_ok = False
    try:
        if asistente and asistente.qdrant_store and asistente.qdrant_store.client:
            asistente.qdrant_store.client.count(collection_name=COLLECTION_CHUNKS)
            qdrant_ok = True
    except Exception:
        qdrant_ok = False

    modelo_ok = bool(getattr(asistente, "llm", None))

    return {
        "ready": True,
        "n_temas": len(asistente.extractor_temario.temas) if asistente.extractor_temario else 0,
        "imagen_activa": os.path.basename(asistente.memoria.get_imagen_activa())
            if asistente.memoria and asistente.memoria.get_imagen_activa() else None,
        "turno": asistente.memoria.turno_actual if asistente.memoria else 0,
        "device": asistente.device,
        "diagnostico": {
            "sistema": "Sistema listo",
            "qdrant": "Qdrant conectado" if qdrant_ok else "Qdrant no disponible",
            "modelo": "Modelo disponible" if modelo_ok else "Modelo no disponible",
            "cuota_modelo": "Cuota del modelo: no verificada / limitada",
        },
    }


# ── API: Temario ─────────────────────────────────────────────────────
@app.get("/api/temario")
async def get_temario():
    _check_ready()
    temas = asistente.extractor_temario.temas if asistente.extractor_temario else []
    return {"temas": temas, "total": len(temas)}


# ── API: Chat (texto plano) ─────────────────────────────────────────
@app.post("/api/chat", response_model=ChatResponse)
async def post_chat(req: ChatRequest):
    _check_ready()

    imagen_path = None
    try:
        # Si hay imagen, guardarla en un directorio persistente
        if req.image_base64:
            chat_img_dir = Path(__file__).parent / "imagenes_chat"
            chat_img_dir.mkdir(exist_ok=True)
            
            ext = ".png"
            if req.image_filename:
                _, ext = os.path.splitext(req.image_filename)
                if not ext:
                    ext = ".png"
            
            nombre_archivo = f"upload_{uuid.uuid4().hex[:8]}{ext}"
            imagen_path = str(chat_img_dir / nombre_archivo)
            
            with open(imagen_path, "wb") as f:
                f.write(base64.b64decode(req.image_base64))

            print(f"📷 Imagen guardada para chat: {imagen_path}")

            activa = asistente.memoria.get_imagen_activa() if asistente.memoria else None
            _prune_chat_images(chat_img_dir, keep=20, protect=activa)

        # Ejecutar consulta RAG
        respuesta = await asistente.consultar(
            consulta_texto=req.query,
            imagen_path=imagen_path,
        )

        # Leer resultado directo del asistente (más confiable que el archivo JSON)
        resultado_directo = getattr(asistente, '_ultimo_resultado', {})
        estructura = resultado_directo.get("estructura_identificada")

        # Imágenes de la BD para mostrar al usuario
        imagenes_para_mostrar = resultado_directo.get("imagenes_para_mostrar", [])
        imagenes_response = []
        mostrar_imgs = resultado_directo.get("mostrar_imagenes", False)
        
        if mostrar_imgs and imagenes_para_mostrar:
            for img_info in imagenes_para_mostrar:
                nombre = img_info.get("nombre_archivo", "")
                if nombre:
                    imagenes_response.append({
                        "url": f"/imagenes_extraidas/{nombre}",
                        "caption": img_info.get("caption", ""),
                        "etiqueta": img_info.get("etiqueta", ""),
                        "nombre_archivo": nombre,
                        "similitud": img_info.get("similitud_semantica", 0),
                    })
            print(f"🖼️ {len(imagenes_response)} imágenes para mostrar al usuario")

        trayectoria = resultado_directo.get("trayectoria", [])

        img_activa = None
        if asistente.memoria and asistente.memoria.get_imagen_activa():
            img_activa = os.path.basename(asistente.memoria.get_imagen_activa())

        return ChatResponse(
            respuesta=respuesta,
            estructura_identificada=estructura,
            imagenes_recuperadas=imagenes_response,
            imagenes_base64=[],
            trayectoria=trayectoria,
            imagen_activa=img_activa,
            mostrar_imagenes=mostrar_imgs and len(imagenes_response) > 0,
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(503, detail=_friendly_error_message(e))
    finally:
        pass



# ── API: Limpiar imagen ──────────────────────────────────────────────
@app.post("/api/imagen/limpiar")
async def limpiar_imagen():
    _check_ready()
    if asistente.memoria:
        asistente.memoria.set_imagen(None)
    return {"ok": True, "mensaje": "Imagen activa eliminada"}


# ── Ruta estática: imágenes extraídas ────────────────────────────────
IMAGENES_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/imagenes_extraidas", StaticFiles(directory=str(IMAGENES_DIR)), name="imagenes_extraidas")


# ── Main ─────────────────────────────────────────────────────────────
def main():
    port = int(os.getenv("PORT", "10007"))
    print(f"🌐 Servidor en http://localhost:{port}")
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
