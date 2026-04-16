/* ═══════════════════════════════════════════════════════
   SAP B1 ServiceLayer Log Viewer - Frontend
   ═══════════════════════════════════════════════════════ */

// ─── State ───

const state = {
    page: 1,
    perPage: 50,
    total: 0,
    pages: 0,
    selectedId: null,
    filters: {},
};

// ─── DOM References ───

const $ = (sel) => document.querySelector(sel);
const $$ = (sel) => document.querySelectorAll(sel);

const dom = {
    welcomeScreen: $('#welcome-screen'),
    mainApp: $('#main-app'),
    parseOverlay: $('#parse-overlay'),
    parseFilename: $('#parse-filename'),
    progressFill: $('#parse-progress-fill'),
    progressText: $('#parse-progress-text'),
    logTbody: $('#log-tbody'),
    emptyState: $('#empty-state'),
    pagination: $('#pagination'),
    detailPanel: $('#detail-panel'),
    fileInfo: $('#file-info'),
    statTotal: $('#stat-total'),
    statSuccess: $('#stat-success'),
    statErrors: $('#stat-errors'),
    statFiltered: $('#stat-filtered'),
    welcomeParsed: $('#welcome-parsed-files'),
    welcomeFileList: $('#welcome-file-list'),
};

// ─── API ───

async function api(path, options = {}) {
    const res = await fetch(path, {
        headers: { 'Content-Type': 'application/json' },
        ...options,
    });
    return res.json();
}

// ─── File Opening ───

function openFileDialog() {
    const input = $('#file-input-fallback');
    input.value = '';
    input.click();
}

async function handleFileSelect(files) {
    if (!files || files.length === 0) return;

    dom.parseOverlay.classList.remove('hidden');
    dom.parseFilename.textContent = files.length === 1
        ? files[0].name
        : `${files[0].name} 외 ${files.length - 1}개`;
    dom.progressFill.style.width = '0%';
    dom.progressText.textContent = '업로드 중...';

    try {
        const formData = new FormData();
        for (const f of files) {
            formData.append('files', f);
        }

        const res = await fetch('/api/upload', {
            method: 'POST',
            body: formData,
        });
        const data = await res.json();

        if (data.error) {
            alert(data.error);
            dom.parseOverlay.classList.add('hidden');
            return;
        }

        dom.progressText.textContent = '분석 중...';
        await pollParseProgress();
    } catch (e) {
        alert('업로드 중 오류: ' + e.message);
        dom.parseOverlay.classList.add('hidden');
    }
}

async function pollParseProgress() {
    while (true) {
        await sleep(300);
        const s = await api('/api/parse/progress');

        dom.progressFill.style.width = s.progress + '%';
        dom.progressText.textContent = s.progress + '%';

        if (!s.active) {
            dom.parseOverlay.classList.add('hidden');

            if (s.error) {
                alert('파싱 오류: ' + s.error);
            } else if (s.result === -1) {
                // 이미 파싱된 파일
            }

            // UI 전환
            await initMainApp();
            return;
        }
    }
}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

// ─── Main App Init ───

async function initMainApp() {
    dom.welcomeScreen.classList.add('hidden');
    dom.mainApp.classList.remove('hidden');

    await Promise.all([
        loadFilters(),
        loadStats(),
        updateLoadedFiles(),
    ]);
    await loadLogs();
}

// ─── Filters ───

async function loadFilters() {
    const f = await api('/api/filters');

    // 엔드포인트
    const epSelect = $('#filter-endpoint');
    epSelect.innerHTML = '<option value="">전체</option>';
    f.endpoints.forEach(ep => {
        // 보기 좋게 /b1s/v1/ 제거
        const label = ep.replace('/b1s/v1/', '');
        epSelect.innerHTML += `<option value="${ep}">${label}</option>`;
    });

    // 메서드 체크박스
    const methodGroup = $('#filter-methods');
    methodGroup.innerHTML = '';
    f.methods.forEach(m => {
        methodGroup.innerHTML += `
            <label class="checkbox-label">
                <input type="checkbox" class="filter-method-cb" value="${m}" checked>
                <span class="method-badge method-${m.toLowerCase()}">${m}</span>
            </label>`;
    });

    // 상태 코드
    const statusSelect = $('#filter-status');
    statusSelect.innerHTML = '<option value="">전체</option>';
    f.status_codes.forEach(sc => {
        statusSelect.innerHTML += `<option value="${sc}">${sc}</option>`;
    });

    // IP
    const ipSelect = $('#filter-ip');
    ipSelect.innerHTML = '<option value="">전체</option>';
    f.ips.forEach(ip => {
        ipSelect.innerHTML += `<option value="${ip}">${ip}</option>`;
    });

    // 파일
    const fileSelect = $('#filter-file');
    fileSelect.innerHTML = '<option value="">전체</option>';
    f.files.forEach(file => {
        fileSelect.innerHTML += `<option value="${file}">${file}</option>`;
    });
}

