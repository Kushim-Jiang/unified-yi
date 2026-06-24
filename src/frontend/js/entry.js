/**
 * Unified Yi Character Manager — Entry System
 *
 * 录入系统：提供注音 (pronunciation) 和释义 (meaning) 的格式化录入功能。
 *
 * 自动格式化规则：
 *   ① 【】 → 〖〗
 *   ② 删除所有空格
 *   ③ 连续 〖〗 之间自动加逗号
 *   ④ 结尾自动加句号 。
 */

class EntryApp {
    constructor() {
        this.$ = id => document.getElementById(id);
        this.state = { currentSource: null, currentRef: null, currentGlyph: null };

        this.inputPron = this.$('inputPronunciation');
        this.inputMean = this.$('inputMeaning');
        this.previewPron = this.$('previewPronunciation');
        this.previewMean = this.$('previewMeaning');
        this.diffSummary = this.$('diffSummary');
        this.charCount = this.$('charCount');
        this.autoFormatChk = this.$('autoFormat');
        this.sourceSelect = this.$('sourceSelect');
        this.refInput = this.$('refInput');
        this.loadStatus = this.$('loadStatus');
        this.btnSave = this.$('btnSave');
    }

    init() {
        this._loadSources();
        this._formatAndPreview();

        this.inputPron.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); this.inputMean.focus(); }
        });
        this.refInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') { e.preventDefault(); this.loadCharacter(); }
        });
        this.inputMean.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); this.saveCharacter(); }
        });
    }

    // ── Source loading ────────────────────────────────────

    async _loadSources() {
        try {
            const sources = await ApiClient.fetch('/sources');
            this.sourceSelect.innerHTML = '<option value="">— 选择来源 —</option>';
            for (const s of sources) {
                const opt = document.createElement('option');
                opt.value = s.id;
                opt.textContent = `${s.id.toUpperCase()} — ${s.name} (${s.character_count} 字)`;
                this.sourceSelect.appendChild(opt);
            }
        } catch (e) {
            Notification.show('加载来源失败: ' + e.message, 'error');
        }
    }

    // ── Load character ────────────────────────────────────

    async loadCharacter() {
        const source = this.sourceSelect.value;
        const ref = this.refInput.value.trim();

        if (!source) { Notification.show('请先选择来源', 'error'); return; }
        if (!ref) { Notification.show('请输入 Ref 编号', 'error'); return; }

        this.loadStatus.textContent = '加载中…';
        try {
            const char = await ApiClient.fetch(`/character/${source}/${encodeURIComponent(ref)}`);
            this.state.currentSource = source;
            this.state.currentRef = ref;
            this.state.currentGlyph = char.glyph || '';

            this.inputPron.value = char.pronunciation || '';
            this.inputMean.value = char.meaning || '';
            this.btnSave.disabled = false;
            this.loadStatus.textContent = `✅ 已加载 ${ref}（字形：${char.glyph || '?'}）`;
            this.loadStatus.style.color = 'var(--success)';

            this._formatAndPreview();
        } catch (e) {
            Notification.show('加载失败: ' + e.message, 'error');
            this.loadStatus.textContent = '❌ 加载失败';
            this.loadStatus.style.color = 'var(--danger)';
            this.btnSave.disabled = true;
            this.state.currentSource = this.state.currentRef = this.state.currentGlyph = null;
        }
    }

    // ── Save character ────────────────────────────────────

    async saveCharacter() {
        if (!this.state.currentSource || !this.state.currentRef) {
            Notification.show('请先加载一个字符', 'error');
            return;
        }

        this._formatAndPreview();
        const fmtPron = this._formatPronunciation(this.inputPron.value || '');
        const fmtMean = this._formatMeaning(this.inputMean.value || '');

        if (!fmtPron && !fmtMean) {
            Notification.show('注音和释义不能同时为空', 'error');
            return;
        }

        const origText = this.btnSave.textContent;
        this.btnSave.textContent = '⏳ 保存中…';
        this.btnSave.disabled = true;

        try {
            await ApiClient.put(`/characters/${this.state.currentSource}/${encodeURIComponent(this.state.currentRef)}`, {
                pronunciation: fmtPron,
                meaning: fmtMean,
            });
            Notification.show(`✅ 已保存到 ${this.state.currentSource}.tsv 的 ${this.state.currentRef}`, 'success');
            this.loadStatus.textContent = `✅ 已保存 ${this.state.currentRef}`;
        } catch (e) {
            Notification.show('保存失败: ' + e.message, 'error');
        } finally {
            this.btnSave.textContent = origText;
            this.btnSave.disabled = false;
        }
    }

    // ── Formatting helpers ───────────────────────────────

    /** 取代 【】 → 〖〗 */
    _replaceBrackets(text) { return text.replace(/【/g, '〖').replace(/】/g, '〗'); }

    /** 删除所有空格 */
    _removeSpaces(text) { return text.replace(/[\s\u3000]+/g, ''); }

    /** 在连续 〖〗 之间自动添加逗号 */
    _addCommasBetweenBrackets(text) { return text.replace(/〗\s*〖/g, '〗，〖'); }

    /** 确保结尾有句号 */
    _ensureEndingPunctuation(text) {
        const enders = /[。！？…；\.!?;]$/;
        if (text.length === 0) return text;
        if (!enders.test(text)) return text + '。';
        return text;
    }

    /** 对注音文本进行格式化 */
    _formatPronunciation(text) { return this._removeSpaces(text); }

    /** 对释义文本进行完整格式化 */
    _formatMeaning(text) {
        let result = text;
        result = this._replaceBrackets(result);
        result = this._removeSpaces(result);
        result = this._addCommasBetweenBrackets(result);
        result = this._ensureEndingPunctuation(result);
        return result;
    }

    /** 生成变更摘要 */
    _generateDiffSummary(original, formatted, type) {
        const changes = [];

        if (type === 'pronunciation') {
            if (original !== formatted) {
                const spaceCount = (original.match(/[\s\u3000]/g) || []).length;
                if (spaceCount > 0) changes.push(`删除了 ${spaceCount} 个空格`);
                if (/[【】]/.test(original)) changes.push('替换了【】为〖〗');
            }
        } else {
            if (/[【】]/.test(original)) {
                const replaced = (original.match(/[【】]/g) || []).length;
                changes.push(`替换了 ${replaced} 个【】为〖〗`);
            }
            const spaceCount = (original.match(/[\s\u3000]/g) || []).length;
            if (spaceCount > 0) changes.push(`删除了 ${spaceCount} 个空格`);
            const beforeComma = original.replace(/[【】]/g, m => m === '【' ? '〖' : '〗');
            if (beforeComma !== formatted && /〗\s*〖/.test(original.replace(/[【】]/g, m => m === '【' ? '〖' : '〗'))) {
                changes.push('在连续〖〗之间添加了逗号');
            }
            if (!/[。！？…；\.!?;]$/.test(original.trim())) {
                changes.push('结尾补充了句号');
            }
        }

        if (changes.length === 0 && original === formatted) return '无需修改 ✓';
        return changes.join('；') + '。';
    }

    // ── Formatting + preview ──────────────────────────────

    _formatAndPreview() {
        const rawPron = this.inputPron.value || '';
        const rawMean = this.inputMean.value || '';

        const fmtPron = this._formatPronunciation(rawPron);
        const fmtMean = this._formatMeaning(rawMean);

        this.previewPron.innerHTML = fmtPron
            ? `<span class="label-formatted">/</span> ${htmlEscape(fmtPron)} <span class="label-formatted">/</span>`
            : '<span style="color:var(--text-secondary);">—</span>';

        this.previewMean.innerHTML = fmtMean
            ? htmlEscape(fmtMean)
            : '<span style="color:var(--text-secondary);">—</span>';

        const pronDiff = this._generateDiffSummary(rawPron, fmtPron, 'pronunciation');
        const meanDiff = this._generateDiffSummary(rawMean, fmtMean, 'meaning');

        this.diffSummary.innerHTML = (rawPron || rawMean)
            ? `<div style="margin-bottom:4px;"><strong>注音：</strong>${htmlEscape(pronDiff)}</div><div><strong>释义：</strong>${htmlEscape(meanDiff)}</div>`
            : '<span style="color:var(--text-secondary);">等待输入…</span>';

        this.charCount.textContent = rawMean.length;

        if (rawPron !== fmtPron || rawMean !== fmtMean) {
            this.previewPron.style.borderLeft = '3px solid var(--success)';
            this.previewMean.style.borderLeft = '3px solid var(--success)';
        } else {
            this.previewPron.style.borderLeft = '1px solid var(--border)';
            this.previewMean.style.borderLeft = '1px solid var(--border)';
        }
    }

    onInputChange() {
        this.charCount.textContent = (this.inputMean.value || '').length;
        if (this.autoFormatChk.checked) {
            this._formatAndPreview();
        } else {
            this.previewPron.innerHTML = this.inputPron.value
                ? htmlEscape(this.inputPron.value) : '<span style="color:var(--text-secondary);">—</span>';
            this.previewMean.innerHTML = this.inputMean.value
                ? htmlEscape(this.inputMean.value) : '<span style="color:var(--text-secondary);">—</span>';
            this.diffSummary.innerHTML = '<span style="color:var(--text-secondary);">自动格式化已禁用</span>';
            this.charCount.textContent = this.inputMean.value.length;
        }
    }

    clearAll() {
        this.inputPron.value = '';
        this.inputMean.value = '';
        this.previewPron.innerHTML = '<span style="color:var(--text-secondary);">—</span>';
        this.previewMean.innerHTML = '<span style="color:var(--text-secondary);">—</span>';
        this.diffSummary.innerHTML = '<span style="color:var(--text-secondary);">等待输入…</span>';
        this.charCount.textContent = '0';
        this.previewPron.style.borderLeft = '1px solid var(--border)';
        this.previewMean.style.borderLeft = '1px solid var(--border)';
        this.inputPron.focus();
    }

    copyResult() {
        const rawPron = this.inputPron.value || '';
        const rawMean = this.inputMean.value || '';
        const fmtPron = this._formatPronunciation(rawPron);
        const fmtMean = this._formatMeaning(rawMean);
        const text = `pronunciation: ${fmtPron}\nmeaning: ${fmtMean}`;

        navigator.clipboard.writeText(text).then(() => {
            const btn = this.$('btnCopy');
            const orig = btn.textContent;
            btn.textContent = '✅ 已复制';
            setTimeout(() => { btn.textContent = orig; }, 2000);
        }).catch(() => {
            const ta = document.createElement('textarea');
            ta.value = text;
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            document.body.removeChild(ta);
            const btn = this.$('btnCopy');
            const orig = btn.textContent;
            btn.textContent = '✅ 已复制';
            setTimeout(() => { btn.textContent = orig; }, 2000);
        });
    }
}


// ─── Boot ─────────────────────────────────────────────────────
const entryApp = new EntryApp();
document.addEventListener('DOMContentLoaded', () => entryApp.init());
