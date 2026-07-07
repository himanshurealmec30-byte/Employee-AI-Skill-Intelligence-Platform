// TalentBeacon global JS utilities
document.addEventListener('DOMContentLoaded', () => {
    document.body.classList.add('page-ready');

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
