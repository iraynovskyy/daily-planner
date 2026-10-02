// Progress rings beside each category's timeline.
// Shows month-to-date completion per habit plus the category overall (optional habits
// excluded, as everywhere else); while a day is hovered on the timeline, shows that day.
// Reads the same checkbox grid as timeline.js, so it stays in sync with every HTMX click.
{
const locale = document.documentElement.lang === "uk" ? "uk-UA" : undefined;
document.querySelectorAll(".category .timeline.with-rings").forEach((section) => {
  const root = section.closest(".category");
  const box = section.querySelector(".timeline-rings");
  const today = section.dataset.today;
  const NS = "http://www.w3.org/2000/svg";
  const MAX_SLOTS = 8; // same slots/colours as the timeline lines
  let habits = window.habitSeries(root, MAX_SLOTS); // from timeline.js: same colours as the lines
  const allDays = [...root.querySelectorAll("table.month thead th[data-day]")].map((th) => th.dataset.day);
  let focusDay = null;

  const count = (h, days) =>
    days.reduce(
      (s, day) => {
        const boxes = [...root.querySelectorAll(`#cell-${h.key}-${day} input[type=checkbox]`)];
        return { done: s.done + boxes.filter((b) => b.checked).length, target: s.target + boxes.length };
      },
      { done: 0, target: 0 },
    );
  const pct = (c) => (c.target ? Math.round((100 * c.done) / c.target) : null);
  const ticked = (h, day) => root.querySelectorAll(`#cell-${h.key}-${day} input:checked`).length > 0;

  function ring(value, color, size) {
    const stroke = size > 60 ? 8 : 5;
    const r = (size - stroke) / 2, c = 2 * Math.PI * r;
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", `0 0 ${size} ${size}`);
    svg.setAttribute("width", size);
    svg.setAttribute("height", size);
    svg.setAttribute("aria-hidden", "true");
    const circle = (cls, extra = {}) => {
      const n = document.createElementNS(NS, "circle");
      for (const [k, v] of Object.entries({ class: cls, cx: size / 2, cy: size / 2, r, "stroke-width": stroke, ...extra }))
        n.setAttribute(k, v);
      svg.appendChild(n);
    };
    circle("ring-track");
    if (value) {
      circle("ring-arc", {
        stroke: color,
        "stroke-dasharray": `${(c * value) / 100} ${c}`,
        transform: `rotate(-90 ${size / 2} ${size / 2})`,
      });
    }
    const t = document.createElementNS(NS, "text");
    t.setAttribute("class", size > 60 ? "ring-value big" : "ring-value");
    t.setAttribute("x", size / 2);
    t.setAttribute("y", size / 2);
    t.textContent = value === null ? "—" : value + "%";
    svg.appendChild(t);
    return svg;
  }

  function row(tag, cls, value, color, size, name, c) {
    const el = document.createElement(tag);
    el.className = cls;
    const label = document.createElement("span");
    label.className = "ring-label";
    const key = document.createElement("span");
    key.className = "key";
    key.style.background = color;
    const title = document.createElement("span");
    title.textContent = name;
    const detail = document.createElement("small");
    detail.textContent = `${c.done}/${c.target}`;
    label.append(key, title, detail);
    el.append(ring(value, color, size), label);
    return el;
  }

  function render() {
    const days = focusDay ? [focusDay] : allDays.filter((d) => d <= today);
    const caption = document.createElement("div");
    caption.className = "rings-caption";
    caption.textContent = focusDay
      ? new Date(focusDay + "T00:00:00").toLocaleDateString(locale, { weekday: "short", day: "numeric", month: "short" })
      : t("Month to date");
    if (!days.length) {
      const empty = document.createElement("p");
      empty.className = "rings-empty";
      empty.textContent = t("No progress to show yet");
      box.replaceChildren(caption, empty);
      return;
    }
    // Today is still in progress: a habit's ring counts it once that habit is ticked, the overall
    // ring once anything in the category is (same rule as the timeline). A hovered day always counts.
    const past = days.filter((d) => d !== today);
    const perHabit = habits.map((h) => ({ ...h, c: count(h, focusDay || ticked(h, today) ? days : past) }));
    const required = habits.filter((h) => !h.optional);
    const started = focusDay || required.some((h) => ticked(h, today));
    const all = required
      .map((h) => count(h, started ? days : past))
      .reduce((s, c) => ({ done: s.done + c.done, target: s.target + c.target }), { done: 0, target: 0 });
    if (!all.target && !focusDay) {
      // Nothing counted yet this month (e.g. the 1st, before any tick): no rings of "—".
      const empty = document.createElement("p");
      empty.className = "rings-empty";
      empty.textContent = t("The rings fill in as you tick.");
      box.replaceChildren(caption, empty);
      return;
    }
    const list = document.createElement("ul");
    list.className = "ring-list";
    list.append(
      ...perHabit.map((h) => row("li", "", pct(h.c), h.color, 44, h.name + (h.optional ? ` (${t("optional")})` : ""), h.c)),
    );
    box.replaceChildren(
      caption,
      row("div", "ring-main", pct(all), "var(--series-overall)", 88, section.dataset.overallLabel, all),
      list,
    );
  }

  section.addEventListener("timeline:focus", (e) => {
    focusDay = e.detail.day;
    render();
  });
  document.body.addEventListener("htmx:afterSettle", render);
  document.body.addEventListener("habits:reordered", () => {
    habits = window.habitSeries(root, MAX_SLOTS);
    render();
  });
  render();
});
}
