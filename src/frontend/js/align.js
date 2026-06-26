/**
 * Unified Yi Character Manager — Alignment Page
 *
 * Workflow: Pick chars from any source → batch suggestions from all other sources → save group.
 */

class AlignmentApp {
  constructor() {
    this.st = {
      sources: [],
      pickSource: null,
      pickPage: 1,
      pickSearch: "",
      currentGroup: [],
      suggestions: {},
      searchResults: {},
      groupSuggestions: [],
      groupSearch: "",
      alignedKeys: new Map(), // "source:src_ref" → groupId
      hiddenSources: new Set(),
    };
    this.progress = new ProgressBar();
    this._suggestTimer = null;
  }

  async init() {
    this.progress.show("📂 正在加载数据…", 5);
    try {
      this.progress.advance(10, "📂 正在加载来源…");
      this.st.sources = await ApiClient.fetch("/sources");

      this.progress.advance(25, "🔑 正在加载对齐索引…");
      await this._loadAlignedKeys();

      this.progress.advance(45, "📋 正在加载当前组…");
      this._populateSelects();
      await this._loadCurrentGroup();

      this.progress.advance(100, "✅ 就绪");
      this.progress.hide();
    } catch (err) {
      this.progress.hide();
      Notification.show("Init failed: " + err.message, "error");
    }
  }

  // ── 初始化辅助 ─────────────────────────────────────────

  _populateSelects() {
    const sel = document.getElementById("pickSource");
    if (!sel) return;
    sel.innerHTML = this.st.sources.map((s) => `<option value="${s.id}">${s.id} — ${s.name}</option>`).join("");
    if (this.st.sources.length) {
      sel.value = this.st.sources[0].id;
      this.st.pickSource = this.st.sources[0].id;
      this._loadPickList();
    }
    this._buildSourceToggles();
  }

  _buildSourceToggles() {
    const container = document.getElementById("sourceToggles");
    if (!container) return;
    container.innerHTML = this.st.sources
      .map((s) => {
        const checked = !this.st.hiddenSources.has(s.id);
        return `<label style="cursor:pointer;white-space:nowrap;display:inline-flex;align-items:center;gap:3px;">
                <input type="checkbox" ${checked ? "checked" : ""} onchange="app.toggleSource('${s.id}',this.checked)" style="margin:0;">
                ${s.id}
            </label>`;
      })
      .join("");
  }

  toggleSource(sourceId, show) {
    if (show) this.st.hiddenSources.delete(sourceId);
    else this.st.hiddenSources.add(sourceId);
    this._renderBatchSuggestions();
  }

  switchPickSource() {
    this.st.pickSource = document.getElementById("pickSource").value;
    this.st.pickPage = 1;
    this.st.pickSearch = "";
    document.getElementById("pickSearch").value = "";
    this._loadPickList();
  }

  // ── Character Picker ───────────────────────────────────

  doPickSearch() {
    this.st.pickSearch = document.getElementById("pickSearch").value;
    this.st.pickPage = 1;
    this._loadPickList();
  }

