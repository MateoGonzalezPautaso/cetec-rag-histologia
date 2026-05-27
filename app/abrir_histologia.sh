#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/home/alenk/Escritorio/CETEC/histo-test-qdrant-vuelta"
LOG_FILE="/tmp/opencode/histo-vuelta-server.log"
URL="http://localhost:10007"

cd "$APP_DIR"

if curl -fsS "$URL/api/status" >/dev/null 2>&1; then
  xdg-open "$URL" >/dev/null 2>&1 || true
  exit 0
fi

mkdir -p "$(dirname "$LOG_FILE")"
nohup npm run dev > "$LOG_FILE" 2>&1 &

for _ in $(seq 1 90); do
  if curl -fsS "$URL/api/status" >/dev/null 2>&1; then
    xdg-open "$URL" >/dev/null 2>&1 || true
    exit 0
  fi
  sleep 2
done

if command -v zenity >/dev/null 2>&1; then
  zenity --error --title="RAG Histología" --text="No se pudo iniciar el asistente. Revisá el log:\n$LOG_FILE"
else
  xdg-open "$LOG_FILE" >/dev/null 2>&1 || true
fi
