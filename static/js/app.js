// TalentBeacon global JS utilities
document.addEventListener('DOMContentLoaded', () => {
    document.body.classList.add('page-ready');
    const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
    if (csrfToken) {
        document.querySelectorAll('form[method]').forEach((form) => {
            const method = (form.getAttribute('method') || 'get').toLowerCase();
            if (method === 'get' || form.querySelector('input[name="csrf_token"]')) return;
            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = 'csrf_token';
            input.value = csrfToken;
            form.appendChild(input);
        });
        const nativeFetch = window.fetch.bind(window);
        window.fetch = (input, init = {}) => {
            const headers = new Headers(init.headers || {});
            const method = (init.method || 'GET').toUpperCase();
            if (!['GET', 'HEAD', 'OPTIONS'].includes(method) && !headers.has('X-CSRF-Token')) {
                headers.set('X-CSRF-Token', csrfToken);
            }
            return nativeFetch(input, { ...init, headers });
        };
    }

    const overlay = document.createElement('div');
    overlay.className = 'page-transition';
    overlay.innerHTML = '<div class="page-transition-card"><span class="spinner-border spinner-border-sm me-2"></span>Loading...</div>';
    document.body.appendChild(overlay);

    const showLoading = () => overlay.classList.add('show');
    const hideLoading = () => overlay.classList.remove('show');
    window.TalentBeaconLoading = { show: showLoading, hide: hideLoading };

    document.addEventListener('click', (event) => {
        const link = event.target.closest('a[href]');
        if (!link) return;
        const href = link.getAttribute('href') || '';
        if (
            link.target ||
            href.startsWith('#') ||
            href.startsWith('javascript:') ||
            link.dataset.noLoading === 'true' ||
            link.hasAttribute('download')
        ) return;
        const url = new URL(link.href, window.location.href);
        if (
            url.pathname.includes('/export/') ||
            /\.(xlsx|xls|csv|pdf|zip)$/i.test(url.pathname)
        ) return;
        if (url.origin === window.location.origin && url.href !== window.location.href) {
            showLoading();
        }
    });

    document.addEventListener('submit', (event) => {
        const form = event.target;
        if (form && form.dataset.noLoading !== 'true') {
            showLoading();
        }
    });

    window.addEventListener('pageshow', hideLoading);
});