function gatherFilters() {
    const filters = {};

    const file = $('#filter-file').value;
    if (file) filters.source_file = file;

    const endpoint = $('#filter-endpoint').value;
    if (endpoint) filters.endpoint = endpoint;

    // 메서드: 체크된 것만 (쉼표 구분)
    const checkedMethods = [...$$('.filter-method-cb:checked')].map(cb => cb.value);
    const allMethods = [...$$('.filter-method-cb')].map(cb => cb.value);
    if (checkedMethods.length < allMethods.length && checkedMethods.length > 0) {
        filters.method = checkedMethods.join(',');
    }

    const status = $('#filter-status').value;
    if (status) filters.status = status;

    const ip = $('#filter-ip').value;
    if (ip) filters.ip = ip;

    const timeFrom = $('#filter-time-from').value.trim();
    const timeTo = $('#filter-time-to').value.trim();
    if (timeFrom) filters.time_from = timeFrom;
    if (timeTo) filters.time_to = timeTo;

    const search = $('#filter-search').value.trim();
    if (search) filters.search = search;

    if ($('#filter-errors-only').checked) filters.errors_only = '1';
    if ($('#filter-hide-noise').checked) filters.hide_noise = '1';

    return filters;
}

// ─── Stats ───

async function loadStats() {
    const s = await api('/api/stats');
    dom.statTotal.textContent = s.total.toLocaleString();
    dom.statSuccess.textContent = s.success.toLocaleString();
    dom.statErrors.textContent = s.errors.toLocaleString();
}

// ─── Log List ───

async function loadLogs(page = 1) {
    state.page = page;
    const filters = gatherFilters();
    state.filters = filters;

    const params = new URLSearchParams({
        page: state.page,
        per_page: state.perPage,
        ...filters,
    });

    const data = await api('/api/logs?' + params);
    state.total = data.total;
    state.pages = data.pages;

    dom.statFiltered.textContent = data.total.toLocaleString();

    renderLogTable(data.items);
    renderPagination();

    // 상세 패널 숨기기
    dom.detailPanel.classList.add('hidden');
    state.selectedId = null;
}

function renderLogTable(items) {
    if (items.length === 0) {
        dom.logTbody.innerHTML = '';
        dom.emptyState.classList.remove('hidden');
        return;
    }

    dom.emptyState.classList.add('hidden');
    dom.logTbody.innerHTML = items.map(item => {
        const isError = item.res_status_code && item.res_status_code >= 400;
        const rowClass = isError ? 'row-error' : '';
        const time = (item.timestamp || '').substring(11, 19);
        const endpoint = (item.endpoint || '').replace('/b1s/v1/', '');
        const statusClass = getStatusClass(item.res_status_code);
        const methodClass = 'method-' + (item.method || '').toLowerCase();
        const errorMsg = item.error_message
            ? truncate(item.error_message, 50)
            : '';
        const dur = formatDuration(item.duration_ms);

        return `<tr class="${rowClass}" data-id="${item.id}">
            <td class="col-id">${item.id}</td>
            <td class="col-time">${time}</td>
            <td class="col-method"><span class="method-badge ${methodClass}">${item.method}</span></td>
            <td class="col-endpoint" title="${escapeHtml(item.url)}">${endpoint}</td>
            <td class="col-status"><span class="status-badge ${statusClass}">${item.res_status_code || '-'}</span></td>
            <td class="col-duration"><span class="${dur.cls}">${dur.text}</span></td>
            <td class="col-ip">${item.ip}</td>
            <td class="col-error-text" title="${escapeHtml(item.error_message || '')}">${escapeHtml(errorMsg)}</td>
        </tr>`;
    }).join('');

    // 행 클릭 이벤트
    dom.logTbody.querySelectorAll('tr').forEach(tr => {
        tr.addEventListener('click', () => {
            const id = parseInt(tr.dataset.id);
            selectLog(id, tr);
        });
    });
}

