/**
 * Unified Yi Character Manager — Groups Page
 *
 * Displays alignment groups in a matrix: columns = sources, rows = groups.
 */

class GroupsApp {
  constructor() {
    this.st = {
      sources: [],
      groups: [],
      filteredGroups: [],
      page: 1,
      pageSize: 20,
      selectedIds: new Set(),
      _visibleSources: [],
    };
  }

  async init() {
    try {
      this.st.sources = await ApiClient.fetch("/sources");
      this.st.groups = await ApiClient.fetch("/alignments");
      this.st.groups.sort((a, b) => a.id - b.id);
      this.st.filteredGroups = this.st.groups;
      this._render();
    } catch (err) {
      Notification.show("Failed to load: " + err.message, "error");
    }
  }

  // ── Filter & Pagination ───────────────────────────────

  filterGroups() {
    const query = (document.getElementById("groupsSearch")?.value || "").toLowerCase().trim();
    if (query) {
      this.st.filteredGroups = this.st.groups.filter((grp) => {
        const idStr = "G" + String(grp.id).padStart(5, "0");
        if (idStr.toLowerCase().includes(query)) return true;
        return (grp.entries || []).some((e) => (e.source || "").toLowerCase().includes(query) || (e.src_ref || "").toLowerCase().includes(query));
      });
    } else {
      this.st.filteredGroups = this.st.groups;
    }
    this.st.page = 1;
    this.st.selectedIds = new Set();
    this._render();
  }

  pageGroups(dir) {
    const totalPages = Math.max(1, Math.ceil(this.st.filteredGroups.length / this.st.pageSize));
    this.st.page = Math.max(1, Math.min(totalPages, this.st.page + dir));
    this._render();
  }

  // ── Selection ─────────────────────────────────────────

  toggleSelectAll() {
    const checked = document.getElementById("selectAll").checked;
    if (checked) {
      const start = (this.st.page - 1) * this.st.pageSize;
      const page = this.st.filteredGroups.slice(start, start + this.st.pageSize);
      page.forEach((g) => this.st.selectedIds.add(g.id));
    } else {
      this.st.selectedIds = new Set();
    }
    this._updateDeleteButton();
    this._renderRows();
  }

  toggleSelectGroup(id) {
    if (this.st.selectedIds.has(id)) this.st.selectedIds.delete(id);
    else this.st.selectedIds.add(id);
    document.getElementById("selectAll").checked = false;
    this._updateDeleteButton();
  }

  _updateDeleteButton() {
    const btn = document.getElementById("btnDeleteSelected");
    if (btn) btn.disabled = this.st.selectedIds.size === 0;
  }

  // ── Delete ────────────────────────────────────────────

  async deleteGroup(id) {
    if (!confirm(`Delete group G${id}?`)) return;
    try {
      await ApiClient.delete(`/alignments/${id}`);
      Notification.show(`Deleted G${id}`, "success");
      this.st.groups = this.st.groups.filter((g) => g.id !== id);
      this.st.selectedIds.delete(id);
      this.filterGroups();
    } catch (err) {
      Notification.show("Failed: " + err.message, "error");
    }
  }

  async deleteSelectedGroups() {
    const ids = Array.from(this.st.selectedIds);
    if (ids.length === 0) return;
    if (!confirm(`Delete ${ids.length} selected group(s)?`)) return;

    let ok = 0,
      fail = 0;
    for (const id of ids) {
      try {
        await ApiClient.delete(`/alignments/${id}`);
        this.st.groups = this.st.groups.filter((g) => g.id !== id);
        ok++;
      } catch (err) {
        fail++;
      }
    }
    this.st.selectedIds = new Set();
    Notification.show(`Deleted ${ok} group(s)` + (fail ? `, ${fail} failed` : ""), fail ? "error" : "success");
    this.filterGroups();
  }

  // ── Render ────────────────────────────────────────────

  _render() {
    const countEl = document.getElementById("groupsCount");
    const total = this.st.groups.length;
    const filteredCount = this.st.filteredGroups.length;
    if (countEl) countEl.textContent = filteredCount === total ? total : `${filteredCount} / ${total}`;
    this._renderHead();
    this._renderRows();
    this._renderPagination();
  }

