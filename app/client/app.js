/**
 * RAG Histología Qdrant + A2UI — Frontend Logic
 * ==============================================
 * Chat client with image upload, markdown rendering, 
 * A2UI JSON visualization, and temario panel.
 */

const API_BASE = '';

// ── State ───────────────────────────────────────────────────────────
let pendingImageBase64 = null;
let pendingImageName = null;
let pendingImagePromise = null;  // resuelve cuando el FileReader terminó de leer
let isWaiting = false;

// Identificador de sesión por navegador. Aísla la conversación, la imagen
// activa y la memoria de cada usuario en el backend (evita fugas entre sesiones).
function getSessionId() {
    let sid = null;
    try {
        sid = localStorage.getItem('histo_session_id');
        if (!sid) {
            sid = (crypto.randomUUID && crypto.randomUUID()) ||
                  `s-${Date.now()}-${Math.random().toString(36).slice(2)}`;
            localStorage.setItem('histo_session_id', sid);
        }
    } catch {
        // localStorage deshabilitado: usamos un id efímero en memoria.
        sid = sid || `s-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    }
    return sid;
}

// ── DOM refs ────────────────────────────────────────────────────────
const messagesContainer = document.getElementById('messages-container');
const welcomeScreen = document.getElementById('welcome-screen');
const chatInput = document.getElementById('chat-input');
const sendBtn = document.getElementById('send-btn');
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const statusPanel = document.getElementById('status-panel');
let lastStatusData = null;

// ── Init ────────────────────────────────────────────────────────────
checkStatus();
setInterval(checkStatus, 15000);
document.addEventListener('paste', handlePasteImage);
closeTemario();

async function checkStatus() {
    if (!statusDot || !statusText) return;  // DOM no listo / ids renombrados
    try {
        const res = await fetch(`${API_BASE}/api/status`);
        const data = await res.json();
        lastStatusData = data;
        if (data.ready) {
            statusDot.classList.add('online');
            statusText.textContent = 'Sistema listo';
            if (data.imagen_activa) {
                statusText.textContent += ` · 📌 ${data.imagen_activa}`;
            }
            updateStatusPanel(data);
        } else {
            statusDot.classList.remove('online');
            statusText.textContent = data.error || 'Inicializando...';
            updateStatusPanel(data);
        }
    } catch {
        statusDot.classList.remove('online');
        statusText.textContent = 'Sin conexión';
        updateStatusPanel({
            ready: false,
            n_temas: 0,
            diagnostico: {
                sistema: 'Sin conexión',
                qdrant: 'No verificado',
                modelo: 'No verificado',
                cuota_modelo: 'No verificada',
            },
        });
    }
}

function updateStatusPanel(data) {
    const diag = data.diagnostico || {};
    setStatusText('diag-sistema', diag.sistema || (data.ready ? 'Sistema listo' : 'Inicializando'));
    setStatusText('diag-qdrant', diag.qdrant || 'No verificado');
    setStatusText('diag-modelo', diag.modelo || 'No verificado');
    setStatusText('diag-cuota', diag.cuota_modelo || 'No verificada');
    setStatusText('diag-temas', `${data.n_temas || 0} temas · ${data.device || 'sin dispositivo'}`);
}

function setStatusText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function toggleStatusPanel() {
    if (!statusPanel) return;
    if (lastStatusData) updateStatusPanel(lastStatusData);
    statusPanel.classList.toggle('visible');
}

document.addEventListener('click', (event) => {
    if (!statusPanel || !statusPanel.classList.contains('visible')) return;
    if (event.target.closest('.status-panel') || event.target.closest('.status-pill')) return;
    statusPanel.classList.remove('visible');
});

// ── Send message ────────────────────────────────────────────────────
async function sendMessage() {
    const query = chatInput.value.trim();
    if (!query || isWaiting) return;

    // Hide welcome
    if (welcomeScreen) welcomeScreen.style.display = 'none';

    // Add user message
    addMessage('user', query, pendingImageBase64);

    // Clear input
    chatInput.value = '';
    autoResize(chatInput);
    isWaiting = true;
    sendBtn.disabled = true;

    // Show typing
    const typingEl = showTyping();

    try {
        // Si hay una imagen todavía cargándose (FileReader async), esperamos
        // a que termine para no enviar la consulta sin la imagen adjunta.
        if (pendingImagePromise) {
            try { await pendingImagePromise; } catch { /* lectura falló: seguimos sin imagen */ }
        }

        const body = { query, session_id: getSessionId() };
        if (pendingImageBase64) {
            body.image_base64 = pendingImageBase64;
            body.image_filename = pendingImageName;
        }

        // Single request — avoid duplicate RAG execution
        const chatRes = await fetch(`${API_BASE}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });

        console.log("Response status:", chatRes.status);
        if (!chatRes.ok) {
            const err = await chatRes.json().catch(() => ({ detail: 'Error desconocido' }));
            console.error("Chat error:", err);
            addMessage('assistant', err.detail || friendlyClientError(chatRes.status));
        } else {
            const data = await chatRes.json();
            console.log("Chat data received:", data);
            data.respuesta = normalizeAssistantResponse(data.respuesta, data);
            addMessage('assistant', data.respuesta, null, data);
        }

    } catch (err) {
        addMessage('assistant', 'No pude conectarme con el asistente. Verificá que el servidor esté abierto e intentá nuevamente.');
    } finally {
        // Cleanup garantizado: aunque addMessage/render lancen, el input no
        // queda bloqueado (isWaiting=true) para siempre.
        removeTyping(typingEl);
        removeImage();
        isWaiting = false;
        sendBtn.disabled = false;
        checkStatus();
    }
}

