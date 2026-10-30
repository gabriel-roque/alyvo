(() => {
  const script = document.currentScript;
  const origin = script?.dataset.origin || new URL(script?.src || window.location.href).origin;
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = "Abrir assistente Alyvo";
  button.setAttribute("aria-expanded", "false");
  button.style.cssText = "position:fixed;right:24px;bottom:24px;z-index:2147483647;border:0;background:#2457ff;color:white;padding:14px 18px;font:600 16px Inter,sans-serif;cursor:pointer";
  const frame = document.createElement("iframe");
  frame.src = `${origin}/chat`;
  frame.title = "Assistente administrativo Alyvo";
  frame.hidden = true;
  frame.style.cssText = "position:fixed;right:24px;bottom:82px;width:min(760px,calc(100vw - 32px));height:min(760px,calc(100vh - 120px));z-index:2147483646;border:1px solid #d8dde6;background:#f7f7f2";
  button.addEventListener("click", () => {
    frame.hidden = !frame.hidden;
    button.setAttribute("aria-expanded", String(!frame.hidden));
    button.textContent = frame.hidden ? "Abrir assistente Alyvo" : "Fechar assistente Alyvo";
  });
  document.body.append(frame, button);
})();
