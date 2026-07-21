function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  }[c]));
}

function createChatWidget(container, options = {}) {
  const form = container.querySelector("[data-chat-form]");
  const input = container.querySelector("[data-chat-input]");
  const messages = container.querySelector("[data-chat-messages]");
  const tokenEl = container.querySelector("[data-chat-tokens]");

  function appendMessage(role, text) {
    const row = document.createElement("div");
    row.className = "chat-message " + role;

    const avatar = document.createElement("div");
    avatar.className = "message-avatar " + role;
    avatar.textContent = role === "user" ? "U" : "AI";

    const bubble = document.createElement("div");
    bubble.className = "message-content " + role;
    bubble.innerHTML = escapeHtml(text);

    row.appendChild(avatar);
    row.appendChild(bubble);
    messages.appendChild(row);
    messages.scrollTop = messages.scrollHeight;
  }

  let activated = false;
  function activate() {
    if (activated) return;
    activated = true;
    messages.style.display = "flex";
    const welcome = container.querySelector(".ai-welcome");
    if (welcome) welcome.style.display = "none";
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const text = input.value.trim();
    if (!text) return;

    activate();
    appendMessage("user", text);
    input.value = "";
    input.style.height = "auto";

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      const data = await response.json();
      appendMessage("assistant", data.reply);
      if (tokenEl && typeof data.total_tokens === "number") {
        tokenEl.textContent =
          `Tokens: ${data.input_tokens} in + ${data.output_tokens} out = ${data.total_tokens} total`;
      }
    } catch (err) {
      appendMessage("assistant", "Error: " + err.message);
    }
  }

  form.addEventListener("submit", handleSubmit);
  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = input.scrollHeight + "px";
  });

  return { appendMessage, activate };
}
