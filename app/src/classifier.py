"""
Domain and intent classifiers.

ClasificadorSemantico: decides if a query belongs to the histology domain.
"""

import json
import re
from typing import Any, Dict, List, Optional

import numpy as np
from langchain_core.messages import HumanMessage, SystemMessage

from .config import ANCLAS_SEMANTICAS_HISTOLOGIA
from .llm import embed_documents_con_reintento, embed_query_con_reintento, invoke_con_reintento


class ClasificadorSemantico:
    """
    Two-stage domain classifier:
    1. Cosine similarity against syllabus embeddings (fast, no LLM call).
    2. LLM arbiter when similarity is below threshold (slower, authoritative).

    The syllabus embeddings are computed lazily and cached. They are invalidated
    whenever the syllabus is updated via the `temario` property setter.
    """

    UMBRAL_SIMILITUD = 0.45
    UMBRAL_LLM = 0.49

    def __init__(self, llm, embeddings, device: str, temario: List[str]):
        self.llm = llm
        self.embeddings = embeddings
        self.device = device
        self._temario: List[str] = temario
        self._anclas_emb: Optional[np.ndarray] = None
        self._temario_emb: Optional[np.ndarray] = None

    @property
    def temario(self) -> List[str]:
        return self._temario

    @temario.setter
    def temario(self, value: List[str]):
        self._temario = value
        self._temario_emb = None
        print(f"   🔄 Ontología actualizada ({len(value)} temas) — cache invalidado")

    def _embed(self, textos: List[str]) -> np.ndarray:
        return np.array(embed_documents_con_reintento(self.embeddings, textos))

    def _get_anclas_emb(self) -> np.ndarray:
        if self._anclas_emb is None:
            print("   🔄 Precalculando embeddings de anclas semánticas (fallback)...")
            self._anclas_emb = self._embed(ANCLAS_SEMANTICAS_HISTOLOGIA)
        return self._anclas_emb

    def _get_temario_emb(self) -> Optional[np.ndarray]:
        if not self._temario:
            return None
        if self._temario_emb is None:
            print(f"   🔄 Precalculando embeddings de ontología ({len(self._temario)} temas)...")
            self._temario_emb = self._embed(self._temario)
        return self._temario_emb

    def similitud_con_dominio(self, consulta: str) -> float:
        try:
            q_emb = np.array(embed_query_con_reintento(self.embeddings, consulta))
            temario_emb = self._get_temario_emb()
            if temario_emb is not None and len(temario_emb) > 0:
                sims = (q_emb @ temario_emb.T).flatten()
                return float(np.max(sims))
            a_emb = self._get_anclas_emb()
            sims = (q_emb @ a_emb.T).flatten()
            return float(np.max(sims))
        except Exception as e:
            print(f"   ⚠️ Error similitud semántica: {e}")
            return 0.0

    async def clasificar(
        self,
        consulta: str,
        analisis_visual: Optional[str] = None,
        imagen_activa: bool = False,
        temario_muestra: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        sim = self.similitud_con_dominio(consulta)
        print(f"   📐 Similitud semántica con dominio: {sim:.4f}")

        umbral_efectivo = self.UMBRAL_SIMILITUD * (0.6 if imagen_activa else 1.0)

        if sim >= umbral_efectivo:
            return {
                "valido": True, "tema_encontrado": None,
                "motivo": f"Similitud {sim:.3f} ≥ umbral {umbral_efectivo:.3f}",
                "similitud_dominio": sim, "metodo": "semantico_embeddings",
            }

        # Stage 2: LLM arbiter
        muestra = (temario_muestra or self.temario)[:60]
        temario_txt = "\n".join(f"- {t}" for t in muestra)

        context_extra = ""
        if analisis_visual:
            context_extra = f"\n\nANÁLISIS DE IMAGEN DISPONIBLE:\n{analisis_visual[:600]}"
        if imagen_activa:
            context_extra += "\n\n[El usuario tiene una imagen histológica activa en el chat]"

        system = f"""Eres un clasificador de intención para un sistema RAG de histología médica.

Tu tarea: determinar si la consulta es una pregunta relacionada con histología,
patología, anatomía microscópica o morfología celular/tisular.

IMPORTANTE:
- "¿de qué tipo de tejido se trata?" SÍ es histológica.
- "¿qué ves en la imagen?" en contexto histológico SÍ es histológica.
- No es necesario que mencione palabras técnicas si el contexto lo indica.
- Si hay imagen histológica activa, dar beneficio de la duda.

TEMARIO DISPONIBLE (muestra):
{temario_txt}
{context_extra}

Responde ÚNICAMENTE en JSON válido (sin backticks):
{{"valido": true/false, "tema_encontrado": "tema más cercano o null", "confianza": 0.0-1.0, "motivo": "explicación breve"}}"""

        try:
            resp = await invoke_con_reintento(self.llm, [
                SystemMessage(content=system),
                HumanMessage(content=f"CONSULTA: {consulta}"),
            ])
            texto = re.sub(r"```json\s*|\s*```", "", resp.content.strip())
            data = json.loads(texto)
            valido = bool(data.get("valido", True))

            if not valido and imagen_activa:
                valido = True
                data["motivo"] = data.get("motivo", "") + " [aceptado por imagen activa]"

            return {
                "valido": valido,
                "tema_encontrado": data.get("tema_encontrado"),
                "motivo": data.get("motivo", ""),
                "similitud_dominio": sim,
                "metodo": "llm" if sim < umbral_efectivo * 0.49 else "combinado",
            }
        except Exception as e:
            print(f"   ⚠️ Error clasificador LLM: {e}")
            return {
                "valido": imagen_activa or sim > 0.10,
                "tema_encontrado": None,
                "motivo": f"Fallback: {e}",
                "similitud_dominio": sim,
                "metodo": "fallback",
            }
