"""
Conversation memory with image persistence across turns.
Stores summaries in a local Qdrant instance every 5 interactions.
"""

import os
import uuid
from typing import Optional

from langchain_core.messages import HumanMessage, SystemMessage
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams

from .config import DIM_IMG_PLIP, DIM_IMG_UNI, DIM_TEXTO
from .llm import embed_query_con_reintento, invoke_con_reintento_sync


class SemanticMemory:
    """
    Tracks conversation history and the currently active image.
    The image persists between turns until the user explicitly clears it.
    Summaries are persisted in a local Qdrant collection every 5 turns.
    """

    def __init__(self, llm, embeddings=None, uni=None, plip=None, max_entries: int = 10):
        self.llm = llm
        self.embeddings = embeddings
        self.uni = uni
        self.plip = plip
        self.max_entries = max_entries

        self.conversations: list = []
        self.summary: str = ""
        self.direct_history: str = ""

        self.imagen_activa_path: Optional[str] = None
        self.imagen_turno_subida: int = 0
        self.analisis_visual_activo: Optional[str] = None
        self.turno_actual: int = 0

        self._collection = "memoria_histo"
        _qdrant_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "qdrant_memoria")
        self._qdrant = QdrantClient(path=_qdrant_dir)
        self._ensure_collection()

    def _ensure_collection(self):
        try:
            info = self._qdrant.get_collection(self._collection)
            config = info.config.params.vectors
            dims_actual = 0
            if isinstance(config, dict) and "texto" in config:
                dims_actual = config["texto"].size
            if dims_actual != DIM_TEXTO:
                print(f"   ⚠️ Dimensión Qdrant incorrecta ({dims_actual} != {DIM_TEXTO}). Recreando...")
                self._qdrant.delete_collection(self._collection)
                raise Exception("Recreate")
        except Exception:
            print(f"   🗂️ Configurando colección Qdrant '{self._collection}'...")
            self._qdrant.create_collection(
                collection_name=self._collection,
                vectors_config={
                    "texto": VectorParams(size=DIM_TEXTO, distance=Distance.COSINE),
                    "uni": VectorParams(size=DIM_IMG_UNI, distance=Distance.COSINE),
                    "plip": VectorParams(size=DIM_IMG_PLIP, distance=Distance.COSINE),
                },
            )

    # ── Image persistence ─────────────────────────────────────────────────────

    def set_imagen(self, path: Optional[str], analisis_visual: Optional[str] = None):
        if path and os.path.exists(path):
            self.imagen_activa_path = path
            self.imagen_turno_subida = self.turno_actual
            self.analisis_visual_activo = analisis_visual
            print(f"   📌 Imagen activa registrada (turno {self.turno_actual}): {path}")
        elif path is None:
            self.imagen_activa_path = None
            self.analisis_visual_activo = None
            print("   🗑️  Imagen activa limpiada")

    def get_imagen_activa(self) -> Optional[str]:
        if self.imagen_activa_path and os.path.exists(self.imagen_activa_path):
            return self.imagen_activa_path
        return None

    def tiene_imagen_previa(self) -> bool:
        return self.get_imagen_activa() is not None

    # ── Conversation history ──────────────────────────────────────────────────

    def add_interaction(self, query: str, response: str):
        self.turno_actual += 1
        self.conversations.append({
            "query": query, "response": response,
            "turno": self.turno_actual, "imagen": self.imagen_activa_path,
        })
        if len(self.conversations) > self.max_entries:
            self.conversations.pop(0)

        self.direct_history += f"\nUsuario: {query}\nAsistente: {response}\n"
        if len(self.conversations) > 3:
            recent = self.conversations[-3:]
            self.direct_history = ""
            for conv in recent:
                img_nota = (
                    f" [con imagen: {os.path.basename(conv['imagen'])}]"
                    if conv.get("imagen") else ""
                )
                self.direct_history += (
                    f"\nUsuario{img_nota}: {conv['query']}\n"
                    f"Asistente: {conv['response']}\n"
                )

        self._update_summary()

        if self.turno_actual % 5 == 0 and self.conversations and self.embeddings:
            self._guardar_en_qdrant()

    def _update_summary(self):
        try:
            if len(self.conversations) > 6:
                resp = invoke_con_reintento_sync(self.llm, [
                    SystemMessage(content="Resume estas consultas de histología manteniendo términos técnicos:"),
                    HumanMessage(content=self.direct_history),
                ])
                self.summary = f"Resumen: {resp.content}\n\nRecientes:{self.direct_history}"
            else:
                self.summary = f"Recientes:{self.direct_history}"
        except Exception:
            self.summary = f"Recientes:{self.direct_history}"

    def _guardar_en_qdrant(self):
        print("   🧠 Guardando resumen en memoria (Qdrant)...")
        try:
            resp = invoke_con_reintento_sync(self.llm, [
                SystemMessage(content=(
                    "Genera un resumen detallado y técnico del siguiente historial "
                    "de conversación sobre histología, destacando las entidades "
                    "mencionadas y las conclusiones."
                )),
                HumanMessage(content=self.direct_history),
            ])
            resumen = resp.content

            emb_texto = embed_query_con_reintento(self.embeddings, resumen)
            emb_uni = [0.0] * DIM_IMG_UNI
            emb_plip = [0.0] * DIM_IMG_PLIP

            if self.imagen_activa_path and os.path.exists(self.imagen_activa_path):
                if self.uni:
                    emb_uni = self.uni.embed_image(self.imagen_activa_path, preprocess=True).tolist()
                if self.plip:
                    emb_plip = self.plip.embed_image(self.imagen_activa_path, preprocess=True).tolist()

            self._qdrant.upsert(
                collection_name=self._collection,
                points=[PointStruct(
                    id=str(uuid.uuid4()),
                    vector={"texto": emb_texto, "uni": emb_uni, "plip": emb_plip},
                    payload={
                        "resumen": resumen,
                        "turno_fin": self.turno_actual,
                        "tiene_imagen": self.imagen_activa_path is not None,
                        "imagen_path": self.imagen_activa_path,
                    },
                )],
            )
            print("   ✅ Resumen guardado en Qdrant (memoria_histo)")
        except Exception as e:
            print(f"   ⚠️ Error guardando memoria en Qdrant: {e}")

    # ── Context retrieval ─────────────────────────────────────────────────────

    def get_context(self, query: str = "") -> str:
        ctx = self.summary.strip() or "No hay consultas previas."

        if query and self.embeddings:
            try:
                emb_query = embed_query_con_reintento(self.embeddings, query)
                results = self._qdrant.query_points(
                    collection_name=self._collection,
                    query=emb_query, using="texto", limit=2,
                ).points
                memorias = [r.payload["resumen"] for r in results if r.score > 0.4]
                if memorias:
                    ctx += "\n\n[Memorias históricas recuperadas:]\n" + "\n- ".join(memorias)
            except Exception as e:
                print(f"   ⚠️ Error recuperando memoria Qdrant: {e}")

        if self.imagen_activa_path:
            ctx += f"\n\n[Imagen activa en el chat: {os.path.basename(self.imagen_activa_path)}]"
        return ctx

    def get_history_for_prompt(self, max_turns: int = 5) -> str:
        recent = self.conversations[-max_turns:]
        if not recent:
            return ""
        lines = []
        for conv in recent:
            lines.append(f"Usuario: {conv['query']}")
            resp_truncada = conv["response"][:200] + ("..." if len(conv["response"]) > 200 else "")
            lines.append(f"Asistente: {resp_truncada}")
        return "\n".join(lines)
