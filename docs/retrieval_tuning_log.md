# Retrieval Tuning Log - Vuelta

## Objetivo

Mejorar la precision del contexto recuperado sin cambiar embeddings, LLM generador ni reindexar Qdrant. La meta inmediata es reducir ruido entre fuentes (`arch3.pdf` arterias y `arch4.pdf` testiculo) manteniendo alto recall.

## Baseline antes del ajuste

Fecha: 2026-05-25

Corpus indexado:
- `arch3.pdf`
- `arch4.pdf`

Smoke API:
- `eval_reliability.py`: 5/5 casos OK.

Retrieval/RAGAS completo NVIDIA:
- `tema_valido_pct`: 100.0
- `contexto_suficiente_pct`: 100.0
- `avg_resultados_validos`: 10.0
- `avg_similitud_dominio`: 0.648
- `recall_at_5`: 0.7569
- `faithfulness`: 0.8058
- `answer_relevancy`: 0.8617
- `context_recall`: 0.9583
- `context_precision`: no reportado de forma confiable por timeouts/NaN.

Diagnostico:
- El sistema recupera el contexto necesario.
- El problema principal es exceso de contexto lateral, no falta de contexto.
- Ejemplo observado: preguntas de arteria muscular recuperan chunks de celulas peritubulares/testiculo por similitud de terminos como `musculo liso`, `fusiforme`, `celulas`.

## Cambios aplicados

Archivo: `qdrant-histo.py`

1. `busqueda_hibrida()` ahora recibe `incluir_imagenes_texto`.
- Antes: toda consulta textual tambien buscaba en `histo_imagenes` usando `texto_emb` y agregaba `res_img_texto`.
- Ahora: `res_img_texto` solo se consulta cuando la pregunta pide referencia visual (`imagen`, `figura`, `foto`, `microfotografia`, `laminilla`) o `mostrar_imagenes` esta activo.

2. Filtro por fuente dominante en texto puro.
- En `_nodo_filtrar_contexto()`, para modo texto se calcula la fuente dominante entre los primeros resultados.
- Si una fuente domina claramente, resultados de otra fuente solo se conservan si tienen coincidencia fuerte con keywords de la consulta.
- Objetivo: evitar cruces `arch3.pdf` ↔ `arch4.pdf` cuando la consulta es especifica.

3. Limite de contexto final en texto puro.
- Antes: el LLM y RAGAS recibian hasta 10 contextos validos.
- Ahora: texto puro usa como maximo 6 contextos finales despues del filtro.

## Criterios de aceptacion

Aceptar el ajuste si:
- `eval_reliability.py` sigue pasando 5/5.
- `contexto_suficiente_pct` se mantiene alto.
- `recall_at_5` no cae mas de aproximadamente 10 puntos relativos.
- Se reducen cruces evidentes entre arteria y testiculo en `detalle[].contextos`.
- En RAGAS chico, `answer_relevancy` y `faithfulness` no caen de forma importante.

Revertir o relajar si:
- El sistema empieza a responder que un tema no esta disponible cuando si esta en el manual.
- `recall_at_5` cae fuerte.
- Preguntas testiculares o arteriales pierden paginas esperadas sistematicamente.

## Protocolo de evaluacion post-cambio

1. Validar sintaxis:
```bash
python3 -c "compile(open('qdrant-histo.py', encoding='utf-8').read(), 'qdrant-histo.py', 'exec')"
python3 -m py_compile eval_reliability.py evaluar_ragas.py
```

2. Levantar API si hace falta:
```bash
npm run dev
```

3. Smoke barato:
```bash
python3 eval_reliability.py --base-url http://localhost:10007 --set eval_set_basico.json --output eval_reliability_report.json
```

4. Retrieval sin juez LLM:
```bash
uv run python evaluar_ragas.py --no-ragas
```

5. RAGAS chico:
```bash
uv run python evaluar_ragas.py --solo-ragas --limit 1
```

## Resultado post-cambio 1

Fecha: 2026-05-25

Cambios activos:
- `res_img_texto` desactivado en texto puro salvo pedido visual explicito.
- Contexto final de texto puro limitado a 6 bloques.
- Filtro suave por fuente dominante.

