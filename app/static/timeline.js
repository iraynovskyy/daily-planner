// Progress timelines for the month page: one chart per category, with one line per habit
// plus an overall line. Each reads its own category's checkbox grid (no extra endpoint),
// so it redraws on every HTMX click.
// Habits of one category grid in row order. Colour slot = rank of the habit id, so a habit keeps
// its colour when rows are reordered or lines hidden (colour follows the habit, not the row).
window.habitSeries = (root, maxSlots) => {
  const rows = [...root.querySelectorAll("table.month tbody tr[data-habit-id]")];
  const slot = new Map(
    rows
      .map((tr) => Number(tr.dataset.habitId))
      .sort((a, b) => a - b)
      .map((id, i) => [String(id), i]),
  );
  return rows
    .filter((tr) => slot.get(tr.dataset.habitId) < maxSlots) // palette is never cycled
    .map((tr) => ({
      key: tr.dataset.habitId,
      name: tr.dataset.habitName,
      optional: "optional" in tr.dataset,
      color: `var(--series-${slot.get(tr.dataset.habitId) + 1})`,
    }));
};

document.querySelectorAll(".category .timeline").forEach((section) => {
  const root = section.closest(".category");
  const svg = section.querySelector(".timeline-svg");
  const tip = section.querySelector(".timeline-tip");
  const legend = section.querySelector(".timeline-legend");
  const today = section.dataset.today;
  const NS = "http://www.w3.org/2000/svg";
  const MAX_SLOTS = 8; // categorical palette size; colours are never cycled
  const M = { top: 16, right: 16, bottom: 26, left: 36 };
  // Phones: start with only the overall line (six crossing lines are unreadable that narrow);
  // tapping a habit in the legend adds its line.
  const phone = matchMedia("(max-width: 700px)"); // same breakpoint as the phone CSS
  const hidden = new Set();
  let series = [], days = [], x = null, y = null, active = null, hover = null;

  let habits = window.habitSeries(root, MAX_SLOTS);
  // Optional habits get their own line but, like on the server, never count towards the overall one.
  const overall = { key: "overall", name: section.dataset.overallLabel, color: "var(--series-overall)" };

  function readGrid() {
    days = [...root.querySelectorAll("table.month thead th[data-day]")].map((th) => ({
      day: th.dataset.day,
      date: new Date(th.dataset.day + "T00:00:00"),
    }));
    const count = (h, day) => {
      const boxes = [...root.querySelectorAll(`#cell-${h.key}-${day} input[type=checkbox]`)];
      return { done: boxes.filter((b) => b.checked).length, target: boxes.length };
    };
    // Future days have no progress yet: leave a gap rather than plotting 0%. Today is still in
    // progress, so it shows only once something is ticked (from tomorrow a 0 counts as a 0).
    const pct = (c, day) =>
      day > today || !c.target || (day === today && !c.done) ? null : Math.round((100 * c.done) / c.target);
    const perHabit = habits.map((h) => ({
      ...h,
      points: days.map(({ day }) => {
        const c = count(h, day);
        return { ...c, value: pct(c, day) };
      }),
    }));
    const all = {
      ...overall,
      points: days.map(({ day }, i) => {
        const c = perHabit
          .filter((h) => !h.optional)
          .reduce(
            (s, h) => ({ done: s.done + h.points[i].done, target: s.target + h.points[i].target }),
            { done: 0, target: 0 },
          );
        return { ...c, value: pct(c, day) };
      }),
    };
    series = [all, ...perHabit];
  }

  function el(name, attrs, parent = svg) {
    const node = document.createElementNS(NS, name);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    parent.appendChild(node);
    return node;
  }

  function buildLegend() {
    if (phone.matches) habits.forEach((h) => hidden.add(h.key));
    legend.replaceChildren(
      ...[overall, ...habits].map((s) => {
        const b = document.createElement("button");
        b.type = "button";
        b.setAttribute("aria-pressed", String(!hidden.has(s.key)));
        const key = document.createElement("span");
        key.className = "key";
        key.style.background = s.color;
        b.append(key, document.createTextNode(s.name));
        b.addEventListener("click", () => {
          hidden.has(s.key) ? hidden.delete(s.key) : hidden.add(s.key);
          b.setAttribute("aria-pressed", String(!hidden.has(s.key)));
          render();
        });
        return b;
      }),
    );
  }

  function render() {
    readGrid();
    const W = svg.clientWidth || 600;
    const H = svg.clientHeight || 260; // set in CSS (lower on phones)
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.replaceChildren();
    const visible = series.filter((s) => !hidden.has(s.key));
    const labelled = visible.length <= 4; // direct labels only while they stay readable
    // Phones label line ends with the value only, in the line's colour, to keep the width.
    const narrow = phone.matches;
    const right = labelled ? (narrow ? 44 : 160) : M.right;
    const left = narrow ? 44 : M.left; // room for "100%" off the screen edge
    const iw = W - left - right, ih = H - M.top - M.bottom;
    const step = iw / Math.max(days.length - 1, 1);
    x = (i) => left + i * step;
    y = (v) => M.top + ih - (v / 100) * ih;

    for (const v of [0, 50, 100]) {
      el("line", { class: "grid", x1: left, x2: left + iw, y1: y(v), y2: y(v) });
      el("text", { class: "axis-label", x: left - 8, y: y(v) + 4, "text-anchor": "end" }).textContent = v + "%";
    }
    days.forEach((d, i) => {
      if (d.date.getDate() === 1 || d.date.getDay() === 1) {
        el("text", { class: "axis-label", x: x(i), y: H - 6, "text-anchor": "middle" }).textContent = d.date.getDate();
      }
      if (d.day === today) el("line", { class: "today-mark", x1: x(i), x2: x(i), y1: M.top, y2: M.top + ih });
    });

    const lastIdx = days.reduce((last, d, i) => (d.day <= today ? i : last), -1);
    if (lastIdx < 0) {
      el("text", { class: "empty", x: left + iw / 2, y: M.top + ih / 2, "text-anchor": "middle" })
        .textContent = "No progress to show yet";
      hover = null;
      return;
    }

    // Draw in reverse so habit 1 sits on top; the overall line stays underneath.
    for (const s of [...visible].reverse()) {
      const d = s.points
        .map((p, i) => (p.value === null ? null : `${x(i)},${y(p.value)}`))
        .filter(Boolean)
        .map((pt, k) => (k ? "L" : "M") + pt)
        .join("");
      if (!d) continue;
      if (s.key === "overall") {
        // Soft fill under the overall line (shown on phones only, see CSS).
        const pts = s.points.map((p, i) => (p.value === null ? null : i)).filter((i) => i !== null);
        el("path", { class: "area", d: `${d}L${x(pts.at(-1))},${y(0)}L${x(pts[0])},${y(0)}Z` });
      }
      el("path", { class: "halo", d });
      el("path", { class: s.key === "overall" ? "line overall" : "line", d, stroke: s.color });
    }

    if (labelled) {
      // Spread end labels so converging lines (e.g. several at 0%) don't collide; a leader ties each to its line.
      // Each line is labelled at its last plotted day (today may not be plotted yet).
      const labels = visible
        .map((s) => ({ s, i: s.points.findLastIndex((p) => p.value !== null) }))
        .filter((l) => l.i >= 0)
        .map((l) => ({ ...l, v: l.s.points[l.i].value }))
        .map((l) => ({ ...l, ly: y(l.v), ty: y(l.v) }))
        .sort((a, b) => a.ly - b.ly);
      for (let k = 1; k < labels.length; k++) labels[k].ty = Math.max(labels[k].ty, labels[k - 1].ty + 14);
      const overflow = labels.length ? labels[labels.length - 1].ty - (M.top + ih + 4) : 0;
      if (overflow > 0) labels.forEach((l) => (l.ty -= overflow));
      const lx = left + iw + 10;
      for (const l of labels) {
        el("line", { class: "leader", x1: x(l.i) + 3, y1: l.ly, x2: lx - 2, y2: l.ty, style: `stroke: ${l.s.color}` });
        const label = el("text", { class: "end-label", x: lx, y: l.ty + 4 });
        label.textContent = narrow ? `${l.v}%` : `${l.v}% ${l.s.name}`;
        if (narrow) label.style.fill = l.s.color;
      }
    }

    const cross = el("line", { class: "crosshair", y1: M.top, y2: M.top + ih, visibility: "hidden" });
    const dots = visible.map((s) => ({ s, node: el("circle", { class: "dot", r: 4, fill: s.color, visibility: "hidden" }) }));
    hover = { cross, dots, visible };
    if (active !== null) show(active);
  }

  function show(i) {
    if (!hover || !days[i]) return;
    active = i;
    // Lets companion widgets (the progress rings) follow the hovered day.
    section.dispatchEvent(new CustomEvent("timeline:focus", { detail: { day: days[i].day } }));
    hover.cross.setAttribute("x1", x(i));
    hover.cross.setAttribute("x2", x(i));
    hover.cross.setAttribute("visibility", "visible");
    for (const { s, node } of hover.dots) {
      const v = s.points[i].value;
      node.setAttribute("visibility", v === null ? "hidden" : "visible");
      if (v !== null) {
        node.setAttribute("cx", x(i));
        node.setAttribute("cy", y(v));
      }
    }

    const date = document.createElement("div");
    date.className = "tip-date";
    date.textContent = days[i].date.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
    tip.replaceChildren(date);
    for (const s of hover.visible) {
      const p = s.points[i];
      const row = document.createElement("div");
      row.className = "tip-row";
      const key = document.createElement("span");
      key.className = "key";
      key.style.background = s.color;
      const value = document.createElement("b");
      value.textContent = p.value === null ? "—" : p.value + "%";
      const name = document.createElement("span");
      name.textContent = s.name;
      const count = document.createElement("span");
      count.textContent = `${p.done}/${p.target}`;
      row.append(key, value, name, count);
      tip.appendChild(row);
    }
    tip.hidden = false;
    const W = svg.clientWidth;
    const px = x(i) * (W / svg.viewBox.baseVal.width);
    const left = px + 12 + tip.offsetWidth > W ? px - 12 - tip.offsetWidth : px + 12;
    tip.style.left = Math.max(0, left) + "px";
  }

  function hide() {
    active = null;
    section.dispatchEvent(new CustomEvent("timeline:focus", { detail: { day: null } }));
    tip.hidden = true;
    hover?.cross.setAttribute("visibility", "hidden");
    hover?.dots.forEach(({ node }) => node.setAttribute("visibility", "hidden"));
  }

  function nearest(evt) {
    const r = svg.getBoundingClientRect();
    const vx = ((evt.clientX - r.left) * svg.viewBox.baseVal.width) / r.width;
    const step = x(1) - x(0) || 1;
    return Math.min(days.length - 1, Math.max(0, Math.round((vx - x(0)) / step)));
  }

  svg.addEventListener("pointermove", (e) => show(nearest(e)));
  svg.addEventListener("pointerleave", hide);
  svg.addEventListener("click", (e) => (location.href = "/day/" + days[nearest(e)].day));
  svg.addEventListener("focus", () => show(active ?? Math.max(0, days.findIndex((d) => d.day === today))));
  svg.addEventListener("blur", hide);
  svg.addEventListener("keydown", (e) => {
    const i = active ?? 0;
    if (e.key === "ArrowRight") show(Math.min(days.length - 1, i + 1));
    else if (e.key === "ArrowLeft") show(Math.max(0, i - 1));
    else if (e.key === "Enter") location.href = "/day/" + days[i].day;
    else return;
    e.preventDefault();
  });
  document.body.addEventListener("htmx:afterSettle", render);
  document.body.addEventListener("habits:reordered", () => {
    habits = window.habitSeries(root, MAX_SLOTS);
    buildLegend();
    render();
  });
  new ResizeObserver(render).observe(svg);
  buildLegend();
});
