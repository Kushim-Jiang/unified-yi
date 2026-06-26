/**
 * Unified Yi Character Manager — Entry Grid System
 *
 * 批量录入系统：以表格形式展示 book/ TSV 数据，
 * 支持单元格编辑、自动格式化、自动保存。
 *
 * 自动格式化规则：
 *   ① 【】 → 〖〗
 *   ② 删除所有空格
 *   ③ 汉字与 〖 之间自动补逗号
 *   ④ 连续 〖〗 之间自动加逗号
 *   ⑤ 结尾自动加句号 。
 */

class EntryGrid {
  constructor() {
    this.$ = (id) => document.getElementById(id);

    // State
    this.currentSource = null;
    this.currentPage = 1;
    this.totalPages = 0;
    this.totalItems = 0;
    this.pageSize = 20;
    this.pageData = []; // current page data
    this._editingRow = null; // OCR 插入用：当前编辑的行
    this._editingCol = null; // OCR 插入用：当前编辑的列

    // OCR 浮动窗口
    this.ocr = new OcrWindow(this);

    // DOM refs
    this.sourceSelect = this.$("sourceSelect");
    this.refInput = this.$("refInput");
    this.loadStatus = this.$("loadStatus");
    this.totalInfo = this.$("totalInfo");
    this.autoFormatChk = this.$("autoFormat");
    this.tableBody = this.$("entryTableBody");
    this.tableEl = this.$("entryTable");
    this.emptyEl = this.$("entryEmpty");
    this.paginationEl = this.$("entryPagination");
    this.statsEl = this.$("entryStats");
    this.statsInfo = this.$("statsInfo");
    this.saveStatus = this.$("saveStatus");
  }

