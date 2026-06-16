"""Backfill de metadatos estructurados en Qdrant sin reindexar embeddings.

Actualiza payloads existentes de `histo_chunks` y `histo_imagenes` con campos
derivados por reglas deterministicas: dominios, organos, celulas y temas.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client import models

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))
from src.config import COLLECTION_CHUNKS, COLLECTION_IMAGENES, QDRANT_PATH, normalizar


def extraer_metadatos(texto: str) -> dict:
    texto_norm = normalizar(texto)
    reglas = {
        "tejidos": {
            "musculo liso": ["musculo liso", "musculares lisas", "musculares lisos"],
            "tejido conectivo": ["tejido conectivo", "conectivo colageno", "fibras colagenas"],
            "epitelio seminifero": ["epitelio seminifero"],
            "endotelio": ["endotelio", "endoteliales"],
        },
        "estructuras": {
            "tunica intima": ["tunica intima"],
            "tunica media": ["tunica media"],
            "tunica adventicia": ["tunica adventicia", "adventicia", "tunica externa"],
            "lamina elastica interna": ["lamina elastica interna"],
            "lamina elastica externa": ["lamina elastica externa"],
            "tubulo seminifero": ["tubulo seminifero", "tubulos seminiferos"],
            "intersticio testicular": ["intersticio testicular", "intersticio"],
            "membrana basal": ["membrana basal"],
        },
        "tinciones": {
            "hematoxilina-eosina": ["hematoxilina", "eosina", "h&e", "he"],
        },
        "dominios": {
            "vasos sanguineos": ["arteria", "arterial", "arteriola", "vena", "venula", "vaso sanguineo", "vascular", "tunica intima", "tunica media"],
            "testiculo": ["testiculo", "testicular", "seminifero", "seminiferos", "sertoli", "leydig", "espermatogonia", "espermatide", "peritubular", "mioide"],
        },
        "organos": {
            "arteria muscular": ["arteria muscular"],
            "testiculo": ["testiculo", "testicular"],
            "tubulo seminifero": ["tubulo seminifero", "tubulos seminiferos"],
        },
        "celulas": {
            "celula de sertoli": ["sertoli"],
            "celula de leydig": ["leydig"],
            "espermatogonia": ["espermatogonia"],
            "espermatide": ["espermatide", "espermátide"],
            "celula peritubular": ["peritubular", "mioide"],
            "celula endotelial": ["endotelial", "endoteliales"],
        },
        "temas": {
            "arteria muscular": ["arteria muscular"],
            "capas arteriales": ["tunica intima", "tunica media", "tunica adventicia", "tunica externa"],
            "laminas elasticas": ["lamina elastica interna", "lamina elastica externa"],
            "espermatogenesis": ["espermatogenesis", "espermatogonia", "espermatide"],
            "epitelio seminifero": ["epitelio seminifero", "tubulo seminifero"],
            "intersticio testicular": ["intersticio", "leydig"],
        },
    }

    metadatos = {k: [] for k in reglas}
    for categoria, valores in reglas.items():
        for etiqueta, patrones in valores.items():
            if any(normalizar(patron) in texto_norm for patron in patrones):
                metadatos[categoria].append(etiqueta)
    return metadatos


def actualizar_coleccion(client: QdrantClient, collection: str) -> int:
    offset = None
    actualizados = 0
    while True:
        puntos, offset = client.scroll(
            collection_name=collection,
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        if not puntos:
            break

        for punto in puntos:
            payload = punto.payload or {}
            texto = "\n".join(
                str(payload.get(campo, ""))
                for campo in ("texto", "caption", "texto_pagina", "ocr_text", "etiqueta")
            )
            metadatos = extraer_metadatos(texto)
            if any(metadatos.values()):
                client.set_payload(collection_name=collection, payload=metadatos, points=[punto.id])
                actualizados += 1

        if offset is None:
            break
    return actualizados


def main() -> None:
    url = os.getenv("QDRANT_URL")
    api_key = os.getenv("QDRANT_KEY")
    qdrant_path = QDRANT_PATH

    if url:
        client = QdrantClient(url=url, api_key=api_key or None, timeout=60)
        print(f"Usando Qdrant remoto: {url}")
    else:
        os.makedirs(qdrant_path, exist_ok=True)
        client = QdrantClient(path=qdrant_path, timeout=60)
        print(f"Usando Qdrant local: {qdrant_path}")
    for collection in (COLLECTION_CHUNKS, COLLECTION_IMAGENES):
        for field in ("tejidos", "estructuras", "tinciones", "dominios", "organos", "celulas", "temas"):
            try:
                client.create_payload_index(
                    collection_name=collection,
                    field_name=field,
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
            except Exception:
                pass
    chunks = actualizar_coleccion(client, COLLECTION_CHUNKS)
    imagenes = actualizar_coleccion(client, COLLECTION_IMAGENES)
    print(f"Payloads actualizados: chunks={chunks}, imagenes={imagenes}")


if __name__ == "__main__":
    main()
