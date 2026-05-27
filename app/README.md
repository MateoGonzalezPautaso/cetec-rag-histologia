# 🔬 RAG Multimodal de Histología — Branch Vuelta (v4.2)

Este repositorio contiene la versión actual estabilizada de **RAG Multimodal de Histología** para FMED. Conserva la arquitectura funcional de la rama `vuelta` original: **FastAPI**, **LangGraph**, **Qdrant**, frontend web, memoria semántica, embeddings de texto MiniLM y soporte visual con **UNI/PLIP**.

La versión actual no es una reescritura ni una migración de modelo. Es la misma base de `histo-test-qdrant-vuelta`, con mejoras aplicadas para que el sistema sea más medible, trazable, estable y apto para instalación.

---

## Estado Actual

La candidata principal para instalación sigue siendo esta rama `histo-test-qdrant-vuelta` actual.

Motivos principales:

- Mantiene backend y frontend integrados.
- Conserva Qdrant como motor vectorial principal.
- Mejora trazabilidad y evaluación respecto de `vuelta` original.
- Reduce ruido contextual sin perder evidencia clave del manual.
- Mejora `faithfulness` y `context_precision` frente a reportes históricos de `main`.
- Mantiene el generador vía Groq; OpenAI se usa solo como juez opcional de RAGAS.

Advertencia: no se afirma que sea mejor en absolutamente todo. RAGAS completo tuvo errores de conexión y algunos valores `nan`, por lo que debe complementarse con smoke tests y prueba manual.

---

## Qué Se Conserva De Vuelta Original

- Backend FastAPI en `server.py`.
- Frontend en `client/index.html`, `client/app.js`, `client/style.css`.
- Grafo LangGraph con flujo bifurcado texto/imagen.
- Qdrant como motor vectorial principal.
- Colecciones Qdrant `histo_chunks`, `histo_imagenes` y memoria semántica.
- Embeddings locales de texto MiniLM 384d.
- Soporte visual con UNI y PLIP.
- Modo texto sin procesar imagen cuando no hay imagen nueva.
- Análisis comparativo cuando el usuario sube imagen.
- PDFs actuales `arch3.pdf` y `arch4.pdf`.
- Generación con LLM vía Groq, sin migrar el generador a OpenAI.

---

## Cambios Aplicados Respecto A Vuelta Original

### Evaluación Fuente + Página

Se agregó evaluación estricta por fuente y página:

```text
recall_at_5_fuente_pagina
recall_at_5_pagina
fuente_esperada
referencias_recuperadas
fuentes_recuperadas_top_5
fuera_fuente_esperada_at_5
fuente_dominante_correcta_pct
```

Esto evita conclusiones optimistas cuando dos PDFs comparten números de página.

### Reducción De Contexto Enviado

El modo texto puro pasó de enviar hasta 10 contextos válidos a usar un máximo final de 6 bloques.

Objetivo:

- Reducir ruido contextual.
- Reducir costo/tokens.
- Evitar mezcla de evidencia lateral entre arteria y testículo.

### Activación Visual Selectiva Híbrida

Las consultas de texto puro ya no buscan siempre en captions/imágenes. Primero se intenta detectar la intención visual con reglas determinísticas baratas y, si la consulta queda ambigua, decide un LLM clasificador que responde solo `VISUAL` o `TEXTO`.

La búsqueda textual sobre imágenes se activa directamente con señales visuales claras:

- `imagen`
- `figura`
- `foto`
- `microfotografia`
- `laminilla`
- `se observa`
- `se reconoce`
- `como se identifica`
- `que se ve`
- `que muestra`
- `que estructura muestra`
- `que estoy viendo`
- `identifica esto`
- `preparado histologico`
- `campo histologico`

Se quitaron activadores demasiado amplios como `corte`, `tincion`, `lamina`, `aspecto` y `morfologia`, porque podían desplazar texto exacto por captions de imagen.

Si la consulta no es claramente visual ni claramente conceptual, se trata como ambigua y el LLM decide si conviene incluir captions/imágenes del manual. Ejemplos: `que hay aca`, `esto que es`, `que estructura corresponde`, `esta preparacion` o cualquier formulación no cubierta por las reglas. Si ese clasificador falla por cuota, el fallback es seguro: usa visual solo si hay imagen activa/subida; si no, queda en texto.

