const form = document.querySelector("#chat-form");
const input = document.querySelector("#message");
const transcript = document.querySelector("#transcript");
const button = form.querySelector("button");

function addMessage(kind, text) {
  const node = document.createElement("div");
  node.className = `message ${kind}`;
  node.textContent = text;
  transcript.appendChild(node);
  transcript.scrollTop = transcript.scrollHeight;
  return node;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) return;
  addMessage("user", message);
  input.value = "";
  button.disabled = true;
  const responseNode = addMessage("assistant", "");
  try {
    const response = await fetch("/api/chat/stream", {
      method: "POST",
      headers: {"content-type": "application/json"},
      body: JSON.stringify({message})
    });
    if (!response.ok || !response.body) throw new Error("The chat service is unavailable.");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {stream: true});
      const events = buffer.split("\n\n");
      buffer = events.pop();
      for (const rawEvent of events) {
        const type = rawEvent.match(/^event: (.+)$/m)?.[1];
        const rawData = rawEvent.match(/^data: (.+)$/m)?.[1];
        if (!type || !rawData) continue;
        const data = JSON.parse(rawData);
        if (type === "delta") responseNode.textContent += data.text;
        if (type === "error") {
          responseNode.className = "message error";
          responseNode.textContent = data.message;
        }
      }
      transcript.scrollTop = transcript.scrollHeight;
    }
  } catch (error) {
    responseNode.className = "message error";
    responseNode.textContent = "The chat service is unavailable.";
  } finally {
    button.disabled = false;
    input.focus();
  }
});