Smoke API:
- Comando: `python3 eval_reliability.py --base-url http://localhost:10007 --set eval_set_basico.json --output eval_reliability_report.json`
- Resultado: 5/5 OK.

Retrieval sin juez LLM:
- Comando: `uv run python evaluar_ragas.py --no-ragas`
- `tema_valido_pct`: 100.0
- `contexto_suficiente_pct`: 100.0
- `avg_resultados_validos`: 6.0
- `avg_similitud_dominio`: 0.6564
- `recall_at_5`: 0.7847

Comparacion contra baseline:
- Contextos promedio: 10.0 -> 6.0.
- Recall@5: 0.7569 -> 0.7847.
- Contexto suficiente: se mantiene 100%.
- El log confirma `ImgTxt=0` en texto puro y aplicacion del filtro por fuente dominante en casos con cruces.

Lectura:
- El ajuste reduce ruido enviado al LLM sin perdida de cobertura en esta evaluacion.
- El resultado cumple los criterios de aceptacion iniciales.
- Falta medir RAGAS chico post-cambio si se quiere estimar impacto en `faithfulness`, `answer_relevancy` y `context_precision`.

## Resultado post-cambio 2: metrica estricta fuente+pagina

Fecha: 2026-05-25

Cambio de evaluacion:
- Se agrego `fuente_esperada` al golden set.
- `recall_at_5` ahora mide coincidencia estricta `fuente + pagina`.
- Se conserva la metrica antigua como `recall_at_5_pagina`.
- Se agregaron contadores de ruido por fuente: `fuera_fuente_esperada_at_5`, `fuente_dominante_top_5`, `fuente_dominante_correcta_pct`.

Retrieval sin juez LLM:
- Comando: `uv run python evaluar_ragas.py --no-ragas`
- `tema_valido_pct`: 100.0
- `contexto_suficiente_pct`: 100.0
- `avg_resultados_validos`: 6.0
- `avg_similitud_dominio`: 0.6103
- `recall_at_5_fuente_pagina`: 0.7569
- `recall_at_5_pagina`: 0.7569
- `avg_fuera_fuente_esperada_at_5`: 0.08
- `fuente_dominante_correcta_pct`: 100.0

Lectura:
- La metrica estricta confirma que casi no hay mezcla de PDFs en top 5.
- El unico ruido de fuente observado fue bajo: 0.08 resultados fuera de fuente esperada por pregunta.
- El conteo de temas extraidos vario entre corridas (`95` en una corrida anterior, `47` en esta). Esto puede mover similitudes y ordenamientos, por lo que conviene estabilizar el temario antes de seguir afinando ranking.

## Cambio post-cambio 3: cache de temario

Fecha: 2026-05-25

Archivo: `qdrant-histo.py`

Cambio:
- `ExtractorTemario.extraer_temario()` ahora usa `temario_histologia.json` como cache local.
- Se agrego `temario_histologia.sha256` para invalidar la cache si cambia el corpus PDF.
- Si existe una cache antigua sin hash, se carga una vez y se crea el hash actual.

Validacion:
- Sintaxis OK: `python3 -m py_compile qdrant-histo.py evaluar_ragas.py`.
- Corrida corta OK: `uv run python evaluar_ragas.py --limit 1 --no-ragas`.
- Log esperado confirmado: `✅ Temario desde cache: 47 temas`.

Nota operativa:
- La corrida corta sobrescribio temporalmente `reporte_ragas.json` con 1 pregunta.
- Se intento regenerar el reporte completo, pero Groq corto por cuota diaria: `TPD Limit 500000, Used 499030`.
- Repetir `uv run python evaluar_ragas.py --no-ragas` cuando resetee la cuota para dejar `reporte_ragas.json` completo otra vez.

## Cambio post-cambio 4: activacion visual selectiva

Fecha: 2026-05-25

Archivo: `qdrant-histo.py`

Problema:
- Desactivar `res_img_texto` en todo texto puro reducia ruido, pero podia perder efectividad en preguntas de reconocimiento histologico que no usan explicitamente la palabra `imagen`.