### Filtro Suave Por Fuente Dominante

Se mantiene un filtro suave por fuente dominante. No se descarta automáticamente otra fuente por reglas fijas de PDF.

Si una fuente domina claramente, resultados de otra fuente se conservan solo si tienen coincidencia fuerte con keywords de la consulta.

### Fallback Textual Exacto

Se agregó búsqueda textual directa para estructuras específicas, por ejemplo:

```text
lamina elastica interna
tunica media
Sertoli
Leydig
```

`busqueda_chunks_por_texto()` ordena por score textual y los matches multi-palabra exactos reciben score alto. Si la consulta tiene dominio (`vasos sanguineos`, `testiculo`), el fallback textual respeta ese dominio.

### Cache De Temario

`ExtractorTemario.extraer_temario()` usa cache local:

```text
temario_histologia.json
temario_histologia.sha256
```

Esto estabiliza la extracción de temas entre corridas y mejora reproducibilidad de evaluaciones.

### Metadatos Estructurados Livianos

Se agregaron payloads consultables en Qdrant:

```text
dominios
organos
tejidos
estructuras
celulas
temas
tinciones
```

También se agregó `backfill_metadata_payloads.py` para actualizar payloads existentes sin reembedding ni reindexado completo.

Resultado documentado del backfill:

```text
Payloads actualizados: chunks=42, imagenes=23
```

### Soporte OpenAI Solo Como Juez RAGAS

`evaluar_ragas.py` puede usar `gpt-4o-mini` si existe `OPENAI_API_KEY`.

Esto no cambia el LLM generador productivo. OpenAI se usa solo para evaluación RAGAS.

### Selección Por Índices En Evaluación

`evaluar_ragas.py` acepta `--indices` para evaluar preguntas específicas del golden set:

```bash
uv run python evaluar_ragas.py --no-ragas --indices 1,5,9
RAGAS_MAX_WORKERS=2 uv run python evaluar_ragas.py --solo-ragas --indices 1,5,9
```

También se corrigió `--solo-ragas --indices` para evitar filtrar dos veces cuando el reporte ya está focalizado.

### Prompt Conservador Más Directo

El prompt textual pide:

- Responder primero la pregunta en 1 a 3 frases.
- Evitar información general no solicitada.
- No decir que falta información si el contexto contiene evidencia directa.
- Mantener cautela: no inventar, responder solo hasta donde permite el manual y derivar a docente/bibliografía oficial si corresponde.

### Fallback UX Para Imagen Identificada Con Cuota Agotada

Si una imagen subida ya fue identificada mediante `metadata.estructura_identificada`, pero la generación textual completa falla por cuota/proveedor, el frontend muestra la referencia identificada en lugar del error crudo.

Ejemplo:

```text
La imagen fue asociada con la referencia del manual: Imagen 17: Espermatide temprana. La explicacion textual completa no se pudo generar porque el modelo esta temporalmente sin cuota.
```

Alcance:

- Archivo modificado: `client/app.js`.
- Función modificada: `normalizeAssistantResponse()`.
- No toca backend, retrieval, Qdrant, LangGraph, prompts ni embeddings.
- Validación: `node -c client/app.js`.

### Corte Rápido Ante Cuota Agotada

Las llamadas LLM ahora distinguen cuota diaria agotada de errores transitorios. Si el proveedor devuelve señales como `tokens per day`, `TPD`, `quota exceeded`, `RESOURCE_EXHAUSTED` o `sin cuota`, el backend no espera ni reintenta: devuelve el mensaje amigable de cuota inmediatamente.

Además se activa un bloqueo temporal en memoria para evitar nuevas llamadas LLM durante unos minutos:

```env
LLM_QUOTA_BLOCK_SECONDS=300
```

Esto reduce la demora percibida en la UI cuando la cuota ya está agotada. Los reintentos se conservan para errores potencialmente transitorios como `503`, `timeout` o problemas de conexión.

---

## Métricas Documentadas

