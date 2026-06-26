/**
 * Unified Yi Character Manager — OCR 浮动窗口
 *
 * 独立 OCR 组件：粘贴图片 → 调用后端 API 识别 → 编辑结果 → 插入到当前单元格。
 *
 * 用法:
 *   const ocr = new OcrWindow(entryGrid);
 *   ocr.open();
 *   ocr.close();
 */

class OcrWindow {
  /**
   * @param {Object} entryGrid - EntryGrid 实例（用于插入文本到单元格）
   */
  constructor(entryGrid) {
    this._entryGrid = entryGrid;
    this._ocrBase64Data = null;
    this._ocrDragCleanup = null;
    this._ocrPasteHandler = (e) => this._onPaste(e);
    this._statusTimer = null;
  }

  // ── 打开 / 关闭 ──────────────────────────────────────

  /** 打开 OCR 浮动窗口 */
  open() {
    const overlay = document.getElementById("ocrOverlay");
    const win = document.getElementById("ocrWindow");
    if (!overlay) return;

    overlay.style.display = "flex";
    win.style.left = "";
    win.style.top = "";
    win.style.transform = "";

    const zone = document.getElementById("ocrImageZone");
    if (zone) {
      zone.focus();
      zone.addEventListener("paste", this._ocrPasteHandler);
    }

    this.clear();
    this._initDrag();
  }

  /** 关闭 OCR 浮动窗口 */
  close() {
    const overlay = document.getElementById("ocrOverlay");
    const zone = document.getElementById("ocrImageZone");
    if (overlay) overlay.style.display = "none";
    if (zone) zone.removeEventListener("paste", this._ocrPasteHandler);
    if (this._ocrDragCleanup) {
      this._ocrDragCleanup();
      this._ocrDragCleanup = null;
    }
  }

  // ── 清空 ──────────────────────────────────────────────

  /** 清空 OCR 图片和结果 */
  clear() {
    const preview = document.getElementById("ocrImagePreview");
    const placeholder = document.getElementById("ocrImagePlaceholder");
    const zone = document.getElementById("ocrImageZone");
    const textarea = document.getElementById("ocrResultText");
    const status = document.getElementById("ocrStatus");

    if (preview) {
      preview.style.display = "none";
      preview.src = "";
    }
    if (placeholder) placeholder.style.display = "flex";
    if (zone) zone.classList.remove("has-image");
    if (textarea) {
      textarea.value = "";
      textarea.readOnly = true;
    }
    if (status) {
      status.textContent = "";
      status.className = "ocr-status";
    }
    this._ocrBase64Data = null;
  }

  // ── 识别 ──────────────────────────────────────────────