function normalizeAssistantResponse(text, metadata) {
    const hasImages = metadata && metadata.imagenes_recuperadas && metadata.imagenes_recuperadas.length > 0;
    const lower = (text || '').toLowerCase();
    const isProviderError = lower.includes('proveedor del modelo')
        || lower.includes('sin cuota disponible')
        || lower.includes('rate limit')
        || lower.includes('error code: 429');

    if (isProviderError && metadata && metadata.estructura_identificada) {
        const estructura = metadata.estructura_identificada;
        const primeraImg = hasImages ? metadata.imagenes_recuperadas[0] : null;
        const etiqueta = primeraImg && primeraImg.etiqueta ? primeraImg.etiqueta : '';
        const referencia = etiqueta
            ? `${etiqueta}, ${estructura}`
            : estructura;
        return `La imagen fue asociada con la referencia del manual: ${referencia}. La explicación textual completa no se pudo generar porque el modelo está temporalmente sin cuota.`;
    }

    if (hasImages && isProviderError) {
        return 'Encontré imágenes del manual relacionadas con tu consulta. Te las muestro abajo; la explicación textual no se pudo generar porque el modelo está temporalmente ocupado.';
    }
    return text;
}

function friendlyClientError(status) {
    if (status === 503 || status === 429) {
        return 'El asistente está temporalmente ocupado. Probá de nuevo en unos minutos.';
    }
    return 'No pude completar la respuesta en este momento. Probá nuevamente.';
}

// ── Send chip ───────────────────────────────────────────────────────
function sendChip(el) {
    if (isWaiting) return;  // no pisar el input con texto que no se enviará
    chatInput.value = el.textContent;
    sendMessage();
}

// ── Keyboard ────────────────────────────────────────────────────────
function handleKeyDown(e) {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
}

function autoResize(el) {
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 120) + 'px';
}

// ── Image handling ──────────────────────────────────────────────────
function handleImageSelect(event) {
    const file = event.target.files[0];
    if (!file) return;

    setPendingImage(file);

    // Reset file input so same file can be selected again
    event.target.value = '';
}

function handlePasteImage(event) {
    if (!event.clipboardData || isWaiting) return;

    const items = Array.from(event.clipboardData.items || []);
    const imageItem = items.find((item) => item.type && item.type.startsWith('image/'));
    if (!imageItem) return;

    const file = imageItem.getAsFile();
    if (!file) return;

    event.preventDefault();
    const ext = file.type.split('/')[1] || 'png';
    const namedFile = new File([file], `portapapeles.${ext}`, { type: file.type });
    setPendingImage(namedFile);
    chatInput.focus();
}

function setPendingImage(file) {
    const reader = new FileReader();
    // Exponemos una promesa para que sendMessage pueda esperar a que la lectura
    // termine; si no, al enviar enseguida se mandaría la consulta sin la imagen.
    pendingImagePromise = new Promise((resolve, reject) => {
        reader.onload = (e) => {
            const base64Full = e.target.result;
            // Strip "data:image/xxx;base64," prefix
            pendingImageBase64 = base64Full.split(',')[1];
            pendingImageName = file.name;

            // Show preview
            document.getElementById('image-thumb').src = base64Full;
            document.getElementById('image-name').textContent = file.name;
            document.getElementById('image-size').textContent = formatBytes(file.size);
            document.getElementById('image-preview-bar').classList.add('visible');
            resolve();
        };
        reader.onerror = () => {
            pendingImageBase64 = null;
            pendingImageName = null;
            reject(reader.error);
        };
    });
    reader.readAsDataURL(file);
}