### Baseline Vuelta Original

```text
n_preguntas: 12
tema_valido_pct: 100.0
contexto_suficiente_pct: 100.0
avg_resultados_validos: 10.0
avg_similitud_dominio: 0.648
recall_at_5: 0.7569

faithfulness: 0.8058
answer_relevancy: 0.8617
context_recall: 0.9583
context_precision: no reportado de forma confiable por timeouts/NaN
```

### Retrieval Actual Sin Juez LLM

```text
n_preguntas: 12
tema_valido_pct: 100.0
contexto_suficiente_pct: 100.0
avg_resultados_validos: 6.0
avg_similitud_dominio: 0.5909
recall_at_5_fuente_pagina: 0.8542
recall_at_5_pagina: 0.8542
avg_fuera_fuente_esperada_at_5: 0.00
fuente_dominante_correcta_pct: 100.0
```

### RAGAS Completo Con GPT-4o-mini Como Juez

```text
faithfulness: 0.8735
answer_relevancy: 0.7110
context_precision: 0.8027
context_recall: 0.8917
```

Notas:

- La corrida tardó aproximadamente 1h11m.
- Hubo `APIConnectionError` y algunos valores `nan`.
- El resultado sirve como comparación, no como medición perfecta absoluta.

### RAGAS Focalizado Con `--indices 1,5,9`

```text
faithfulness: 0.9000
answer_relevancy: 0.7513
context_precision: 0.7870
context_recall: 0.8333
```

Detalle relevante:

- Pregunta 1 subió en `answer_relevancy`: `0.000` -> `0.901`.
- Pregunta 5 tuvo `context_precision=1.000` y `context_recall=1.000`, pero `answer_relevancy=nan` por error del juez.
- Pregunta 9, Sertoli, sigue siendo el caso más débil.

---

## Arquitectura Técnica

El sistema está orquestado por un grafo de estados LangGraph:

- `inicializar`: carga estado y memoria semántica.
- `procesar_imagen`: genera embeddings UNI y PLIP si hay imagen nueva.
- `clasificar`: valida dominio histológico.
- `generar_consulta`: reformula la pregunta para retrieval.
- `buscar_qdrant`: consulta `histo_chunks` e `histo_imagenes`.
- `filtrar_contexto`: selecciona resultados válidos y arma contexto.
- `analisis_comparativo`: compara imagen del usuario con referencias del manual.
- `generar_respuesta`: sintetiza respuesta con el LLM.
- `finalizar`: guarda trayectoria y actualiza memoria.

---

## Modelos Y Embeddings

| Tipo | Modelo | Propósito |
| :--- | :--- | :--- |
| LLM | Llama-4-Scout vía Groq | Razonamiento agéntico y generación productiva |
| Embeddings texto | all-MiniLM-L6-v2 | Búsqueda semántica de chunks de texto, 384d |
| Vision UNI | MahmoodLab/UNI | Morfología celular y arquitectura tisular, 1024d |
| Vision PLIP | vinid/PLIP | Alineación semántica visual-textual, 512d |
| Juez RAGAS opcional | gpt-4o-mini | Evaluación, no generación productiva |

---

## Configuración E Instalación

### Requisitos Previos

- Python 3.10+
- `uv`
- Tesseract OCR y Poppler para extracción de PDFs
- Node/NPM para el frontend

### Instalación

```bash
uv sync
```

Configurar `.env`:

```env
GROQ_API_KEY=tu_clave
HF_TOKEN=tu_token_huggingface
QDRANT_URL=tu_url_qdrant
QDRANT_KEY=tu_clave_qdrant
OPENAI_API_KEY=opcional_para_ragas
```

### Ejecución

```bash
npm run dev
```

Verificar estado:

```bash
curl http://localhost:10007/api/status
```

---

## Evaluación Y Validación

Validar sintaxis:

```bash
python3 -m py_compile qdrant-histo.py server.py evaluar_ragas.py eval_reliability.py
node -c client/app.js
```

Smoke test barato:

```bash
python3 eval_reliability.py --base-url http://localhost:10007 --set eval_set_basico.json --output eval_reliability_report.json
```

