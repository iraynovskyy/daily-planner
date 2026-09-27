// Reorder habit rows inside one category: drag the ⠿ handle, or focus it and press ↑/↓.
// Works on any `[data-reorder]` list whose items carry `data-habit-id`. Required habits can't
// be moved below optional ones (the server enforces the same rule) and the order is saved at once.
(() => {
  const items = (list) => [...list.children].filter((el) => el.matches("[data-habit-id]"));
  const sameGroup = (a, b) => ("optional" in a.dataset) === ("optional" in b.dataset);

  function flash(el) {
    el.classList.remove("just-moved");
    void el.offsetWidth; // restart the animation
    el.classList.add("just-moved");
  }

  async function save(list) {
    const body = new URLSearchParams(items(list).map((el) => ["ids", el.dataset.habitId]));
    const r = await fetch("/habits/reorder", { method: "POST", body }).catch(() => null);
    if (!r?.ok) return location.reload(); // show the stored order rather than a wrong one
    // Month page: timelines and rings re-read the grid so legends follow the new row order.
    document.body.dispatchEvent(new CustomEvent("habits:reordered"));
  }

  for (const list of document.querySelectorAll("[data-reorder]")) {
    if (window.Sortable) {
      Sortable.create(list, {
        handle: ".drag-handle",
        draggable: "[data-habit-id]",
        animation: 180,
        easing: "cubic-bezier(.2, .8, .2, 1)",
        ghostClass: "drag-ghost",
        chosenClass: "drag-chosen",
        dragClass: "drag-dragging",
        delay: 120,
        delayOnTouchOnly: true, // long-press on phones, so scrolling still works
        onMove: (e) => sameGroup(e.dragged, e.related),
        onEnd: (e) => {
          if (e.oldIndex === e.newIndex) return;
          flash(e.item);
          save(list);
        },
      });
    }
    list.addEventListener("keydown", (e) => {
      const handle = e.target.closest(".drag-handle");
      if (!handle || (e.key !== "ArrowUp" && e.key !== "ArrowDown")) return;
      e.preventDefault();
      const item = handle.closest("[data-habit-id]");
      const sib = e.key === "ArrowUp" ? item.previousElementSibling : item.nextElementSibling;
      if (!sib?.matches("[data-habit-id]") || !sameGroup(item, sib)) return;
      e.key === "ArrowUp" ? sib.before(item) : sib.after(item);
      handle.focus();
      flash(item);
      save(list);
    });
  }
})();