function renderPagination() {
    if (state.pages <= 1) {
        dom.pagination.innerHTML = '';
        return;
    }

    let html = '';
    html += `<button ${state.page <= 1 ? 'disabled' : ''} data-page="${state.page - 1}">&lt;</button>`;

    const range = getPaginationRange(state.page, state.pages);
    for (const p of range) {
        if (p === '...') {
            html += `<span class="page-info">...</span>`;
        } else {
            html += `<button class="${p === state.page ? 'active' : ''}" data-page="${p}">${p}</button>`;
        }
    }

    html += `<button ${state.page >= state.pages ? 'disabled' : ''} data-page="${state.page + 1}">&gt;</button>`;
    html += `<span class="page-info">${state.total.toLocaleString()}건</span>`;

    dom.pagination.innerHTML = html;

    dom.pagination.querySelectorAll('button[data-page]').forEach(btn => {
        btn.addEventListener('click', () => {
            const p = parseInt(btn.dataset.page);
            if (p >= 1 && p <= state.pages) loadLogs(p);
        });
    });
}

function getPaginationRange(current, total) {
    if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);

    const pages = [];
    pages.push(1);

    if (current > 3) pages.push('...');

    const start = Math.max(2, current - 1);
    const end = Math.min(total - 1, current + 1);
    for (let i = start; i <= end; i++) pages.push(i);

    if (current < total - 2) pages.push('...');

    pages.push(total);
    return pages;
}

// ─── Detail View ───

async function selectLog(id, tr) {
    // 행 하이라이트
    dom.logTbody.querySelectorAll('tr.selected').forEach(el => el.classList.remove('selected'));
    tr.classList.add('selected');
    state.selectedId = id;

    const data = await api(`/api/logs/${id}`);
    renderDetail(data);
}

function renderDetail(data) {
    dom.detailPanel.classList.remove('hidden');

    // 헤더 정보
    const methodClass = 'method-' + (data.method || '').toLowerCase();
    $('#detail-method').className = 'method-badge ' + methodClass;
    $('#detail-method').textContent = data.method;
    $('#detail-url').textContent = data.url.replace('//b1s/', '/b1s/');

    const statusCode = data.res_status_code;
    const statusEl = $('#detail-status');
    statusEl.className = 'status-badge ' + getStatusClass(statusCode);
    statusEl.textContent = statusCode ? `${statusCode} ${data.res_status_text}` : '응답 없음';

    $('#detail-time').textContent = data.timestamp || '';
    $('#detail-ip').textContent = data.ip || '';
    $('#detail-pid').textContent = `PID: ${data.pid}`;

    // Request
    $('#detail-req-headers').innerHTML = formatHeaders(data.req_headers || '');
    $('#detail-req-body').innerHTML = formatBody(data.req_body || '');

    // Response
    $('#detail-res-headers').innerHTML = formatHeaders(data.res_headers || '');
    $('#detail-res-body').innerHTML = formatBody(data.res_body || '', data.res_status_code >= 400);

    // 스크롤
    dom.detailPanel.scrollTop = 0;
}

// ─── Formatters ───

function formatHeaders(raw) {
    if (!raw) return '<span class="raw-text">(없음)</span>';
    return raw.split('\n').map(line => {
        const idx = line.indexOf(':');
        if (idx > 0) {
            const name = line.substring(0, idx);
            const value = line.substring(idx + 1);
            return `<span class="header-name">${escapeHtml(name)}</span>:${escapeHtml(value)}`;
        }
        return escapeHtml(line);
    }).join('\n');
}

function formatBody(raw, isError = false) {
    if (!raw || !raw.trim()) return '<span class="raw-text">(없음)</span>';

    // 마스킹된 내용
    if (/^\*+$/.test(raw.trim())) {
        return '<span class="masked-text">[마스킹된 데이터]</span>';
    }

    // JSON 파싱 시도
    try {
        const obj = JSON.parse(raw);
        return formatJson(obj, 0, isError);
    } catch {
        // JSON이 아닌 경우 그대로 표시
        return `<span class="raw-text">${escapeHtml(raw)}</span>`;
    }
}