  /** 调用后端 API 进行 OCR 识别（流式 SSE，逐 token 更新） */
  async recognize() {
    const status = document.getElementById("ocrStatus");
    const textarea = document.getElementById("ocrResultText");
    const btn = document.getElementById("ocrRecognizeBtn");

    if (!this._ocrBase64Data) {
      if (status) {
        status.textContent = "请先粘贴图片";
        status.className = "ocr-status error";
      }
      return;
    }

    if (!textarea) return;
    if (btn) btn.disabled = true;

    // 清空旧结果，开启可编辑
    textarea.value = "";
    textarea.readOnly = false;

    // 显示识别状态
    if (status) {
      status.textContent = "⏳ 正在识别…";
      status.className = "ocr-status loading";
      this._statusTimer = this._startStatusTimer(status);
    }

    try {
      // 流式端点 /api/ocr/stream（SSE）
      const baseUrl = window.location.origin || "http://localhost:8080";

      // 读取用户输入（全部必填）
      const fields = this._readConfig();
      if (!fields) {
        this._stopStatusTimer();
        if (btn) btn.disabled = false;
        return;
      }

      const resp = await fetch(`${baseUrl}/api/ocr/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ image: this._ocrBase64Data, ...fields }),
      });

      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}`);
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      let hasContent = false;
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || ""; // 保留未完成的行

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const data = line.slice(6).trim();
            if (data === "[DONE]") {
              this._stopStatusTimer();
              if (status) {
                status.textContent = "✅ 识别完成";
                status.className = "ocr-status success";
              }
            } else if (data.startsWith("[ERROR]")) {
              this._stopStatusTimer();
              const errMsg = data.slice(7).trim();
              if (status) {
                status.textContent = "❌ " + errMsg;
                status.className = "ocr-status error";
              }
              Notification.show("OCR 识别失败: " + errMsg, "error");
            } else {
              // 第一个内容 token 到达，停止等待提示
              if (!hasContent) {
                hasContent = true;
                this._stopStatusTimer();
                if (status) {
                  status.textContent = "⏳ 正在输出…";
                  status.className = "ocr-status";
                }
              }
              // 追加文本块到 textarea
              textarea.value += data;
              textarea.scrollTop = textarea.scrollHeight;
            }
          }
        }
      }
    } catch (e) {
      this._stopStatusTimer();
      if (status) {
        status.textContent = "❌ 识别失败: " + e.message;
        status.className = "ocr-status error";
      }
      Notification.show("OCR 识别失败: " + e.message, "error");
    } finally {
      this._stopStatusTimer();
      if (btn) btn.disabled = false;
      textarea.focus();
    }
  }

  // ── 测试连接 ──────────────────────────────────────────

  /** 测试 / 加载模型 按钮 */
  async testConnection() {
    const fields = this._readConfig(false);
    if (!fields) return;

    // 还没选模型：先加载模型列表；已选模型：验证该模型可用
    if (!fields.model) {
      await this._fetchModels(fields);
      return;
    }
    await this._verifyModel(fields);
  }

  /** 验证已选模型是否可用 */
  async _verifyModel(fields) {
    const status = document.getElementById("ocrStatus");
    const btn = document.getElementById("ocrTestBtn");

    if (btn) btn.disabled = true;
    if (status) {
      status.textContent = "⏳ 正在测试模型…";
      status.className = "ocr-status loading";
    }

    try {
      const baseUrl = window.location.origin || "http://localhost:8080";
      const resp = await fetch(`${baseUrl}/api/ocr/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(fields),
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(err.detail || `HTTP ${resp.status}`);
      }

      const result = await resp.json();
      if (status) {
        status.textContent = `✅ ${result.message}`;
        status.className = "ocr-status success";
      }
      Notification.show("模型可用", "success");
    } catch (e) {
      if (status) {
        status.textContent = "❌ " + e.message;
        status.className = "ocr-status error";
      }
      Notification.show("测试失败: " + e.message, "error");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  // ── 获取模型列表 ──────────────────────────────────────

  async _fetchModels(fields) {
    const status = document.getElementById("ocrStatus");
    const btn = document.getElementById("ocrTestBtn");
    const list = document.getElementById("ocrModelList");
    const input = document.getElementById("ocrModel");
    if (!list) return;

    if (btn) btn.disabled = true;
    if (status) {
      status.textContent = "⏳ 正在获取模型列表…";
      status.className = "ocr-status loading";
    }

    try {
      const baseUrl = window.location.origin || "http://localhost:8080";
      const resp = await fetch(`${baseUrl}/api/ocr/models`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(fields),
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }));
        throw new Error(err.detail || `HTTP ${resp.status}`);
      }

      const data = await resp.json();
      const models = data.models || [];
      const message = data.message || "";
      list.innerHTML = "";
      for (const m of models) {
        const opt = document.createElement("option");
        opt.value = m;
        list.appendChild(opt);
      }

      // 自动选中偏好模型，否则选第一个
      const prefers = ["vision", "gpt-4o", "claude", "doubao", "gemini"];
      let picked = "";
      for (const p of prefers) {
        const match = models.find((m) => m.toLowerCase().includes(p));
        if (match) { picked = match; break; }
      }
      if (!picked && models.length > 0) {
        picked = models[0];
      }
      if (picked && input) {
        input.value = picked;
      }

      if (status) {
        if (models.length > 0) {
          status.textContent = `✅ ${message}，请选择或修改模型后再次点击测试`;
          status.className = "ocr-status success";
        } else {
          status.textContent = `⚠️ ${message}`;
          status.className = "ocr-status";
        }
      }
    } catch (e) {
      list.innerHTML = "";
      if (status) {
        status.textContent = "❌ 获取模型列表失败: " + e.message;
        status.className = "ocr-status error";
      }
      Notification.show("获取模型列表失败: " + e.message, "error");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  // ── 配置读取 ──────────────────────────────────────────

  /** 读取并校验 OCR 配置输入，返回 {api_key, base_url, model, provider} 或 null */
  _readConfig(requireModel = true) {
    const status = document.getElementById("ocrStatus");
    const apiKey = this._val("ocrApiKey");
    const baseUrl = this._val("ocrBaseUrl");
    const model = this._val("ocrModel");
    const provider = this._val("ocrProvider") || "openai";

    const missing = [];
    if (!apiKey) missing.push("API Key");
    if (!baseUrl) missing.push("Base URL");
    if (requireModel && !model) missing.push("模型");

    if (missing.length > 0) {
      const hint = (!model && document.getElementById("ocrModelList")?.childElementCount > 0)
        ? "（模型列表已加载，请在框内点击选择）" : "（请先点 🔌 测试连接）";
      const msg = "❌ 请填写: " + missing.join("、") + hint;
      if (status) {
        status.textContent = msg;
        status.className = "ocr-status error";
      }
      Notification.show("请填写: " + missing.join("、"), "error");
      return null;
    }

    // 自动补全 /v1 后缀：只有 openai 且 URL 没有明显路径时才补，避免用户已填完整 endpoint base 时被改成 /v1/xxx
    let finalUrl = baseUrl;
    if (provider === "openai") {
      const path = new URL(finalUrl).pathname;
      const looksLikeEndpointBase = path.endsWith("/v1") || path.includes("/v3") || path.includes("/v2") || path.endsWith("/chat/completions");
      if (!looksLikeEndpointBase) {
        finalUrl = finalUrl.replace(/\/$/, "") + "/v1";
      }
    }

    return { api_key: apiKey, base_url: finalUrl, model, provider };
  }

  _val(id) {
    const el = document.getElementById(id);
    return el ? el.value.trim() : "";
  }

  // ── 插入 ──────────────────────────────────────────────

  /** 将 OCR 结果插入到当前正在编辑的单元格 */
  insert() {
    const textarea = document.getElementById("ocrResultText");
    if (!textarea || !textarea.value.trim()) {
      Notification.show("没有可插入的文本", "error");
      return;
    }

    const text = textarea.value;

    // 方案1: 有正在编辑的单元格
    const editingCell = document.querySelector(".cell-editable.editing");
    if (editingCell) {
      const input = editingCell.querySelector("input, textarea");
      if (input) {
        this._insertIntoInput(input, text);
        Notification.show("已插入文本", "success");
        this.clear();
        return;
      }
    }

    // 方案2: 有之前记录编辑位置的单元格
    const eg = this._entryGrid;
    if (eg._editingRow != null && eg._editingCol != null) {
      const item = eg.pageData[eg._editingRow];
      if (item) {
        eg.editCell(eg._editingRow, eg._editingCol);
        requestAnimationFrame(() => {
          const cell = document.querySelector(".cell-editable.editing");
          if (cell) {
            const input = cell.querySelector("input, textarea");
            if (input) {
              input.value = text;
              const evt = new Event("input", { bubbles: true });
              input.dispatchEvent(evt);
              Notification.show("已插入文本", "success");
              this.clear();
            }
          }
        });
        return;
      }
    }

    Notification.show("请先点击要编辑的单元格，再点击插入", "info");
  }

  /** 向输入框的当前光标位置插入文本 */
  _insertIntoInput(input, text) {
    const start = input.selectionStart;
    const end = input.selectionEnd;
    const before = input.value.substring(0, start);
    const after = input.value.substring(end);
    input.value = before + text + after;
    input.selectionStart = input.selectionEnd = start + text.length;
    input.focus();
    const evt = new Event("input", { bubbles: true });
    input.dispatchEvent(evt);
  }

  // ── 内部方法 ──────────────────────────────────────────

  /** 启动状态计时器，每 15 秒更新提示文字，让用户知道仍在处理 */
  _startStatusTimer(statusEl) {
    const messages = ["⏳ 图片分析中，请稍候…", "⏳ 快要出来了…"];
    let idx = 0;
    const timer = setInterval(() => {
      idx = (idx + 1) % messages.length;
      if (statusEl && statusEl.classList.contains("loading")) {
        statusEl.textContent = messages[idx];
      } else {
        clearInterval(timer);
      }
    }, 15000);
    return timer;
  }

  /** 停止状态计时器 */
  _stopStatusTimer() {
    if (this._statusTimer) {
      clearInterval(this._statusTimer);
      this._statusTimer = null;
    }
  }

  /** 粘贴事件处理器 — 压缩图片后存入 _ocrBase64Data */
  _onPaste(e) {
    const items = e.clipboardData && e.clipboardData.items;
    if (!items) return;

    let imageFile = null;
    for (const item of items) {
      if (item.type.startsWith("image/")) {
        imageFile = item.getAsFile();
        break;
      }
    }
    if (!imageFile) {
      Notification.show("剪贴板中没有图片", "error");
      return;
    }

    // 用 Canvas 压缩图片，最大宽高 1024px，降低模型处理延迟
    const reader = new FileReader();
    reader.onload = (ev) => {
      const img = new Image();
      img.onload = () => {
        // 计算缩放尺寸
        const MAX = 1024;
        let { width, height } = img;
        if (width > MAX || height > MAX) {
          const ratio = Math.min(MAX / width, MAX / height);
          width = Math.round(width * ratio);
          height = Math.round(height * ratio);
        }

        // 绘制到 Canvas
        const canvas = document.createElement("canvas");
        canvas.width = width;
        canvas.height = height;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(img, 0, 0, width, height);

        // 压缩为 JPEG 0.85 质量（比 PNG 小得多）
        const compressedDataUrl = canvas.toDataURL("image/jpeg", 0.85);
        const base64 = compressedDataUrl.split(",")[1];

        // 显示压缩后的预览
        const preview = document.getElementById("ocrImagePreview");
        const placeholder = document.getElementById("ocrImagePlaceholder");
        const zone = document.getElementById("ocrImageZone");

        if (preview) {
          preview.src = compressedDataUrl;
          preview.style.display = "block";
        }
        if (placeholder) placeholder.style.display = "none";
        if (zone) zone.classList.add("has-image");

        this._ocrBase64Data = base64;

        // 显示压缩信息
        const originalSize = imageFile.size;
        const compressedSize = Math.round(base64.length * 0.75); // base64 -> bytes
        const saved = Math.round((1 - compressedSize / originalSize) * 100);
        const status = document.getElementById("ocrStatus");
        if (status) {
          status.textContent = `📷 ${width}×${height} (已压缩 ${saved}%)`;
          status.className = "ocr-status";
        }
      };
      img.src = ev.target.result;
    };
    reader.readAsDataURL(imageFile);
  }

  /** 初始化窗口拖拽 */
  _initDrag() {
    const header = document.getElementById("ocrHeader");
    const win = document.getElementById("ocrWindow");
    if (!header || !win) return;

    if (this._ocrDragCleanup) {
      this._ocrDragCleanup();
      this._ocrDragCleanup = null;
    }

    let isDragging = false;
    let startX, startY, origLeft, origTop;

    const onStart = (e) => {
      if (e.button !== 0) return;
      isDragging = true;
      const rect = win.getBoundingClientRect();
      startX = e.clientX;
      startY = e.clientY;
      origLeft = rect.left;
      origTop = rect.top;
      win.style.transform = "none";
      win.style.left = origLeft + "px";
      win.style.top = origTop + "px";
      win.style.cursor = "grabbing";
      win.classList.add("dragging");
      e.preventDefault();
    };

    const onMove = (e) => {
      if (!isDragging) return;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      win.style.left = origLeft + dx + "px";
      win.style.top = origTop + dy + "px";
    };

    const onEnd = () => {
      isDragging = false;
      win.style.cursor = "default";
      win.classList.remove("dragging");
    };

    header.addEventListener("mousedown", onStart);
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onEnd);

    this._ocrDragCleanup = () => {
      header.removeEventListener("mousedown", onStart);
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onEnd);
    };
  }
}
