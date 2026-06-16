#!/usr/bin/env python3
"""Evaluacion basica de confiabilidad contra la API local.

Uso:
    python3 eval_reliability.py --base-url http://localhost:10007 --set eval_set_basico.json

El objetivo no es reemplazar RAGAS, sino tener una prueba barata y repetible
para detectar regresiones antes de cambiar retrieval, prompts o modelos visuales.
"""

from __future__ import annotations

import argparse
import json
import re
import time
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path


def _norm(text: str) -> str:
    text = text.lower()
    text = "".join(
        char for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )
    return text


def _post_json(url: str, payload: dict, timeout: int) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def evaluar(base_url: str, eval_set: list[dict], timeout: int) -> list[dict]:
    resultados = []
    for caso in eval_set:
        inicio = time.time()
        error = None
        respuesta = ""
        try:
            data = _post_json(
                f"{base_url.rstrip('/')}/api/chat",
                {"query": caso.get("query", "")},
                timeout=timeout,
            )
            respuesta = data.get("respuesta", "")
        except Exception as exc:
            # Cualquier fallo en un caso (red, JSON inválido, clave faltante, etc.)
            # se registra como error de ese caso, sin abortar la corrida completa.
            error = str(exc)

        respuesta_norm = _norm(respuesta)
        expected_terms = caso.get("expected_terms", [])
        found_terms = [term for term in expected_terms if _norm(term) in respuesta_norm]
        citation_ok = (
            not caso.get("requires_citation")
            or "[manual:" in respuesta_norm
            or "fuente:" in respuesta_norm
            or re.search(r"\[[^\]]*\.pdf[^\]]*\]", respuesta_norm) is not None
        )
        no_error = error is None and not respuesta_norm.startswith("error:")
        term_recall = len(found_terms) / max(len(expected_terms), 1)
        passed = no_error and citation_ok and term_recall >= 0.5

        resultados.append({
            "id": caso.get("id"),
            "query": caso.get("query"),
            "passed": passed,
            "latency_s": round(time.time() - inicio, 2),
            "citation_ok": citation_ok,
            "term_recall": round(term_recall, 2),
            "found_terms": found_terms,
            "error": error,
            "respuesta_preview": respuesta[:300],
        })
        estado = "OK" if passed else "FAIL"
        print(f"{estado} {caso.get('id')} | cita={citation_ok} | terms={term_recall:.2f}")
    return resultados


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:10007")
    parser.add_argument("--set", default="eval_set_basico.json")
    parser.add_argument("--output", default="eval_reliability_report.json")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    eval_path = Path(args.set)
    eval_set = json.loads(eval_path.read_text(encoding="utf-8"))
    resultados = evaluar(args.base_url, eval_set, args.timeout)
    resumen = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "base_url": args.base_url,
        "n": len(resultados),
        "passed": sum(1 for item in resultados if item["passed"]),
        "resultados": resultados,
    }
    Path(args.output).write_text(json.dumps(resumen, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Reporte guardado en {args.output}")
    return 0 if resumen["passed"] == resumen["n"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