Cambio:
- `res_img_texto` sigue apagado para preguntas conceptuales generales.
- Ahora se activa tambien en consultas con patrones de reconocimiento/observacion visual:
  - `se observa`, `se reconoce`, `se identifica`, `se ve`;
  - `como se observa/reconoce/identifica/ve`;
  - `aspecto`, `morfologia`, `corte`, `tincion`, `lamina`, `preparado`, `campo`, `detalle histologico`.
- Cuando se activa por este criterio, el log muestra: `Consulta de reconocimiento visual: se incluye texto de imágenes`.

Validacion:
- Sintaxis OK: `python3 -m py_compile qdrant-histo.py evaluar_ragas.py`.
- Evaluacion completa pendiente hasta que resetee la cuota Groq.

Lectura:
- Este cambio recupera soporte para captions/textos de imagen cuando la pregunta es visual.
- Mantiene la reduccion de ruido para preguntas teoricas como capas, componentes, funciones o diferencias generales.

## Cambio post-cambio 5: filtro estricto por fuente en consultas especificas

Fecha: 2026-05-25

Motivo:
- RAGAS chico con `--solo-ragas --limit 3` dio `context_precision: 0.6556` y `faithfulness: 0.7000`.
- El problema estuvo concentrado en la pregunta sobre caracteristicas del musculo liso de la tunica media.
- En esa pregunta entro un contexto de `arch4.pdf`: `Imagen 21: Celula peritubular`, por coincidencias lexicas como `fusiforme`, `musculares` y `lisas`.
- Ese contexto es biologicamente relacionado, pero incorrecto para una pregunta de arteria muscular (`arch3.pdf`).

Cambio:
- `_filtrar_contexto_texto_por_fuente()` ahora detecta consultas con anclas arteriales (`arteria`, `tunica`, `media`, `adventicia`, `endotelio`, `elastica`, `vaso`) o testiculares (`testiculo`, `seminifero`, `Sertoli`, `Leydig`, etc.).
- Si la fuente dominante coincide con esa familia (`arch3` para arteria, `arch4` para testiculo), descarta resultados de otras fuentes en vez de conservarlos por keyword match.
- El filtro suave anterior se mantiene para consultas menos especificas.

Validacion:
- Sintaxis OK: `python3 -m py_compile qdrant-histo.py evaluar_ragas.py`.
- Pendiente regenerar `reporte_ragas.json` y repetir RAGAS chico cuando haya cuota suficiente.

Resultado RAGAS chico posterior:
- `faithfulness`: 0.8376
- `answer_relevancy`: 0.5889
- `context_precision`: 0.8833
- `context_recall`: 0.6667
- Lectura: la precision de contexto subio fuerte y la pregunta de tunica media quedo corregida, pero la pregunta sobre lamina elastica interna perdio la pagina 2 y por eso RAGAS marco `answer_relevancy=0` y `context_recall=0`.

## Cambio post-cambio 6: fallback textual para estructuras especificas

Fecha: 2026-05-25

Motivo:
- En preguntas visuales/de reconocimiento, captions de imagen pueden rankear arriba y desplazar el chunk textual exacto.
- Caso observado: `Como se reconoce la lamina elastica interna...` recupero solo paginas de `arch3.pdf`, pero no la pagina 2, que contiene la frase clave `linea ondulada que se tiñe de color rosa translucido`.

Cambio:
- En `busqueda_hibrida()`, cuando `incluir_imagenes_texto=True` y la consulta contiene estructuras especificas multi-palabra o anclas como `lamina`, `tunica`, `Sertoli`, `Leydig`, se ejecuta tambien `busqueda_chunks_por_texto()`.
- Esto fuerza un fallback textual exacto sin volver a abrir globalmente el ruido de imagenes.

Validacion:
- Sintaxis OK: `python3 -m py_compile qdrant-histo.py evaluar_ragas.py`.
- Pendiente repetir `uv run python evaluar_ragas.py --no-ragas` y `uv run python evaluar_ragas.py --solo-ragas --limit 3`.

## Proximas mejoras sugeridas

