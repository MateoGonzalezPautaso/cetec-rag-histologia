# Informe Técnico — Evolución Branch Vuelta (RAG Histología v4.2)

**Grupo:** Histología Computacional  
**Fecha:** 26 de mayo de 2026  
**Pipeline:** RAG Multimodal Qdrant v4.2  
**Base comparativa:** `histo-test-qdrant-vuelta` original  

---

## 1. Resumen Ejecutivo

Se realizó una estabilización técnica de la rama `histo-test-qdrant-vuelta` manteniendo su arquitectura original basada en **FastAPI**, **LangGraph**, **Qdrant**, frontend web, memoria semántica, embeddings locales MiniLM y soporte visual con **UNI/PLIP**.

La versión actual no constituye una reescritura ni una migración de modelo. Conserva la base funcional de `vuelta` original y agrega mejoras orientadas a **medición**, **trazabilidad**, **control de ruido contextual**, **robustez operativa** y **mejor experiencia de usuario ante fallos de cuota**.

Los cambios más relevantes fueron:

- Evaluación estricta por `fuente + página`.
- Reducción de contexto enviado al LLM de 10 a 6 bloques válidos en texto puro.
- Activación visual selectiva híbrida: reglas primero y LLM solo en consultas ambiguas.
- Filtro suave por fuente dominante para evitar mezcla entre `arch3.pdf` y `arch4.pdf`.
- Fallback textual exacto para estructuras histológicas específicas.
- Cache local de temario.
- Payloads estructurados livianos en Qdrant.
- Soporte de `gpt-4o-mini` como juez RAGAS, sin cambiar el generador productivo.
- Evaluación focalizada mediante `--indices`.
- Prompt de generación más directo y conservador.
- Fallback UX cuando una imagen fue identificada pero la explicación falla por cuota.
- Corte rápido ante cuota agotada del proveedor LLM.

La versión actual queda como candidata principal para instalación, con la advertencia de que RAGAS completo presentó errores de conexión y algunos valores `nan`, por lo que debe complementarse con smoke tests y prueba manual.

---

## 2. Configuración Del Sistema

### 2.1 Stack Tecnológico

| Componente | Tecnología | Detalles |
| ---------- | ---------- | -------- |
| **Backend** | FastAPI | API de chat, estado, frontend y archivos estáticos |
| **Frontend** | HTML/CSS/JS | Cliente web con chat, estado, galería e indicadores |
| **Orquestador** | LangGraph `StateGraph` | Flujo agéntico texto/imagen |
| **Base vectorial** | Qdrant Cloud | Colecciones `histo_chunks`, `histo_imagenes`, memoria semántica |
| **LLM generador** | Groq Llama-4-Scout | Generación productiva y nodos de clasificación |
| **Embeddings texto** | all-MiniLM-L6-v2 | 384 dimensiones, costo local bajo |
| **Embeddings visuales** | UNI + PLIP | Retrieval multimodal de imágenes histológicas |
| **Juez RAGAS opcional** | OpenAI `gpt-4o-mini` | Solo evaluación, no generación productiva |

### 2.2 Corpus Actual

| Archivo | Dominio principal |
| ------- | ----------------- |
| `arch3.pdf` | Vasos sanguíneos / arteria muscular |
| `arch4.pdf` | Testículo / espermatogénesis |

### 2.3 Aspectos Conservados De Vuelta Original

- Backend FastAPI en `server.py`.
- Frontend en `client/index.html`, `client/app.js`, `client/style.css`.
- Grafo LangGraph con flujo bifurcado texto/imagen.
- Qdrant como motor vectorial principal.
- Embeddings locales de texto MiniLM.
- Soporte visual con UNI y PLIP.
- Análisis comparativo cuando el usuario sube imagen.
- Memoria semántica persistente.
- Generación con LLM vía Groq.

---

## 3. Cambios Técnicos Aplicados

### 3.1 Evaluación Fuente + Página

