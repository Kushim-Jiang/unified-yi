/**
 * Unified Yi Character Manager — Browse Page
 *
 * Main browsing UI: source grid → character table → character detail + suggestions.
 */

class BrowseApp {
  constructor() {
    this.state = {
      sources: [],
      currentSource: null,
      currentPage: 1,
      pageSize: 100,
      searchQuery: "",
      selectedChar: null,
      alignedKeys: new Set(),
    };
    this.progress = new ProgressBar();
  }

  async init() {
    await this._loadAlignedKeys();
    await this._loadSources();
    const searchInput = document.getElementById("searchInput");
    if (searchInput) {
      searchInput.addEventListener("keydown", (e) => {
        if (e.key === "Enter") this.doSearch();
      });
    }
  }

  // ── Sources ────────────────────────────────────────────

  async _loadSources() {
    try {
      this.state.sources = await ApiClient.fetch("/sources");
      this._renderSourceGrid();
    } catch (err) {
      Notification.show("Failed to load sources: " + err.message, "error");
    }
  }

  _renderSourceGrid() {
    const grid = document.getElementById("sourceGrid");
    if (!grid) return;

    const groups = { unified: [], yunnan: [], guizhou: [], other: [] };
    for (const src of this.state.sources) {
      const g = src.group || "other";
      if (groups[g]) groups[g].push(src);
      else groups.other.push(src);
    }

    const groupNames = {
      unified: "📖 通用 (Unified)",
      yunnan: "🏔️ 云南 (Yunnan)",
      guizhou: "🏯 贵州 (Guizhou)",
    };

    let html = "";
    for (const [group, sources] of Object.entries(groups)) {
      if (sources.length === 0) continue;
      if (groupNames[group]) {
        html += `<div style="grid-column:1/-1;font-weight:700;color:var(--text-secondary);margin-top:12px;font-size:13px;text-transform:uppercase;letter-spacing:0.5px">${groupNames[group]}</div>`;
      }
      for (const src of sources) {
        const isSelected = this.state.currentSource === src.id;
        html += `
                    <div class="source-card ${isSelected ? "selected" : ""}"
                         onclick="app.selectSource('${src.id}')">
                        <span class="region-badge ${src.group}">${src.region}</span>
                        <h3>${src.id}.tsv</h3>
                        <div class="meta">${src.name}</div>
                        <div class="meta">${src.character_count.toLocaleString()} characters</div>
                        ${src.year ? `<div class="meta">Year: ${src.year}</div>` : ""}
                    </div>`;
      }
    }
    grid.innerHTML = html;
  }

  selectSource(sourceId) {
    this.state.currentSource = sourceId;
    this.state.currentPage = 1;
    this.state.searchQuery = "";
    document.getElementById("searchInput").value = "";
    this._renderSourceGrid();
    this._loadCharacters();
  }

  // ── Characters ─────────────────────────────────────────

  async _loadCharacters() {
    if (!this.state.currentSource) {
      document.getElementById("charTableBody").innerHTML = '<tr><td colspan="4" style="text-align:center;padding:40px;color:var(--text-secondary)">Select a source to view characters</td></tr>';
      return;
    }

    document.getElementById("charTableBody").innerHTML = '<tr><td colspan="4" style="text-align:center;padding:20px"><span class="spinner"></span> Loading...</td></tr>';

    try {
      const params = new URLSearchParams({
        page: this.state.currentPage,
        page_size: this.state.pageSize,
        search: this.state.searchQuery,
      });
      const result = await ApiClient.fetch(`/characters/${this.state.currentSource}?${params}`);

      document.getElementById("currentSourceLabel").textContent = this.state.currentSource;
      document.getElementById("totalChars").textContent = result.total.toLocaleString();
      this._renderCharacterTable(result.data);
      this._renderPagination(result);
    } catch (err) {
      Notification.show("Failed to load characters: " + err.message, "error");
    }
  }

  _renderCharacterTable(characters) {
    const tbody = document.getElementById("charTableBody");
    if (characters.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;padding:40px;color:var(--text-secondary)">No characters found</td></tr>';
      return;
    }

    tbody.innerHTML = characters
      .map((c) => {
        const aligned = this.state.alignedKeys.has(`${this.state.currentSource}:${c.src_ref}`);
        const selected = this.state.selectedChar && this.state.selectedChar.src_ref === c.src_ref;
        const cls = selected ? "selected" : aligned ? "aligned" : "";
        return `<tr class="${cls}"
                onclick="app.selectCharacter('${htmlEscape(c.src_ref)}', '${this.state.currentSource}')">
                <td class="glyph-cell" title="${htmlEscape(c.glyph)}">${c.glyph}</td>
                <td class="src-ref">${htmlEscape(c.src_ref)}${aligned ? " 🔗" : ""}</td>
                <td class="pronunciation">${htmlEscape(c.pronunciation)}</td>
                <td>${htmlEscape(c.meaning)}</td>
            </tr>`;
      })
      .join("");
  }

