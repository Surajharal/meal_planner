/**
 * Full-screen loading overlay for AI and slow form submissions.
 */
(function () {
    var overlay = null;

    function ensureOverlay() {
        if (overlay) return overlay;
        overlay = document.createElement("div");
        overlay.id = "ai-loading-overlay";
        overlay.className = "ai-loading-overlay";
        overlay.setAttribute("role", "status");
        overlay.setAttribute("aria-live", "polite");
        overlay.setAttribute("aria-hidden", "true");
        overlay.innerHTML =
            '<div class="ai-loading-card">' +
            '<div class="ai-loading-spinner" aria-hidden="true"></div>' +
            '<p class="ai-loading-message" id="ai-loading-message">Working with AI…</p>' +
            '<p class="ai-loading-hint">This may take up to a minute. Please keep this tab open.</p>' +
            '</div>';
        document.body.appendChild(overlay);
        return overlay;
    }

    window.showAiLoading = function (message) {
        var el = ensureOverlay();
        var msg = document.getElementById("ai-loading-message");
        if (msg && message) msg.textContent = message;
        el.classList.add("is-visible");
        el.setAttribute("aria-hidden", "false");
        document.body.classList.add("ai-loading-active");
    };

    window.hideAiLoading = function () {
        if (!overlay) return;
        overlay.classList.remove("is-visible");
        overlay.setAttribute("aria-hidden", "true");
        document.body.classList.remove("ai-loading-active");
    };

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("form[data-ai-loading]").forEach(function (form) {
            form.addEventListener("submit", function () {
                var msg = form.getAttribute("data-ai-loading-message") || "Working with AI…";
                window.showAiLoading(msg);
            });
        });
    });
})();