La versión original medía `recall_at_5` principalmente por página. La versión actual incorpora una evaluación estricta por **fuente + página**, evitando falsos positivos cuando distintos PDFs comparten numeración.

Métricas agregadas:

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

- Mayor trazabilidad del retrieval.
- Mejor diagnóstico de ruido entre PDFs.
- Evaluación más alineada con el uso real del manual.

### 3.2 Reducción De Contexto Enviado

En texto puro, el sistema pasó de enviar hasta **10 resultados válidos** a usar un máximo final de **6 bloques**.

Motivo:

- Reducir ruido contextual.
- Evitar mezcla lateral entre arteria y testículo.
- Disminuir tokens enviados al LLM.

Resultado documentado:

```text
avg_resultados_validos: 10.0 -> 6.0
```

### 3.3 Activación Visual Selectiva Híbrida

La versión original tendía a incluir texto de imágenes/captions con más facilidad. Esto generaba ruido cuando preguntas conceptuales recuperaban captions visuales de otro PDF.

La versión actual usa un router híbrido:

1. Reglas determinísticas primero.
2. Si la consulta es claramente visual, activa captions/imágenes.
3. Si es claramente conceptual, mantiene solo texto.
4. Si no es clara, un LLM clasificador decide `VISUAL` o `TEXTO`.
5. Si el clasificador falla por cuota, el fallback es conservador: visual solo si hay imagen activa/subida.

Se activan directamente señales como:

```text
imagen
figura
foto
microfotografia
laminilla
se observa
se reconoce
como se identifica
que se ve
que muestra
que estoy viendo
identifica esto
preparado histologico
campo histologico
```

Se quitaron activadores amplios que habían generado ruido:

```text
corte
tincion
lamina
aspecto
morfologia
```

Impacto esperado:

- Evita abrir captions/imágenes para todas las preguntas.
- Reduce el riesgo de perder consultas visuales mal redactadas.
- Usa LLM solo en casos ambiguos, reduciendo costo.

### 3.4 Filtro Suave Por Fuente Dominante

Se probó un filtro estricto por familias (`arch3` arteria / `arch4` testículo), pero se relajó porque podía bajar `context_recall`.

Estado final:

- Filtro suave por fuente dominante.
- No se descarta automáticamente otra fuente por reglas fijas.
- Resultados de otra fuente se conservan solo si tienen coincidencia fuerte con keywords.
- El fallback textual puede usar `dominios` para filtrar (`vasos sanguineos`, `testiculo`).

Razonamiento:

- En medicina se prioriza no perder evidencia clave del manual.
- La precisión se mejora sin sacrificar recall crítico.

### 3.5 Fallback Textual Exacto

Se incorporó búsqueda textual directa para estructuras específicas, con score alto para matches multi-palabra.

Ejemplos:

```text
lamina elastica interna
tunica media
Sertoli
Leydig
```

Esto corrige casos donde captions de imagen rankeaban por encima del chunk textual exacto.

### 3.6 Cache De Temario

`ExtractorTemario.extraer_temario()` usa cache local:

```text
temario_histologia.json
temario_histologia.sha256
```

Impacto:

- Evita variabilidad en cantidad de temas extraídos entre corridas.
- Mejora reproducibilidad.
- No cambia corpus ni embeddings.

### 3.7 Payloads Estructurados Livianos

Se agregaron metadatos consultables en Qdrant:

```text
dominios
organos
tejidos
estructuras
celulas
temas
tinciones
```

Se agregó `backfill_metadata_payloads.py` para actualizar payloads existentes sin reembedding ni reindexado completo.

Resultado documentado:

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

### 3.8 Evaluación Focalizada Con `--indices`

`evaluar_ragas.py` ahora permite evaluar preguntas específicas del golden set:

```bash
uv run python evaluar_ragas.py --no-ragas --indices 1,5,9
RAGAS_MAX_WORKERS=2 uv run python evaluar_ragas.py --solo-ragas --indices 1,5,9
```