Retrieval sin juez RAGAS:

```bash
uv run python evaluar_ragas.py --no-ragas
```

Evaluación focalizada:

```bash
uv run python evaluar_ragas.py --no-ragas --indices 1,5,9
RAGAS_MAX_WORKERS=2 uv run python evaluar_ragas.py --solo-ragas --indices 1,5,9
```

RAGAS completo chico/controlado:

```bash
RAGAS_MAX_WORKERS=2 uv run python evaluar_ragas.py --solo-ragas --limit 12
```

Nota: no usar el frontend mientras corre RAGAS completo. Ambos procesos compiten por modelos, memoria, Qdrant y cuota de proveedores.

---

## Checklist Operativo De Instalación

Antes de entregar o instalar:

1. Confirmar `.env` con `GROQ_API_KEY`, `HF_TOKEN`, `QDRANT_URL` y `QDRANT_KEY`.
2. Ejecutar `uv sync`.
3. Validar sintaxis con `python3 -m py_compile qdrant-histo.py server.py evaluar_ragas.py eval_reliability.py`.
4. Validar frontend con `node -c client/app.js`.
5. Levantar `npm run dev`.
6. Abrir `http://localhost:10007` y confirmar que el frontend muestra `RAG Histología Qdrant`.
7. Consultar `/api/status` y confirmar `ready: true`.
8. Correr `eval_reliability.py`; resultado esperado: casos OK.
9. Probar manualmente arteria muscular, lámina elástica interna, Sertoli y Leydig.
10. Probar una imagen conocida, por ejemplo `Imagen 17: Espermatide temprana`, y verificar que ante cuota agotada se muestre el fallback amigable si llega `estructura_identificada`.
11. Si se usa `OPENAI_API_KEY`, usarla solo como juez RAGAS.

---

## Troubleshooting Rápido

- Si Qdrant falla, revisar `QDRANT_URL`, `QDRANT_KEY` y conectividad.
- Si Groq falla por cuota, esperar reset o reducir pruebas; no ejecutar RAGAS y frontend en paralelo.
- Si la UI tarda en mostrar cuota agotada, verificar que el backend tenga activo el corte rápido de cuota y ajustar `LLM_QUOTA_BLOCK_SECONDS` si hace falta.
- Si Hugging Face falla, revisar `HF_TOKEN` y acceso a UNI/PLIP.
- Si RAGAS devuelve `nan` o `APIConnectionError`, repetir corrida chica; no interpretar esa medición como absoluta.
- Si una imagen fue identificada pero falla la explicación por cuota, revisar que `client/app.js` reciba `estructura_identificada` y active el fallback de `normalizeAssistantResponse()`.

---

## Estructura Del Proyecto

- `server.py`: servidor FastAPI que expone API de chat y frontend.
- `qdrant-histo.py`: agente LangGraph, retrieval, embeddings y lógica RAG.
- `client/`: interfaz web.
- `pdf/`: manuales de referencia.
- `imagenes_extraidas/`: figuras procesadas de los manuales.
- `evaluar_ragas.py`: evaluación retrieval/RAGAS, incluyendo `--indices`.
- `backfill_metadata_payloads.py`: backfill de payloads estructurados livianos en Qdrant.
- `docs/retrieval_tuning_log.md`: log de cambios y mediciones.
- `docs/vuelta_original_vs_actual.md`: comparación entre `vuelta` original y versión actual.

---

## Qué No Se Cambió

- No se migró a Gemini embeddings.
- No se migró el generador a OpenAI.
- No se integró CONCH al flujo principal.
- No se creó una ontología completa órgano -> tejido -> célula.
- No se reindexaron embeddings por completo para estos ajustes.
- No se cambió la arquitectura FastAPI/LangGraph/Qdrant.
- No se conservaron los cambios backend probados y revertidos para reintentar sin imágenes o forzar `mostrar_imagenes=True` al subir imagen.

---

## Documentación Relacionada

- `docs/retrieval_tuning_log.md`: historial detallado de cambios, validaciones y métricas.
- `docs/vuelta_original_vs_actual.md`: resumen comparativo contra la rama `vuelta` original.