function removeImage() {
    pendingImageBase64 = null;
    pendingImageName = null;
    pendingImagePromise = null;
    document.getElementById('image-preview-bar').classList.remove('visible');
}

async function limpiarImagen() {
    try {
        await fetch(`${API_BASE}/api/imagen/limpiar`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ session_id: getSessionId() }),
        });
        removeImage();
        checkStatus();
    } catch { }
}

// ── Message rendering ───────────────────────────────────────────────
function addMessage(role, text, imageBase64 = null, metadata = null) {
    const wrapper = document.createElement('div');
    wrapper.className = `message ${role}`;

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';

    // Image thumbnail for user messages
    if (imageBase64 && role === 'user') {
        const img = document.createElement('img');
        img.className = 'message-image-preview';
        img.src = `data:image/png;base64,${imageBase64}`;
        bubble.appendChild(img);
    }

    // Render text
    if (role === 'assistant') {
        bubble.innerHTML += renderMarkdown(text);
        const support = buildSupportPanel(text, metadata);
        if (support) bubble.appendChild(support);
    } else {
        const p = document.createElement('p');
        p.textContent = text;
        bubble.appendChild(p);
    }

    // Image gallery from database (retrieved images)
    if (metadata && metadata.imagenes_recuperadas && metadata.imagenes_recuperadas.length > 0) {
        const gallery = document.createElement('div');
        gallery.className = 'image-gallery';

        const galleryTitle = document.createElement('div');
        galleryTitle.className = 'gallery-title';
        galleryTitle.textContent = `📸 Imágenes del manual (${metadata.imagenes_recuperadas.length})`;
        gallery.appendChild(galleryTitle);

        const galleryGrid = document.createElement('div');
        galleryGrid.className = 'gallery-grid';

        metadata.imagenes_recuperadas.forEach((img, idx) => {
            const item = document.createElement('div');
            item.className = 'gallery-item';

            const imgEl = document.createElement('img');
            imgEl.className = 'gallery-img';
            imgEl.src = img.url;
            imgEl.alt = img.etiqueta || img.nombre_archivo || `Imagen ${idx + 1}`;
            imgEl.loading = 'lazy';
            imgEl.onclick = () => openLightbox(img.url, img.etiqueta, img.caption);
            item.appendChild(imgEl);

            if (img.etiqueta || img.nombre_archivo) {
                const label = document.createElement('div');
                label.className = 'gallery-label';
                label.textContent = img.etiqueta || img.nombre_archivo;
                item.appendChild(label);
            }

            const ref = parseImageReference(img.nombre_archivo || img.url || '');
            if (ref) {
                const refEl = document.createElement('div');
                refEl.className = 'gallery-ref';
                refEl.textContent = ref;
                item.appendChild(refEl);
            }

            if (img.caption) {
                const caption = document.createElement('div');
                caption.className = 'gallery-caption';
                caption.textContent = img.caption.substring(0, 120) + (img.caption.length > 120 ? '...' : '');
                item.appendChild(caption);
            }

            const actions = document.createElement('div');
            actions.className = 'gallery-actions';
            const openBtn = document.createElement('button');
            openBtn.type = 'button';
            openBtn.textContent = 'Ampliar';
            openBtn.onclick = (e) => {
                e.stopPropagation();
                openLightbox(img.url, img.etiqueta || ref, img.caption);
            };
            actions.appendChild(openBtn);
            item.appendChild(actions);

            galleryGrid.appendChild(item);
        });

        gallery.appendChild(galleryGrid);
        bubble.appendChild(gallery);
    }

    wrapper.appendChild(bubble);

    // Metadata
    const meta = document.createElement('div');
    meta.className = 'message-meta';
    const now = new Date();
    meta.textContent = now.toLocaleTimeString('es-AR', { hour: '2-digit', minute: '2-digit' });

    if (metadata) {
        if (metadata.estructura_identificada) {
            meta.textContent += ` · 🏷️ ${metadata.estructura_identificada}`;
        }
        if (metadata.imagen_activa) {
            meta.textContent += ` · 📌 ${metadata.imagen_activa}`;
        }
        const tray = metadata.trayectoria || [];
        const finalNode = tray.find(t => t.tiempo_total !== undefined);
        if (finalNode) {
            meta.textContent += ` · ⏱️ ${finalNode.tiempo_total}s`;
        }
    }

    wrapper.appendChild(meta);
    messagesContainer.appendChild(wrapper);
    scrollToBottom();
}