- Cachear o versionar el temario extraido por PDF para reducir variabilidad entre corridas.
- Regenerar `reporte_ragas.json` completo cuando resetee la cuota Groq.
- Medir que consultas visuales ahora muestran `ImgTxt>0` y consultas conceptuales mantienen `ImgTxt=0`.
- Repetir `uv run python evaluar_ragas.py --no-ragas` y luego `uv run python evaluar_ragas.py --solo-ragas --limit 3` para verificar que la pregunta de tunica media ya no recupere `arch4.pdf`.
- Verificar que la pregunta de lamina elastica interna vuelva a recuperar `arch3.pdf` pagina 2.
- Ampliar golden set a 30-50 preguntas.

## Cambio post-cambio 7: payloads estructurados livianos

Fecha: 2026-05-25

Motivo:
- Las reglas por palabras sueltas son utiles como parche, pero no escalan.
- El siguiente paso robusto es representar cada chunk/imagen con metadatos estructurados consultables por payload.

Cambio:
- `ExtractorEntidades` ahora agrega metadatos deterministas ademas de la extraccion LLM:
  - `dominios`
  - `organos`
  - `celulas`
  - `temas`
- `upsert_chunk()` guarda esos campos en Qdrant.
- `busqueda_por_entidades()` puede filtrar tambien por esos campos.
- Se agregaron indices de payload para esos campos en `histo_chunks` y `histo_imagenes`.
- `_filtrar_contexto_texto_por_fuente()` ahora puede usar `dominios` extraidos de la consulta (`vasos sanguineos`, `testiculo`) como senal estructurada, no solo tokens hardcodeados.

Backfill:
- Se agrego `backfill_metadata_payloads.py` para actualizar payloads existentes sin reembedding ni reindexado de PDFs.
- Ejecucion: `uv run python backfill_metadata_payloads.py`.
- Resultado: `Payloads actualizados: chunks=42, imagenes=23`.

Validacion:
- Sintaxis OK: `python3 -m py_compile qdrant-histo.py evaluar_ragas.py backfill_metadata_payloads.py`.
- Verificacion manual Qdrant: el chunk de `arch3.pdf` pagina 2 con `lamina elastica interna` quedo con `dominios=['vasos sanguineos']`, `temas=['capas arteriales', 'laminas elasticas']` y `estructuras=['tunica media', 'tunica adventicia', 'lamina elastica interna']`.

Lectura:
- Esto no reemplaza una ontologia completa organo->tejido->celula, pero reduce dependencia de reglas ad hoc por pregunta.
- El proximo paso es medir si mejora retrieval/RAGAS y luego ampliar el extractor a mas PDFs/temas.

## Cambio post-cambio 8: rollback parcial orientado a recall

Fecha: 2026-05-25

Motivo:
- RAGAS `--solo-ragas --limit 3` mostro que optimizar precision de contexto podia bajar `context_recall`.
- Para instalacion en FMED se prioriza no perder evidencia clave del manual.
- Caso critico: `lamina elastica interna` debe recuperar `arch3.pdf` pagina 2.

Cambios:
- Se relajo el filtro estricto por fuente: ya no descarta automaticamente otra fuente por reglas `arch3/arch4`; vuelve a ser filtro suave por fuente dominante + keywords.
- Se redujo la activacion visual selectiva a senales claras (`se observa`, `se reconoce`, `como se identifica`, `imagen`, `figura`, etc.). Se quitaron activadores demasiado amplios como `corte`, `tincion`, `lamina`, `aspecto`, `morfologia`.
- `busqueda_chunks_por_texto()` ahora ordena resultados por score textual antes de devolverlos.
- Matches multi-palabra exactos reciben score alto (`0.95`).
- El fallback textual por keywords se ejecuta cuando hay estructuras especificas, y filtra por `dominios` si la consulta los tiene (`vasos sanguineos` vs `testiculo`).

Validacion:
- Sintaxis OK: `python3 -m py_compile qdrant-histo.py evaluar_ragas.py backfill_metadata_payloads.py`.
- `uv run python evaluar_ragas.py --limit 3 --no-ragas`:
  - `contexto_suficiente_pct`: 100.0
  - `avg_resultados_validos`: 6.0
  - `recall_at_5_fuente_pagina`: 0.8056
  - `avg_fuera_fuente_esperada_at_5`: 0.0
  - `fuente_dominante_correcta_pct`: 100.0