function formatJson(value, indent = 0, highlightError = false) {
    const pad = '  '.repeat(indent);
    const padInner = '  '.repeat(indent + 1);

    if (value === null) {
        return `<span class="json-null">null</span>`;
    }

    if (typeof value === 'boolean') {
        return `<span class="json-bool">${value}</span>`;
    }

    if (typeof value === 'number') {
        return `<span class="json-number">${value}</span>`;
    }

    if (typeof value === 'string') {
        const escaped = escapeHtml(value);
        // 에러 메시지 강조
        if (highlightError && (value.includes('error') || value.includes('Error') ||
            value.length > 30)) {
            return `<span class="json-string">"${escaped}"</span>`;
        }
        return `<span class="json-string">"${escaped}"</span>`;
    }

    if (Array.isArray(value)) {
        if (value.length === 0) return `<span class="json-bracket">[]</span>`;

        let html = `<span class="json-bracket">[</span>\n`;
        value.forEach((item, i) => {
            html += padInner + formatJson(item, indent + 1, highlightError);
            if (i < value.length - 1) html += ',';
            html += '\n';
        });
        html += pad + `<span class="json-bracket">]</span>`;
        return html;
    }

    if (typeof value === 'object') {
        const keys = Object.keys(value);
        if (keys.length === 0) return `<span class="json-bracket">{}</span>`;

        // 에러 객체 특별 처리
        const isErrorObj = highlightError && ('error' in value || 'code' in value);

        let html = `<span class="json-bracket">{</span>\n`;
        keys.forEach((key, i) => {
            const keyClass = (isErrorObj && (key === 'code' || key === 'message' || key === 'value'))
                ? 'json-error' : 'json-key';
            html += padInner + `<span class="${keyClass}">"${escapeHtml(key)}"</span>: `;
            html += formatJson(value[key], indent + 1, highlightError);
            if (i < keys.length - 1) html += ',';
            html += '\n';
        });
        html += pad + `<span class="json-bracket">}</span>`;
        return html;
    }

    return escapeHtml(String(value));
}

// ─── Helpers ───

function formatDuration(ms) {
    if (ms === null || ms === undefined) return { text: '-', cls: '' };
    if (ms === 0) return { text: '<1s', cls: 'duration-fast' };
    if (ms <= 2000) return { text: Math.round(ms / 1000) + 's', cls: 'duration-mid' };
    return { text: Math.round(ms / 1000) + 's', cls: 'duration-slow' };
}

function getStatusClass(code) {
    if (!code) return 'status-null';
    if (code < 300) return 'status-2xx';
    if (code < 400) return 'status-3xx';
    if (code < 500) return 'status-4xx';
    return 'status-5xx';
}

function truncate(str, len) {
    if (!str) return '';
    return str.length > len ? str.substring(0, len) + '...' : str;
}

