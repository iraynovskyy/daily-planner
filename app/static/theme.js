// Light / dark switch in the header: flips <html data-theme> and remembers the choice.
(() => {
  const button = document.querySelector(".theme-toggle");
  if (!button) return;
  const root = document.documentElement;
  const sync = () => button.setAttribute("aria-pressed", String(root.dataset.theme === "light"));
  sync();
  button.addEventListener("click", () => {
    root.dataset.theme = root.dataset.theme === "light" ? "dark" : "light";
    try { localStorage.setItem("theme", root.dataset.theme); } catch {}
    sync();
  });
})();
