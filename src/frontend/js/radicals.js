/**
 * Unified Yi Character Manager — Radical Assignment System
 *
 * 部首标注界面：为各个 book 的字形标注一个或多个部首及笔画数。
 * 单击部首面板切换标注/取消标注，每个部首可单独设笔画数。
 */

class RadicalApp {
  constructor() {
    this.$ = (id) => document.getElementById(id);

    this.currentSource = null;
    this.allData = []; // all characters from current source
    this.radicalList = []; // ordered radical glyphs
    this.selectedGlyph = null; // currently selected character glyph

    this.sourceSelect = this.$("sourceSelect");
    this.filterSelect = this.$("filterSelect");
    this.searchInput = this.$("searchInput");
    this.statsInfo = this.$("statsInfo");
    this.charGrid = this.$("charGrid");
    this.paletteGrid = this.$("paletteGrid");
    this.selGlyph = this.$("selGlyph");
    this.selRef = this.$("selRef");
    this.assignedRadicalsEl = this.$("assignedRadicals");
    this.btnClear = this.$("btnClear");
  }

  init() {
    this._loadSources();
    this.sourceSelect.addEventListener("change", () => this._onSourceChange());
    this.filterSelect.addEventListener("change", () => this._renderGrid());
    this.searchInput.addEventListener("input", () => this._renderGrid());

    // Enter key: save current, copy RS to next unassigned, select it
    document.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && this.selectedGlyph) {
        e.preventDefault();
        this._quickNext();
      }
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

  async _onSourceChange() {
    this.currentSource = this.sourceSelect.value;
    this.selectedGlyph = null;
    this._clearDetail();

    if (!this.currentSource) {
      this.charGrid.innerHTML = '<div class="loading" style="grid-column:1/-1;"><span class="spinner"></span> 请选择来源</div>';
      this.paletteGrid.innerHTML = "";
      return;
    }

    this.charGrid.innerHTML = '<div class="loading" style="grid-column:1/-1;"><span class="spinner"></span> 加载中…</div>';

    try {
      const [rsRes, orderRes] = await Promise.all([ApiClient.fetch(`/radical-data/${this.currentSource}`), ApiClient.fetch("/radical-order")]);

      this.allData = rsRes.data || [];
      this.radicalList = orderRes.radicals || rsRes.radicals || [];

      this._renderGrid();
      this._renderPalette();
      this._renderStats();
    } catch (e) {
      Notification.show("加载失败: " + e.message, "error");
      this.charGrid.innerHTML = `<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--danger);">❌ 加载失败: ${htmlEscape(e.message)}</div>`;
    }
  }

  // ── Rendering ─────────────────────────────────────────

  _getFilteredData() {
    const filter = this.filterSelect.value;
    const query = this.searchInput.value.trim().toLowerCase();

    let data = this.allData;
    if (filter === "unassigned") data = data.filter((d) => !d.has_rs);
    else if (filter === "assigned") data = data.filter((d) => d.has_rs);

    if (query) {
      data = data.filter((d) => d.glyph.includes(query) || d.src_ref.toLowerCase().includes(query));
    }
    return data;
  }

  _renderGrid() {
    const data = this._getFilteredData();

    if (data.length === 0) {
      this.charGrid.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:40px;color:var(--text-secondary);">没有匹配的字符</div>';
      return;
    }

    let html = "";
    for (const item of data) {
      const hasRs = item.has_rs;
      const rads = item.radicals || [];
      const strokes = item.strokes || [];
      const isSelected = this.selectedGlyph === item.glyph;

      html += `<div class="rs-card${isSelected ? " selected" : ""}"
                         onclick="rsApp.selectGlyph('${htmlEscape(item.glyph)}')"
                         data-glyph="${htmlEscape(item.glyph)}">`;
      html += `<span class="glyph">${htmlEscape(item.glyph)}</span>`;
      if (hasRs && rads.length > 0) {
        for (let j = 0; j < rads.length; j++) {
          html += `<span class="radical-badge">${htmlEscape(rads[j])}</span>`;
          if (strokes[j] !== undefined) {
            html += `<span class="stroke-num">${strokes[j]}画</span>`;
          }
        }
        html += `<span class="assigned-tag">✅</span>`;
      } else {
        html += `<span class="unassigned-tag">— 未标注</span>`;
      }
      html += `</div>`;
    }

    this.charGrid.innerHTML = html;
    this._renderStats();
  }

