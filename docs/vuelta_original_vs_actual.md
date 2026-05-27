# Vuelta original vs version actual

Fecha: 2026-05-25

## Resumen ejecutivo

La version actual conserva la arquitectura original de `histo-test-qdrant-vuelta` y agrega mejoras de evaluacion, trazabilidad, control de ruido y metadatos. No es una reescritura ni una migracion de modelo: sigue siendo la misma base funcional con Qdrant, LangGraph, FastAPI, frontend, memoria semantica y soporte multimodal UNI/PLIP.

La conclusion practica es:

- `vuelta` original era mas simple y ya funcionaba bien.
- La version actual es mas medible, mas trazable y tiene mejor control de fuentes.
- Las mejoras riesgosas que bajaban `context_recall` fueron relajadas o revertidas parcialmente.
- La version actual queda como candidata principal para instalacion, con la advertencia de que RAGAS completo tuvo errores de conexion/NaN y debe complementarse con smoke test y prueba manual.

## Que se conserva de vuelta original

- Backend FastAPI en `server.py`.
- Frontend en `client/index.html`, `client/app.js`, `client/style.css`.
- Grafo LangGraph con flujo bifurcado texto/imagen.
- Qdrant como motor vectorial principal.
- Colecciones Qdrant:
  - `histo_chunks`.
  - `histo_imagenes`.
- Embeddings locales de texto MiniLM 384d.
- Soporte visual con UNI y PLIP.
- Modo texto sin procesar imagen cuando no hay imagen nueva.
- Analisis comparativo cuando el usuario sube imagen.
- Memoria semantica persistente en `qdrant_memoria`.
- PDFs actuales:
  - `arch3.pdf`.
  - `arch4.pdf`.
- Generacion con LLM via Groq, sin migrar el generador a OpenAI.

## Baseline de vuelta original

Reporte RAGAS/retrieval inicial de `vuelta` despues de reindexar `arch3.pdf` y `arch4.pdf`:

