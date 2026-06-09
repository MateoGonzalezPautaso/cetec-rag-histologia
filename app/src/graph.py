"""
LangGraph state definition for the RAG pipeline.
"""

import operator
from typing import Annotated, Any, Dict, List, Optional

from typing_extensions import TypedDict


class AgentState(TypedDict):
    messages:                    Annotated[list, operator.add]
    consulta_texto:              str
    imagen_path:                 Optional[str]
    imagen_embedding_uni:        Optional[List[float]]
    imagen_embedding_plip:       Optional[List[float]]
    texto_embedding:             Optional[List[float]]
    contexto_memoria:            str
    contenido_base:              str
    terminos_busqueda:           str
    entidades_consulta:          Dict[str, List[str]]
    consulta_busqueda_texto:     str
    consulta_busqueda_visual:    str
    resultados_busqueda:         List[Dict[str, Any]]
    resultados_validos:          List[Dict[str, Any]]
    contexto_documentos:         str
    respuesta_final:             str
    trayectoria:                 List[Dict[str, Any]]
    user_id:                     str
    tiempo_inicio:               float
    analisis_visual:             Optional[str]
    tiene_imagen:                bool
    imagen_es_nueva:             bool
    contexto_suficiente:         bool
    temario:                     List[str]
    tema_valido:                 bool
    tema_encontrado:             Optional[str]
    imagenes_recuperadas:        List[str]
    imagenes_texto_map:          Dict[str, str]
    analisis_comparativo:        Optional[str]
    estructura_identificada:     Optional[str]
    similitud_semantica_dominio: float
    mostrar_imagenes:            bool
    imagenes_para_mostrar:       List[Dict[str, str]]
    historial_conversacional:    str
