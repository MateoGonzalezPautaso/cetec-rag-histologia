# RAG Histología — v5.0

Sistema RAG multimodal para histología médica. Permite hacer preguntas sobre un manual en PDF y obtener respuestas fundamentadas en el texto e imágenes del documento. Soporta subir imágenes histológicas para análisis comparativo.

**Stack:** FastAPI · LangGraph · Qdrant · Groq (Llama-4-Scout) · MiniLM · UNI/PLIP · frontend web

---

## Inicio rápido

```bash
# 1. Copiar y completar el archivo de configuración
cp .env.example app/.env
# Editar app/.env con tus claves (ver sección Configuración)

# 2. Verificar que estén los PDFs del manual
# El repo ya incluye PDFs en data/pdf/. También se pueden poner PDFs propios en app/pdf/.

# 3. Ejecutar el script de inicio
cd app && ./start.sh
```

El script instala dependencias, crea/usa una base Qdrant local en `app/qdrant_data/`, inicia el servidor y abre el navegador automáticamente en `http://localhost:10007`.

La primera vez también crea un acceso directo **«RAG Histología»** en el escritorio. Al hacer doble clic: si el servidor ya está corriendo abre el navegador; si no, lo inicia (vía `launch.sh`) y abre el navegador cuando está listo.

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

Copiar `.env.example` a `app/.env` y completar las claves:

```bash
cp .env.example app/.env
```

| Variable | Requerida | Descripción | Dónde obtenerla |
|---|---|---|---|
| `GROQ_API_KEY` | ✅ | LLM principal (Llama-4-Scout) | https://console.groq.com/keys |
| `HF_TOKEN` | ✅ | Descarga modelos UNI y PLIP — requiere aceptar los términos del modelo | https://huggingface.co/settings/tokens |
| `QDRANT_PATH` | ❌ | Carpeta local persistente de Qdrant. Por defecto: `./qdrant_data` | No aplica |
| `QDRANT_URL` | ❌ | URL de Qdrant remoto si se quiere usar Cloud en lugar de local | https://cloud.qdrant.io/ |
| `QDRANT_KEY` | ❌ | API key para Qdrant remoto | https://cloud.qdrant.io/ |
| `LANGSMITH_API_KEY` | ❌ | Trazabilidad del pipeline. El sistema funciona sin esto | https://smith.langchain.com/ |

---

## Agregar PDFs

El servidor usa los PDFs versionados en `data/pdf/`. Si se agregan PDFs en `app/pdf/`, esos tienen prioridad. Al iniciar, el servidor:

1. Lee el texto de los PDFs y lo divide en chunks.
2. Extrae las imágenes de cada página.
3. Genera embeddings de texto (MiniLM), visuales (UNI, PLIP) e indexa todo en Qdrant local.
4. Extrae el temario automáticamente del contenido.

El indexado se saltea solo si las colecciones de Qdrant ya están pobladas **y** existe la marca de indexación completa (`app/.qdrant_index_complete`). Si una indexación previa quedó incompleta —por una interrupción o porque algún ítem falló al indexarse— la marca no se escribe y el sistema reindexa automáticamente en el próximo arranque (los upserts son idempotentes). Para forzar una reindexación manual: borrar `app/.qdrant_index_complete` y, si se quiere empezar desde cero, borrar también `app/qdrant_data/`.

---

## Ejecutar manualmente

```bash
cd app

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
├── start.sh               # Script de inicio con checks automáticos + acceso directo
├── launch.sh              # Lanzador del acceso directo del escritorio
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
├── pdf/                   # PDFs locales opcionales; tienen prioridad sobre data/pdf/
├── imagenes_extraidas/    # Imágenes extraídas de los PDFs (generado automáticamente)
├── imagenes_chat/         # Imágenes subidas por usuarios (generado automáticamente)
├── qdrant_data/           # Base Qdrant local persistente (generado automáticamente)
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

Todos los comandos se ejecutan desde dentro de `app/`:

```bash
cd app

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
- Por defecto no se necesita Qdrant Cloud: se usa `app/qdrant_data/`.
- Verificar permisos de escritura en la carpeta `app/`.
- Si se configuró `QDRANT_URL`, verificar también `QDRANT_URL` y `QDRANT_KEY` en `.env`.

**El LLM responde "sin cuota"**
- La cuota de Groq se resetea diariamente. Esperar o cambiar `GROQ_API_KEY`.
- El sistema bloquea automáticamente nuevas llamadas por 5 minutos tras detectar cuota agotada (configurable con `LLM_QUOTA_BLOCK_SECONDS`).

**No aparecen imágenes del manual**
- Verificar que los PDFs estén en `data/pdf/` o `app/pdf/` y que Qdrant tenga datos (`/api/status` muestra `n_temas > 0`).
- Tesseract y Poppler deben estar instalados para la extracción.
