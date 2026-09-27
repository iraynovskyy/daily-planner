// Row highlight picker: the round button at the right of each habit row opens a small palette;
// picking a colour tints every row of that habit on the page and saves it for next time.
(() => {
  const rows = (id) => document.querySelectorAll(`.habit-row[data-habit-id="${id}"], table.month tr[data-habit-id="${id}"]`);
  let open = null; // { button, menu }

  function close({ focus = false } = {}) {
    if (!open) return;
    open.menu.hidden = true;
    open.button.setAttribute("aria-expanded", "false");
    open.button.closest(".hl-col")?.classList.remove("hl-open");
    if (focus) open.button.focus();
    open = null;
  }

  function show(button) {
    close();
    const menu = button.nextElementSibling;
    menu.hidden = false;
    button.setAttribute("aria-expanded", "true");
    button.closest(".hl-col")?.classList.add("hl-open"); // lift above neighbouring (sticky) cells
    open = { button, menu };
    (menu.querySelector('[aria-checked="true"]') || menu.querySelector(".hl-dot")).focus();
  }

  function apply(id, value) {
    for (const row of rows(id)) {
      if (value) row.dataset.hl = value;
      else delete row.dataset.hl;
      for (const dot of row.querySelectorAll(".hl-dot"))
        dot.setAttribute("aria-checked", String(dot.dataset.hlValue === value));
    }
  }

  async function pick(dot) {
    const id = open.button.dataset.habitId;
    const before = rows(id)[0]?.dataset.hl || "";
    const value = dot.dataset.hlValue;
    close({ focus: true });
    apply(id, value); // instant feedback; roll back if saving fails
    const r = await fetch(`/habits/${id}/highlight`, { method: "POST", body: new URLSearchParams({ color: value }) }).catch(() => null);
    if (!r?.ok) apply(id, before);
  }

  document.addEventListener("click", (e) => {
    const button = e.target.closest(".hl-button");
    if (button) return open?.button === button ? close() : show(button);
    const dot = e.target.closest(".hl-dot");
    if (dot && open) return pick(dot);
    if (open && !e.target.closest(".hl-menu")) close();
  });

  document.addEventListener("keydown", (e) => {
    if (!open) return;
    if (e.key === "Escape") return close({ focus: true });
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    const dots = [...open.menu.querySelectorAll(".hl-dot")];
    const i = dots.indexOf(document.activeElement);
    dots[(i + (e.key === "ArrowRight" ? 1 : -1) + dots.length) % dots.length].focus();
    e.preventDefault();
  });
})();