También se corrigió `--solo-ragas --indices` para evitar filtrar dos veces si `reporte_ragas.json` ya estaba focalizado.

### 3.9 Prompt Más Directo Y Conservador

El prompt textual fue ajustado para:

- Responder primero la pregunta en 1 a 3 frases.
- Evitar información general no solicitada.
- No decir que falta información si el contexto contiene evidencia directa.
- Mantener cautela médica y académica.
- Responder solo hasta donde permite el manual.

### 3.10 Fallback UX Para Imagen Identificada Con Cuota Agotada

En el frontend, `normalizeAssistantResponse()` fue ajustado para aprovechar `metadata.estructura_identificada` aunque no haya galería de imágenes.

Antes:

```text
Error: El proveedor del modelo está temporalmente ocupado o sin cuota disponible...
```

Aunque la UI mostrara:

```text
Identificado: Imagen 17: Espermatide temprana
```

Ahora:

```text
La imagen fue asociada con la referencia del manual: Imagen 17: Espermatide temprana. La explicacion textual completa no se pudo generar porque el modelo esta temporalmente sin cuota.
```

Este cambio mejora la comunicación al alumno sin modificar retrieval, backend ni embeddings.

### 3.11 Corte Rápido Ante Cuota Agotada

Las llamadas LLM ahora distinguen cuota diaria agotada de errores transitorios.

Si el error contiene señales como:

```text
tokens per day
TPD
quota exceeded
insufficient_quota
RESOURCE_EXHAUSTED
sin cuota
cupo diario
```

el backend corta inmediatamente sin dormir ni reintentar.

Además, activa un bloqueo temporal en memoria:

```env
LLM_QUOTA_BLOCK_SECONDS=300
```

Esto evita cascadas de llamadas fallidas y reduce la demora percibida en la UI.

---

## 4. Resultados De Evaluación

### 4.1 Baseline Vuelta Original

| Métrica | Valor |
| ------- | ----- |
| `n_preguntas` | 12 |
| `tema_valido_pct` | 100.0 |
| `contexto_suficiente_pct` | 100.0 |
| `avg_resultados_validos` | 10.0 |
| `avg_similitud_dominio` | 0.648 |
| `recall_at_5` | 0.7569 |
| `faithfulness` | 0.8058 |
| `answer_relevancy` | 0.8617 |
| `context_recall` | 0.9583 |
| `context_precision` | No reportado confiablemente |

Diagnóstico del baseline:

- Recuperaba contexto suficiente.
- Tenía buen `faithfulness` y buen `answer_relevancy`.
- Enviaba demasiado contexto al LLM.
- Había cruces entre arteria/testículo por términos compartidos.
- No medía estrictamente fuente + página.

### 4.2 Retrieval Actual Sin Juez LLM

| Métrica | Valor |
| ------- | ----- |
| `n_preguntas` | 12 |
| `tema_valido_pct` | 100.0 |
| `contexto_suficiente_pct` | 100.0 |
| `avg_resultados_validos` | 6.0 |
| `avg_similitud_dominio` | 0.5909 |
| `recall_at_5_fuente_pagina` | 0.8542 |
| `recall_at_5_pagina` | 0.8542 |
| `avg_fuera_fuente_esperada_at_5` | 0.00 |
| `fuente_dominante_correcta_pct` | 100.0 |

Comparación contra original:

```text
avg_resultados_validos: 10.0 -> 6.0
recall_at_5: 0.7569 -> 0.8542
contexto_suficiente_pct: 100.0 -> 100.0
ruido fuera de fuente: no medido -> 0.00
```

### 4.3 RAGAS Chico Sobre Subset Crítico

Comando:

```bash
uv run python evaluar_ragas.py --solo-ragas --limit 3
```

| Métrica | Valor |
| ------- | ----- |
| `faithfulness` | 0.7571 |
| `answer_relevancy` | 0.9076 |
| `context_precision` | 0.8736 |
| `context_recall` | 1.0000 |

Lectura:

