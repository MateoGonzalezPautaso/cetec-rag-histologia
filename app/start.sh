#!/usr/bin/env bash
# start.sh — Inicia el servidor RAG Histología
# Uso: ./start.sh [--port 10007] [--no-browser]
set -euo pipefail

# ── Configuración ─────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PORT=10007
OPEN_BROWSER=true
URL="http://localhost:${PORT}"

# ── Argumentos ────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --port)     PORT="$2"; URL="http://localhost:${PORT}"; shift 2 ;;
        --no-browser) OPEN_BROWSER=false; shift ;;
        *) echo "Uso: $0 [--port N] [--no-browser]"; exit 1 ;;
    esac
done

LOG_FILE="/tmp/rag-histologia-${PORT}.log"

cd "$SCRIPT_DIR"

# ── Colores ───────────────────────────────────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC}  $1"; }
fail() { echo -e "${RED}✗${NC} $1"; }

echo ""
echo "🔬 RAG Histología — iniciando..."
echo ""

# ── Extender PATH para uv (instalado por el script oficial de astral.sh) ──
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

# ── Si ya está corriendo, solo abrir el browser ───────────────────────
if curl -fsS "${URL}/api/status" >/dev/null 2>&1; then
    ok "El servidor ya está corriendo en ${URL}"
    if $OPEN_BROWSER; then
        xdg-open "$URL" >/dev/null 2>&1 || open "$URL" >/dev/null 2>&1 || true
    fi
    exit 0
fi

# ── Verificar dependencias ────────────────────────────────────────────
echo "Verificando dependencias..."

if ! command -v uv &>/dev/null; then
    fail "uv no está instalado."
    echo "  Instalarlo con: curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo "  Luego cerrar y volver a abrir la terminal."
    exit 1
fi
ok "uv $(uv --version 2>/dev/null | head -1)"

if ! command -v python3 &>/dev/null || ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" 2>/dev/null; then
    fail "Se requiere Python 3.10 o superior."
    exit 1
fi
ok "Python $(python3 --version)"

if ! command -v tesseract &>/dev/null; then
    warn "Tesseract no encontrado — la extracción de texto en imágenes de PDFs no funcionará."
    warn "Instalar con: sudo apt install tesseract-ocr tesseract-ocr-spa"
fi

if ! command -v pdftoppm &>/dev/null; then
    warn "Poppler no encontrado — la extracción de imágenes de PDFs no funcionará."
    warn "Instalar con: sudo apt install poppler-utils"
fi

# ── Verificar .env ────────────────────────────────────────────────────
echo ""
echo "Verificando configuración..."

if [[ ! -f ".env" ]]; then
    fail "Archivo .env no encontrado en ${SCRIPT_DIR}/.env"
    if [[ -f "${SCRIPT_DIR}/../.env.example" ]]; then
        echo "  Crear con: cp ${SCRIPT_DIR}/../.env.example ${SCRIPT_DIR}/.env"
        echo "  Luego completar las claves en ${SCRIPT_DIR}/.env"
    else
        echo "  Crear ${SCRIPT_DIR}/.env con: GROQ_API_KEY, QDRANT_URL, QDRANT_KEY, HF_TOKEN"
    fi
    exit 1
fi

missing_keys=()
for key in GROQ_API_KEY QDRANT_URL QDRANT_KEY HF_TOKEN; do
    val=$(grep -E "^${key}=" .env 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'")
    if [[ -z "$val" || "$val" == "tu-"* || "$val" == "tu_"* ]]; then
        missing_keys+=("$key")
    fi
done

if [[ ${#missing_keys[@]} -gt 0 ]]; then
    fail "Las siguientes claves faltan o tienen valor de ejemplo en .env:"
    for k in "${missing_keys[@]}"; do echo "    - $k"; done
    exit 1
fi
ok ".env con claves configuradas"

# ── Verificar carpeta pdf/ ────────────────────────────────────────────
if [[ ! -d "pdf" ]] || [[ -z "$(ls -A pdf/*.pdf 2>/dev/null)" ]]; then
    warn "No hay PDFs en pdf/ — el sistema iniciará pero sin contenido para consultar."
    warn "Agregar PDFs con: cp tu_manual.pdf ${SCRIPT_DIR}/pdf/"
    mkdir -p pdf
fi

# ── Instalar dependencias Python ──────────────────────────────────────
echo ""
echo "Instalando dependencias Python..."
uv sync
ok "Dependencias instaladas"

# ── Iniciar servidor en background ───────────────────────────────────
echo ""
echo "Iniciando servidor (log: ${LOG_FILE})..."

nohup uv run uvicorn server:app --host 0.0.0.0 --port "${PORT}" \
    > "$LOG_FILE" 2>&1 &
SERVER_PID=$!
echo "  PID: ${SERVER_PID}"

# ── Esperar a que esté listo ──────────────────────────────────────────
echo "  Esperando que el servidor cargue los modelos (puede tardar 1-3 min)..."
WAIT_SECONDS=180
READY=false
for i in $(seq 1 $WAIT_SECONDS); do
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        fail "El proceso del servidor terminó inesperadamente."
        echo ""
        echo "Últimas líneas del log:"
        tail -20 "$LOG_FILE"
        exit 1
    fi

    if curl -fsS "${URL}/api/status" >/dev/null 2>&1; then
        READY=true
        echo ""
        ok "Servidor listo en ${URL}"
        break
    fi

    if (( i % 15 == 0 )); then
        echo "  ...${i}s — aún cargando modelos..."
    fi
    sleep 1
done

if ! $READY; then
    fail "El servidor no respondió después de ${WAIT_SECONDS}s."
    echo "Deteniendo proceso..."
    kill "$SERVER_PID" 2>/dev/null || true
    echo "Revisar el log en: ${LOG_FILE}"
    exit 1
fi

# ── Crear acceso directo en el escritorio ────────────────────────────
DESKTOP_DIR=""
for candidate in "$HOME/Desktop" "$HOME/Escritorio"; do
    if [[ -d "$candidate" ]]; then
        DESKTOP_DIR="$candidate"
        break
    fi
done

if [[ -n "$DESKTOP_DIR" ]]; then
    SHORTCUT="${DESKTOP_DIR}/RAG Histología.desktop"
    cat > "$SHORTCUT" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=RAG Histología
Comment=Asistente de histología médica
Exec=bash -c 'cd "${SCRIPT_DIR}" && ./start.sh'
Terminal=true
Categories=Education;Science;
EOF
    chmod +x "$SHORTCUT"
    gio set "$SHORTCUT" metadata::trusted true 2>/dev/null || true
    ok "Acceso directo creado en: ${SHORTCUT}"
fi

# ── Abrir navegador ───────────────────────────────────────────────────
if $OPEN_BROWSER; then
    xdg-open "$URL" >/dev/null 2>&1 || open "$URL" >/dev/null 2>&1 || true
fi

echo ""
echo "  Frontend: ${URL}"
echo "  Estado:   ${URL}/api/status"
echo "  Log:      ${LOG_FILE}"
echo ""
echo "Para detener el servidor: kill ${SERVER_PID}"
echo ""
