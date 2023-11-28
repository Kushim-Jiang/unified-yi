/**
 * Unified Yi Character Manager - Alignment Page
 */
const API_BASE = '/api';

const alignState = {
    sources: [],
    sourceA: null, sourceB: null,
    charA: null, charB: null,
    pageA: 1, pageB: 1,
    searchA: '', searchB: '',
};

async function apiFetch(path) {
    const res = await fetch(API_BASE + path);
    if (!res.ok) throw new Error((await res.json().catch(()=>({detail:res.statusText}))).detail);
    return res.json();
}
async function apiPost(path, body) {
    const res = await fetch(API_BASE + path, {
        method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error((await res.json().catch(()=>({detail:res.statusText}))).detail);
    return res.json();
}
async function apiDelete(path) {
    const res = await fetch(API_BASE + path, { method: 'DELETE' });
    if (!res.ok) throw new Error('Delete failed');
    return res.json();
}

function notify(msg, type='info') {
    const el = document.createElement('div');
    el.className = `notification ${type}`;
    el.textContent = msg;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 3000);
}
function escapeHtml(s) { const d=document.createElement('div'); d.textContent=s; return d.innerHTML; }
function scoreColor(s) { return s>=0.7?'good':s>=0.4?'medium':'bad'; }

async function initAlignPage() {
    try {
        alignState.sources = await apiFetch('/sources');
        populateSourceSelects();
        loadExistingAlignments();
    } catch (err) {
        notify('Failed to initialize: ' + err.message, 'error');
    }
}

function populateSourceSelects() {
    const selA = document.getElementById('sourceSelectA');
    const selB = document.getElementById('sourceSelectB');
    if (!selA || !selB) return;
    const options = alignState.sources.map(s =>
        `<option value="${s.id}">${s.id} — ${s.name} (${s.character_count})</option>`
    ).join('');
    selA.innerHTML = options;
    selB.innerHTML = options;
    if (alignState.sources.length >= 2) {
        selA.value = alignState.sources[0].id;
        selB.value = alignState.sources[1].id;
        alignState.sourceA = alignState.sources[0].id;
        alignState.sourceB = alignState.sources[1].id;
        loadCharsA(); loadCharsB();
    }
}

function switchSources() {
    const selA = document.getElementById('sourceSelectA');
    const selB = document.getElementById('sourceSelectB');
    const tmp = selA.value;
    selA.value = selB.value; selB.value = tmp;
    alignState.sourceA = selA.value; alignState.sourceB = selB.value;
    alignState.charA = null; alignState.charB = null;
    alignState.pageA = 1; alignState.pageB = 1;
    updateCharDisplay('A'); updateCharDisplay('B'); updateComparePanel();
    loadCharsA(); loadCharsB();
}

async function loadCharsA() { if (alignState.sourceA) await loadCharList('A', alignState.sourceA, alignState.pageA, alignState.searchA); }
async function loadCharsB() { if (alignState.sourceB) await loadCharList('B', alignState.sourceB, alignState.pageB, alignState.searchB); }

async function loadCharList(panel, source, page, search) {
    const tbody = document.getElementById(`charList${panel}`);
    if (!tbody) return;
    tbody.innerHTML = '<tr><td colspan="3" style="text-align:center;padding:12px"><span class="spinner"></span></td></tr>';
    try {
        const params = new URLSearchParams({ page, page_size: 50, search });
        const result = await apiFetch(`/characters/${source}?${params}`);
        document.getElementById(`sourceLabel${panel}`).textContent = source;
        document.getElementById(`totalLabel${panel}`).textContent = result.total.toLocaleString();
        tbody.innerHTML = result.data.map(c => `
            <tr class="${(panel==='A'?alignState.charA:alignState.charB) && (panel==='A'?alignState.charA:alignState.charB).src_ref===c.src_ref?'selected':''}"
                onclick="selectChar('${panel}', '${escapeHtml(c.src_ref)}')">
                <td class="glyph-cell">${c.glyph}</td>
                <td class="src-ref">${escapeHtml(c.src_ref)}</td>
                <td style="font-family:'Gentium Plus',serif;font-size:12px;color:var(--info);">/${escapeHtml(c.pronunciation)}/</td>
            </tr>
        `).join('');
        renderMiniPagination(panel, result);
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="3" style="color:red">Error: ${err.message}</td></tr>`;
    }
}

function renderMiniPagination(panel, result) {
    const pag = document.getElementById(`pagination${panel}`);
    if (!pag) return;
    const page = panel === 'A' ? alignState.pageA : alignState.pageB;
    pag.innerHTML = `
        <button ${page<=1?'disabled':''} onclick="goPage('${panel}', ${page-1})">←</button>
        <span style="font-size:12px;color:var(--text-secondary)">${page}/${result.total_pages||1}</span>
        <button ${page>=result.total_pages?'disabled':''} onclick="goPage('${panel}', ${page+1})">→</button>
    `;
}

function goPage(panel, p) {
    if (panel === 'A') { alignState.pageA = p; loadCharsA(); }
    else { alignState.pageB = p; loadCharsB(); }
}

function doSearchPanel(panel) {
    const search = document.getElementById(`search${panel}`).value;
    if (panel === 'A') { alignState.searchA = search; alignState.pageA = 1; loadCharsA(); }
    else { alignState.searchB = search; alignState.pageB = 1; loadCharsB(); }
}

async function selectChar(panel, srcRef) {
    const source = panel === 'A' ? alignState.sourceA : alignState.sourceB;
    try {
        const char = await apiFetch(`/character/${source}/${srcRef}`);
        if (panel === 'A') alignState.charA = { ...char, source };
        else alignState.charB = { ...char, source };
        updateCharDisplay(panel);
        updateComparePanel();
        if (panel === 'A') loadCharsA(); else loadCharsB();
        if (panel === 'A') loadSuggestionsFor('B', char);
        else loadSuggestionsFor('A', char);
    } catch (err) {
        notify('Failed to load character: ' + err.message, 'error');
    }
}

function updateCharDisplay(panel) {
    const char = panel === 'A' ? alignState.charA : alignState.charB;
    const display = document.getElementById(`charDisplay${panel}`);
    const info = document.getElementById(`charInfo${panel}`);
    if (char) {
        display.textContent = char.glyph;
        const radInfo = char.radical ? ` · ⾸${char.radical}+${char.other_stroke}` : '';
        info.innerHTML = `
            <div><strong>${escapeHtml(char.src_ref)}</strong>${radInfo}</div>
            <div style="font-family:'Gentium Plus',serif;color:var(--info);">/${escapeHtml(char.pronunciation)}/</div>
            <div>${escapeHtml(char.meaning)}</div>
        `;
    } else {
        display.textContent = '?';
        info.innerHTML = '<div style="color:var(--text-secondary)">Select a character</div>';
    }
}

async function loadSuggestionsFor(targetPanel, sourceChar) {
    const targetSource = targetPanel === 'A' ? alignState.sourceA : alignState.sourceB;
    if (!targetSource || !sourceChar) return;
    const listEl = document.getElementById(`suggestions${targetPanel}`);
    if (!listEl) return;
    listEl.innerHTML = '<div style="padding:8px;color:var(--text-secondary)"><span class="spinner"></span> Finding matches...</div>';
    try {
        const src = sourceChar.source || alignState[`source${targetPanel==='A'?'B':'A'}`];
        const result = await apiFetch(`/suggest-alignments/${src}/${sourceChar.src_ref}?target_source=${targetSource}&method=combined&top_k=15`);
        renderSuggestionsList(targetPanel, result.suggestions);
    } catch (err) {
        listEl.innerHTML = `<div style="padding:8px;color:var(--text-secondary)">No suggestions: ${err.message}</div>`;
    }
}

function renderSuggestionsList(panel, suggestions) {
    const listEl = document.getElementById(`suggestions${panel}`);
    if (!listEl) return;
    if (suggestions.length === 0) {
        listEl.innerHTML = '<div style="padding:8px;color:var(--text-secondary)">No similar characters found</div>';
        return;
    }
    listEl.innerHTML = suggestions.map(s => `
        <div class="suggestion-item" onclick="selectChar('${panel}', '${escapeHtml(s.src_ref)}')" style="margin-bottom:4px;">
            <span class="sugg-glyph">${s.glyph}</span>
            <div class="sugg-info">
                <div>${escapeHtml(s.src_ref)}</div>
                <div style="font-family:'Gentium Plus',serif;font-size:11px;color:var(--info);">/${escapeHtml(s.pronunciation)}/</div>
            </div>
            <div class="sugg-score">${(s.combined_score*100).toFixed(0)}%</div>
        </div>
    `).join('');
}

async function updateComparePanel() {
    if (!alignState.charA || !alignState.charB) {
        document.getElementById('compareContent').innerHTML =
            '<p style="color:var(--text-secondary)">Select characters from both sides to compare</p>';
        return;
    }
    try {
        const result = await apiFetch(
            `/compare/${alignState.charA.source}/${alignState.charA.src_ref}/${alignState.charB.source}/${alignState.charB.src_ref}`
        );
        const pd = result.pronunciation_distance;
        const ms = result.meaning_similarity;
        const rs = result.radical_stroke_similarity || {};
        const pronSim = (1 - pd.combined_distance) * 100;

        document.getElementById('compareContent').innerHTML = `
            <table>
                <tr><td colspan="2" style="font-weight:700;color:var(--accent);padding-top:12px;">🎵 Pronunciation</td></tr>
                <tr><td>Overall Similarity</td><td>
                    <strong>${pronSim.toFixed(1)}%</strong>
                    <div class="score-bar"><div class="fill ${scoreColor(pronSim/100)}" style="width:${pronSim.toFixed(0)}%"></div></div>
                </td></tr>
                <tr><td>Consonant Distance</td><td>${(pd.consonant_distance*100).toFixed(0)}%</td></tr>
                <tr><td>Vowel Distance</td><td>${(pd.vowel_distance*100).toFixed(0)}%</td></tr>
                <tr><td>Tone Distance</td><td>${(pd.tone_distance*100).toFixed(0)}%</td></tr>
                <tr><td colspan="2" style="font-weight:700;color:var(--accent);padding-top:12px;">📝 Meaning</td></tr>
                <tr><td>Jaccard Similarity</td><td><strong>${(ms.jaccard*100).toFixed(1)}%</strong></td></tr>
                <tr><td>Overlap</td><td>${(ms.overlap*100).toFixed(1)}%</td></tr>
                <tr><td>Common Characters</td><td style="font-size:18px;">${escapeHtml(ms.common_chars || '(none)')}</td></tr>
                <tr><td colspan="2" style="font-weight:700;color:var(--accent);padding-top:12px;">🏗️ Radical-Stroke</td></tr>
                <tr><td>Radical Similarity</td><td><strong>${(rs.radical_similarity*100).toFixed(1)}%</strong></td></tr>
                <tr><td>Stroke Similarity</td><td>${(rs.stroke_similarity*100).toFixed(1)}%</td></tr>
                <tr><td>RS Combined</td><td><strong>${(rs.combined_score*100).toFixed(1)}%</strong></td></tr>
                <tr><td colspan="2" style="font-weight:700;padding-top:12px;">⭐ Combined Score</td></tr>
                <tr><td colspan="2"><strong style="font-size:22px;color:var(--accent);">${(result.combined_score*100).toFixed(1)}%</strong></td></tr>
            </table>
        `;
    } catch (err) {
        document.getElementById('compareContent').innerHTML = `<p style="color:red">Failed to compare: ${err.message}</p>`;
    }
}

async function createAlignment() {
    if (!alignState.charA || !alignState.charB) {
        notify('Select characters on both sides first', 'error');
        return;
    }
    try {
        await apiPost('/alignments', {
            source_a: alignState.charA.source, src_ref_a: alignState.charA.src_ref,
            source_b: alignState.charB.source, src_ref_b: alignState.charB.src_ref, note: '',
        });
        notify(`✅ Linked: ${alignState.charA.src_ref} ↔ ${alignState.charB.src_ref}`, 'success');
        loadExistingAlignments();
    } catch (err) {
        if (err.message.includes('already exists')) notify('These characters are already linked', 'info');
        else notify('Failed to link: ' + err.message, 'error');
    }
}

async function loadExistingAlignments() {
    try {
        const data = await apiFetch('/alignments');
        renderExistingAlignments(data);
    } catch (err) { console.error('Failed to load alignments', err); }
}

function renderExistingAlignments(data) {
    const tbody = document.getElementById('existingAlignBody');
    if (!tbody) return;
    document.getElementById('existingCount').textContent = data.length;
    if (data.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:20px;color:var(--text-secondary)">No links yet</td></tr>';
        return;
    }
    tbody.innerHTML = data.map(al => {
        const ca = al.char_a || {}; const cb = al.char_b || {};
        return `<tr>
            <td class="glyph-cell">${ca.glyph||'?'}</td>
            <td>${escapeHtml(al.source_a)} · ${escapeHtml(al.src_ref_a)}</td>
            <td style="color:var(--accent);">↔</td>
            <td class="glyph-cell">${cb.glyph||'?'}</td>
            <td>${escapeHtml(al.source_b)} · ${escapeHtml(al.src_ref_b)}</td>
            <td><button class="btn btn-danger btn-sm" onclick="deleteAlignment(${al.id})">✕</button></td>
        </tr>`;
    }).join('');
}

async function deleteAlignment(id) {
    if (!confirm('Delete this link?')) return;
    try { await apiDelete(`/alignments/${id}`); notify('Link deleted', 'success'); loadExistingAlignments(); }
    catch (err) { notify('Failed to delete: ' + err.message, 'error'); }
}

document.addEventListener('keydown', (e) => { if (e.ctrlKey && e.key === 'Enter') createAlignment(); });
document.addEventListener('DOMContentLoaded', initAlignPage);
