(function () {
  const current = document.currentScript;
  const origin = current && current.src ? new URL(current.src).origin : "http://localhost:3000";
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "Falar com a Alyvo";
  button.setAttribute("aria-label", "Abrir assistente Alyvo");
  Object.assign(button.style, {
    position: "fixed", right: "24px", bottom: "24px", zIndex: "2147483646",
    minHeight: "52px", padding: "0 20px", border: "0", borderRadius: "26px",
    background: "#2457ff", color: "white", font: "600 16px Inter, sans-serif", cursor: "pointer"
  });
  const frame = document.createElement("iframe");
  frame.src = origin + "/chat?widget=1";
  frame.title = "Assistente Alyvo";
  frame.hidden = true;
  Object.assign(frame.style, {
    position: "fixed", right: "24px", bottom: "88px", zIndex: "2147483647",
    width: "min(440px, calc(100vw - 32px))", height: "min(720px, calc(100vh - 112px))",
    border: "1px solid #d8dde6", background: "#f7f7f2", boxShadow: "0 18px 50px rgba(16,24,40,.18)"
  });
  button.addEventListener("click", function () {
    frame.hidden = !frame.hidden;
    button.textContent = frame.hidden ? "Falar com a Alyvo" : "Fechar assistente";
  });
  document.body.append(frame, button);
})();
