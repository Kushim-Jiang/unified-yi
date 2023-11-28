/**
 * Unified Yi Character Manager - Main Application
 */
const API_BASE = '/api';

// ─── State ───
const state = {
    sources: [],
    currentSource: null,
    currentPage: 1,
    pageSize: 100,
    searchQuery: '',
    selectedChar: null,
    alignments: [],
};

// ─── API Helpers ───
async function apiFetch(path) {
    const res = await fetch(API_BASE + path);
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'Request failed');
    }
    return res.json();
}

async function apiPost(path, body) {
    const res = await fetch(API_BASE + path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    });
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }));
        throw new Error(err.detail || 'Request failed');
    }
    return res.json();
}

async function apiDelete(path) {
    const res = await fetch(API_BASE + path, { method: 'DELETE' });
    if (!res.ok) throw new Error('Delete failed');
    return res.json();
}

// ─── UI Helpers ───
function notify(msg, type = 'info') {
    const el = document.createElement('div');
    el.className = `notification ${type}`;
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 3000);
}

function escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function scoreColor(score) {
    if (score >= 0.7) return 'good';
    if (score >= 0.4) return 'medium';
    return 'bad';
}

// ─── Sources ───
async function loadSources() {
    try {
        state.sources = await apiFetch('/sources');
        renderSourceGrid();
    } catch (err) {
        notify('Failed to load sources: ' + err.message, 'error');
    }
}

function renderSourceGrid() {
    const grid = document.getElementById('sourceGrid');
    if (!grid) return;

    const groups = { unified: [], yunnan: [], guizhou: [], other: [] };
    for (const src of state.sources) {
        const g = src.group || 'other';
        if (groups[g]) groups[g].push(src);
        else groups.other.push(src);
    }

    const groupNames = {
        unified: '📖 通用 (Unified)',
        yunnan: '🏔️ 云南 (Yunnan)',
        guizhou: '🏯 贵州 (Guizhou)',
    };

    let html = '';
    for (const [group, sources] of Object.entries(groups)) {
        if (sources.length === 0) continue;
        if (groupNames[group]) {
            html += `<div style="grid-column:1/-1;font-weight:700;color:var(--text-secondary);margin-top:12px;font-size:13px;text-transform:uppercase;letter-spacing:0.5px">${groupNames[group]}</div>`;
        }
        for (const src of sources) {
            const isSelected = state.currentSource === src.id;
            html += `
                <div class="source-card ${isSelected ? 'selected' : ''}"
                     onclick="selectSource('${src.id}')">
                    <span class="region-badge ${src.group}">${src.region}</span>
                    <h3>${src.id}.tsv</h3>
                    <div class="meta">${src.name}</div>
                    <div class="meta">${src.character_count.toLocaleString()} characters</div>
                    ${src.year ? `<div class="meta">Year: ${src.year}</div>` : ''}
                </div>`;
        }
    }
    grid.innerHTML = html;
}

async function selectSource(sourceId) {
    state.currentSource = sourceId;
    state.currentPage = 1;
    state.searchQuery = '';
    document.getElementById('searchInput').value = '';
    renderSourceGrid();
    await loadCharacters();
}

// ─── Characters ───
async function loadCharacters() {
    if (!state.currentSource) {
        document.getElementById('charTableBody').innerHTML =
            '<tr><td colspan="4" style="text-align:center;padding:40px;color:var(--text-secondary)">Select a source to view characters</td></tr>';
        return;
    }

    document.getElementById('charTableBody').innerHTML =
        '<tr><td colspan="4" style="text-align:center;padding:20px"><span class="spinner"></span> Loading...</td></tr>';

    try {
        const params = new URLSearchParams({
            page: state.currentPage,
            page_size: state.pageSize,
            search: state.searchQuery,
        });
        const result = await apiFetch(`/characters/${state.currentSource}?${params}`);

        document.getElementById('currentSourceLabel').textContent = state.currentSource;
        document.getElementById('totalChars').textContent = result.total.toLocaleString();
        renderCharacterTable(result.data);
        renderPagination(result);
    } catch (err) {
        notify('Failed to load characters: ' + err.message, 'error');
    }
}

function renderCharacterTable(characters) {
    const tbody = document.getElementById('charTableBody');
    if (characters.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:40px;color:var(--text-secondary)">No characters found</td></tr>';
        return;
    }

    tbody.innerHTML = characters.map(c => `
        <tr class="${state.selectedChar && state.selectedChar.src_ref === c.src_ref ? 'selected' : ''}"
            onclick="selectCharacter('${escapeHtml(c.src_ref)}', '${state.currentSource}')">
            <td class="glyph-cell" title="${escapeHtml(c.glyph)}">${c.glyph}</td>
            <td class="src-ref">${escapeHtml(c.src_ref)}</td>
            <td class="pronunciation">${escapeHtml(c.pronunciation)}</td>
            <td>${escapeHtml(c.meaning)}</td>
        </tr>
    `).join('');
}

function renderPagination(result) {
    const pag = document.getElementById('pagination');
    if (result.total_pages <= 1) {
        pag.innerHTML = '';
        return;
    }

    pag.innerHTML = `
        <button ${result.page <= 1 ? 'disabled' : ''} onclick="goToPage(${result.page - 1})">← Prev</button>
        <span class="page-info">Page ${result.page} / ${result.total_pages} (${result.total} total)</span>
        <button ${result.page >= result.total_pages ? 'disabled' : ''} onclick="goToPage(${result.page + 1})">Next →</button>
    `;
}

function goToPage(page) { state.currentPage = page; loadCharacters(); }
function doSearch() { state.searchQuery = document.getElementById('searchInput').value; state.currentPage = 1; loadCharacters(); }
function clearSearch() { state.searchQuery = ''; document.getElementById('searchInput').value = ''; state.currentPage = 1; loadCharacters(); }

