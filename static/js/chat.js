document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");
  const messages = document.getElementById("chat-messages");
  const tokenEl = document.getElementById("token-usage");

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text) return;
    appendMsg("user", text);
    input.value = "";
    input.style.height = "auto";

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      const data = await res.json();
      appendMsg("assistant", data.reply);
      if (data.usage) {
        tokenEl.textContent = `Tokens: ${data.usage.prompt_tokens} in + ${data.usage.completion_tokens} out = ${data.usage.total_tokens} total`;
      }
    } catch (e) {
      appendMsg("assistant", "Error: " + e.message);
    }
  });

  function appendMsg(role, text) {
    const div = document.createElement("div");
    div.className = "msg " + role;
    div.textContent = text;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
  }

  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = input.scrollHeight + "px";
  });
});