- Casos criticos:
  - `lamina elastica interna`: `Recall@5 fuente+pagina = 1.00`.
  - `musculo liso de tunica media`: sin ruido de `arch4.pdf`, `Recall@5 fuente+pagina = 0.67`.

Lectura:
- Esta version vuelve a priorizar `context_recall` y evidencia correcta.
- Las mejoras seguras se conservan: evaluacion fuente+pagina, cache de temario, payloads estructurados, backfill y documentacion.
- RAGAS `--limit 3` deberia mejorar respecto a la corrida donde `context_recall` caia por perder pagina 2.

Resultado RAGAS chico posterior:
- Comando: `uv run python evaluar_ragas.py --solo-ragas --limit 3`
- `faithfulness`: 0.7571
- `answer_relevancy`: 0.9076
- `context_precision`: 0.8736
- `context_recall`: 1.0000

Detalle:
- Capas de arteria muscular: `faithfulness=1.000`, `answer_relevancy=0.902`, `context_precision=0.950`, `context_recall=1.000`.
- Lamina elastica interna: `faithfulness=0.571`, `answer_relevancy=0.989`, `context_precision=0.817`, `context_recall=1.000`.
- Musculo liso de tunica media: `faithfulness=0.700`, `answer_relevancy=0.833`, `context_precision=0.854`, `context_recall=1.000`.

Lectura:
- Esta es la mejor configuracion reciente para instalacion: preserva evidencia completa (`context_recall=1.0`) y mantiene alta precision de contexto (`context_precision=0.8736`).
- La principal debilidad restante es `faithfulness` en la pregunta de lamina elastica interna, probablemente por redaccion del generador mas que por falta de contexto.
- No seguir ajustando retrieval antes de la instalacion salvo bug critico; priorizar smoke test, frontend y documentacion operativa.
- Probar `gpt-4o-mini` como juez RAGAS si se necesita context precision confiable y rapido.
- Luego evaluar payloads estructurados y chunking por pagina/imagen en coleccion experimental.

## Resultado final RAGAS completo con gpt-4o-mini

Fecha: 2026-05-25

Comando:
```bash
RAGAS_MAX_WORKERS=2 uv run python evaluar_ragas.py --solo-ragas --limit 12
```

Juez:
- `gpt-4o-mini` via OpenAI, usado solo para evaluacion RAGAS.

Resultado:
- `faithfulness`: 0.8735
- `answer_relevancy`: 0.7110
- `context_precision`: 0.8027
- `context_recall`: 0.8917

Notas operativas:
- Duracion aproximada: 1h11m.
- Hubo varios `APIConnectionError` durante la corrida.
- Hubo algunos valores `nan` por pregunta/metrica.
- Por eso el resultado se considera util para comparacion, pero no perfecto como medicion final absoluta.

Lectura:
- La version actual mejora fuertemente `faithfulness` y `context_precision` respecto de `main` historico.
- `answer_relevancy` quedo mas bajo que `main` y debe revisarse manualmente con preguntas demo.
- Para instalacion se recomienda congelar retrieval y priorizar smoke test, frontend, README/checklist y prueba manual.

Documento comparativo:
- Ver `docs/vuelta_original_vs_actual.md`.

## Cambio post-cambio 9: seleccion por indices y ajuste conservador de prompt

Fecha: 2026-05-25

Motivo:
- El RAGAS completo con `gpt-4o-mini` mostro `answer_relevancy` bajo en preguntas puntuales, especialmente indices humanos `1`, `5` y `9`.
- El retrieval ya estaba suficientemente estable, por lo que se decidio no tocar ranking y probar solo generacion.

Cambios:
- `evaluar_ragas.py` ahora acepta `--indices 1,5,9` para evaluar preguntas especificas del golden set.
- `--solo-ragas --indices` detecta si el `reporte_ragas.json` ya esta filtrado y evita aplicar dos veces el filtro.
- El prompt de texto en `qdrant-histo.py` ahora pide responder primero la pregunta en 1 a 3 frases, evitar informacion general no solicitada y no decir que falta informacion si el contexto contiene evidencia directa.
- Se conserva la cautela: no inventar, responder solo hasta donde permite el manual y derivar a docente/bibliografia oficial si la informacion es insuficiente para decisiones academicas, diagnosticas o clinicas.

