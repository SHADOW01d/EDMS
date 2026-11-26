(() => {
    const dialog = document.getElementById("actionFeedbackDialog");
    const queue = document.getElementById("actionFeedbackQueue");
    const icon = document.getElementById("actionFeedbackIcon");
    const title = document.getElementById("actionFeedbackTitle");
    const message = document.getElementById("actionFeedbackMessage");
    const closeButton = document.getElementById("actionFeedbackClose");
    if (!dialog || !queue || !icon || !title || !message || !closeButton) return;

    const feedbackItems = [...queue.querySelectorAll("[data-feedback-item]")].map((item) => ({
        level: item.dataset.level,
        message: item.textContent.trim(),
    }));
    const levels = {
        success: { title: "Imefanikiwa", icon: "bi-check-lg", role: "status" },
        error: { title: "Haikufanikiwa", icon: "bi-x-lg", role: "alert" },
        warning: { title: "Tahadhari", icon: "bi-exclamation-lg", role: "alert" },
        info: { title: "Taarifa", icon: "bi-info-lg", role: "status" },
    };
    const showNextFeedback = () => {
        const item = feedbackItems.shift();
        if (!item) return;

        const level = levels[item.level] || levels.info;
        dialog.dataset.level = item.level in levels ? item.level : "info";
        dialog.setAttribute("role", level.role === "alert" ? "alertdialog" : "dialog");
        icon.className = `bi ${level.icon}`;
        title.textContent = level.title;
        message.textContent = item.message;
        dialog.showModal();
        closeButton.focus();
    };

    closeButton.addEventListener("click", () => dialog.close());
    dialog.addEventListener("close", () => {
        if (feedbackItems.length) showNextFeedback();
    });

    window.showActionFeedback = (text, level = "info") => {
        feedbackItems.push({ level, message: String(text) });
        if (!dialog.open) showNextFeedback();
    };

    if (feedbackItems.length) showNextFeedback();
})();
