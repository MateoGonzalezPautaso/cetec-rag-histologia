#!/usr/bin/env bash
# launch.sh — Lanzador para el acceso directo del escritorio.
# Si el servidor ya está corriendo abre el navegador directamente.
# Si no, lo inicia en primer plano y abre el navegador cuando esté listo.
set -euo pipefail

export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

PORT=10007
URL="http://localhost:${PORT}"
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

open_browser() {
    launch_detached() {
        if command -v setsid >/dev/null 2>&1; then
            setsid -f "$@" >/dev/null 2>&1
        else
            nohup "$@" >/dev/null 2>&1 &
        fi
    }

    for browser in google-chrome-stable google-chrome chromium-browser chromium firefox brave-browser microsoft-edge; do
        if command -v "$browser" >/dev/null 2>&1; then
            launch_detached "$browser" --new-window "${URL}"
            return 0
        fi
    done

    if command -v sensible-browser >/dev/null 2>&1; then
        launch_detached sensible-browser "${URL}"
        return 0
    fi

    if command -v gio >/dev/null 2>&1; then
        gio open "${URL}" >/dev/null 2>&1 && return 0
    fi

    xdg-open "${URL}" >/dev/null 2>&1 || open "${URL}" >/dev/null 2>&1 || {
        echo "⚠️ No pude abrir el navegador automáticamente. Abrí manualmente: ${URL}"
        return 1
    }
}

echo ""
echo "🔬 RAG Histología — verificando estado..."
echo ""

if curl -fsS "${URL}/api/status" > /dev/null 2>&1; then
    echo "✅ El servidor ya está corriendo."
    echo "🌐 Abriendo navegador en ${URL}..."
    open_browser
    sleep 2
else
    echo "🚀 Iniciando servidor RAG Histología..."
    echo "   (cerrá esta ventana con Ctrl+C para detenerlo)"
    echo ""

    # Abrir el navegador en cuanto el servidor responda
    (
        while ! curl -fsS "${URL}/api/status" > /dev/null 2>&1; do
            sleep 1
        done
        echo "✅ Servidor listo. Abriendo navegador..."
        open_browser
    ) &

    cd "${APP_DIR}"
    uv run uvicorn server:app --host 0.0.0.0 --port "${PORT}"

    echo ""
    echo "🛑 Servidor detenido."
    read -rp "Presioná Enter para cerrar esta ventana..."
fi