  async _loadPickList() {
    const tbody = document.getElementById("pickCharList");
    if (!tbody) return;
    const scrollContainer = tbody.parentElement.parentElement;
    const needsScrollRestore = scrollContainer && scrollContainer.scrollTop > 0;
    const prevScrollTop = needsScrollRestore ? scrollContainer.scrollTop : 0;

    try {
      const p = new URLSearchParams({ page: this.st.pickPage, page_size: 50, search: this.st.pickSearch });
      const r = await ApiClient.fetch(`/characters/${this.st.pickSource}?${p}`);
      document.getElementById("pickSourceLabel").textContent = this.st.pickSource;
      document.getElementById("pickTotal").textContent = r.total.toLocaleString();

      const currentKeys = new Set(this.st.currentGroup.map((e) => `${e.source}:${e.src_ref}`));

      tbody.innerHTML = r.data
        .map((c) => {
          const key = `${this.st.pickSource}:${c.src_ref}`;
          const inGroup = currentKeys.has(key);
          const aligned = this.st.alignedKeys.has(key);
          return `<tr class="${inGroup ? "selected" : ""}${aligned ? " aligned" : ""}" data-ref="${htmlEscape(c.src_ref)}" onclick="${inGroup ? "" : "app.pickChar('" + htmlEscape(c.src_ref) + "')"}"${aligned ? ' title="点击加载该组"' : ""}>
                    <td class="glyph-cell">${c.glyph}</td>
                    <td class="src-ref">${htmlEscape(c.src_ref)}</td>
                    <td style="font-size:10px;color:var(--info);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">/${htmlEscape(c.pronunciation || "")}/</td>
                    <td style="font-size:10px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:120px;">${htmlEscape((c.meaning || "").slice(0, 20))}</td>
                    <td class="status-cell" style="text-align:center;">${inGroup ? "✓" : aligned ? "🔗" : "+"}</td>
                </tr>`;
        })
        .join("");

      this._renderPickPagination(r);
      if (needsScrollRestore) {
        requestAnimationFrame(() => {
          scrollContainer.scrollTop = prevScrollTop;
        });
      }
    } catch (err) {
      tbody.innerHTML = `<tr><td colspan="3" style="color:red;">${err.message}</td></tr>`;
    }
  }

  _renderPickPagination(r) {
    const pag = document.getElementById("pickPagination");
    if (!pag) return;
    if (r.total_pages <= 1) {
      pag.innerHTML = "";
      return;
    }
    const total = r.total_pages;
    pag.innerHTML = `<button ${this.st.pickPage <= 1 ? "disabled" : ""} onclick="app.pagePick(${this.st.pickPage - 1})">←</button>
            <input type="text" id="pickPageInput" value="${this.st.pickPage}"
                   style="width:36px;text-align:center;padding:2px 4px;border:1px solid var(--border);border-radius:4px;font-size:11px;background:var(--surface);color:var(--text);"
                   onkeydown="if(event.key==='Enter')app.jumpPickPage()" onfocus="this.select()">
            <span style="font-size:11px;color:var(--text-secondary);">/ ${total}</span>
            <button ${this.st.pickPage >= total ? "disabled" : ""} onclick="app.pagePick(${this.st.pickPage + 1})">→</button>`;
  }

  pagePick(p) {
    this.st.pickPage = p;
    this._loadPickList();
  }

  jumpPickPage() {
    const input = document.getElementById("pickPageInput");
    const p = parseInt(input?.value, 10);
    if (isNaN(p) || p < 1) {
      input.value = this.st.pickPage;
      return;
    }
    this.st.pickPage = p;
    this._loadPickList();
  }

  // ── Pick / Add / Remove ────────────────────────────────

  async pickChar(srcRef) {
    const key = `${this.st.pickSource}:${srcRef}`;
    if (this.st.alignedKeys.has(key)) {
      // 已归组的字符 → 加载该组到工作区
      const gid = this.st.alignedKeys.get(key);
      await this.loadGroupFromExisting(gid);
      return;
    }
    if (this.st.currentGroup.some((e) => `${e.source}:${e.src_ref}` === key)) return;

    try {
      const char = await ApiClient.fetch(`/character/${this.st.pickSource}/${srcRef}`);
      this.st.currentGroup.push({ source: this.st.pickSource, src_ref: srcRef, char });
      this._renderCurrentGroup();
      const row = document.querySelector(`#pickCharList tr[data-ref="${srcRef}"]`);
      if (row) {
        row.className = "selected";
        row.onclick = null;
        const statusCell = row.querySelector(".status-cell");
        if (statusCell) statusCell.textContent = "✓";
      }
      this._updateButtons();
      await this._autoSave();
      // 自动触发推荐计算
      this._fetchBatchSuggestions();
    } catch (err) {
      Notification.show("Failed: " + err.message, "error");
    }
  }