  _renderPalette() {
    if (!this.radicalList || this.radicalList.length === 0) {
      this.paletteGrid.innerHTML = '<div style="grid-column:1/-1;padding:20px;text-align:center;color:var(--text-secondary);">暂无部首数据</div>';
      return;
    }

    const assignedRads = this._getAssignedRadicals();

    let html = "";
    for (const rad of this.radicalList) {
      if (!rad || rad === "0") continue;
      const isActive = assignedRads.includes(rad);
      html += `<div class="rs-palette-item${isActive ? " active" : ""}"
                         onclick="rsApp.toggleRadical('${htmlEscape(rad)}')"
                         title="${isActive ? "点击移除部首" : "点击添加部首"}">${htmlEscape(rad)}</div>`;
    }
    this.paletteGrid.innerHTML = html;
  }

  _renderStats() {
    const total = this.allData.length;
    const assigned = this.allData.filter((d) => d.has_rs).length;
    const unassigned = total - assigned;
    this.statsInfo.innerHTML =
      `共 <strong>${total}</strong> 字 · ` + `<span class="assigned">已标注 <strong>${assigned}</strong></span> · ` + `<span class="unassigned">未标注 <strong>${unassigned}</strong></span>`;
  }

  // ── Selection ─────────────────────────────────────────

  selectGlyph(glyph) {
    if (this.selectedGlyph) {
      const prev = this.charGrid.querySelector(`.rs-card[data-glyph="${htmlEscape(this.selectedGlyph)}"]`);
      if (prev) prev.classList.remove("selected");
    }

    this.selectedGlyph = glyph;

    const card = this.charGrid.querySelector(`.rs-card[data-glyph="${htmlEscape(glyph)}"]`);
    if (card) card.classList.add("selected");

    this._updateDetail();
    this._renderPalette();

    this.btnClear.disabled = false;
  }

  _updateDetail() {
    if (!this.selectedGlyph) return this._clearDetail();

    const item = this.allData.find((d) => d.glyph === this.selectedGlyph);
    if (!item) return;

    this.selGlyph.textContent = item.glyph;
    this.selRef.textContent = item.src_ref;

    const rads = item.radicals || [];
    const strokes = item.strokes || [];

    if (rads.length === 0) {
      this.assignedRadicalsEl.innerHTML = '<div style="color:var(--text-secondary);font-size:12px;padding:8px;">尚未标注部首</div>';
      return;
    }

    let html = "";
    for (let j = 0; j < rads.length; j++) {
      html += `<div style="display:flex;align-items:center;gap:6px;margin-bottom:4px;padding:4px 6px;background:var(--bg);border-radius:4px;">`;
      html += `<span style="font-family:\'YiFont\';font-size:18px;">${htmlEscape(rads[j])}</span>`;
      html += `<input type="number" class="stroke-edit" data-idx="${j}" value="${strokes[j] || 0}"
                         min="0" max="30" style="width:50px;padding:2px 4px;border:1px solid var(--border);border-radius:3px;font-size:12px;text-align:center;">`;
      html += `<span style="font-size:11px;color:var(--text-secondary);">画</span>`;
      html += `<button class="btn btn-sm" style="margin-left:auto;padding:2px 8px;font-size:11px;color:var(--danger);" onclick="rsApp.removeRadical(${j})">✕</button>`;
      html += `</div>`;
    }
    this.assignedRadicalsEl.innerHTML = html;

    // Wire stroke change handlers
    this.assignedRadicalsEl.querySelectorAll(".stroke-edit").forEach((inp) => {
      inp.addEventListener("change", () => this._saveCurrent());
    });

    // Auto-focus first stroke input (for quick Enter → adjust flow)
    setTimeout(() => {
      const first = this.assignedRadicalsEl.querySelector(".stroke-edit");
      if (first) {
        first.focus();
        first.select();
      }
    }, 0);
  }

  _clearDetail() {
    this.selectedGlyph = null;
    this.selGlyph.textContent = "?";
    this.selRef.textContent = "—";
    this.assignedRadicalsEl.innerHTML = '<div style="color:var(--text-secondary);font-size:12px;padding:8px;">选择字形后在此编辑</div>';
    this.btnClear.disabled = true;
  }

  // ── Toggle / add / remove ─────────────────────────────

  _getAssignedRadicals() {
    if (!this.selectedGlyph) return [];
    const item = this.allData.find((d) => d.glyph === this.selectedGlyph);
    return item?.radicals || [];
  }

  async toggleRadical(rad) {
    if (!this.selectedGlyph) return;
    const item = this.allData.find((d) => d.glyph === this.selectedGlyph);
    if (!item) return;

    const rads = item.radicals || [];
    const strokes = item.strokes || [];
    const idx = rads.indexOf(rad);

    if (idx >= 0) {
      // Remove
      rads.splice(idx, 1);
      strokes.splice(idx, 1);
    } else {
      // Add with default stroke 0
      rads.push(rad);
      strokes.push(0);
    }

    item.radicals = rads;
    item.strokes = strokes;
    item.radical = rads.join(",");
    item.other_stroke = strokes.join(",");
    item.has_rs = rads.length > 0;

    await this._saveCurrent();
    this._renderGrid();
    this._renderPalette();
    this._updateDetail();
  }