  _renderPagination(result) {
    const pag = document.getElementById("pagination");
    if (result.total_pages <= 1) {
      pag.innerHTML = "";
      return;
    }
    pag.innerHTML = `
            <button ${result.page <= 1 ? "disabled" : ""} onclick="app.goToPage(${result.page - 1})">← Prev</button>
            <span class="page-info">Page ${result.page} / ${result.total_pages} (${result.total} total)</span>
            <button ${result.page >= result.total_pages ? "disabled" : ""} onclick="app.goToPage(${result.page + 1})">Next →</button>
        `;
  }

  goToPage(page) {
    this.state.currentPage = page;
    this._loadCharacters();
  }
  doSearch() {
    this.state.searchQuery = document.getElementById("searchInput").value;
    this.state.currentPage = 1;
    this._loadCharacters();
  }
  clearSearch() {
    this.state.searchQuery = "";
    document.getElementById("searchInput").value = "";
    this.state.currentPage = 1;
    this._loadCharacters();
  }

  // ── Character Detail & Suggestions ─────────────────────

  async selectCharacter(srcRef, source) {
    try {
      const char = await ApiClient.fetch(`/character/${source}/${srcRef}`);
      this.state.selectedChar = { ...char, source };
      this._showCharDetail(char, source);
      this._loadCharacters();
      this._loadSuggestions(source, srcRef);
    } catch (err) {
      Notification.show("Failed to load character: " + err.message, "error");
    }
  }

  _showCharDetail(char, source) {
    const detail = document.getElementById("charDetail");
    if (!detail) return;

    detail.innerHTML = `
            <div style="display:flex;align-items:center;gap:16px;padding:16px;background:var(--accent-bg);border-radius:var(--radius);margin-bottom:12px;">
                <span style="font-family:'YiFont';font-size:48px;">${char.glyph}</span>
                <div>
                    <div style="font-weight:700;font-size:18px;">${htmlEscape(char.src_ref)}</div>
                    <div style="font-family:'Gentium Plus',serif;color:var(--info);">${htmlEscape(char.pronunciation)}</div>
                    <div>${htmlEscape(char.meaning)}</div>
                    <div style="font-size:12px;color:var(--text-secondary);">Source: ${source}</div>
                </div>
            </div>
            <div id="suggestionsArea">
                <span class="spinner"></span> Loading suggestions...
            </div>
        `;
  }

  async _loadSuggestions(source, srcRef) {
    const area = document.getElementById("suggestionsArea");
    if (!area) return;

    try {
      const result = await ApiClient.fetch(`/suggest-alignments/${source}/${srcRef}?method=combined&top_k=15`);
      this._renderSuggestions(result.suggestions);
    } catch (err) {
      area.innerHTML = `<p style="color:var(--text-secondary)">Could not load suggestions: ${err.message}</p>`;
    }
  }

  _renderSuggestions(suggestions) {
    const area = document.getElementById("suggestionsArea");
    if (!area) return;

    if (suggestions.length === 0) {
      area.innerHTML = '<p style="color:var(--text-secondary)">No similar characters found</p>';
      return;
    }

    area.innerHTML = `
            <h4 style="margin-bottom:8px;color:var(--text-secondary);font-size:13px;">🔍 Suggested Matches (pronunciation + meaning + radical)</h4>
            <div class="suggestions-list">
                ${suggestions
                  .map(
                    (s) => `
                    <div class="suggestion-item" onclick="app.quickAlign('${htmlEscape(this.state.currentSource)}', '${htmlEscape(this.state.selectedChar.src_ref)}', '${htmlEscape(s.source)}', '${htmlEscape(s.src_ref)}')">
                        <span class="sugg-glyph">${s.glyph}</span>
                        <div class="sugg-info">
                            <div><strong>${htmlEscape(s.source)}</strong> · ${htmlEscape(s.src_ref)}</div>
                            <div style="font-family:'Gentium Plus',serif;font-size:12px;color:var(--info);">/${htmlEscape(s.pronunciation)}/</div>
                            <div style="font-size:12px;">${htmlEscape(s.meaning)}</div>
                            <div class="score-bar">
                                <div class="fill ${scoreColor(s.combined_score)}" style="width:${(s.combined_score * 100).toFixed(0)}%"></div>
                            </div>
                        </div>
                        <div class="sugg-score">${(s.combined_score * 100).toFixed(0)}%</div>
                    </div>
                `,
                  )
                  .join("")}
            </div>
        `;
  }

  async quickAlign(sourceA, refA, sourceB, refB) {
    try {
      await ApiClient.post("/alignments", { entries: [refA, refB], note: "" });
      Notification.show(`Aligned: ${refA} ↔ ${refB}`, "success");
    } catch (err) {
      if (err.message.includes("Duplicate source")) Notification.show("Already in group", "info");
      else Notification.show("Failed to align: " + err.message, "error");
    }
  }

  async _loadAlignedKeys() {
    this.state.alignedKeys = new Set();
    try {
      const groups = await ApiClient.fetch("/alignments");
      for (const grp of groups) {
        for (const e of grp.entries || []) {
          this.state.alignedKeys.add(`${e.source}:${e.src_ref}`);
        }
      }
    } catch (err) {
      /* ignore */
    }
  }
}

// ─── Boot ─────────────────────────────────────────────────────
const app = new BrowseApp();
document.addEventListener("DOMContentLoaded", () => app.init());