  async addSuggestionToGroup(source, srcRef) {
    const key = `${source}:${srcRef}`;
    if (this.st.alignedKeys.has(key)) {
      Notification.show("Already in an existing group", "info");
      return;
    }
    if (this.st.currentGroup.some((e) => `${e.source}:${e.src_ref}` === key)) return;

    try {
      const char = await ApiClient.fetch(`/character/${source}/${srcRef}`);
      this.st.currentGroup.push({ source, src_ref: srcRef, char });
      this._renderCurrentGroup();
      if (source === this.st.pickSource) {
        const row = document.querySelector(`#pickCharList tr[data-ref="${srcRef}"]`);
        if (row) {
          row.className = "selected";
          row.onclick = null;
          const statusCell = row.querySelector(".status-cell");
          if (statusCell) statusCell.textContent = "✓";
        }
      }
      this._updateButtons();
      await this._autoSave();
      this._fetchBatchSuggestions();
    } catch (err) {
      Notification.show("Failed: " + err.message, "error");
    }
  }

  async removeFromGroup(idx) {
    const removed = this.st.currentGroup[idx];
    this.st.currentGroup.splice(idx, 1);
    this._renderCurrentGroup();
    if (removed && removed.source === this.st.pickSource) {
      const row = document.querySelector(`#pickCharList tr[data-ref="${removed.src_ref}"]`);
      if (row) {
        const aligned = this.st.alignedKeys.has(`${removed.source}:${removed.src_ref}`);
        row.className = aligned ? "aligned" : "";
        const ref = removed.src_ref;
        row.onclick = function () {
          app.pickChar(ref);
        };
        const statusCell = row.querySelector(".status-cell");
        if (statusCell) statusCell.textContent = aligned ? "🔗" : "+";
      }
    }
    if (this.st.currentGroup.length === 0) {
      this._updateButtons();
      document.getElementById("batchSuggestions").style.display = "none";
      this.st.suggestions = {};
      this.st.searchResults = {};
      await ApiClient.delete("/alignments/current-group");
    } else {
      await this._autoSave();
      this._fetchBatchSuggestions();
    }
  }

  async clearCurrentGroup() {
    this.progress.show("🧹 正在清空工作区…", 30);
    this.st.currentGroup = [];
    this.st.suggestions = {};
    this._renderCurrentGroup();
    this._loadPickList();
    this._updateButtons();
    document.getElementById("batchSuggestions").style.display = "none";
    this.progress.advance(70, "🧹 正在清除远程数据…");
    await ApiClient.delete("/alignments/current-group");
    this.progress.hide();
  }

  // ── Render current group ───────────────────────────────

  _renderCurrentGroup() {
    const el = document.getElementById("currentGroupDisplay");
    const countEl = document.getElementById("currentGroupCount");
    if (!el) return;

    countEl.textContent = `${this.st.currentGroup.length} entries`;

    if (this.st.currentGroup.length === 0) {
      el.innerHTML = '<p style="color:var(--text-secondary);font-size:13px;padding:20px 0;text-align:center;">Pick a character from the left panel to start a group</p>';
      return;
    }

    el.innerHTML = `<div style="display:flex;flex-wrap:wrap;gap:6px;">
            ${this.st.currentGroup
              .map((e, i) => {
                const c = e.char || {};
                return `<div style="display:flex;align-items:center;gap:6px;padding:3px 8px;border:1px solid var(--border);border-radius:var(--radius);background:var(--bg);">
                    <span style="font-family:'YiFont';font-size:22px;">${c.glyph || "?"}</span>
                    <div style="line-height:1.3;">
                        <div style="font-size:12px;"><strong>${htmlEscape(e.source)}</strong> · ${htmlEscape(e.src_ref)}</div>
                        <div style="font-family:'Gentium Plus',serif;font-size:11px;color:var(--info);">/${htmlEscape(c.pronunciation || "")}/</div>
                        <div style="font-size:10px;">${htmlEscape((c.meaning || "").slice(0, 30))}</div>
                    </div>
                    <button class="btn btn-sm btn-danger" onclick="app.removeFromGroup(${i})" title="Remove">✕</button>
                </div>`;
              })
              .join("")}
        </div>`;
  }