  async removeRadical(idx) {
    if (!this.selectedGlyph) return;
    const item = this.allData.find((d) => d.glyph === this.selectedGlyph);
    if (!item) return;

    const rads = item.radicals || [];
    const strokes = item.strokes || [];
    if (idx < 0 || idx >= rads.length) return;

    rads.splice(idx, 1);
    strokes.splice(idx, 1);

    item.radicals = rads;
    item.strokes = strokes;
    item.radical = rads.join(",");
    item.other_stroke = strokes.join(",");
    item.has_rs = rads.length > 0;

    await this._saveCurrent();
    this._renderGrid();
    this._renderPalette();
    this._updateDetail();
  }

  async clearRadical() {
    if (!this.selectedGlyph) return;
    const item = this.allData.find((d) => d.glyph === this.selectedGlyph);
    if (!item) return;

    item.radicals = [];
    item.strokes = [];
    item.radical = "";
    item.other_stroke = "";
    item.has_rs = false;

    await this._saveCurrent();
    this._renderGrid();
    this._renderPalette();
    this._updateDetail();
    Notification.show(`✕ 已清除 ${this.selectedGlyph} 所有部首`, "info");
  }

  async _saveCurrent() {
    if (!this.selectedGlyph) return;
    const item = this.allData.find((d) => d.glyph === this.selectedGlyph);
    if (!item) return;

    // Read current stroke values from inputs
    const inputs = this.assignedRadicalsEl.querySelectorAll(".stroke-edit");
    inputs.forEach((inp) => {
      const idx = parseInt(inp.dataset.idx);
      if (idx >= 0 && idx < item.strokes.length) {
        item.strokes[idx] = parseInt(inp.value) || 0;
      }
    });

    // Sync string fields
    item.other_stroke = item.strokes.join(",");

    const glyph = this.selectedGlyph;
    try {
      await ApiClient.put(`/radical-data/${this.currentSource}/${encodeURIComponent(glyph)}` + `?radical=${encodeURIComponent(item.radical)}&other_stroke=${encodeURIComponent(item.other_stroke)}`);
      this._renderGrid();
    } catch (e) {
      Notification.show("保存失败: " + e.message, "error");
    }
  }

  // ── Quick annotation: Enter copies RS to next glyph ─────

  async _quickNext() {
    const curItem = this.allData.find((d) => d.glyph === this.selectedGlyph);
    if (!curItem) return;

    // Save current first
    await this._saveCurrent();

    // Find next glyph in the filtered grid
    const filtered = this._getFilteredData();
    const curIdx = filtered.findIndex((d) => d.glyph === this.selectedGlyph);
    if (curIdx < 0 || curIdx + 1 >= filtered.length) {
      Notification.show("已是最后一个字", "info");
      return;
    }

    const nextItem = filtered[curIdx + 1];

    // Copy radicals & strokes from current to next
    const srcRads = curItem.radicals || [];
    const srcStrokes = curItem.strokes || [];
    const tgtRads = nextItem.radicals || [];
    const tgtStrokes = nextItem.strokes || [];

    // Merge: add any source radicals not already in target
    let changed = false;
    for (let j = 0; j < srcRads.length; j++) {
      if (!tgtRads.includes(srcRads[j])) {
        tgtRads.push(srcRads[j]);
        tgtStrokes.push(srcStrokes[j] || 0);
        changed = true;
      }
    }

    if (changed) {
      nextItem.radicals = tgtRads;
      nextItem.strokes = tgtStrokes;
      nextItem.radical = tgtRads.join(",");
      nextItem.other_stroke = tgtStrokes.join(",");
      nextItem.has_rs = tgtRads.length > 0;

      // Save next item
      try {
        await ApiClient.put(
          `/radical-data/${this.currentSource}/${encodeURIComponent(nextItem.glyph)}` + `?radical=${encodeURIComponent(nextItem.radical)}&other_stroke=${encodeURIComponent(nextItem.other_stroke)}`,
        );
      } catch (e) {
        Notification.show("保存失败: " + e.message, "error");
      }
    }

    // Select next
    this.selectGlyph(nextItem.glyph);
    // Scroll into view
    const card = this.charGrid.querySelector(`.rs-card[data-glyph="${htmlEscape(nextItem.glyph)}"]`);
    if (card) card.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }
}

// ─── Boot ─────────────────────────────────────────────────────
const rsApp = new RadicalApp();
document.addEventListener("DOMContentLoaded", () => rsApp.init());
