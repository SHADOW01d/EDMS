(() => {
    if ("serviceWorker" in navigator) {
        window.addEventListener("load", () => {
            navigator.serviceWorker.register("/sw.js")
                .catch((error) => console.error("Service Worker registration failed:", error));
        });
    }

    const installButtons = [...document.querySelectorAll("[data-pwa-install]")];
    if (!installButtons.length) return;

    const installHelp = [...document.querySelectorAll("[data-pwa-install-help]")];
    const isStandalone = window.matchMedia("(display-mode: standalone)").matches
        || window.navigator.standalone === true;
    const isAppleMobile = /iPhone|iPad|iPod/.test(window.navigator.userAgent)
        || (window.navigator.platform === "MacIntel" && window.navigator.maxTouchPoints > 1);
    let installPrompt;

    if (isStandalone) return;

    const showInstallButtons = () => {
        installButtons.forEach((button) => {
            button.hidden = false;
        });
    };

    window.addEventListener("beforeinstallprompt", (event) => {
        event.preventDefault();
        installPrompt = event;
        showInstallButtons();
    });

    installButtons.forEach((button) => {
        button.addEventListener("click", async () => {
            if (!installPrompt) {
                if (isAppleMobile) {
                    installHelp.forEach((help) => {
                        help.hidden = false;
                    });
                }
                return;
            }

            button.disabled = true;
            try {
                await installPrompt.prompt();
                await installPrompt.userChoice;
            } catch (error) {
                console.error("EDMS install prompt failed:", error);
            } finally {
                installPrompt = null;
                button.disabled = false;
                if (!isAppleMobile) {
                    installButtons.forEach((installButton) => {
                        installButton.hidden = true;
                    });
                }
            }
        });
    });

    window.addEventListener("appinstalled", () => {
        installButtons.forEach((button) => {
            button.hidden = true;
        });
    });

    if (isAppleMobile) showInstallButtons();
})();