function escapeHtml(str) {
    if (!str) return '';
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

// ─── Copy to Clipboard ───

function copyToClipboard(target) {
    let text = '';
    if (target === 'req') {
        text = 'Headers:\n' + ($('#detail-req-headers').textContent || '') +
               '\n\nBody:\n' + ($('#detail-req-body').textContent || '');
    } else {
        text = 'Headers:\n' + ($('#detail-res-headers').textContent || '') +
               '\n\nBody:\n' + ($('#detail-res-body').textContent || '');
    }
    navigator.clipboard.writeText(text).then(() => {
        // 간단한 피드백
        const btn = document.querySelector(`.btn-copy[data-target="${target}"]`);
        const orig = btn.innerHTML;
        btn.innerHTML = '<span style="color:var(--success);font-size:12px">&#10003;</span>';
        setTimeout(() => btn.innerHTML = orig, 1000);
    });
}

// ─── Drag & Drop ───

function initDragDrop() {
    let dragCounter = 0;
    const overlay = $('#drop-overlay');

    document.addEventListener('dragenter', (e) => {
        e.preventDefault();
        dragCounter++;
        if (e.dataTransfer.types.includes('Files')) {
            overlay.classList.remove('hidden');
        }
    });

    document.addEventListener('dragleave', (e) => {
        e.preventDefault();
        dragCounter--;
        if (dragCounter <= 0) {
            dragCounter = 0;
            overlay.classList.add('hidden');
        }
    });

    document.addEventListener('dragover', (e) => {
        e.preventDefault();
    });

    document.addEventListener('drop', (e) => {
        e.preventDefault();
        dragCounter = 0;
        overlay.classList.add('hidden');
        if (e.dataTransfer.files.length > 0) {
            handleFileSelect(e.dataTransfer.files);
        }
    });
}

// ─── Loaded Files Display ───

async function updateLoadedFiles() {
    const files = await api('/api/files');
    const container = $('#loaded-files');
    if (!container) return;
    container.innerHTML = files.map(f =>
        `<span class="loaded-file-chip">${f.filename} (${f.entry_count.toLocaleString()})</span>`
    ).join('');
}

// ─── Keyboard Navigation ───

function initKeyboardNav() {
    document.addEventListener('keydown', (e) => {
        if (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'SELECT') return;

        const rows = [...dom.logTbody.querySelectorAll('tr')];
        if (rows.length === 0) return;

        const currentIdx = rows.findIndex(r => r.classList.contains('selected'));

        if (e.key === 'ArrowDown') {
            e.preventDefault();
            const next = currentIdx < rows.length - 1 ? currentIdx + 1 : currentIdx;
            rows[next].click();
            rows[next].scrollIntoView({ block: 'nearest' });
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            const prev = currentIdx > 0 ? currentIdx - 1 : 0;
            rows[prev].click();
            rows[prev].scrollIntoView({ block: 'nearest' });
        }
    });
}

// ─── Column Resize ───

function initColumnResize() {
    const handles = $$('.col-resize');
    let startX, startW, th;

    handles.forEach(handle => {
        handle.addEventListener('mousedown', (e) => {
            e.preventDefault();
            th = handle.parentElement;
            startX = e.pageX;
            startW = th.offsetWidth;
            handle.classList.add('active');

            const onMove = (e) => {
                const diff = e.pageX - startX;
                const newW = Math.max(40, startW + diff);
                th.style.width = newW + 'px';
            };

            const onUp = () => {
                handle.classList.remove('active');
                document.removeEventListener('mousemove', onMove);
                document.removeEventListener('mouseup', onUp);
            };

            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
        });
    });
}

// ─── Startup ───

async function checkExistingFiles() {
    const files = await api('/api/files');
    if (files.length > 0) {
        dom.welcomeParsed.classList.remove('hidden');
        dom.welcomeFileList.innerHTML = files.map(f =>
            `<button class="welcome-file-btn" data-filename="${f.filename}">
                <span>${f.filename}</span>
                <span class="file-count">${f.entry_count.toLocaleString()}건</span>
            </button>`
        ).join('');

        dom.welcomeFileList.querySelectorAll('.welcome-file-btn').forEach(btn => {
            btn.addEventListener('click', () => initMainApp());
        });
    }
}

// ─── Event Listeners ───

document.addEventListener('DOMContentLoaded', () => {
    // 파일 열기 버튼
    $('#btn-open-file').addEventListener('click', openFileDialog);
    $('#btn-welcome-open').addEventListener('click', openFileDialog);

    // 파일 input 변경 시 업로드
    $('#file-input-fallback').addEventListener('change', (e) => {
        handleFileSelect(e.target.files);
    });

    // 필터
    $('#btn-apply-filter').addEventListener('click', () => loadLogs(1));
    $('#btn-reset-filter').addEventListener('click', () => {
        $('#filter-file').value = '';
        $('#filter-endpoint').value = '';
        $('#filter-status').value = '';
        $('#filter-ip').value = '';
        $('#filter-time-from').value = '';
        $('#filter-time-to').value = '';
        $('#filter-search').value = '';
        $('#filter-errors-only').checked = false;
        $('#filter-hide-noise').checked = true;
        $$('.filter-method-cb').forEach(cb => cb.checked = true);
        loadLogs(1);
    });

    // Enter 키로 필터 적용
    $$('.sidebar .input').forEach(input => {
        input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') loadLogs(1);
        });
    });

    // / 키로 검색에 포커스
    document.addEventListener('keydown', (e) => {
        if (e.key === '/' && document.activeElement.tagName !== 'INPUT') {
            e.preventDefault();
            $('#filter-search').focus();
        }
        if (e.key === 'Escape') {
            dom.detailPanel.classList.add('hidden');
            state.selectedId = null;
            dom.logTbody.querySelectorAll('tr.selected').forEach(el => el.classList.remove('selected'));
        }
    });

    // 상세 패널 닫기
    $('#btn-close-detail').addEventListener('click', () => {
        dom.detailPanel.classList.add('hidden');
        state.selectedId = null;
    });

    // 복사 버튼
    $$('.btn-copy').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            copyToClipboard(btn.dataset.target);
        });
    });

    // select 변경 시 자동 필터 적용
    $$('.sidebar select').forEach(sel => {
        sel.addEventListener('change', () => loadLogs(1));
    });

    // 체크박스 변경 시 자동 필터 적용
    $('#filter-errors-only').addEventListener('change', () => loadLogs(1));
    $('#filter-hide-noise').addEventListener('change', () => loadLogs(1));

    // 종료 버튼
    $('#btn-shutdown').addEventListener('click', async () => {
        if (confirm('SL Log Viewer를 종료하시겠습니까?')) {
            await fetch('/api/shutdown', { method: 'POST' });
            document.body.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100vh;color:#8B949E;font-size:16px;">종료되었습니다. 이 탭을 닫아주세요.</div>';
        }
    });

    // 드래그 앤 드롭, 키보드 탐색, 컬럼 리사이즈
    initDragDrop();
    initKeyboardNav();
    initColumnResize();

    // 서버 heartbeat (3초마다) - 탭 닫으면 서버 자동 종료
    setInterval(() => fetch('/api/heartbeat', { method: 'POST' }).catch(() => {}), 3000);
});