Validacion:
- Sintaxis OK: `python3 -m py_compile evaluar_ragas.py qdrant-histo.py`.
- Retrieval focalizado:
```bash
uv run python evaluar_ragas.py --no-ragas --indices 1,5,9
```
- Resultado retrieval focalizado:
  - `tema_valido_pct`: 100.0
  - `contexto_suficiente_pct`: 100.0
  - `avg_resultados_validos`: 6.0
  - `recall_at_5_fuente_pagina`: 0.9167
  - `avg_fuera_fuente_esperada_at_5`: 0.0
  - `fuente_dominante_correcta_pct`: 100.0

RAGAS focalizado:
```bash
RAGAS_MAX_WORKERS=2 uv run python evaluar_ragas.py --solo-ragas --indices 1,5,9
```

Resultado RAGAS focalizado:
- `faithfulness`: 0.9000
- `answer_relevancy`: 0.7513
- `context_precision`: 0.7870
- `context_recall`: 0.8333

Detalle relevante:
- Pregunta 1 subio en `answer_relevancy` frente al RAGAS completo anterior: `0.000` -> `0.901`.
- Pregunta 5 quedo con `context_precision=1.000` y `context_recall=1.000`, pero con `answer_relevancy=nan` por error del juez.
- Pregunta 9, Sertoli, sigue siendo el caso mas debil: `answer_relevancy=0.602`, `context_precision=0.411`, `context_recall=0.667`.

Notas operativas:
- Durante RAGAS hubo varios `APIConnectionError` y valores `nan`; la medicion es util como senal, pero no debe tratarse como valor absoluto perfecto.
- El ajuste de prompt parece corregir el falso negativo de relevancia en la pregunta 1 sin tocar retrieval.
- El siguiente ajuste, si se hace, deberia ser focalizado en Sertoli y revisando manualmente la respuesta/contextos antes de cambiar mas reglas globales.

## Cambio post-cambio 10: fallback visual con identificacion ya disponible

Fecha: 2026-05-26

Motivo:
- En consultas con imagen subida, el sistema podia identificar correctamente la referencia del manual mediante metadata (`estructura_identificada`), pero si el proveedor LLM fallaba por cuota se mostraba el error tecnico como texto principal.
- Caso observado: imagen identificada como `Imagen 17: Espermatide temprana`, mientras el mensaje principal decia que el proveedor estaba ocupado o sin cuota.

Cambio final aplicado:
- Archivo: `client/app.js`.
- Funcion: `normalizeAssistantResponse()`.
- El fallback por error de proveedor/cuota ahora revisa primero `metadata.estructura_identificada`, sin exigir que `metadata.imagenes_recuperadas` tenga elementos.
- Si existe identificacion, el frontend muestra un mensaje amigable: `La imagen fue asociada con la referencia del manual: <estructura_identificada>. La explicacion textual completa no se pudo generar porque el modelo esta temporalmente sin cuota.`
- Si ademas hay imagen recuperada con `etiqueta`, se combina `etiqueta` + `estructura_identificada`.
- Si no hay identificacion pero si imagenes recuperadas, se conserva el fallback generico anterior.

Cambios probados y revertidos:
- Se probo un fallback backend que reintentaba sin imagenes cuando el modelo no soportaba input visual.
- Se probo activar `mostrar_imagenes=True` al subir imagen nueva.
- Ambos cambios se revirtieron por pedido del usuario para mantener el alcance minimo.

Validacion:
- Sintaxis OK: `node -c client/app.js`.

Impacto:
- Mejora UX ante cuota agotada sin modificar retrieval ni evaluacion RAGAS.
- Conserva la identificacion ya calculada por el sistema y evita que el alumno vea un error crudo cuando ya hay una referencia util.
- No afecta `qdrant-histo.py`, `server.py`, Qdrant, embeddings ni prompts de generacion.

## Cambio post-cambio 11: router hibrido para intencion visual de retrieval

Fecha: 2026-05-26