- El subset crítico recupera toda la evidencia esperada.
- `context_precision` se mantiene alto.
- La debilidad principal fue redacción/fidelidad puntual en lámina elástica interna.

### 4.4 RAGAS Completo Con `gpt-4o-mini`

Comando:

```bash
RAGAS_MAX_WORKERS=2 uv run python evaluar_ragas.py --solo-ragas --limit 12
```

| Métrica | Valor |
| ------- | ----- |
| `faithfulness` | 0.8735 |
| `answer_relevancy` | 0.7110 |
| `context_precision` | 0.8027 |
| `context_recall` | 0.8917 |

Notas operativas:

- Duración aproximada: 1h11m.
- Hubo varios `APIConnectionError`.
- Hubo algunos valores `nan`.
- El resultado es útil como comparación, pero no debe interpretarse como medición perfecta.

### 4.5 RAGAS Focalizado Con `--indices 1,5,9`

| Métrica | Valor |
| ------- | ----- |
| `faithfulness` | 0.9000 |
| `answer_relevancy` | 0.7513 |
| `context_precision` | 0.7870 |
| `context_recall` | 0.8333 |

Detalle relevante:

- Pregunta 1 subió en `answer_relevancy`: `0.000 -> 0.901`.
- Pregunta 5 tuvo `context_precision=1.000` y `context_recall=1.000`, con `answer_relevancy=nan` por error del juez.
- Pregunta 9, Sertoli, sigue siendo el caso más débil.

---

## 5. Cambios Backend

| Archivo | Cambio |
| ------- | ------ |
| `qdrant-histo.py` | Router híbrido para intención visual de retrieval |
| `qdrant-histo.py` | Reducción de contexto final en texto puro |
| `qdrant-histo.py` | Filtro suave por fuente dominante |
| `qdrant-histo.py` | Fallback textual exacto para estructuras específicas |
| `qdrant-histo.py` | Cache de temario con hash |
| `qdrant-histo.py` | Prompt textual más directo y conservador |
| `qdrant-histo.py` | Corte rápido ante cuota agotada |
| `evaluar_ragas.py` | Métricas fuente+página y `--indices` |
| `backfill_metadata_payloads.py` | Backfill de payloads estructurados livianos |

---

## 6. Cambios Frontend

| Archivo | Cambio |
| ------- | ------ |
| `client/app.js` | Fallback UX usando `metadata.estructura_identificada` ante error de cuota |
| `client/app.js` | Normalización de respuesta para evitar error crudo si ya hay identificación |
| `client/index.html` | Limpieza de referencias heredadas y copy orientado a Qdrant |
| `client/style.css` | Soporte visual para badges, paneles y estados documentados en la UI |

El cambio frontend más importante fue evitar que el alumno vea únicamente un error de proveedor cuando el sistema ya había reconocido correctamente una imagen.

---

## 7. Validaciones Realizadas

Validaciones de sintaxis documentadas:

```bash
python3 -m py_compile qdrant-histo.py
python3 -m py_compile evaluar_ragas.py
python3 -m py_compile backfill_metadata_payloads.py
node -c client/app.js
```

Evaluaciones documentadas:

```bash
uv run python evaluar_ragas.py --no-ragas
uv run python evaluar_ragas.py --solo-ragas --limit 3
RAGAS_MAX_WORKERS=2 uv run python evaluar_ragas.py --solo-ragas --limit 12
uv run python evaluar_ragas.py --no-ragas --indices 1,5,9
RAGAS_MAX_WORKERS=2 uv run python evaluar_ragas.py --solo-ragas --indices 1,5,9
```

Smoke API documentado:

```bash
python3 eval_reliability.py --base-url http://localhost:10007 --set eval_set_basico.json --output eval_reliability_report.json
```

---

## 8. Limitaciones Y Decisiones No Tomadas

No se realizaron los siguientes cambios:

