// The header's "Must" dropdown (partials/must.html). HTMX re-renders the whole #must element after
// every change, so everything here is delegated to the document or re-applied after a swap.
(() => {
  const must = () => document.getElementById("must");

  // Close on a click outside it, or on Escape.
  document.addEventListener("click", (e) => {
    const el = must();
    if (el?.open && !el.contains(e.target)) el.open = false;
  });
  document.addEventListener("keydown", (e) => {
    const el = must();
    if (e.key === "Escape" && el?.open) {
      el.open = false;
      el.querySelector("summary")?.focus();
    }
  });

  // Opening it puts the cursor in the "add" field.
  document.addEventListener("toggle", (e) => {
    if (e.target.id === "must" && e.target.open) e.target.querySelector(".must-add input")?.focus();
  }, true);

  // Edit in place: ✎ or a double-click turns the text into a field; Enter saves, Escape cancels.
  function edit(li) {
    const span = li.querySelector(".must-text");
    if (!span || li.querySelector(".must-edit-input")) return;
    const input = document.createElement("input");
    input.className = "must-edit-input";
    input.value = span.textContent;
    input.maxLength = 200;
    input.setAttribute("aria-label", t("Edit"));
    span.replaceWith(input);
    input.focus();
    input.select();
    let finished = false;
    const finish = (save) => {
      if (finished) return;
      finished = true;
      const text = input.value.trim();
      if (!save || !text || text === span.textContent) return input.replaceWith(span);
      htmx.ajax("POST", `/must/${li.dataset.mustId}`, { target: "#must", swap: "outerHTML", values: { text } });
    };
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") finish(true);
      else if (e.key === "Escape") {
        e.stopPropagation(); // don't close the dropdown as well
        finish(false);
      }
    });
    input.addEventListener("blur", () => finish(true));
  }
  document.addEventListener("click", (e) => {
    const btn = e.target.closest("#must .must-edit");
    if (btn) edit(btn.closest("li"));
  });
  document.addEventListener("dblclick", (e) => {
    const span = e.target.closest("#must .must-text");
    if (span) edit(span.closest("li"));
  });

  // Drag ⠿ to reorder the open items; the new order is saved at once (the page already shows it).
  function sortable() {
    const list = must()?.querySelector("[data-must-list]");
    if (!list || !window.Sortable || list.dataset.sortable) return;
    list.dataset.sortable = "1";
    Sortable.create(list, {
      handle: ".drag-handle",
      draggable: "li[data-must-id]:not(.done)",
      animation: 160,
      ghostClass: "drag-ghost",
      delay: 120,
      delayOnTouchOnly: true,
      onEnd: (e) => {
        if (e.oldIndex === e.newIndex) return;
        const ids = [...list.querySelectorAll("li[data-must-id]:not(.done)")].map((li) => ["ids", li.dataset.mustId]);
        fetch("/must/order", { method: "POST", body: new URLSearchParams(ids) });
      },
    });
  }
  document.body.addEventListener("htmx:afterSettle", sortable);
})();
