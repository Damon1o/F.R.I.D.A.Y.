document.addEventListener("DOMContentLoaded", () => {
  const container = document.getElementById("dash-chat");
  if (!container) return;

  const widget = createChatWidget(container, { compact: false });

  container.querySelectorAll("[data-quick-prompt]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const input = container.querySelector("[data-chat-input]");
      input.value = btn.dataset.quickPrompt;
      container.querySelector("[data-chat-form]").requestSubmit();
    });
  });
});