```text
timestamp: 2026-05-25 00:45:27
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

Diagnostico del baseline:

- Recuperaba contexto suficiente.
- Tenia buen `faithfulness` y buen `answer_relevancy`.
- Enviaba mucho contexto al LLM: promedio de `10` resultados validos.
- Se observaron cruces de contexto entre arteria/testiculo por terminos compartidos como `musculo liso`, `fusiforme`, `celulas`.
- No tenia metrica estricta `fuente + pagina`, por lo que `recall_at_5` podia ser optimista.

## Cambios seguros que se agregaron

Estos cambios conviene conservar porque mejoran evaluacion, trazabilidad o estabilidad sin cambiar la arquitectura principal.

### Evaluacion fuente + pagina

Antes:

```text
recall_at_5 medido solo por pagina
```

Ahora:

```text
recall_at_5_fuente_pagina
recall_at_5_pagina
fuente_esperada
referencias_recuperadas
fuentes_recuperadas_top_5
fuera_fuente_esperada_at_5
fuente_dominante_correcta_pct
```

Impacto:

- Permite saber si se recupero la pagina correcta del PDF correcto.
- Evita conclusiones optimistas cuando dos PDFs comparten numeros de pagina.
- Alinea la evaluacion con el diagnostico de `cetec-rag-histologia`.

### Cache de temario

Se agrego cache para estabilizar la extraccion de temario:

```text
temario_histologia.json
temario_histologia.sha256
```

Impacto:

- Evita que el LLM extraiga distinta cantidad de temas en cada corrida.
- Mejora reproducibilidad de evaluaciones.
- No cambia el corpus ni los embeddings.

### Metadatos estructurados livianos

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

Tambien se agrego backfill:

```bash
uv run python backfill_metadata_payloads.py
```

Resultado del backfill:

```text
Payloads actualizados: chunks=42, imagenes=23
```

Ejemplo verificado:

```text
arch3.pdf pagina 2
dominios=['vasos sanguineos']
temas=['capas arteriales', 'laminas elasticas']
estructuras=['tunica media', 'tunica adventicia', 'lamina elastica interna']
```

Impacto:

- Es una base para escalar a mas PDFs.
- Reduce dependencia futura de reglas ad hoc.
- Todavia no reemplaza una ontologia completa organo -> tejido -> celula.

### Documentacion de tuning

Se creo:

```text
docs/retrieval_tuning_log.md
```

Impacto:

- Registra cambios, resultados, errores y rollbacks parciales.
- Permite defender que no se hicieron cambios a ciegas.

### Soporte OpenAI como juez RAGAS

`evaluar_ragas.py` ahora usa `gpt-4o-mini` si existe `OPENAI_API_KEY`:

```text
Juez RAGAS: OpenAI gpt-4o-mini
```

Si no hay OpenAI, mantiene fallback a NVIDIA.

Impacto:

- No cambia el LLM generador del sistema.
- Solo cambia el juez de evaluacion RAGAS.
- Permite comparar con un evaluador mas estable que Groq/NVIDIA en RAGAS moderno.

## Cambios de retrieval aplicados y ajustados

### Reduccion de contexto enviado

Original:

```text
avg_resultados_validos: 10.0
```

Actual:

```text
avg_resultados_validos: 6.0
```

Motivo:

- Reducir ruido contextual.
- Reducir costo/tokens.
- Evitar que el LLM mezcle evidencia lateral.

Validacion actual de retrieval:

```text
contexto_suficiente_pct: 100.0
recall_at_5_fuente_pagina: 0.8542
avg_fuera_fuente_esperada_at_5: 0.00
fuente_dominante_correcta_pct: 100.0
```

### Activacion visual selectiva hibrida

Se evito que texto puro busque siempre en captions/imagenes.

Estado final:

- Se activa `res_img_texto` directamente con senales visuales claras:
  - `imagen`.
  - `figura`.
  - `foto`.
  - `microfotografia`.
  - `laminilla`.
  - `se observa`.
  - `se reconoce`.
  - `como se identifica`.
  - `que se ve`.
  - `que muestra`.
  - `que estoy viendo`.
  - `identifica esto`.
  - `preparado histologico`.
  - `campo histologico`.
- Se quitaron activadores demasiado amplios:
  - `corte`.
  - `tincion`.
  - `lamina`.
  - `aspecto`.
  - `morfologia`.
- Si la consulta no es claramente visual ni claramente conceptual, queda como ambigua y un LLM clasificador decide `VISUAL` o `TEXTO`.
- Si el clasificador falla por cuota, el fallback es conservador: visual solo si hay imagen activa/subida.

Motivo:

- Activadores demasiado amplios podian desplazar texto exacto por captions de imagen.
- Caso critico: `lamina elastica interna` necesitaba recuperar `arch3.pdf`, pagina 2.
- Las reglas exactas eran demasiado fragiles ante consultas naturales como `que hay aca`, `esto que es` o `que estructura corresponde`; por eso cualquier formulacion no clara pasa al clasificador LLM.
- El router hibrido mantiene bajo costo porque solo usa LLM en casos ambiguos.

### Filtro por fuente dominante

Se probo un filtro estricto `arch3/arch4`, pero se relajo.

Estado final:

- Filtro suave por fuente dominante.
- No se descarta automaticamente otra fuente por reglas fijas de PDF.
- Se conservan resultados de otra fuente solo si tienen coincidencia fuerte con keywords.
- Para fallback textual, si la consulta tiene `dominios`, los matches se filtran por esos dominios.

Motivo:

- El filtro estricto subio `context_precision`, pero bajo `context_recall` al perder evidencia clave.
- Para medicina se prioriza no perder evidencia del manual.

### Fallback textual exacto

Se agrego busqueda textual directa para estructuras especificas:

```text
lamina elastica interna
tunica media
Sertoli
Leydig
```

Estado final:

- `busqueda_chunks_por_texto()` ordena resultados por score textual.
- Matches multi-palabra exactos reciben score alto.
- Si la consulta tiene dominio (`vasos sanguineos`, `testiculo`), el fallback textual respeta ese dominio.

Impacto:

- La pregunta de `lamina elastica interna` vuelve a recuperar `arch3.pdf`, pagina 2.
- La pregunta de `musculo liso de tunica media` ya no trae ruido de `arch4.pdf` en el subset critico.

## Evidencia de la version actual

### Retrieval completo sin juez LLM

Comando:

```bash
uv run python evaluar_ragas.py --no-ragas
```

Resultado actual:

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

Comparacion contra original:

```text
avg_resultados_validos: 10.0 -> 6.0
recall_at_5: 0.7569 -> 0.8542
contexto_suficiente_pct: 100.0 -> 100.0
ruido fuera de fuente: no medido -> 0.00
```

### RAGAS chico sobre subset critico

Comando:

```bash
uv run python evaluar_ragas.py --solo-ragas --limit 3
```

Resultado:

```text
faithfulness: 0.7571
answer_relevancy: 0.9076
context_precision: 0.8736
context_recall: 1.0000
```

Lectura:

- El subset critico recupera toda la evidencia esperada.
- Alta precision de contexto.
- `faithfulness` aceptable, con debilidad puntual en redaccion de `lamina elastica interna`.

### RAGAS completo con gpt-4o-mini

Comando:

```bash
RAGAS_MAX_WORKERS=2 uv run python evaluar_ragas.py --solo-ragas --limit 12
```

Resultado:

```text
faithfulness: 0.8735
answer_relevancy: 0.7110
context_precision: 0.8027
context_recall: 0.8917
```

Detalle operativo:

- La corrida tardo aproximadamente `1h11m`.
- Hubo varios `APIConnectionError` durante la corrida.
- Hubo algunos valores `nan` por pregunta/metrica.
- Por eso el resultado es util para comparacion, pero no debe interpretarse como medicion perfecta.

Comparacion con `main` historico:

```text
main:
faithfulness: 0.5165
answer_relevancy: 0.8311
context_precision: 0.6757
context_recall: 0.9500