  _showSuggestionHint() {
    const container = document.getElementById("batchSuggestions");
    const body = document.getElementById("batchSuggestionsBody");
    if (!container || !body) return;
    if (this.st.currentGroup.length < 1) {
      container.style.display = "none";
      return;
    }
    container.style.display = "block";
    body.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text-secondary);font-size:13px;">⏳ 正在自动计算推荐…</div>';
    this._fetchBatchSuggestions();
  }

  _updateButtons() {
    document.getElementById("btnSaveGroup").disabled = this.st.currentGroup.length < 2;
  }

  // ── Batch Suggestions ──────────────────────────────────

  async _fetchBatchSuggestions() {
    // 防抖：取消之前的未执行请求
    if (this._suggestTimer) {
      clearTimeout(this._suggestTimer);
      this._suggestTimer = null;
      // 如果已经有结果显示，暂不刷新，等用户停止操作后再计算
    }

    if (this.st.currentGroup.length < 1) {
      document.getElementById("batchSuggestions").style.display = "none";
      return;
    }

    // 延迟 300ms 执行，避免频繁操作时多次请求
    this._suggestTimer = setTimeout(async () => {
      this._suggestTimer = null;
      this._doFetchBatchSuggestions();
    }, 300);
  }

  async _doFetchBatchSuggestions() {
    const entries = this.st.currentGroup.map((e) => e.src_ref);

    this.progress.show("🔍 正在计算推荐…", 10);
    try {
      this.progress.advance(15, "🔍 正在跨源匹配…");
      const chResult = await ApiClient.post("/suggest-alignments/batch", { entries });
      this.st.suggestions = chResult.suggestions_by_source || {};
      this.st.searchResults = {};

      const usedPairs = new Set(this.st.currentGroup.map((e) => `${e.source}:${e.src_ref}`));
      for (const [src, items] of Object.entries(this.st.suggestions)) {
        this.st.suggestions[src] = items.filter((item) => !usedPairs.has(`${src}:${item.src_ref}`));
        if (this.st.suggestions[src].length === 0) delete this.st.suggestions[src];
      }

      this.progress.advance(60, "🔍 正在查找相似群组…");
      try {
        const grpResult = await ApiClient.post("/suggest-groups/batch", { entries });
        this.st.groupSuggestions = grpResult.suggestions || [];
        this.st.groupSearch = "";
      } catch (e) {
        this.st.groupSuggestions = [];
        this.st.groupSearch = "";
      }

      this.progress.advance(85, "📊 正在渲染结果…");
      this._renderBatchSuggestions();
      this.progress.hide();
    } catch (err) {
      this.progress.hide();
      console.error("Batch suggestions failed", err);
    }
  }

  _renderBatchSuggestions() {
    const container = document.getElementById("batchSuggestions");
    const body = document.getElementById("batchSuggestionsBody");
    if (!container || !body) return;

    const sources = Object.keys(this.st.suggestions).filter((src) => !this.st.hiddenSources.has(src));
    if (sources.length === 0 && this.st.groupSuggestions.length === 0) {
      container.style.display = "none";
      return;
    }

    container.style.display = "block";

    // ─── 来源建议卡片 ───
    const sourceCards = sources
      .map((src) => {
        const items = this.st.suggestions[src] || [];
        if (items.length === 0) return "";
        const meta = this.st.sources.find((s) => s.id === src) || {};
        const sr = this.st.searchResults[src] || [];
        return `<div style="flex:1;min-width:180px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:8px;">
                <div style="font-size:11px;font-weight:700;color:var(--accent);margin-bottom:4px;">
                    <span class="region-badge ${meta.group || "other"}">${meta.region || src}</span> ${src}
                </div>
                <div style="display:flex;gap:3px;margin-bottom:6px;">
                    <input type="text" id="refSearch_${src}" placeholder="搜索 src-ref / 读音 / 含义…" style="flex:1;min-width:0;padding:3px 4px;border:1px solid var(--border);border-radius:4px;font-size:11px;background:var(--surface);"
                           onkeydown="if(event.key==='Enter')app.searchRefInSource('${src}')">
                    <button class="btn btn-sm" style="flex-shrink:0;padding:2px 6px;font-size:11px;" onclick="app.searchRefInSource('${src}')">🔍</button>
                </div>
                ${
                  sr.length > 0
                    ? `<div style="max-height:180px;overflow-y:auto;margin-bottom:6px;border-bottom:1px solid var(--border);padding-bottom:4px;">
                    <div style="font-size:10px;color:var(--text-secondary);margin-bottom:2px;">🔍 搜索结果</div>
                    ${sr
                      .map((item) => {
                        const key = `${src}:${item.src_ref}`;
                        const inGroup = this.st.currentGroup.some((e) => `${e.source}:${e.src_ref}` === key);
                        const aligned = this.st.alignedKeys.has(key);
                        const disabled = inGroup || aligned;
                        return `<div style="display:flex;align-items:center;gap:5px;padding:3px 6px;margin-bottom:3px;border-radius:4px;${disabled ? "" : "cursor:pointer;"}background:var(--surface);"
                                    ${disabled ? "" : "onclick=\"app.addSearchResultToGroup('" + src + "','" + htmlEscape(item.src_ref) + "')\""}>
                            <span style="font-family:'YiFont';font-size:18px;flex-shrink:0;">${item.glyph}</span>
                            <div style="flex:1;min-width:0;">
                                <div style="display:flex;align-items:baseline;gap:4px;">
                                    <span style="font-size:10px;color:var(--info);white-space:nowrap;">/${htmlEscape(item.pronunciation)}/</span>
                                    <span style="font-size:10px;color:var(--text-secondary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${htmlEscape(item.src_ref)}</span>
                                </div>
                                <div style="font-size:9px;color:var(--text-secondary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${htmlEscape((item.meaning || "").slice(0, 30))}</div>
                            </div>
                            <span style="font-size:16px;color:${disabled ? "var(--text-secondary)" : "var(--success)"};flex-shrink:0;">${disabled ? "✓" : "+"}</span>
                        </div>`;
                      })
                      .join("")}
                </div>`
                    : ""
                }
                <div style="max-height:300px;overflow-y:auto;">
                ${items
                  .slice(0, 20)
                  .map(
                    (item) => `
                    <div style="display:flex;align-items:center;gap:5px;padding:3px 6px;margin-bottom:3px;border-radius:4px;cursor:pointer;background:var(--surface);"
                         onclick="app.addSuggestionToGroup('${src}','${htmlEscape(item.src_ref)}')">
                        <span style="font-family:'YiFont';font-size:18px;flex-shrink:0;">${item.glyph}</span>
                        <div style="flex:1;min-width:0;">
                            <div style="display:flex;align-items:baseline;gap:4px;">
                                <span style="font-size:10px;color:var(--info);white-space:nowrap;">/${htmlEscape(item.pronunciation)}/</span>
                                <span style="font-size:10px;color:var(--text-secondary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${htmlEscape((item.meaning || "").slice(0, 25))}</span>
                            </div>
                            <div class="score-bar" style="width:100%;height:3px;margin-top:2px;">
                                <div class="fill ${scoreColor(item.combined_score)}" style="width:${(item.combined_score * 100).toFixed(0)}%"></div>
                            </div>
                        </div>
                        <span style="font-size:16px;color:var(--success);flex-shrink:0;">+</span>
                    </div>
                `,
                  )
                  .join("")}
                </div>
            </div>`;
      })
      .join("");

    // ─── 相似群组建议（一个卡片，带搜索栏）放在最后 ───
    let groupHtml = "";
    if (this.st.groupSuggestions && this.st.groupSuggestions.length > 0) {
      const query = this.st.groupSearch.toLowerCase().trim();
      const filtered = query
        ? this.st.groupSuggestions.filter((gs) => {
            const idStr = "G" + String(gs.group_id).padStart(5, "0");
            if (idStr.toLowerCase().includes(query)) return true;
            return (gs.preview || []).some((p) => {
              const c = p.char || {};
              return (
                (p.source || "").toLowerCase().includes(query) ||
                (p.src_ref || "").toLowerCase().includes(query) ||
                (c.pronunciation || "").toLowerCase().includes(query) ||
                (c.meaning || "").toLowerCase().includes(query) ||
                (c.glyph || "").includes(query)
              );
            });
          })
        : this.st.groupSuggestions;

      const items = filtered
        .map((gs) => {
          const preview = (gs.preview || []).slice(0, 2);
          const p0 = (preview[0] && preview[0].char) || {};
          const p1 = (preview[1] && preview[1].char) || {};
          return `<div style="display:flex;align-items:center;gap:6px;padding:5px 8px;margin-bottom:3px;border-radius:4px;cursor:pointer;background:var(--surface);"
                            onclick="app.addGroupToCurrent(${gs.group_id})">
                        <div style="display:flex;align-items:center;gap:2px;flex-shrink:0;">
                            <span style="font-family:'YiFont';font-size:22px;line-height:1.1;">${htmlEscape(p0.glyph || "?")}</span>
                            <span style="font-family:'YiFont';font-size:22px;line-height:1.1;">${htmlEscape(p1.glyph || "?")}</span>
                        </div>
                        <div style="flex:1;min-width:0;font-size:11px;">
                            <div style="font-weight:700;">G${String(gs.group_id).padStart(5, "0")}</div>
                            <div class="score-bar" style="width:100%;height:3px;margin-top:3px;">
                                <div class="fill ${scoreColor(gs.similarity)}" style="width:${(gs.similarity * 100).toFixed(0)}%"></div>
                            </div>
                        </div>
                        <span style="font-size:18px;color:var(--success);flex-shrink:0;">+</span>
                    </div>`;
        })
        .join("");

      const showAll = filtered.length < this.st.groupSuggestions.length;
      groupHtml = `<div style="flex:1;min-width:180px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:8px;">
            <div style="font-size:11px;font-weight:700;color:var(--accent);margin-bottom:4px;">📂 Similar Existing Groups</div>
            <div style="display:flex;gap:3px;margin-bottom:6px;">
                <input type="text" id="groupSuggestSearch" placeholder="搜索 ID / 字 / 读音 / 含义…" style="flex:1;min-width:0;padding:3px 4px;border:1px solid var(--border);border-radius:4px;font-size:11px;background:var(--surface);"
                       value="${htmlEscape(this.st.groupSearch)}"
                       onkeydown="if(event.key==='Enter')app.doGroupSuggestSearch()" oninput="app.doGroupSuggestSearch()">
            </div>
            <div style="max-height:300px;overflow-y:auto;">
                ${items}
                ${showAll ? `<div style="font-size:10px;color:var(--text-secondary);text-align:center;padding:4px;">显示 ${filtered.length}/${this.st.groupSuggestions.length} 组</div>` : ""}
            </div>
        </div>`;
    }

    body.innerHTML = sourceCards + groupHtml;
  }

  // ── Search within group suggestions ───────────────────

  doGroupSuggestSearch() {
    const input = document.getElementById("groupSuggestSearch");
    this.st.groupSearch = input ? input.value : "";
    this._renderBatchSuggestions();
  }

  // ── Search in source card ─────────────────────────────

  async searchRefInSource(src) {
    const input = document.getElementById("refSearch_" + src);
    const query = input ? input.value.trim() : "";
    if (!query) {
      Notification.show("请输入搜索词", "error");
      return;
    }

    try {
      const p = new URLSearchParams({ page: 1, page_size: 20, search: query });
      const r = await ApiClient.fetch(`/characters/${src}?${p}`);
      this.st.searchResults[src] = r.data || [];
      this._renderBatchSuggestions();
    } catch (e) {
      Notification.show("搜索失败: " + e.message, "error");
    }
  }

  // ── Add fuzzy search result to current group ─────────

  async addSearchResultToGroup(src, srcRef) {
    const key = `${src}:${srcRef}`;
    if (this.st.alignedKeys.has(key)) {
      Notification.show("已在其他组中", "info");
      return;
    }
    if (this.st.currentGroup.some((e) => `${e.source}:${e.src_ref}` === key)) {
      Notification.show("已在当前组中", "info");
      return;
    }

    try {
      const char = await ApiClient.fetch(`/character/${src}/${encodeURIComponent(srcRef)}`);
      this.st.currentGroup.push({ source: src, src_ref: srcRef, char });
      this._renderCurrentGroup();
      if (src === this.st.pickSource) {
        const row = document.querySelector(`#pickCharList tr[data-ref="${srcRef}"]`);
        if (row) {
          row.className = "selected";
          row.onclick = null;
          const statusCell = row.querySelector(".status-cell");
          if (statusCell) statusCell.textContent = "✓";
        }
      }
      this._updateButtons();
      this.st.searchResults[src] = (this.st.searchResults[src] || []).filter((item) => item.src_ref !== srcRef);
      await this._autoSave();
      this._updateButtons();
      this._fetchBatchSuggestions();
      Notification.show(`✅ 已添加 ${srcRef}`, "success");
    } catch (e) {
      Notification.show(`添加失败: ${e.message}`, "error");
    }
  }

  // ── Save current group → permanent → clear working ───

  async saveCurrentGroup() {
    if (this.st.currentGroup.length < 2) {
      Notification.show("Need at least 2 characters to form a group", "error");
      return;
    }

    const entries = this.st.currentGroup.map((e) => e.src_ref);
    const seen = new Set();
    const unique = entries.filter((ref) => {
      if (seen.has(ref)) return false;
      seen.add(ref);
      return true;
    });

    this.progress.show("💾 正在保存对齐组…", 10);
    try {
      this.progress.advance(30, "💾 正在写入数据…");
      const result = await ApiClient.post("/alignments", { entries: unique, note: "" });
      Notification.show(`✅ Saved: ${unique.length} chars (${result.action})`, "success");

      this.progress.advance(50, "🧹 正在清理工作区…");
      await ApiClient.delete("/alignments/current-group");
      this.st.currentGroup = [];
      this.st.suggestions = {};
      this.st.searchResults = {};
      this._renderCurrentGroup();
      this._updateButtons();
      document.getElementById("batchSuggestions").style.display = "none";

      this.progress.advance(65, "🔄 正在刷新对齐数据…");
      await this._loadAlignedKeys();

      this.progress.advance(80, "🔄 正在刷新列表…");
      this._loadPickList();

      this.progress.advance(100, "✅ 保存完成");
      this.progress.hide();
    } catch (err) {
      this.progress.hide();
      Notification.show("Save failed: " + err.message, "error");
    }
  }

  // ── Load existing group into working area ────────────

  async loadGroupFromExisting(groupId) {
    this.progress.show(`📂 正在加载群组 G${groupId}…`, 10);
    try {
      this.progress.advance(30, "📂 正在获取数据…");
      const allGroups = await ApiClient.fetch("/alignments");
      const grp = allGroups.find((g) => g.id === groupId);
      if (!grp) {
        this.progress.hide();
        Notification.show("Group not found", "error");
        return;
      }

      this.st.currentGroup = [];
      for (let i = 0; i < grp.entries.length; i++) {
        const e = grp.entries[i];
        if (e.char) {
          this.st.currentGroup.push({ source: e.source, src_ref: e.src_ref, char: e.char });
        }
      }
      this.progress.advance(50, "📋 正在更新界面…");
      this._renderCurrentGroup();
      this._loadPickList();
      this._updateButtons();

      this.progress.advance(65, "💾 正在自动保存…");
      await this._autoSave();

      this.progress.advance(75, "✅ 就绪");
      this._fetchBatchSuggestions();

      this.progress.hide();
      Notification.show(`Loaded group G${groupId} (${this.st.currentGroup.length} entries)`, "info");
    } catch (err) {
      this.progress.hide();
      Notification.show("Failed to load group: " + err.message, "error");
    }
  }

  // ── Add existing group entries into current working group ─

  async addGroupToCurrent(groupId) {
    this.progress.show(`📂 正在合并群组 G${groupId}…`, 10);
    try {
      this.progress.advance(25, "📂 正在获取数据…");
      const allGroups = await ApiClient.fetch("/alignments");
      const grp = allGroups.find((g) => g.id === groupId);
      if (!grp) {
        this.progress.hide();
        Notification.show("Group not found", "error");
        return;
      }

      const currentKeys = new Set(this.st.currentGroup.map((e) => `${e.source}:${e.src_ref}`));
      let added = 0;
      for (let i = 0; i < grp.entries.length; i++) {
        const e = grp.entries[i];
        const key = `${e.source}:${e.src_ref}`;
        if (currentKeys.has(key)) continue;
        if (!e.char) continue;
        this.st.currentGroup.push({ source: e.source, src_ref: e.src_ref, char: e.char });
        currentKeys.add(key);
        added++;
      }
      if (added === 0) {
        this.progress.hide();
        Notification.show("All entries already in current group", "info");
        return;
      }

      this.progress.advance(50, "📋 正在更新界面…");
      this._renderCurrentGroup();
      this._loadPickList();
      this._updateButtons();

      this.progress.advance(65, "💾 正在自动保存…");
      await this._autoSave();

      this.progress.advance(75, "✅ 就绪");
      this._fetchBatchSuggestions();

      this.progress.hide();
      Notification.show(`Added ${added} entries from group G${groupId}`, "success");
    } catch (err) {
      this.progress.hide();
      Notification.show("Failed: " + err.message, "error");
    }
  }

  // ── Auto-save / load working group ────────────────────

  async _autoSave() {
    const entries = this.st.currentGroup.map((e) => e.src_ref);
    try {
      await ApiClient.post("/alignments/current-group", { entries, note: "" });
    } catch (err) {
      /* silent auto-save */
    }
  }

  async _loadCurrentGroup() {
    try {
      const data = await ApiClient.fetch("/alignments/current-group");
      const entries = data.entries || [];
      for (let i = 0; i < entries.length; i++) {
        const ref = entries[i];
        try {
          const src = ref.split("-")[0].toLowerCase();
          this.progress.advance(45 + Math.round((i / entries.length) * 15), `📋 正在加载条目 ${i + 1}/${entries.length}…`);
          const char = await ApiClient.fetch(`/character/${src}/${ref}`);
          this.st.currentGroup.push({ source: src, src_ref: ref, char });
        } catch (err) {
          /* skip invalid */
        }
      }
      this._renderCurrentGroup();
      if (this.st.currentGroup.length > 0) {
        this._updateButtons();
        this._fetchBatchSuggestions();
      }
    } catch (err) {
      /* no saved group */
    }
  }

  async _loadAlignedKeys() {
    this.st.alignedKeys = new Map();
    try {
      const groups = await ApiClient.fetch("/alignments");
      for (let i = 0; i < groups.length; i++) {
        const grp = groups[i];
        for (const e of grp.entries || []) {
          this.st.alignedKeys.set(`${e.source}:${e.src_ref}`, grp.id);
        }
        if (groups.length > 5) {
          this.progress.advance(25 + Math.round((i / groups.length) * 20), `🔑 正在索引群组 ${i + 1}/${groups.length}…`);
        }
      }
    } catch (err) {
      /* ignore */
    }
  }
}

// ─── Boot ─────────────────────────────────────────────────────
const app = new AlignmentApp();
document.addEventListener("DOMContentLoaded", () => app.init());
