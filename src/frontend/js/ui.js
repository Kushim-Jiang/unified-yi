/**
 * Unified Yi Character Manager — UI Utilities
 *
 * Shared UI components: notification, progress bar, HTML escaping, score colors.
 */

// ─── Notification ────────────────────────────────────────────

class Notification {
    /**
     * Show a notification toast.
     * @param {string} msg - Message text
     * @param {'info'|'success'|'error'} type
     */
    static show(msg, type = 'info') {
        const el = document.createElement('div');
        el.className = `notification ${type}`;
        el.textContent = msg;
        document.body.appendChild(el);
        setTimeout(() => el.remove(), 3000);
    }
}


// ─── Progress Bar ────────────────────────────────────────────

class ProgressBar {
    constructor() {
        this._timer = null;
    }

    /**
     * Show the progress overlay.
     * @param {string} msg - Message text
     * @param {number} [pct] - Initial percentage (0-100), or undefined for pulsing animation
     */
    show(msg, pct) {
        const overlay = document.getElementById('progressOverlay');
        const bar = document.getElementById('progressBar');
        const msgEl = document.getElementById('progressMessage');
        const textEl = document.getElementById('progressText');
        if (!overlay || !bar) return;

        overlay.style.display = 'block';
        msgEl.style.display = 'block';
        textEl.textContent = msg || '⏳ Loading…';

        if (pct !== undefined) {
            bar.style.width = Math.min(100, Math.max(0, pct)) + '%';
        } else {
            bar.style.width = '30%';
            clearTimeout(this._timer);
            this._timer = setTimeout(() => {
                bar.style.transition = 'width 4s ease';
                bar.style.width = '70%';
            }, 200);
        }
    }

    /**
     * Advance the progress bar to a given percentage with an optional message.
     * @param {number} pct
     * @param {string} [msg]
     */
    advance(pct, msg) {
        const bar = document.getElementById('progressBar');
        const textEl = document.getElementById('progressText');
        if (bar && pct !== undefined) {
            bar.style.transition = 'width .3s ease';
            bar.style.width = Math.min(100, Math.max(0, pct)) + '%';
        }
        if (textEl && msg) textEl.textContent = msg;
    }

    /**
     * Hide the progress overlay with a brief fill-to-complete animation.
     */
    hide() {
        const overlay = document.getElementById('progressOverlay');
        const bar = document.getElementById('progressBar');
        const msgEl = document.getElementById('progressMessage');
        if (!overlay) return;

        if (bar) { bar.style.transition = 'width .15s ease'; bar.style.width = '100%'; }
        clearTimeout(this._timer);
        setTimeout(() => {
            overlay.style.display = 'none';
            msgEl.style.display = 'none';
            if (bar) bar.style.width = '0%';
        }, 300);
    }

    /**
     * Convenience: wrap a promise with show/hide progress.
     * @param {Promise<T>} promise
     * @param {string} msg
     * @returns {Promise<T>}
     * @template T
     */
    async wrap(promise, msg) {
        this.show(msg);
        try {
            return await promise;
        } finally {
            this.hide();
        }
    }
}


// ─── HTML 转义 ───────────────────────────────────────────────

/**
 * Escape HTML special characters in a string for safe innerHTML assignment.
 * @param {string} s
 * @returns {string}
 */
function htmlEscape(s) {
    const d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
}


// ─── 分数颜色 ───────────────────────────────────────────────

/**
 * Return a CSS class name based on a similarity/score value.
 * @param {number} score - 0 to 1
 * @returns {'good'|'medium'|'bad'}
 */
function scoreColor(score) {
    if (score >= 0.7) return 'good';
    if (score >= 0.4) return 'medium';
    return 'bad';
}