  init() {
    this._loadSources();
    this.sourceSelect.addEventListener("change", () => this._onSourceChange());
    this.refInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") this.jumpToRef();
    });
  }

  // ── Source loading ────────────────────────────────────

  async _loadSources() {
    try {
      const sources = await ApiClient.fetch("/sources");
      this.sourceSelect.innerHTML = '<option value="">— 选择来源 —</option>';
      for (const s of sources) {
        const opt = document.createElement("option");
        opt.value = s.id;
        opt.textContent = `${s.id.toUpperCase()} — ${s.name} (${s.character_count} 字)`;
        this.sourceSelect.appendChild(opt);
      }
    } catch (e) {
      Notification.show("加载来源失败: " + e.message, "error");
    }
  }

  _onSourceChange() {
    this.currentSource = this.sourceSelect.value;
    if (!this.currentSource) {
      this._showEmpty("请先选择一个来源");
      return;
    }
    this.currentPage = 1;
    this.loadPage(1);
  }

  // ── Data loading ──────────────────────────────────────

  async loadPage(page) {
    if (!this.currentSource) return;

    this.currentPage = page;
    this.loadStatus.textContent = "⏳ 加载中…";
    this.loadStatus.style.color = "var(--text-secondary)";

    try {
      const res = await ApiClient.fetch(`/characters/${this.currentSource}?page=${page}&page_size=${this.pageSize}`);
      this.pageData = res.data || [];
      this.totalItems = res.total;
      this.totalPages = res.total_pages || 0;

      this._renderTable();
      this._renderPagination();
      this._renderStats();

      this.tableEl.style.display = "";
      this.emptyEl.style.display = "none";
      this.paginationEl.style.display = "";
      this.statsEl.style.display = "";

      this.loadStatus.textContent = `✅ 第 ${page}/${this.totalPages} 页`;
      this.loadStatus.style.color = "var(--success)";
    } catch (e) {
      Notification.show("加载数据失败: " + e.message, "error");
      this.loadStatus.textContent = "❌ 加载失败";
      this.loadStatus.style.color = "var(--danger)";
    }
  }

  // ── Table rendering ───────────────────────────────────

  _renderTable() {
    const data = this.pageData;
    const startIdx = (this.currentPage - 1) * this.pageSize;

    if (!data || data.length === 0) {
      this.tableBody.innerHTML = `
                <tr><td colspan="4" style="text-align:center;padding:32px;color:var(--text-secondary);">
                    该页没有数据
                </td></tr>`;
      return;
    }

    let html = "";
    for (let i = 0; i < data.length; i++) {
      const item = data[i];
      const rowIdx = startIdx + i;
      const pron = item.pronunciation || "";
      const mean = item.meaning || "";
      const ref = item.src_ref || "";
      const glyph = item.glyph || "";

      html += `<tr data-ref="${htmlEscape(ref)}">`;
      // Col 1: row index
      html += `<td class="col-idx">${rowIdx + 1}</td>`;
      // Col 2: glyph + ref
      html += `<td>
                <div class="col-glyph">${htmlEscape(glyph)}</div>
                <div class="col-ref">${htmlEscape(ref)}</div>
            </td>`;
      // Col 3: pronunciation (editable)
      html += `<td>
                <div class="cell-editable" data-row="${i}" data-col="3"
                     onclick="entryApp.editCell(${i}, 3)"
                     title="点击编辑注音">${htmlEscape(pron) || '<span style="color:var(--text-secondary);font-size:11px;">空</span>'}</div>
            </td>`;
      // Col 4: meaning (editable)
      html += `<td>
                <div class="cell-editable" data-row="${i}" data-col="4"
                     onclick="entryApp.editCell(${i}, 4)"
                     title="点击编辑释义">${htmlEscape(mean) || '<span style="color:var(--text-secondary);font-size:11px;">空</span>'}</div>
            </td>`;
      html += `</tr>`;
    }

    this.tableBody.innerHTML = html;
  }

  // ── Pagination ────────────────────────────────────────

  _renderPagination() {
    const total = this.totalPages;
    const curr = this.currentPage;

    if (total <= 1) {
      this.paginationEl.innerHTML = "";
      return;
    }

    let html = "";

    // Prev
    html += `<button onclick="entryApp.loadPage(${curr - 1})" ${curr <= 1 ? "disabled" : ""}>◀ 上一页</button>`;

    // Page numbers
    const range = this._getPageRange(curr, total);
    for (const p of range) {
      if (p === "...") {
        html += `<span class="page-info">…</span>`;
      } else {
        html += `<button class="${p === curr ? "active" : ""}" onclick="entryApp.loadPage(${p})">${p}</button>`;
      }
    }

    // Next
    html += `<button onclick="entryApp.loadPage(${curr + 1})" ${curr >= total ? "disabled" : ""}>下一页 ▶</button>`;

    // 页码跳转输入框
    html += `<span class="page-info" style="margin-left:12px;">跳转</span>`;
    html += `<input type="number" id="pageJumpInput" min="1" max="${total}" value="${curr}"
                     onkeydown="if(event.key==='Enter')entryApp.loadPage(parseInt(this.value)||1)"
                     onchange="entryApp.loadPage(parseInt(this.value)||1)"
                     style="width:52px;padding:4px 6px;border:1px solid var(--border);border-radius:var(--radius);font-size:13px;background:var(--bg);color:var(--text);text-align:center;">`;
    html += `<span class="page-info">/ ${total}</span>`;

    this.paginationEl.innerHTML = html;
  }

  _getPageRange(curr, total) {
    const range = [];
    if (total <= 7) {
      for (let i = 1; i <= total; i++) range.push(i);
    } else {
      range.push(1);
      if (curr > 3) range.push("...");
      const start = Math.max(2, curr - 1);
      const end = Math.min(total - 1, curr + 1);
      for (let i = start; i <= end; i++) range.push(i);
      if (curr < total - 2) range.push("...");
      range.push(total);
    }
    return range;
  }

  // ── Stats ─────────────────────────────────────────────

  _renderStats() {
    const start = (this.currentPage - 1) * this.pageSize + 1;
    const end = Math.min(this.currentPage * this.pageSize, this.totalItems);
    this.statsInfo.textContent = `共 ${this.totalItems} 条，显示第 ${start}-${end} 条`;
  }

  // ── Inline editing ────────────────────────────────────

  editCell(rowIdx, colIdx) {
    const item = this.pageData[rowIdx];
    if (!item) return;

    const cell = this.tableBody.querySelector(`tr[data-ref="${htmlEscape(item.src_ref)}"] .cell-editable[data-row="${rowIdx}"][data-col="${colIdx}"]`);
    if (!cell || cell.classList.contains("editing")) return;

    const currentValue = colIdx === 3 ? item.pronunciation || "" : item.meaning || "";

    cell.classList.add("editing");
    cell.innerHTML = colIdx === 4 ? `<textarea class="edit-textarea" rows="2">${htmlEscape(currentValue)}</textarea>` : `<input class="edit-input" type="text" value="${htmlEscape(currentValue)}">`;

    const input = cell.querySelector("input, textarea");
    if (!input) return;

    input.focus();
    input.select();

    // Auto-resize textarea for meaning
    if (colIdx === 4) {
      input.addEventListener("input", () => {
        input.style.height = "auto";
        input.style.height = Math.min(input.scrollHeight, 200) + "px";
      });
      setTimeout(() => {
        input.style.height = "auto";
        input.style.height = Math.min(input.scrollHeight, 200) + "px";
      }, 0);
    }

    // 记录当前编辑位置，供 OCR 插入使用
    this._editingRow = rowIdx;
    this._editingCol = colIdx;

    // Guard flag: prevents blur from re-entering _commitCell when we are
    // already committing from the keyboard handler (blur fires synchronously
    // when _commitCell replaces cell.innerHTML, which removes the input).
    let committing = false;

    const doCommit = () => {
      if (committing) return;
      committing = true;
      this._commitCell(rowIdx, colIdx, cell, input).finally(() => {
        committing = false;
      });
    };
    input.addEventListener("blur", doCommit);

    // Ctrl+Enter commits; Enter commits + jumps to next cell; Escape cancels
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
        e.preventDefault();
        input.blur();
        return;
      }
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        committing = true; // suppress the blur handler
        const doNext = async () => {
          try {
            await this._commitCell(rowIdx, colIdx, cell, input);
          } finally {
            committing = false;
          }
          if (colIdx === 3) {
            this.editCell(rowIdx, 4);
          } else if (colIdx === 4) {
            const nextRow = rowIdx + 1;
            if (nextRow < this.pageData.length) {
              this.editCell(nextRow, 3);
            }
          }
        };
        doNext();
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        // Restore original value
        cell.innerHTML = htmlEscape(currentValue) || '<span style="color:var(--text-secondary);font-size:11px;">空</span>';
        cell.classList.remove("editing");
      }
    });
  }

  async _commitCell(rowIdx, colIdx, cell, input) {
    const item = this.pageData[rowIdx];
    if (!item) return;

    const rawValue = input.value || "";
    const isPron = colIdx === 3;
    const srcRef = item.src_ref;
    const source = this.currentSource;
    if (!source || !srcRef) return;

    // Capture the original value from the API (before any in-session edits)
    const origKey = isPron ? "_origPron" : "_origMean";
    const apiValue = isPron ? item.pronunciation || "" : item.meaning || "";
    const originalValue = item[origKey] !== undefined ? item[origKey] : apiValue;

    // Format the value (respect auto-format toggle)
    const applyFormat = this.autoFormatChk.checked;
    const formatted = applyFormat ? (isPron ? this._formatPronunciation(rawValue) : this._formatMeaning(rawValue)) : rawValue;

    // Update cell display
    cell.innerHTML = htmlEscape(formatted) || '<span style="color:var(--text-secondary);font-size:11px;">空</span>';
    cell.classList.remove("editing");

    // Remember original for future comparison (first edit only)
    if (item[origKey] === undefined) {
      item[origKey] = apiValue;
    }

    // Update local data
    if (isPron) {
      item.pronunciation = formatted;
    } else {
      item.meaning = formatted;
    }

    // Don't save if nothing changed
    if (formatted === originalValue) {
      return;
    }

    // Save indicator
    this.saveStatus.textContent = "⏳ 保存中…";
    this.saveStatus.className = "save-queue saving";

    try {
      await ApiClient.put(`/characters/${source}/${encodeURIComponent(srcRef)}`, {
        pronunciation: item.pronunciation,
        meaning: item.meaning,
      });
      // Show brief success indicator
      const indicator = document.createElement("span");
      indicator.className = "cell-save-indicator";
      indicator.textContent = "✓";
      cell.appendChild(indicator);
      setTimeout(() => indicator.remove(), 1500);

      this.saveStatus.textContent = `✅ 已保存 ${srcRef}`;
      this.saveStatus.className = "save-queue done";
      // Clear status after 2s
      clearTimeout(this._saveStatusTimer);
      this._saveStatusTimer = setTimeout(() => {
        this.saveStatus.textContent = "";
        this.saveStatus.className = "save-queue";
      }, 2000);
    } catch (e) {
      const indicator = document.createElement("span");
      indicator.className = "cell-save-error cell-save-indicator";
      indicator.textContent = "✗";
      cell.appendChild(indicator);
      setTimeout(() => indicator.remove(), 2000);

      this.saveStatus.textContent = `❌ 保存失败 ${srcRef}: ${e.message}`;
      this.saveStatus.className = "save-queue error";
      Notification.show(`保存失败 ${srcRef}: ${e.message}`, "error");
    }
  }

  // ── Jump to ref ───────────────────────────────────────

  async jumpToRef() {
    const ref = this.refInput.value.trim();
    if (!ref) {
      Notification.show("请输入 Ref 编号", "error");
      return;
    }
    if (!this.currentSource) {
      Notification.show("请先选择来源", "error");
      return;
    }

    this.loadStatus.textContent = "🔍 查找中…";
    this.loadStatus.style.color = "var(--text-secondary)";

    try {
      // Search for the ref page by page (max 1000 per page)
      let idx = -1;
      let page = 1;
      const BATCH = 1000;
      while (true) {
        const batch = await ApiClient.fetch(`/characters/${this.currentSource}?page=${page}&page_size=${BATCH}`);
        const items = batch.data || [];
        idx = items.findIndex((c) => c.src_ref === ref);
        if (idx !== -1) break;
        if (items.length < BATCH) break; // last page
        page++;
      }
      if (idx === -1) {
        Notification.show(`未找到 Ref: ${ref}`, "error");
        this.loadStatus.textContent = "❌ 未找到";
        this.loadStatus.style.color = "var(--danger)";
        return;
      }

      // Calculate the page number in the 20-row pagination
      const globalIdx = (page - 1) * BATCH + idx;
      const targetPage = Math.floor(globalIdx / this.pageSize) + 1;
      await this.loadPage(targetPage);

      // Highlight the row
      setTimeout(() => {
        const row = this.tableBody.querySelector(`tr[data-ref="${htmlEscape(ref)}"]`);
        if (row) {
          row.scrollIntoView({ behavior: "smooth", block: "center" });
          row.style.background = "var(--accent-bg)";
          setTimeout(() => {
            row.style.background = "";
          }, 2000);
        }
      }, 100);

      this.loadStatus.textContent = `🔍 已跳转到 ${ref}（第 ${targetPage} 页）`;
      this.loadStatus.style.color = "var(--success)";
    } catch (e) {
      Notification.show("查找失败: " + e.message, "error");
      this.loadStatus.textContent = "❌ 查找失败";
      this.loadStatus.style.color = "var(--danger)";
    }
  }

  // ── Formatting helpers ───────────────────────────────

  /** 取代 【】 → 〖〗 */
  _replaceBrackets(text) {
    return text.replace(/【/g, "〖").replace(/】/g, "〗");
  }

  /** 删除所有空格 */
  _removeSpaces(text) {
    return text.replace(/[\s\u3000]+/g, "");
  }

  /**
   * 汉字与 〖 之间自动补逗号。
   * 如果 〖 前面是非标点符号字符，插入 ，
   */
  _addCommaBeforeBracket(text) {
    return text.replace(/([^\s。，！？、；：·…—～\]」』】〙〗〕》〉〕])(〖)/g, "$1，$2");
  }

  /** 在连续 〖〗 之间自动添加逗号 */
  _addCommasBetweenBrackets(text) {
    return text.replace(/〗\s*〖/g, "〗，〖");
  }

  /** 〗后跟汉字时自动加句号 */
  _addPeriodAfterBracket(text) {
    return text.replace(/〗(?=[\u4e00-\u9fff\u3400-\u4dbf])/g, "〗。");
  }

  /** 英文标点 → 中文标点：()→（） ,→， .→。 */
  _normalizePunctuation(text) {
    return text.replace(/\(/g, "（").replace(/\)/g, "）").replace(/,/g, "，").replace(/\./g, "。");
  }

  /** 合并重复的中文标点：。。→。，，→， */
  _collapseRepeatedPunctuation(text) {
    return text.replace(/。。/g, "。").replace(/，，/g, "，");
  }

  /** 确保结尾有句号 */
  _ensureEndingPunctuation(text) {
    const enders = /[。！？…；\.!?;]$/;
    if (text.length === 0) return text;
    if (!enders.test(text)) return text + "。";
    return text;
  }

  // ── ASCII → IPA input method ──────────────────────────

  /**
   * Mapping table: ASCII input → IPA output.
   * Used in the pronunciation field to let users type
   * hard-to-enter IPA characters with simple ASCII sequences.
   *
   * Applied in order — multi-character keys must come first
   * so they match before shorter subsequences.
   */
  static get IPA_MAP() {
    return [
      // ── Prenasalization + affricate digraphs (longest) ──
      ["Ndzr", "ᶯd͡ʐ"],
      ["Ndzj", "ᶮd͡ʑ"],
      ["Ndz", "ⁿd͡z"],
      ["Ntcj", "ᶮt͡ɕ"],
      ["Nts", "ⁿt͡s"],
      ["Ntr", "ᶯʈ"],
      ["Ngh", "ᵑɡʰ"],
      ["Ng", "ᵑɡ"],
      ["Mb", "ᵐb"],
      ["drh", "ɖʰ"],
      ["trh", "ʈʰ"],
      ["tsrh", "t͡ʂʰ"],
      ["dzrh", "d͡ʐʰ"],
      ["tsh", "t͡sʰ"],
      ["dzh", "d͡zʰ"],
      ["tcjh", "t͡ɕʰ"],
      ["dzjh", "d͡ʑʰ"],
      ["srh", "ʂʰ"],
      ["zrh", "ʐʰ"],
      // ── Prenasalization (plain) ──
      ["N", "ⁿ"],
      ["M", "ᵐ"],
      // ── Affricates with tie bar ──
      ["ts", "t͡s"],
      ["dz", "d͡z"],
      ["tcj", "t͡ɕ"],
      ["dzj", "d͡ʑ"],
      ["tsr", "t͡ʂ"],
      ["dzr", "d͡ʐ"],
      // ── Retroflex fricatives / stops ──
      ["sr", "ʂ"],
      ["zr", "ʐ"],
      // ── Palatal fricatives ──
      ["cj", "ɕ"],
      ["zj", "ʑ"],
      // ── Lateral ──
      ["lh", "ɬ"],
      // ── Velar / uvular ──
      ["ng", "ŋ"],
      ["vx", "ɣ"],
      ["xx", "χ"],
      ["hh", "ɦ"],
      // ── Palatal nasal ──
      ["ny", "ɲ"],
      // ── Special vowels ──
      ["md", "ɯ"],
      ["vr", "ɤ"],
      ["ee", "ɛ"],
      ["cd", "ɔ"],
      ["aa", "ɑ"],
      ["ix", "ɿ"],
      ["ir", "ʅ"],
      ["ii", "ɪ"],
      ["uu", "ʊ"],
      ["ae", "æ"],
      ["ad", "ɒ"],
      ["ed", "ə"],
      ["er", "ɚ"],
      // ── Other letters ──
      ["A", "ᴀ"],
      ["g", "ɡ"],
      ["nr", "ɳ"],
      // ── Glottal stop ──
      ["?", "ʔ"],
      // ── Tie bar ──
      ["_", "͡"],
      // ── Creaky voice (after vowel) ──
      ["~", "̰"],
      // ── More rounded (after vowel) ──
      ["o:", "o̹"],
      // Aspiration h after consonant
      // (handled separately in _applyIPAMapping)
    ];
  }

  /**
   * Apply ASCII→IPA conversion to pronunciation text.
   * Also converts plain digits to superscript tone numbers.
   */
  _applyIPAMapping(text) {
    if (!text) return text;

    let result = text;

    // Step 1: Convert known digraphs (longest match first)
    const map = EntryGrid.IPA_MAP;
    // Sort by key length descending to match longest first
    const sorted = [...map].sort((a, b) => b[0].length - a[0].length);
    for (const [ascii, ipa] of sorted) {
      // Escape special regex chars in the ASCII key
      const escaped = ascii.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
      result = result.replace(new RegExp(escaped, "g"), ipa);
    }

    // Step 2: Aspiration — "h" after a consonant becomes ʰ
    const cons = "ptkbdgɡʈɖcɟqɢfvszʃʒɕʑʂʐxɣχʁħɦh";
    result = result.replace(new RegExp("([" + cons + "])h", "g"), "$1ʰ");

    // Step 3: Prenasalization — lowercase n/m before consonant,
    //         using the correct superscript variant.
    //         (n/m already consumed by explicit digraphs above are safe.)
    result = result.replace(/n(?=[ɡg])/g, "ᵑ"); // velar
    result = result.replace(/n(?=[ʈɖʂʐtʂdʐ])/g, "ᶯ"); // retroflex
    result = result.replace(/n(?=[cɟɕʑtɕdʑɲɲ])/g, "ᶮ"); // palatal
    result = result.replace(/n(?=[ptkbdʦʣtsdzfvt])/g, "ⁿ"); // dental/alveolar
    result = result.replace(/m(?=[pb])/g, "ᵐ"); // bilabial

    // Step 4: Plain digits → superscript tone numbers
    result = result.replace(/0/g, "⁰");
    result = result.replace(/1/g, "¹");
    result = result.replace(/2/g, "²");
    result = result.replace(/3/g, "³");
    result = result.replace(/4/g, "⁴");
    result = result.replace(/5/g, "⁵");

    // Step 5: Superscript minus for tone sandhi (e.g. 21-33 → ²¹⁻³³)
    //         Only convert hyphens that sit between superscript digits.
    result = result.replace(/([⁰¹²³⁴⁵])-([⁰¹²³⁴⁵])/g, "$1⁻$2");

    return result;
  }

  /** 对注音文本进行格式化（含 IPA 映射） */
  _formatPronunciation(text) {
    let result = this._removeSpaces(text);
    result = this._applyIPAMapping(result);
    return result;
  }

  /** 对释义文本进行完整格式化 */
  _formatMeaning(text) {
    let result = text;
    result = this._replaceBrackets(result);
    result = this._removeSpaces(result);
    result = this._normalizePunctuation(result);
    result = this._collapseRepeatedPunctuation(result);
    result = this._addCommaBeforeBracket(result);
    result = this._addCommasBetweenBrackets(result);
    result = this._addPeriodAfterBracket(result);
    result = this._ensureEndingPunctuation(result);
    return result;
  }

  // ── Helpers ──────────────────────────────────────────

  _showEmpty(msg) {
    this.tableEl.style.display = "none";
    this.paginationEl.style.display = "none";
    this.statsEl.style.display = "none";
    this.emptyEl.style.display = "";
    this.emptyEl.innerHTML = `<span class="empty-icon">📋</span>${htmlEscape(msg)}`;
  }
}

// ─── Boot ─────────────────────────────────────────────────────
const entryApp = new EntryGrid();
document.addEventListener("DOMContentLoaded", () => entryApp.init());
