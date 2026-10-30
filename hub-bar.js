const BASE_URL = 'https://thadeutourinho-tech.github.io/hub_inutil/index.html';

(() => {
    if (document.getElementById('hub-shared-bar')) return;

    const appName = window.location.pathname.split('/').pop().replace(/\.html$/i, '');
    const shareUrl = BASE_URL + '#app=' + appName;
    document.body.style.paddingTop = '56px';

    const bar = document.createElement('nav');
    bar.id = 'hub-shared-bar';
    bar.className = 'fixed inset-x-0 top-0 z-[10000] flex h-14 items-center justify-between bg-gray-900/90 px-4 text-white shadow-lg backdrop-blur';

    const backLink = document.createElement('a');
    backLink.href = 'index.html';
    backLink.target = '_top';
    backLink.className = 'font-bold transition-colors hover:text-gray-300';
    backLink.textContent = '← Voltar';

    const shareButton = document.createElement('button');
    shareButton.type = 'button';
    shareButton.className = 'rounded bg-white/10 px-4 py-2 font-bold transition-colors hover:bg-white/20';
    shareButton.textContent = 'Compartilhar';

    const toast = document.createElement('div');
    toast.className = 'fixed bottom-4 left-1/2 z-[10001] hidden -translate-x-1/2 rounded bg-gray-900 px-4 py-3 text-white shadow-lg';
    toast.setAttribute('role', 'status');
    toast.setAttribute('aria-live', 'polite');
    bar.append(backLink, shareButton);
    document.body.append(bar, toast);

    let toastTimer;
    function showToast(message) {
        toast.textContent = message;
        toast.classList.remove('hidden');
        clearTimeout(toastTimer);
        toastTimer = setTimeout(() => toast.classList.add('hidden'), 2000);
    }

    async function copyShareUrl() {
        try {
            if (navigator.clipboard && navigator.clipboard.writeText) {
                await navigator.clipboard.writeText(shareUrl);
            } else {
                const temporaryInput = document.createElement('textarea');
                temporaryInput.value = shareUrl;
                temporaryInput.setAttribute('readonly', '');
                temporaryInput.style.position = 'fixed';
                temporaryInput.style.opacity = '0';
                document.body.appendChild(temporaryInput);
                temporaryInput.select();
                const copied = document.execCommand('copy');
                temporaryInput.remove();
                if (!copied) throw new Error('O navegador recusou a cópia.');
            }
            showToast('Link copiado!');
        } catch {
            showToast('Não consegui copiar o link');
        }
    }

    shareButton.addEventListener('click', async () => {
        if (!navigator.share) {
            await copyShareUrl();
            return;
        }

        try {
            await navigator.share({ title: document.title, url: shareUrl });
        } catch (error) {
            if (error.name !== 'AbortError') showToast('Não foi possível compartilhar o link');
        }
    });
})();
