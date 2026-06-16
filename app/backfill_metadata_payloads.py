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
from src.config import (
    COLLECTION_CHUNKS, COLLECTION_IMAGENES, QDRANT_PATH,
    extraer_entidades_por_reglas,
)


def extraer_metadatos(texto: str) -> dict:
    # Reglas compartidas con el pipeline en vivo (config.REGLAS_ENTIDADES) para
    # que el backfill y la indexación produzcan exactamente la misma metadata.
    return extraer_entidades_por_reglas(texto)


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