vuelta actual:
faithfulness: 0.8735
answer_relevancy: 0.7110
context_precision: 0.8027
context_recall: 0.8917
```

Lectura:

- `vuelta` actual es mas fiel al contexto que `main`.
- `vuelta` actual tiene mejor precision de contexto que `main`.
- `main` conserva mejor `answer_relevancy` y algo mas de `context_recall` en su reporte historico.
- Para un entorno medico/educativo, se prioriza `faithfulness` y `context_precision` sobre una respuesta mas fluida pero menos fiel.

## Que no se cambio

- No se migro a Gemini embeddings.
- No se migro el generador a OpenAI.
- No se integro CONCH al flujo principal.
- No se hizo una ontologia completa organo -> tejido -> celula.
- No se reindexaron embeddings por completo.
- No se cambio la arquitectura FastAPI/LangGraph/Qdrant.

## Cambio UX posterior - 2026-05-26

Se agrego un ajuste minimo en el frontend para el caso de imagenes ya reconocidas cuando falla la generacion textual por cuota/proveedor.

Antes:

```text
Error: El proveedor del modelo esta temporalmente ocupado o sin cuota disponible...
```

Aunque el panel ya mostrara:

```text
Identificado: Imagen 17: Espermatide temprana
```

Ahora:

```text
La imagen fue asociada con la referencia del manual: Imagen 17: Espermatide temprana. La explicacion textual completa no se pudo generar porque el modelo esta temporalmente sin cuota.
```

Alcance:

- Archivo modificado: `client/app.js`.
- Funcion modificada: `normalizeAssistantResponse()`.
- Se usa `metadata.estructura_identificada` aun cuando no haya `imagenes_recuperadas` disponibles para galeria.
- Si existe una imagen recuperada con `etiqueta`, se usa `etiqueta` junto con la estructura identificada.
- No se toco backend, retrieval, Qdrant, LangGraph, prompts ni embeddings.
- Se verifico sintaxis con `node -c client/app.js`.

Nota:

- Este cambio no pretende resolver la cuota del proveedor ni mejorar metricas RAGAS.
- Solo evita ocultar una identificacion correcta detras de un mensaje de error cuando la metadata ya esta disponible.

## Cambio operativo posterior - 2026-05-26

Se agrego corte rapido ante cuota agotada del proveedor LLM.

Antes:

```text
El backend detectaba 429/cuota, esperaba el retry configurado y podia seguir intentando llamadas LLM posteriores antes de responder a la UI.
```

Ahora:

```text
Si el error indica cuota diaria agotada, se devuelve inmediatamente el mensaje amigable y se bloquean temporalmente nuevas llamadas LLM.
```

Alcance:

- Archivo modificado: `qdrant-histo.py`.
- Funciones afectadas: `invoke_con_reintento()` e `invoke_con_reintento_sync()`.
- Variables nuevas: bloqueo temporal en memoria y `LLM_QUOTA_BLOCK_SECONDS` con default de `300` segundos.
- Se mantienen reintentos para errores transitorios, pero no para cuota diaria agotada.
- Validacion: `python3 -m py_compile qdrant-histo.py` y `node -c client/app.js`.

## Que queda pendiente

- Limpiar textos visibles del frontend que aun dicen `Neo4j`.
- Correr smoke API final:

```bash
python3 eval_reliability.py --base-url http://localhost:10007 --set eval_set_basico.json --output eval_reliability_report.json
```

- Probar manualmente preguntas demo en frontend.
- Preparar README/checklist de instalacion.
- Si se agregan mas PDFs, pasar de metadatos livianos a una ontologia externa versionada.
- Validar CONCH solo con imagenes reales externas de alumnos antes de integrarlo productivamente.

## Decision recomendada

Para instalacion en la Facultad de Medicina, la candidata principal sigue siendo `histo-test-qdrant-vuelta` actual.

Motivos:

- Es la unica de las tres opciones con frontend + backend integrados y flujo estable.
- Tiene mejor trazabilidad y evaluacion que `vuelta` original.
- Tiene mejor `faithfulness` y `context_precision` que `main` historico.
- `cetec-rag-histologia` es valioso como experimento CONCH, pero su retrieval textual reportado es bajo y RAGAS estaba pendiente.

Advertencia:

- No afirmar que la version actual es mejor en absolutamente todo.
- Afirmar que conserva la base original, reduce ruido, mejora trazabilidad y muestra mejor evidencia de fidelidad/context precision, con validacion RAGAS completa afectada por errores de conexion pero favorable en metricas principales de fidelidad.
