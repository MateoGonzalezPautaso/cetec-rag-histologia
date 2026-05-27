"""
Global constants, paths, and utility functions.
"""

import os
import unicodedata
from typing import Optional


# ── Thresholds ────────────────────────────────────────────────────────────────
SIMILARITY_THRESHOLD = 0.70
SIMILAR_IMG_THRESHOLD = 0.85

# ── Embedding dimensions ──────────────────────────────────────────────────────
DIM_TEXTO = 384
DIM_IMG_UNI = 1024
DIM_IMG_PLIP = 512

# ── Directories ───────────────────────────────────────────────────────────────
_BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIRECTORIO_IMAGENES = os.path.join(_BASE, "imagenes_extraidas")
DIRECTORIO_PDFS = os.path.join(_BASE, "pdf")

# ── Qdrant collections ────────────────────────────────────────────────────────
COLLECTION_CHUNKS = "histo_chunks"
COLLECTION_IMAGENES = "histo_imagenes"

INDEX_TEXTO = "histo_text"
INDEX_UNI = "histo_img_uni"
INDEX_PLIP = "histo_img_plip"

NEO4J_GRAPH_DEPTH = 2

# ── Histology domain knowledge ────────────────────────────────────────────────
FEATURES_DISCRIMINATORIAS = [
    "presencia/ausencia de lumen central",
    "estratificación celular (capas concéntricas vs difusa)",
    "tipo de queratinización (parakeratosis, ortoqueratosis, ninguna)",
    "aspecto del núcleo (picnótico, fantasma, ausente, vesicular)",
    "células fantasma (sí/no)",
    "material amorfo central (sí/no y aspecto)",
    "patrón de tinción H&E (eosinofilia, basofilia)",
    "tamaño estimado de la estructura",
    "tejido circundante (estroma, epitelio, piel, otro)",
    "reacción inflamatoria perilesional (sí/no, tipo)",
    "tipo de matriz extracelular: homogénea/vítrea (cartílago) vs calcificada con canalículos (hueso)",
    "células en lagunas: condrocitos (redondeados, en nidos/isógenos) vs osteocitos (estrellados, aislados con prolongaciones)",
    "presencia de pericondrio (cartílago) vs periostio (hueso)",
    "sistemas de Havers / osteonas (exclusivo de hueso compacto)",
    "nidos isógenos / grupos celulares (exclusivo de cartílago)",
    "tinción de la matriz: basófila-azulada (cartílago hialino) vs eosinófila-rosada (hueso)",
    "fibras visibles en la matriz: ausentes (hialino), elásticas (elástico), colágenas gruesas (fibroso)",
    "vascularización: avascular (cartílago, excepto fibrocartílago) vs muy vascularizado (hueso)",
]

ANCLAS_SEMANTICAS_HISTOLOGIA = [
    "histología tejido celular microscopía",
    "tipos de tejido epitelial conectivo muscular nervioso",
    "coloración hematoxilina eosina H&E tinción histológica",
    "estructuras celulares núcleo citoplasma membrana",
    "diagnóstico diferencial patología biopsia",
    "glándulas epitelio estratificado cilíndrico simple",
    "identificar tejido muestra microscópica",
    "¿qué tipo de tejido es este?",
    "¿cuál es la estructura observada en la imagen?",
    "clasificar célula estructura histológica",
    "tumor quiste folículo cuerpo lúteo albicans",
    "corte histológico preparación muestra lámina",
    "tejido epitelial simple cilíndrico estratificado pseudoestratificado",
    "tejido conectivo laxo denso adiposo cartilaginoso óseo",
    "tejido muscular liso estriado cardíaco esquelético",
    "tejido nervioso neurona glía axón dendrita",
]


# ── Utilities ─────────────────────────────────────────────────────────────────

def _safe(value, default: str = "") -> str:
    return value if isinstance(value, str) and value else default


def normalizar(texto: str) -> str:
    texto = str(texto or "").lower()
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )
