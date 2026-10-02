// Note blocks (Own Tips, Ideas, Comfort):
// - drag a note by ⠿ to reorder it or drop it into another block;
//   keyboard: focus ⠿, ↑/↓ inside the block, ←/→ to the previous / next block;
// - edit in place: ✎ or double-click the text, Enter saves, Esc cancels.
// The server re-renders the affected block(s); they are swapped in and re-initialised here.
(() => {
  const blocks = () => [...document.querySelectorAll("details.notes")];
  const notesOf = (ul) => [...ul.querySelectorAll(":scope > li[data-note-id]")].map((li) => li.dataset.noteId);

  // Swap in re-rendered <details class="notes"> blocks (by id), keeping the open ones open.
  function replaceBlocks(html, focusNoteId) {
    const tpl = document.createElement("template");
    tpl.innerHTML = html;
    for (const fresh of tpl.content.querySelectorAll("details.notes")) {
      const current = document.getElementById(fresh.id);
      if (!current) continue;
      fresh.open = current.open || fresh.open;
      current.replaceWith(fresh);
      htmx.process(fresh);
      init(fresh);
    }
    if (focusNoteId) document.querySelector(`li[data-note-id="${focusNoteId}"] .drag-handle`)?.focus();
  }

  async function post(url, body) {
    const r = await fetch(url, { method: "POST", body }).catch(() => null);
    return r?.ok ? r.text() : null;
  }

  async function saveOrder(focusNoteId) {
    const body = new URLSearchParams();
    for (const ul of document.querySelectorAll("ul[data-notes]"))
      for (const id of notesOf(ul)) body.append(ul.dataset.notes, id);
    const html = await post("/notes/order", body);
    if (html === null) return location.reload(); // show the stored order rather than a wrong one
    replaceBlocks(html, focusNoteId);
  }

  function startEdit(li) {
    if (li.querySelector(".notes-text-input")) return;
    const span = li.querySelector(".notes-text");
    const input = document.createElement("input");
    input.className = "notes-text-input";
    input.value = span.textContent;
    input.maxLength = 300;
    input.setAttribute("aria-label", t("Edit note"));
    span.replaceWith(input);
    input.focus();
    input.select();

    let done = false;
    const finish = async (save) => {
      if (done) return;
      done = true;
      const text = input.value.trim();
      if (!save || !text || text === span.textContent) {
        input.replaceWith(span);
        return li.querySelector(".notes-edit").focus();
      }
      li.classList.add("saving");
      const html = await post(`/notes/${li.dataset.noteId}`, new URLSearchParams({ text }));
      if (html === null) {
        li.classList.remove("saving");
        input.replaceWith(span);
        return;
      }
      replaceBlocks(html, li.dataset.noteId);
    };
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") finish(true);
      else if (e.key === "Escape") finish(false);
      else return;
      e.preventDefault();
      e.stopPropagation();
    });
    input.addEventListener("blur", () => finish(true));
  }

  function init(block) {
    const ul = block.querySelector("ul[data-notes]");
    if (!ul || ul.dataset.ready) return;
    ul.dataset.ready = "1";
    if (window.Sortable) {
      Sortable.create(ul, {
        group: "notes", // lets notes move between Own Tips and Ideas
        handle: ".drag-handle",
        draggable: "li[data-note-id]",
        animation: 180,
        easing: "cubic-bezier(.2, .8, .2, 1)",
        ghostClass: "drag-ghost",
        chosenClass: "drag-chosen",
        delay: 120,
        delayOnTouchOnly: true,
        emptyInsertThreshold: 24,
        onStart: () => document.querySelectorAll("ul[data-notes]").forEach((u) => u.classList.add("drop-target")),
        onEnd: (e) => {
          document.querySelectorAll("ul[data-notes]").forEach((u) => u.classList.remove("drop-target"));
          if (e.from !== e.to || e.oldIndex !== e.newIndex) saveOrder();
        },
      });
    }
    ul.addEventListener("click", (e) => {
      const edit = e.target.closest(".notes-edit");
      if (edit) startEdit(edit.closest("li"));
    });
    ul.addEventListener("dblclick", (e) => {
      const text = e.target.closest(".notes-text");
      if (text) startEdit(text.closest("li"));
    });
    ul.addEventListener("keydown", (e) => {
      const handle = e.target.closest(".drag-handle");
      if (!handle || !["ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight"].includes(e.key)) return;
      e.preventDefault();
      const li = handle.closest("li");
      if (e.key === "ArrowUp" || e.key === "ArrowDown") {
        const sib = e.key === "ArrowUp" ? li.previousElementSibling : li.nextElementSibling;
        if (!sib?.matches("li[data-note-id]")) return;
        e.key === "ArrowUp" ? sib.before(li) : sib.after(li);
      } else {
        const all = blocks();
        const other = all[(all.indexOf(block) + (e.key === "ArrowRight" ? 1 : -1) + all.length) % all.length];
        const target = other?.querySelector("ul[data-notes]");
        if (!target || other === block) return;
        other.open = true;
        target.querySelector(":scope > li:not([data-note-id])")?.remove(); // "Nothing here yet"
        target.append(li);
      }
      saveOrder(li.dataset.noteId);
    });
  }

  blocks().forEach(init);
  // Blocks re-rendered by HTMX (add / delete) need wiring up again.
  document.body.addEventListener("htmx:afterSettle", () => blocks().forEach(init));
})();
