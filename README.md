# RAG Histología — v5.0

Sistema RAG multimodal para histología médica. Permite hacer preguntas sobre un manual en PDF y obtener respuestas fundamentadas en el texto e imágenes del documento. Soporta subir imágenes histológicas para análisis comparativo.

**Stack:** FastAPI · LangGraph · Qdrant · Groq (Llama-4-Scout) · MiniLM · UNI/PLIP · frontend web

---

## Inicio rápido

```bash
# 1. Copiar y completar el archivo de configuración
cp ../.env.example .env
# Editar .env con tus claves (ver sección Configuración)

# 2. Poner los PDFs del manual en pdf/
mkdir -p pdf
# cp tus_manuales.pdf pdf/

# 3. Ejecutar el script de inicio
./start.sh
```

El script instala dependencias, inicia el servidor y abre el navegador automáticamente en `http://localhost:10007`.

---

## Requisitos previos

| Herramienta | Para qué | Cómo instalar |
|---|---|---|
| Python 3.10+ | Ejecutar el backend | `python3 --version` |
| [uv](https://docs.astral.sh/uv/) | Gestor de paquetes Python | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| Tesseract OCR | Extraer texto de imágenes en PDFs | `sudo apt install tesseract-ocr tesseract-ocr-spa` |
| Poppler | Renderizar PDFs como imágenes | `sudo apt install poppler-utils` |

---

## Configuración

Copiar `.env.example` a `.env` y completar:

```env
# LLM principal (REQUERIDO)
GROQ_API_KEY=gsk_...

# Base vectorial Qdrant Cloud (REQUERIDO)
# Crear cluster gratis en https://cloud.qdrant.io/
QDRANT_URL=https://tu-cluster.region.gcp.cloud.qdrant.io:6333
QDRANT_KEY=tu-api-key-de-qdrant

# Modelos de visión UNI y PLIP (REQUERIDO)
# Requiere aceptar los términos en https://huggingface.co/MahmoodLab/UNI
HF_TOKEN=hf_...

# Observabilidad LangSmith (OPCIONAL)
LANGSMITH_API_KEY=ls__...
LANGSMITH_PROJECT=rag-histologia
```

---

## Agregar PDFs

Colocar los archivos PDF en la carpeta `pdf/`. Al iniciar, el servidor:

1. Lee el texto de los PDFs y lo divide en chunks.
2. Extrae las imágenes de cada página.
3. Genera embeddings de texto (MiniLM), visuales (UNI, PLIP) e indexa todo en Qdrant.
4. Extrae el temario automáticamente del contenido.

El indexado solo corre si Qdrant está vacío. Para forzar una reindexación: borrar las colecciones en el panel de Qdrant Cloud y reiniciar.

---

## Ejecutar manualmente

```bash
# Instalar dependencias
uv sync

# Modo desarrollo (recarga automática)
uv run uvicorn server:app --reload --host 0.0.0.0 --port 10007

# Modo producción
uv run python server.py
```

El servidor tarda ~1-3 minutos en arrancar la primera vez porque carga los modelos de visión (UNI, PLIP) desde HuggingFace.

Verificar que esté listo:
```bash
curl http://localhost:10007/api/status
# → {"ready": true, ...}
```

---

## Estructura del proyecto

```
app/
├── server.py              # FastAPI: endpoints REST + sirviendo el frontend
├── pyproject.toml         # Dependencias Python (gestor: uv)
├── start.sh               # Script de inicio con checks automáticos
├── .env                   # Claves privadas (no commitear)
│
├── src/                   # Módulos del backend
│   ├── assistant.py       # Orquestador principal: grafo LangGraph + todos los nodos
│   ├── graph.py           # AgentState: estado compartido entre nodos
│   ├── config.py          # Constantes, rutas, anclas semánticas
│   ├── llm.py             # Wrappers de LLM con reintentos y manejo de cuota
│   ├── embeddings.py      # Wrappers PLIP y UNI para embeddings de imagen
│   ├── qdrant_store.py    # Cliente Qdrant: esquema, upsert y búsqueda híbrida
│   ├── memory.py          # Memoria semántica: historial + imagen activa por sesión
│   ├── classifier.py      # Clasificador de dominio histológico (embeddings + LLM)
│   └── extractors.py      # Extractor de imágenes PDF, temario y entidades
│
├── client/                # Frontend web
│   ├── index.html
│   ├── app.js
│   └── style.css
│
├── pdf/                   # PDFs del manual (no en git, agregar manualmente)
├── imagenes_extraidas/    # Imágenes extraídas de los PDFs (generado automáticamente)
├── imagenes_chat/         # Imágenes subidas por usuarios (generado automáticamente)
│
├── evaluar_ragas.py       # Evaluación RAGAS del pipeline
├── eval_reliability.py    # Smoke test de confiabilidad
└── eval_set_basico.json   # Conjunto de preguntas de evaluación
```

---

## Cómo funciona

Cada consulta pasa por un grafo de nodos LangGraph:

```
inicializar → procesar_imagen? → clasificar → generar_consulta
    → buscar_qdrant → filtrar_contexto → analisis_comparativo?
    → generar_respuesta → finalizar
```

1. **inicializar** — carga estado y memoria conversacional.
2. **procesar_imagen** — si hay imagen nueva, genera embeddings UNI y PLIP; si no hay imagen nueva pero había una en el turno anterior, la reutiliza.
3. **clasificar** — verifica que la consulta sea sobre histología usando similitud semántica y, si está cerca del umbral, un árbitro LLM.
4. **generar_consulta** — reformula la pregunta para mejorar el retrieval, extrae entidades (tejidos, tinciones, células, etc.).
5. **buscar_qdrant** — búsqueda híbrida: texto semántico + entidades + keyword + captions de imagen + embeddings visuales.
6. **filtrar_contexto** — descarta resultados por debajo del umbral de similitud y limita a 6 bloques de contexto.
7. **analisis_comparativo** — si hay imagen del usuario, la compara contra imágenes del manual.
8. **generar_respuesta** — sintetiza la respuesta con el LLM usando el contexto recuperado.
9. **finalizar** — guarda trayectoria, actualiza memoria semántica.

---

## Evaluación

```bash
# Smoke test (rápido, no requiere LLM juez)
uv run python eval_reliability.py --base-url http://localhost:10007 \
  --set eval_set_basico.json --output eval_reliability_report.json

# Retrieval sin RAGAS (sin costo de LLM juez)
uv run python evaluar_ragas.py --no-ragas

# RAGAS completo (requiere OPENAI_API_KEY como juez, puede tardar ~1h)
RAGAS_MAX_WORKERS=2 uv run python evaluar_ragas.py --solo-ragas --limit 12

# Evaluación focalizada en preguntas específicas
uv run python evaluar_ragas.py --no-ragas --indices 1,5,9
```

No ejecutar RAGAS y el frontend en paralelo — compiten por cuota de modelos.

---

## Troubleshooting

**El servidor no arranca / error al cargar modelos**
- Verificar que `HF_TOKEN` esté en `.env` y que hayas aceptado los términos de UNI en HuggingFace.
- Si no hay GPU compatible, el sistema usa CPU automáticamente (más lento).

**Qdrant no conecta**
- Verificar `QDRANT_URL` y `QDRANT_KEY` en `.env`.
- Confirmar que el cluster de Qdrant Cloud esté activo.

**El LLM responde "sin cuota"**
- La cuota de Groq se resetea diariamente. Esperar o cambiar `GROQ_API_KEY`.
- El sistema bloquea automáticamente nuevas llamadas por 5 minutos tras detectar cuota agotada (configurable con `LLM_QUOTA_BLOCK_SECONDS`).

**No aparecen imágenes del manual**
- Verificar que los PDFs estén en `pdf/` y que Qdrant tenga datos (`/api/status` muestra `n_temas > 0`).
- Tesseract y Poppler deben estar instalados para la extracción.