Motivo:
- La activacion visual selectiva por palabras exactas podia ser demasiado fragil.
- Si el usuario no usaba una palabra prevista, escribia con otra formulacion o hacia un pedido ambiguo (`que hay aca`, `esto que es`, `que estructura corresponde`), el sistema podia no incluir captions/imagenes del manual en retrieval textual.
- Volver a activar imagenes siempre no era deseable, porque ya se habia observado ruido de captions desplazando texto exacto.

Cambio aplicado:
- Archivo: `qdrant-histo.py`.
- Se agrego `_detectar_retrieval_visual_por_reglas()` con salida tri-state:
  - `True`: activar captions/imagenes.
  - `False`: consulta claramente conceptual/textual.
  - `None`: consulta no claramente visual ni conceptual; se considera ambigua.
- Se agrego `_detectar_retrieval_visual()` como router hibrido:
  - usa reglas deterministicas primero;
  - si la consulta queda ambigua, llama a un LLM clasificador que responde solo `VISUAL` o `TEXTO`;
  - si el clasificador falla por cuota, usa fallback seguro: visual solo si hay imagen activa/subida.
- `_nodo_buscar_qdrant()` ahora usa este router para definir `incluir_imagenes_texto`.

Reglas deterministicas:
- Activan visual directamente ante senales claras como `imagen`, `figura`, `foto`, `microfotografia`, `laminilla`, `se observa`, `que se ve`, `que muestra`, `que estoy viendo`, `identifica esto`, `preparado histologico`, `campo histologico`.
- Mantienen texto en consultas conceptuales como `funcion`, `caracteristicas`, `componentes`, `capas`, `diferencias`, `que es`, `define`, `explica`.
- Toda consulta que no matchea una señal visual clara ni una señal conceptual clara queda como ambigua y delega al LLM. Ejemplos: `que hay aca`, `esto que es`, `que estructura corresponde`, `esta preparacion`.

Validacion:
- Sintaxis OK: `python3 -m py_compile qdrant-histo.py`.
- Sintaxis frontend OK: `node -c client/app.js`.

Impacto esperado:
- Mejora la deteccion de intencion visual sin volver a abrir imagenes/captions para todas las consultas.
- Reduce el riesgo de perder consultas visuales por mala redaccion o sinonimos.
- Mantiene bajo costo porque solo usa LLM en casos ambiguos.

## Cambio post-cambio 12: corte rapido ante cuota agotada del LLM

Fecha: 2026-05-26

Motivo:
- Cuando el proveedor LLM ya estaba sin cuota, la consola mostraba el problema rapidamente pero la UI tardaba mucho en recibir el mensaje.
- La causa era que `invoke_con_reintento()` e `invoke_con_reintento_sync()` trataban cuota agotada como un error reintentable, esperando `LLM_RETRY_BASE_SECONDS` antes de devolver error.
- Ademas, varios nodos podian intentar llamadas LLM posteriores, acumulando demora.

Cambio aplicado:
- Archivo: `qdrant-histo.py`.
- Se agregaron helpers globales:
  - `_mensaje_cuota_modelo()`.
  - `_es_error_cuota_agotada()`.
  - `_cuota_modelo_bloqueada()`.
  - `_marcar_cuota_modelo_bloqueada()`.
- Si el error contiene senales de cuota diaria agotada (`tokens per day`, `TPD`, `daily`, `quota exceeded`, `insufficient_quota`, `RESOURCE_EXHAUSTED`, `sin cuota`, `cupo diario`), se corta inmediatamente sin dormir ni reintentar.
- Al detectar cuota agotada, se activa un bloqueo temporal en memoria para nuevas llamadas LLM.
- Duracion configurable: `LLM_QUOTA_BLOCK_SECONDS`, default `300` segundos.
- Los reintentos se conservan para errores transitorios como `503`, `timeout` o conexion.

Validacion:
- Sintaxis OK: `python3 -m py_compile qdrant-histo.py`.
- Sintaxis frontend OK: `node -c client/app.js`.

Impacto esperado:
- La UI deberia mostrar el mensaje de cuota agotada mucho mas rapido.
- Se evita gastar tiempo en reintentos inutiles cuando el cupo diario ya esta agotado.
- Se reducen cascadas de llamadas LLM fallidas durante el periodo de bloqueo.
