// Golden day: two quick taps (or a double-click) on a habit's box mark that day gold.
// The first tap is an ordinary check/un-check done by htmx. The second, within DOUBLE_TAP_MS on
// the same habit and day, is taken over here: its plain toggle is cancelled and, once the first
// request has finished (so responses can't overtake each other), "all done + gold" is sent.
(() => {
  const DOUBLE_TAP_MS = 450;
  const lastTap = new Map(); // "habitId/day" → time of the previous tap
  const inFlight = new Map(); // "habitId/day" → callbacks to run when its request has finished

  function sendGold(box) {
    const values = JSON.parse(box.getAttribute("hx-vals") || "{}"); // keeps e.g. view=month
    htmx.ajax("POST", box.getAttribute("hx-post"), {
      target: box.getAttribute("hx-target"),
      swap: "outerHTML",
      values: { ...values, count: box.dataset.goldCount, golden: "true" },
    });
  }

  document.addEventListener("htmx:beforeRequest", (e) => {
    const box = e.detail.elt;
    if (!box.matches?.("input[data-gold-key]")) return;
    const key = box.dataset.goldKey;
    const waiting = [];
    inFlight.set(key, waiting);
    // loadend fires after htmx has swapped the response in.
    e.detail.xhr.addEventListener("loadend", () => {
      inFlight.delete(key);
      waiting.forEach((run) => run());
    });
  });

  document.addEventListener("click", (e) => {
    const box = e.target.closest?.("input[data-gold-key]");
    if (!box) return;
    const key = box.dataset.goldKey;
    const now = performance.now();
    if (now - (lastTap.get(key) ?? -Infinity) >= DOUBLE_TAP_MS) {
      lastTap.set(key, now);
      return; // first tap: ordinary check / un-check
    }
    lastTap.delete(key); // a third tap starts over
    e.preventDefault(); // no toggle, so htmx sends nothing for this tap
    const run = () => sendGold(box);
    if (inFlight.has(key)) inFlight.get(key).push(run);
    else run();
  });
})();