function buildSupportPanel(text, metadata) {
    if (!text && !metadata) return null;

    const panel = document.createElement('div');
    panel.className = 'support-panel';

    const badges = document.createElement('div');
    badges.className = 'support-badges';

    const status = inferAnswerStatus(text || '');
    badges.appendChild(makeBadge(status.label, status.type));

    if (metadata && metadata.mostrar_imagenes) {
        badges.appendChild(makeBadge('Imágenes del manual', 'image'));
    }
    if (metadata && metadata.estructura_identificada) {
        badges.appendChild(makeBadge(`Identificado: ${metadata.estructura_identificada}`, 'info'));
    }

    panel.appendChild(badges);

    const fuentes = extractManualSources(text || '');
    if (fuentes.length > 0) {
        const sources = document.createElement('div');
        sources.className = 'source-strip';
        fuentes.forEach((fuente) => {
            const item = document.createElement('span');
            item.textContent = `Fuente: ${fuente}`;
            sources.appendChild(item);
        });
        panel.appendChild(sources);
    }

    return panel;
}

function makeBadge(label, type) {
    const badge = document.createElement('span');
    badge.className = `support-badge ${type}`;
    badge.textContent = label;
    return badge;
}

function inferAnswerStatus(text) {
    const lower = text.toLowerCase();
    if (lower.includes('no se encuentra en el manual') || lower.includes('no encontré')) {
        return { label: 'No encontrado en manual', type: 'missing' };
    }
    if (lower.includes('información es parcial') || lower.includes('información parcial') || lower.includes('no está disponible')) {
        return { label: 'Respuesta parcial', type: 'partial' };
    }
    // Solo marcamos "Basado en manual" ante una cita real con corchete
    // ([Manual: ...]); la prosa suelta "según el manual:" no es una fuente.
    if (lower.includes('[manual:')) {
        return { label: 'Basado en manual', type: 'manual' };
    }
    return { label: 'Revisar fuente', type: 'info' };
}

function extractManualSources(text) {
    // Requiere el corchete de cita real para no capturar prosa como fuente.
    const matches = [...text.matchAll(/\[Manual:\s*([^\]\n|]+)/gi)];
    return [...new Set(matches.map((m) => m[1].trim()).filter(Boolean))];
}

function parseImageReference(value) {
    // Matches "<pdf-basename>_pag<N>" for any manual, e.g. arch2_pag5 or
    // histologia_completo_pag12(_full).
    const match = value.match(/^(.*?)_pag(\d+)/i);
    if (!match || !match[1]) return '';
    return `${match[1]}.pdf · pág. ${Number(match[2])}`;
}

function showTyping() {
    const div = document.createElement('div');
    div.className = 'typing-indicator';
    div.id = 'typing-indicator';
    div.innerHTML = '<div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>';
    messagesContainer.appendChild(div);
    scrollToBottom();
    return div;
}

function removeTyping(el) {
    if (el && el.parentNode) el.parentNode.removeChild(el);
}

function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

// ── Simple Markdown renderer ────────────────────────────────────────
function renderMarkdown(text) {
    if (!text) return '';

    let html = escapeHtml(text);

    // Tables (process before other rules)
    html = html.replace(/^(\|.+\|)\n(\|[-:| ]+\|)\n((?:\|.+\|\n?)*)/gm, (match, header, sep, body) => {
        const headers = header.split('|').filter(c => c.trim()).map(c => `<th>${c.trim()}</th>`);
        const rows = body.trim().split('\n').map(row => {
            const cells = row.split('|').filter(c => c.trim()).map(c => `<td>${c.trim()}</td>`);
            return `<tr>${cells.join('')}</tr>`;
        });
        return `<table><thead><tr>${headers.join('')}</tr></thead><tbody>${rows.join('')}</tbody></table>`;
    });

    // Headers
    html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>');
    html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>');
    html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>');

    // Bold + Italic
    html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>');
    html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    html = html.replace(/\*(.+?)\*/g, '<em>$1</em>');

    // Code blocks
    html = html.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');

    // Inline code
    html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

    // Lists
    html = html.replace(/^\s*[-*] (.+)$/gm, '<li>$1</li>');
    html = html.replace(/(<li>.*<\/li>)/gs, '<ul>$1</ul>');
    // Remove nested <ul> wraps
    html = html.replace(/<\/ul>\s*<ul>/g, '');

    // Numbered lists
    html = html.replace(/^\s*\d+\. (.+)$/gm, '<li>$1</li>');

    // Line breaks → paragraphs
    html = html.replace(/\n\n/g, '</p><p>');
    html = html.replace(/\n/g, '<br>');

    // Wrap in paragraph if not already structured
    if (!html.startsWith('<')) {
        html = `<p>${html}</p>`;
    }

    return html;
}