- No se migró a Gemini embeddings.
- No se migró el generador productivo a OpenAI.
- No se integró CONCH al flujo principal.
- No se creó una ontología completa órgano -> tejido -> célula.
- No se reindexaron embeddings por completo para estos ajustes.
- No se cambió la arquitectura FastAPI/LangGraph/Qdrant.
- No se conservaron los cambios backend probados y revertidos para reintentar sin imágenes o forzar `mostrar_imagenes=True` al subir imagen.

Limitaciones actuales:

- El corpus actual está limitado a `arch3.pdf` y `arch4.pdf`.
- RAGAS completo presentó errores de conexión y valores `nan`.
- `answer_relevancy` quedó más bajo que el reporte histórico de `main`.
- El caso Sertoli sigue siendo el punto más débil en la evaluación focalizada.
- El sistema depende de cuota del proveedor Groq para generación productiva.

---

## 9. Conclusiones

1. **La versión actual conserva la base funcional de `vuelta` original**. No se cambió la arquitectura central ni el proveedor generador.

2. **El retrieval es más trazable y controlado**. La métrica fuente+página permite evaluar si se recuperó evidencia del PDF correcto y no solo una página coincidente.

3. **Se redujo el ruido contextual sin perder evidencia crítica**. El promedio de resultados válidos bajó de 10 a 6, mientras `contexto_suficiente_pct` se mantuvo en 100%.

4. **La activación visual ahora es más robusta**. El sistema no busca imágenes/captions siempre, pero tampoco depende solo de palabras exactas: si la intención no es clara, un LLM clasifica `VISUAL` o `TEXTO`.

5. **La UX ante fallos de cuota mejoró**. Si una imagen ya fue identificada, el frontend muestra la referencia del manual aunque falle la explicación textual. Además, el backend corta rápido ante cuota agotada.

6. **La versión actual es una candidata sólida para instalación**, siempre complementando RAGAS con smoke tests y validación manual docente.

---

## 10. Recomendaciones

1. Mantener esta rama como candidata principal para instalación en FMED.
2. No tocar retrieval nuevamente salvo bug crítico.
3. Ampliar el golden set a 30-50 preguntas reales.
4. Revisar manualmente el caso Sertoli antes de ajustar reglas globales.
5. Usar `gpt-4o-mini` solo como juez RAGAS, no como generador productivo.
6. Si se agregan más PDFs, avanzar hacia una ontología externa versionada.
7. Mantener el fallback rápido de cuota para evitar demoras innecesarias en la UI.

---

## Apéndice A — Comandos Operativos

Instalación:

```bash
uv sync
```

Ejecución:

```bash
npm run dev
```

Estado:

```bash
curl http://localhost:10007/api/status
```

Validación sintáctica:

```bash
python3 -m py_compile qdrant-histo.py server.py evaluar_ragas.py eval_reliability.py
node -c client/app.js
```

Evaluación retrieval:

```bash
uv run python evaluar_ragas.py --no-ragas
```

Evaluación focalizada:

```bash
uv run python evaluar_ragas.py --no-ragas --indices 1,5,9
RAGAS_MAX_WORKERS=2 uv run python evaluar_ragas.py --solo-ragas --indices 1,5,9
```

---

## Apéndice B — Archivos Relevantes

| Archivo | Descripción |
| ------- | ----------- |
| `qdrant-histo.py` | Pipeline RAG, LangGraph, retrieval, embeddings, prompt, cuota |
| `server.py` | API FastAPI, estado y errores amigables |
| `client/app.js` | Lógica frontend y fallback UX |
| `client/index.html` | Estructura del cliente web |
| `client/style.css` | Estilos de UI |
| `evaluar_ragas.py` | Evaluación retrieval/RAGAS, incluyendo `--indices` |
| `backfill_metadata_payloads.py` | Backfill de payloads estructurados livianos |
| `docs/retrieval_tuning_log.md` | Log técnico de cambios y métricas |
| `docs/vuelta_original_vs_actual.md` | Comparación contra `vuelta` original |
| `README.md` | Estado operativo y guía de uso |