// ─── Character Selection ───
async function selectCharacter(srcRef, source) {
    try {
        const char = await apiFetch(`/character/${source}/${srcRef}`);
        state.selectedChar = { ...char, source };
        showCharDetail(char, source);
        loadCharacters();
        loadSuggestions(source, srcRef);
    } catch (err) {
        notify('Failed to load character: ' + err.message, 'error');
    }
}

function showCharDetail(char, source) {
    const detail = document.getElementById('charDetail');
    if (!detail) return;

    detail.innerHTML = `
        <div style="display:flex;align-items:center;gap:16px;padding:16px;background:var(--accent-bg);border-radius:var(--radius);margin-bottom:12px;">
            <span style="font-family:'YiFont';font-size:48px;">${char.glyph}</span>
            <div>
                <div style="font-weight:700;font-size:18px;">${escapeHtml(char.src_ref)}</div>
                <div style="font-family:'Gentium Plus',serif;color:var(--info);">${escapeHtml(char.pronunciation)}</div>
                <div>${escapeHtml(char.meaning)}</div>
                <div style="font-size:12px;color:var(--text-secondary);">Source: ${source}</div>
            </div>
        </div>
        <div id="suggestionsArea">
            <span class="spinner"></span> Loading suggestions...
        </div>
    `;
}

async function loadSuggestions(source, srcRef) {
    const area = document.getElementById('suggestionsArea');
    if (!area) return;

    try {
        const result = await apiFetch(`/suggest-alignments/${source}/${srcRef}?method=combined&top_k=15`);
        renderSuggestions(result.suggestions);
    } catch (err) {
        area.innerHTML = `<p style="color:var(--text-secondary)">Could not load suggestions: ${err.message}</p>`;
    }
}

function renderSuggestions(suggestions) {
    const area = document.getElementById('suggestionsArea');
    if (!area) return;

    if (suggestions.length === 0) {
        area.innerHTML = '<p style="color:var(--text-secondary)">No similar characters found</p>';
        return;
    }

    area.innerHTML = `
        <h4 style="margin-bottom:8px;color:var(--text-secondary);font-size:13px;">🔍 Suggested Matches (pronunciation + meaning + radical)</h4>
        <div class="suggestions-list">
            ${suggestions.map(s => `
                <div class="suggestion-item" onclick="quickAlign('${escapeHtml(state.currentSource)}', '${escapeHtml(state.selectedChar.src_ref)}', '${escapeHtml(s.source)}', '${escapeHtml(s.src_ref)}')">
                    <span class="sugg-glyph">${s.glyph}</span>
                    <div class="sugg-info">
                        <div><strong>${escapeHtml(s.source)}</strong> · ${escapeHtml(s.src_ref)}</div>
                        <div style="font-family:'Gentium Plus',serif;font-size:12px;color:var(--info);">/${escapeHtml(s.pronunciation)}/</div>
                        <div style="font-size:12px;">${escapeHtml(s.meaning)}</div>
                        <div class="score-bar">
                            <div class="fill ${scoreColor(s.combined_score)}" style="width:${(s.combined_score*100).toFixed(0)}%"></div>
                        </div>
                    </div>
                    <div class="sugg-score">${(s.combined_score*100).toFixed(0)}%</div>
                </div>
            `).join('')}
        </div>
    `;
}

// ─── Quick Align ───
async function quickAlign(sourceA, refA, sourceB, refB) {
    try {
        await apiPost('/alignments', {
            source_a: sourceA, src_ref_a: refA,
            source_b: sourceB, src_ref_b: refB, note: '',
        });
        notify(`Aligned: ${refA} ↔ ${refB}`, 'success');
        loadAlignments();
    } catch (err) {
        notify('Failed to align: ' + err.message, 'error');
    }
}

// ─── Alignments ───
async function loadAlignments() {
    try {
        const data = await apiFetch('/alignments');
        state.alignments = data;
        renderAlignmentsTable();
        updateAlignmentCount();
    } catch (err) {
        console.error('Failed to load alignments', err);
    }
}

function renderAlignmentsTable() {
    const tbody = document.getElementById('alignTableBody');
    if (!tbody) return;

    if (state.alignments.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:40px;color:var(--text-secondary)">No alignments yet. Browse characters and link them!</td></tr>';
        return;
    }

    tbody.innerHTML = state.alignments.map(al => {
        const ca = al.char_a || {};
        const cb = al.char_b || {};
        return `
            <tr>
                <td class="glyph-cell">${ca.glyph || '?'}</td>
                <td class="src-ref">${escapeHtml(al.source_a)} / ${escapeHtml(al.src_ref_a)}</td>
                <td style="text-align:center;color:var(--accent);font-size:20px;">↔</td>
                <td class="glyph-cell">${cb.glyph || '?'}</td>
                <td class="src-ref">${escapeHtml(al.source_b)} / ${escapeHtml(al.src_ref_b)}</td>
                <td><button class="btn btn-danger btn-sm" onclick="deleteAlignment(${al.id})">✕</button></td>
            </tr>
        `;
    }).join('');
}

async function deleteAlignment(id) {
    if (!confirm('Delete this alignment?')) return;
    try {
        await apiDelete(`/alignments/${id}`);
        notify('Alignment deleted', 'success');
        loadAlignments();
    } catch (err) {
        notify('Failed to delete: ' + err.message, 'error');
    }
}

function updateAlignmentCount() {
    const el = document.getElementById('alignmentCount');
    if (el) el.textContent = state.alignments.length;
}

// ─── Init ───
document.addEventListener('DOMContentLoaded', () => {
    loadSources();
    loadAlignments();
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') doSearch();
        });
    }
});
