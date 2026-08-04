:root {
    --bg: #f5f7fa;
    --card-bg: #ffffff;
    --primary: #5b6ee1;
    --danger: #e85555;
    --text: #333333;
    --muted: #999999;
    --border: #e0e0e0;
    --hover: #f0f2ff;
}

@media (prefers-color-scheme: dark) {
    :root {
        --bg: #1a1a2e;
        --card-bg: #16213e;
        --primary: #7c8cf0;
        --danger: #e85555;
        --text: #e0e0e0;
        --muted: #888888;
        --border: #2a2a4a;
        --hover: #1e2a4a;
    }
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: var(--bg);
    color: var(--text);
    padding: 16px;
}

.stats-bar {
    display: flex;
    gap: 12px;
    margin-bottom: 20px;
}

.stat-card {
    flex: 1;
    background: var(--card-bg);
    border-radius: 12px;
    padding: 20px;
    text-align: center;
    border: 1px solid var(--border);
}

.stat-value {
    font-size: 28px;
    font-weight: 700;
    color: var(--primary);
}

.stat-label {
    font-size: 13px;
    color: var(--muted);
    margin-top: 4px;
}

.view { display: none; }
.view.active { display: block; }

.view-header {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 16px;
}

.view-header h2 {
    flex: 1;
    font-size: 18px;
}

.table-wrap {
    background: var(--card-bg);
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid var(--border);
}

.data-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
}

.data-table th {
    background: var(--hover);
    padding: 12px 16px;
    text-align: left;
    font-weight: 600;
    color: var(--muted);
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}

.data-table td {
    padding: 12px 16px;
    border-top: 1px solid var(--border);
}

.data-table tr:hover {
    background: var(--hover);
}

.user-row {
    cursor: pointer;
}

.score-badge {
    display: inline-block;
    background: var(--primary);
    color: #fff;
    padding: 2px 10px;
    border-radius: 12px;
    font-weight: 600;
    font-size: 13px;
}

.muted { color: var(--muted); font-size: 13px; }
.loading, .empty { text-align: center; color: var(--muted); padding: 40px; }
.reason-cell, .preview-cell {
    max-width: 200px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.btn {
    padding: 8px 16px;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    font-size: 14px;
    transition: opacity 0.2s;
}
.btn:hover { opacity: 0.85; }
.btn-sm { padding: 4px 10px; font-size: 12px; }
.btn-primary { background: var(--primary); color: #fff; }
.btn-danger { background: var(--danger); color: #fff; }
.btn-cancel { background: var(--border); color: var(--text); }
.btn-back { background: transparent; color: var(--primary); border: 1px solid var(--primary); }
.btn-refresh { background: var(--primary); color: #fff; }

.detail-summary {
    display: flex;
    gap: 12px;
    margin-bottom: 16px;
}

.summary-item {
    flex: 1;
    background: var(--card-bg);
    border-radius: 12px;
    padding: 16px;
    text-align: center;
    border: 1px solid var(--border);
}

.summary-label {
    display: block;
    font-size: 12px;
    color: var(--muted);
    margin-bottom: 6px;
}

.summary-value {
    font-size: 22px;
    font-weight: 700;
    color: var(--primary);
}

.modal {
    display: none;
    position: fixed;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.5);
    z-index: 1000;
    align-items: center;
    justify-content: center;
}

.modal.active {
    display: flex;
}

.modal-content {
    background: var(--card-bg);
    border-radius: 16px;
    padding: 24px;
    min-width: 360px;
    max-width: 500px;
}

.modal-content h3 {
    margin-bottom: 16px;
    font-size: 18px;
}

.modal-body {
    margin-bottom: 20px;
}

.modal-body label {
    display: block;
    margin-bottom: 8px;
    font-size: 14px;
}

.modal-body input {
    width: 100%;
    padding: 10px 12px;
    border: 1px solid var(--border);
    border-radius: 8px;
    font-size: 16px;
    background: var(--bg);
    color: var(--text);
}

.modal-hint {
    margin-top: 8px;
    font-size: 12px;
    color: var(--muted);
}

.modal-footer {
    display: flex;
    gap: 12px;
    justify-content: flex-end;
}

.toast {
    position: fixed;
    bottom: 24px;
    left: 50%;
    transform: translateX(-50%) translateY(100px);
    background: var(--text);
    color: var(--bg);
    padding: 12px 24px;
    border-radius: 24px;
    font-size: 14px;
    opacity: 0;
    transition: all 0.3s;
    z-index: 2000;
}

.toast.show {
    transform: translateX(-50%) translateY(0);
    opacity: 1;
}

/* 记录详情页样式 */
.record-detail-content {
    background: var(--card-bg);
    border-radius: 12px;
    padding: 24px;
    border: 1px solid var(--border);
}

.record-detail-section {
    margin-bottom: 24px;
}

.record-detail-section:last-child {
    margin-bottom: 0;
}

.record-detail-label {
    font-size: 12px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 8px;
    font-weight: 600;
}

.record-detail-value {
    font-size: 15px;
    line-height: 1.6;
    color: var(--text);
    word-break: break-word;
}

.record-detail-value.original-message {
    background: var(--bg);
    padding: 16px;
    border-radius: 8px;
    border-left: 3px solid var(--primary);
    white-space: pre-wrap;
}

.record-detail-score {
    display: flex;
    align-items: center;
    gap: 12px;
}

.record-detail-score .score-badge {
    font-size: 18px;
    padding: 6px 16px;
}

.record-detail-meta {
    display: flex;
    gap: 24px;
    padding-top: 16px;
    border-top: 1px solid var(--border);
    margin-top: 24px;
}

.record-detail-meta-item {
    font-size: 13px;
    color: var(--muted);
}