// ── Temario ─────────────────────────────────────────────────────────
let temarioLoaded = false;

async function toggleTemario() {
    const overlay = document.getElementById('temario-overlay');
    const panel = document.getElementById('temario-panel');
    const isVisible = getComputedStyle(panel).display !== 'none';

    if (isVisible) {
        closeTemario();
    } else {
        overlay.classList.add('visible');
        panel.style.display = 'flex';
        if (!temarioLoaded) await loadTemario();
    }
}

function closeTemario() {
    const overlay = document.getElementById('temario-overlay');
    const panel = document.getElementById('temario-panel');
    if (overlay) overlay.classList.remove('visible');
    if (panel) panel.style.display = 'none';
}

async function loadTemario() {
    const list = document.getElementById('temario-list');
    try {
        const res = await fetch(`${API_BASE}/api/temario`);
        const data = await res.json();
        if (data.temas && data.temas.length > 0) {
            list.innerHTML = data.temas.map((t, i) =>
                `<div class="temario-item" onclick="sendChip(this)">
                    <span class="num">${i + 1}.</span> ${escapeHtml(t)}
                </div>`
            ).join('');
            temarioLoaded = true;
        } else {
            list.innerHTML = '<p style="color:var(--text-muted)">Sin temas disponibles</p>';
        }
    } catch {
        list.innerHTML = '<p style="color:var(--error)">Error cargando temario</p>';
    }
}


// ── Utils ───────────────────────────────────────────────────────────
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatBytes(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / 1048576).toFixed(1) + ' MB';
}

// ── Lightbox for database images ────────────────────────────────────
let lightboxEscHandler = null;

function openLightbox(url, title, caption) {
    // Remove existing lightbox if any
    const existing = document.getElementById('image-lightbox');
    if (existing) existing.remove();

    const overlay = document.createElement('div');
    overlay.id = 'image-lightbox';
    overlay.className = 'lightbox-overlay';
    overlay.onclick = (e) => { if (e.target === overlay) closeLightbox(); };

    const container = document.createElement('div');
    container.className = 'lightbox-container';

    // Close button
    const closeBtn = document.createElement('button');
    closeBtn.className = 'lightbox-close';
    closeBtn.innerHTML = '✕';
    closeBtn.onclick = closeLightbox;
    container.appendChild(closeBtn);

    // Image
    const img = document.createElement('img');
    img.className = 'lightbox-img';
    img.src = url;
    img.alt = title || 'Imagen histológica';
    container.appendChild(img);

    // Title
    if (title) {
        const titleEl = document.createElement('div');
        titleEl.className = 'lightbox-title';
        titleEl.textContent = title;
        container.appendChild(titleEl);
    }

    // Caption
    if (caption) {
        const captionEl = document.createElement('div');
        captionEl.className = 'lightbox-caption';
        captionEl.textContent = caption;
        container.appendChild(captionEl);
    }

    overlay.appendChild(container);
    document.body.appendChild(overlay);

    // Close on Escape. Guardamos el handler a nivel de módulo para poder
    // removerlo siempre desde closeLightbox (se cierre con Escape, con la X
    // o haciendo click en el fondo) y no acumular listeners.
    if (lightboxEscHandler) {
        document.removeEventListener('keydown', lightboxEscHandler);
    }
    lightboxEscHandler = (e) => {
        if (e.key === 'Escape') closeLightbox();
    };
    document.addEventListener('keydown', lightboxEscHandler);
}

function closeLightbox() {
    const lb = document.getElementById('image-lightbox');
    if (lb) lb.remove();
    if (lightboxEscHandler) {
        document.removeEventListener('keydown', lightboxEscHandler);
        lightboxEscHandler = null;
    }
}


// ── Log ─────────────────────────────────────────────────────────────
console.log('🔬 RAG Histología Qdrant + A2UI client initialized');
