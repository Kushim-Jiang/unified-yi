/**
 * Unified Yi Character Manager — API Client
 *
 * Centralized HTTP client for all backend API calls.
 * Provides consistent error handling, JSON parsing, and method helpers.
 */
class ApiClient {
    static BASE = '/api';

    /**
     * GET request.
     * @param {string} path - API path (e.g. '/sources')
     * @returns {Promise<any>} parsed JSON response
     */
    static async fetch(path) {
        const r = await fetch(ApiClient.BASE + path);
        if (!r.ok) {
            const err = await r.json().catch(() => ({ detail: r.statusText }));
            throw new Error(err.detail || 'Request failed');
        }
        return r.json();
    }

    /**
     * POST request with JSON body.
     * @param {string} path
     * @param {object} body
     * @returns {Promise<any>}
     */
    static async post(path, body) {
        const r = await fetch(ApiClient.BASE + path, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!r.ok) {
            const err = await r.json().catch(() => ({ detail: r.statusText }));
            throw new Error(err.detail || 'Request failed');
        }
        return r.json();
    }

    /**
     * PUT request with JSON body.
     * @param {string} path
     * @param {object} body
     * @returns {Promise<any>}
     */
    static async put(path, body) {
        const r = await fetch(ApiClient.BASE + path, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
        });
        if (!r.ok) {
            const err = await r.json().catch(() => ({ detail: r.statusText }));
            throw new Error(err.detail || 'Request failed');
        }
        return r.json();
    }

    /**
     * DELETE request.
     * @param {string} path
     * @returns {Promise<any>}
     */
    static async delete(path) {
        const r = await fetch(ApiClient.BASE + path, { method: 'DELETE' });
        if (!r.ok) throw new Error('Delete failed');
        return r.json();
    }
}
