const gatewayInput = document.querySelector("#gateway-url");
const userInput = document.querySelector("#user-id");
const promptInput = document.querySelector("#prompt-input");
const sessionIdOutput = document.querySelector("#session-id");
const requestIdOutput = document.querySelector("#request-id");
const identityOutput = document.querySelector("#identity-output");
const responseOutput = document.querySelector("#response-output");

function defaultGateway() {
  if (window.location.protocol === "http:" || window.location.protocol === "https:") {
    return window.location.origin;
  }
  return "http://localhost:8080";
}

function buildRequestId() {
  return `req-${crypto.randomUUID()}`;
}

function currentGateway() {
  const explicitValue = gatewayInput.value.trim().replace(/\/$/, "");
  return explicitValue || defaultGateway();
}

gatewayInput.value = defaultGateway();

async function requestJson(path, options = {}) {
  const requestId = buildRequestId();
  requestIdOutput.textContent = requestId;
  const headers = {
    "x-request-id": requestId,
    ...(options.headers || {})
  };

  if (options.body) {
    headers["content-type"] = "application/json";
  }

  const response = await fetch(`${currentGateway()}${path}`, {
    ...options,
    headers
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status} ${response.statusText}`);
  }

  return response.json();
}

async function getLoginUrl() {
  const payload = await requestJson("/api/v1/auth/login-url", { method: "GET" });
  identityOutput.textContent = JSON.stringify(payload, null, 2);
}

async function normalizeIdentity() {
  const payload = await requestJson("/api/v1/identity/normalize", {
    method: "POST",
    body: JSON.stringify({
      sub: "user-123",
      preferred_username: userInput.value,
      email: `${userInput.value}@example.com`,
      groups: ["ops-operators"]
    })
  });
  identityOutput.textContent = JSON.stringify(payload, null, 2);
}

async function createSession() {
  const payload = await requestJson("/api/v1/sessions", {
    method: "POST",
    body: JSON.stringify({ user_id: userInput.value })
  });
  sessionIdOutput.textContent = payload.session_id;
  responseOutput.textContent = JSON.stringify(payload, null, 2);
}

async function sendPrompt() {
  const payload = await requestJson("/api/v1/chat", {
    method: "POST",
    body: JSON.stringify({
      session_id: sessionIdOutput.textContent === "Not created" ? null : sessionIdOutput.textContent,
      user_id: userInput.value,
      message: promptInput.value
    })
  });
  sessionIdOutput.textContent = payload.session_id;
  responseOutput.textContent = payload.response;
}

async function streamPrompt() {
  const requestId = buildRequestId();
  requestIdOutput.textContent = requestId;
  responseOutput.textContent = "";

  const params = new URLSearchParams({
    message: promptInput.value,
    user_id: userInput.value
  });

  if (sessionIdOutput.textContent !== "Not created") {
    params.set("session_id", sessionIdOutput.textContent);
  }

  const response = await fetch(`${currentGateway()}/api/v1/chat/stream?${params.toString()}`, {
    headers: {
      "x-request-id": requestId
    }
  });

  if (!response.ok || !response.body) {
    throw new Error("Stream request failed.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() || "";

    for (const event of events) {
      if (!event.startsWith("data: ")) {
        continue;
      }
      const payloadText = event.slice(6);
      const payload = JSON.parse(payloadText);
      sessionIdOutput.textContent = payload.session_id || sessionIdOutput.textContent;
      if (payload.delta) {
        responseOutput.textContent += payload.delta;
      }
      if (payload.message && payload.event === "message_end") {
        responseOutput.textContent += "\n\n[stream complete]";
      }
    }
  }
}

document.querySelector("#login-button").addEventListener("click", () => {
  getLoginUrl().catch((error) => {
    identityOutput.textContent = error.message;
  });
});

document.querySelector("#normalize-button").addEventListener("click", () => {
  normalizeIdentity().catch((error) => {
    identityOutput.textContent = error.message;
  });
});

document.querySelector("#session-button").addEventListener("click", () => {
  createSession().catch((error) => {
    responseOutput.textContent = error.message;
  });
});

document.querySelector("#send-button").addEventListener("click", () => {
  sendPrompt().catch((error) => {
    responseOutput.textContent = error.message;
  });
});

document.querySelector("#stream-button").addEventListener("click", () => {
  streamPrompt().catch((error) => {
    responseOutput.textContent = error.message;
  });
});