  _renderHead() {
    const headRow = document.querySelector("#groupsHead tr");
    if (!headRow) return;

    const checkboxTh = headRow.querySelector("th:first-child");
    const idTh = headRow.querySelector("th:nth-child(2)");
    headRow.innerHTML = "";
    if (checkboxTh) headRow.appendChild(checkboxTh);
    if (idTh) headRow.appendChild(idTh);

    const sourceSet = new Set();
    for (const grp of this.st.filteredGroups) {
      for (const e of grp.entries || []) sourceSet.add(e.source);
    }
    const sourceOrder = this.st.sources.map((s) => s.id);
    const visibleSources = Array.from(sourceSet).sort((a, b) => {
      const ia = sourceOrder.indexOf(a),
        ib = sourceOrder.indexOf(b);
      if (ia >= 0 && ib >= 0) return ia - ib;
      if (ia >= 0) return -1;
      if (ib >= 0) return 1;
      return a.localeCompare(b);
    });

    for (const src of visibleSources) {
      const meta = this.st.sources.find((s) => s.id === src) || {};
      const th = document.createElement("th");
      th.textContent = src;
      th.title = meta.name || src;
      headRow.appendChild(th);
    }

    const actionTh = document.createElement("th");
    actionTh.style.width = "50px";
    headRow.appendChild(actionTh);

    this.st._visibleSources = visibleSources;
  }

  _renderRows() {
    const tbody = document.getElementById("groupsBody");
    if (!tbody) return;

    const totalPages = Math.max(1, Math.ceil(this.st.filteredGroups.length / this.st.pageSize));
    if (this.st.page > totalPages) this.st.page = totalPages;

    const start = (this.st.page - 1) * this.st.pageSize;
    const page = this.st.filteredGroups.slice(start, start + this.st.pageSize);

    if (page.length === 0) {
      tbody.innerHTML = '<tr><td colspan="3" style="text-align:center;padding:20px;color:var(--text-secondary)">No groups found</td></tr>';
      return;
    }

    const sources = this.st._visibleSources || [];

    tbody.innerHTML = page
      .map((grp) => {
        const entryMap = {};
        for (const e of grp.entries || []) {
          if (!entryMap[e.source]) entryMap[e.source] = [];
          entryMap[e.source].push(e);
        }

        const cells = sources
          .map((src) => {
            const entries = entryMap[src];
            if (!entries || entries.length === 0) return "<td></td>";
            const divs = entries
              .map((e) => {
                const c = e.char || {};
                return `<div class="group-cell-item">
                        <span class="group-glyph">${htmlEscape(c.glyph || "?")}</span>
                        <span class="group-ref">${htmlEscape(e.src_ref)}</span>
                    </div>`;
              })
              .join("");
            return `<td class="group-cell">${divs}</td>`;
          })
          .join("");

        const checked = this.st.selectedIds.has(grp.id) ? "checked" : "";

        return `<tr>
                <td style="text-align:center;"><input type="checkbox" ${checked} onchange="app.toggleSelectGroup(${grp.id})"></td>
                <td class="group-id"><strong>G${String(grp.id).padStart(5, "0")}</strong></td>
                ${cells}
                <td style="text-align:center;">
                    <button class="btn btn-danger btn-sm" onclick="app.deleteGroup(${grp.id})" title="Delete">✕</button>
                </td>
            </tr>`;
      })
      .join("");
  }

  _renderPagination() {
    const totalPages = Math.max(1, Math.ceil(this.st.filteredGroups.length / this.st.pageSize));
    const prevBtn = document.getElementById("groupsPrevBtn");
    const nextBtn = document.getElementById("groupsNextBtn");
    const pageInfo = document.getElementById("groupsPageInfo");

    if (prevBtn) prevBtn.disabled = this.st.page <= 1;
    if (nextBtn) nextBtn.disabled = this.st.page >= totalPages;
    if (pageInfo) pageInfo.textContent = totalPages > 1 ? `第 ${this.st.page}/${totalPages} 页` : "";
  }
}

// ─── Boot ─────────────────────────────────────────────────────
const app = new GroupsApp();
document.addEventListener("DOMContentLoaded", () => app.init());
