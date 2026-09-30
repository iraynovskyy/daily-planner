import re
from datetime import date, timedelta

import pytest


def test_index_redirects_to_current_month(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 307 and r.headers["location"].startswith("/month/")


def test_month_page_lists_every_day_with_checkboxes(client):
    r = client.get("/month/2026-02")
    assert r.status_code == 200
    assert 'id="cell-2-2026-02-28"' in r.text and "2026-02-29" not in r.text
    assert r.text.count('type="checkbox"') == 28 * 16  # target counts of the 12 default habits


def test_invalid_month_rejected(client):
    assert client.get("/month/2026-13").status_code == 404
    assert client.get("/month/sept").status_code == 422


def test_month_click_returns_cell_and_progress(client):
    r = client.post("/entries/2/2026-09-27", data={"count": 3, "view": "month"})
    assert r.status_code == 200
    assert 'id="cell-2-2026-09-27"' in r.text
    assert 'id="day-progress-1-2026-09-27" hx-swap-oob="true"' in r.text
    assert "38%" in r.text  # Base on that day: 3 of 8
    assert 'id="progress-cat-1" class="progress-bar" hx-swap-oob="true"' in r.text
    assert 'id="progress" class="progress-bar" hx-swap-oob="true"' in r.text


def test_day_page_renders_default_habits(client):
    r = client.get("/day/2026-09-27")
    assert r.status_code == 200
    assert "Workout" in r.text and "Food" in r.text


def test_checking_a_box_persists(client, session):
    habit_id = 2  # Food, target 3
    r = client.post(f"/entries/{habit_id}/2026-09-27", data={"count": 2})
    assert r.status_code == 200
    assert 'id="habit-2"' in r.text and 'hx-swap-oob="true"' in r.text

    page = client.get("/day/2026-09-27").text
    assert "Overall · 13% done" in page  # 2 of 15 (optional No sugar not counted)
    assert "25% done" in page  # Base: 2 of 8


def test_unknown_habit_404(client):
    assert client.post("/entries/999/2026-09-27", data={"count": 1}).status_code == 404


def test_habit_crud(client):
    r = client.post("/habits", data={"name": "Meditate", "target_count": 1, "unit": "5 min"})
    assert r.status_code == 200 and "Meditate" in r.text  # followed 303 redirect
    client.post("/habits/13/active", data={"active": "false"})
    assert "Meditate" not in client.get("/day/2030-01-01").text


def test_optional_habit_shown_but_not_counted(client):
    page = client.get("/day/2026-09-27").text
    assert "No sugar" in page and "optional-tag" in page
    r = client.post("/entries/10/2026-09-27", data={"count": 1})  # No sugar
    assert "Overall · 0% done" in r.text


def test_habit_can_be_marked_optional(client):
    client.post("/habits/1", data={"name": "Workout", "target_count": 1, "optional": "true"})
    r = client.post("/entries/1/2026-09-27", data={"count": 1})
    assert "Overall · 0% done" in r.text


def test_pages_are_split_into_categories(client):
    for url in ("/day/2026-09-27", "/month/2026-09", "/habits"):
        page = client.get(url).text
        assert all(c in page for c in ("Base", "Career", "Good habits")), url
    month = client.get("/month/2026-09").text
    assert month.count('class="timeline with-rings"') == 3
    assert month.count('class="timeline-rings"') == 3 and "/static/rings.js" in month
    # Timelines are collapsible (closed unless the browser remembers them open).
    assert month.count('<details class="timeline-box" data-remember="timeline-') == 3
    # Highlight picker sits in its own last column: one per habit row + header + footer.
    assert month.count('class="hl-col"') == 12 + 3 * 2


def test_category_crud(client):
    r = client.post("/categories", data={"name": "Health"})
    assert r.status_code == 200 and "Health" in r.text
    client.post("/categories/4", data={"name": "Wellbeing"})
    client.post("/habits", data={"name": "Stretch", "target_count": 1, "category_id": 4})
    assert "Wellbeing" in client.get("/day/2026-09-27").text
    assert client.post("/categories/99", data={"name": "x"}).status_code == 404
    r = client.post("/habits", data={"name": "x", "target_count": 1, "category_id": 99})
    assert r.status_code == 404


def test_note_blocks_are_collapsed_on_pages(client):
    for url in ("/day/2026-09-27", "/month/2026-09"):
        page = client.get(url).text
        assert '<details class="notes" id="notes-tip" data-kind="tip">' in page, url  # closed
        assert '<details class="notes" id="notes-idea" data-kind="idea">' in page, url
        assert '<details class="notes" id="notes-comfort" data-kind="comfort">' in page, url
        assert all(t in page for t in ("Own Tips (to Grow)", "Ideas (to Grow)", "Comfort (Life)"))
        assert "Call a friend" in page
        assert "Small steps every day beat rare big ones" in page


def test_note_add_and_delete(client):
    r = client.post("/notes", data={"kind": "idea", "text": "Try pair programming"})
    assert r.status_code == 200
    assert '<details class="notes" id="notes-idea" data-kind="idea" open>' in r.text  # stays open
    assert "Try pair programming" in r.text and 'aria-label="3 notes"' in r.text

    r = client.post("/notes/8/delete")
    assert (
        r.status_code == 200
        and "Try pair programming" not in r.text
        and 'aria-label="2 notes"' in r.text
    )
    assert client.post("/notes/8/delete").status_code == 404
    assert client.post("/notes", data={"kind": "other", "text": "x"}).status_code == 422


def test_reorder_endpoint(client):
    page = client.get("/day/2026-09-27").text
    habit_handles = page.count('class="drag-handle"') - page.count('aria-label="Move note:')
    assert habit_handles == 12 and "data-reorder" in page
    assert client.post("/habits/reorder", data={"ids": [3, 1, 2]}).status_code == 204
    names = client.get("/day/2026-09-27").text
    assert names.index("Run") < names.index("Workout") < names.index("Food")
    # Mixing categories, unknown ids and duplicates are rejected.
    assert client.post("/habits/reorder", data={"ids": [1, 6]}).status_code == 400
    assert client.post("/habits/reorder", data={"ids": [1, 999]}).status_code == 400
    assert client.post("/habits/reorder", data={"ids": [1, 1]}).status_code == 400
    assert client.post("/habits/reorder").status_code == 422


def test_row_highlight(client):
    assert 'class="hl-button"' in client.get("/day/2026-09-27").text
    assert client.post("/habits/3/highlight", data={"color": "green"}).status_code == 204
    for url in ("/day/2026-09-27", "/month/2026-09"):
        assert 'data-habit-id="3" data-hl="green"' in client.get(url).text.replace(
            ' data-habit-name="Run"', ""
        ), url
    assert client.post("/habits/3/highlight", data={"color": ""}).status_code == 204
    assert (
        'data-hl="green"' not in client.get("/day/2026-09-27").text.split('id="habit-3"')[1][:200]
    )
    assert client.post("/habits/3/highlight", data={"color": "pink"}).status_code == 422
    assert client.post("/habits/999/highlight", data={"color": "blue"}).status_code == 404


def test_note_edit_and_move(client):
    r = client.post("/notes/1", data={"text": "  Practice daily  "})
    assert r.status_code == 200 and "Practice daily" in r.text and 'data-kind="tip" open' in r.text
    assert client.post("/notes/99", data={"text": "x"}).status_code == 404
    assert client.post("/notes/1", data={"text": ""}).status_code == 422

    # Move note 1 from Own Tips to the top of Ideas, and reorder Own Tips.
    r = client.post("/notes/order", data={"tip": [2], "idea": [1, 3, 4]})
    assert r.status_code == 200
    assert 'id="notes-tip" data-kind="tip" open' in r.text and 'aria-label="1 notes"' in r.text
    ideas = r.text.split('id="notes-idea"')[1]
    assert ideas.index("Practice daily") < ideas.index("Try a new recipe")
    assert client.post("/notes/order", data={"tip": [1], "idea": [1]}).status_code == 400
    assert client.post("/notes/order", data={"tip": [999]}).status_code == 400
    assert client.post("/notes/order").status_code == 400
    # Notes can also move into (and out of) the Comfort block.
    r = client.post("/notes/order", data={"comfort": [5, 6, 7, 2]})
    assert r.status_code == 200
    assert r.text.split('id="notes-comfort"')[1].count("data-note-id=") == 4


def test_multi_check_cells_are_one_row(client):
    page = client.get("/month/2026-09").text
    assert 'class="cell multi" id="cell-2-2026-09-01"' in page  # Food, 3 checks
    assert 'class="cell" id="cell-1-2026-09-01"' in page  # Sport, 1 check


def test_category_icon_only_on_timeline_title(client):
    page = client.get("/month/2026-09").text
    assert "<summary>🧱 Base timeline</summary>" in page
    assert '<h3>Base<span class="cat-icon" aria-hidden="true">🧱</span></h3>' in page


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_category_delete(client):
    page = client.get("/habits").text
    assert page.count('class="category-delete"') == 3 and "Move habits to Career" in page
    assert client.post("/categories/2/delete").status_code == 400  # has habits
    assert client.post("/categories/99/delete").status_code == 404
    r = client.post("/categories/2/delete", data={"move_to": 1})
    assert r.status_code == 200 and "Career" not in r.text
    assert "Deep work" in client.get("/day/2026-09-27").text
    client.post("/categories/3/delete", data={"move_to": 1})
    assert 'class="category-delete"' not in client.get("/habits").text  # last category
    assert client.post("/categories/1/delete").status_code == 400


def test_streak_badge(client):
    today = date.today()
    for back in range(1, 5):
        client.post(f"/entries/3/{today - timedelta(days=back)}", data={"count": 1})
    # 4 in a row: no badge yet (it starts at 5).
    assert '<span class="streak" id="streak-3"></span>' in client.get(f"/day/{today}").text
    # Checking today updates the badge: inside the row (day) or out-of-band (month).
    r = client.post(f"/entries/3/{today}", data={"count": 1})
    assert 'id="streak-3" title="5 days in a row · best 5">🔥 5' in r.text
    assert 'id="streak-3" title="5 days' in client.get(f"/month/{today:%Y-%m}").text
    r = client.post(f"/entries/3/{today}", data={"count": 0, "view": "month"})
    assert '<span class="streak" id="streak-3" hx-swap-oob="true"></span>' in r.text


def test_habit_delete(client):
    client.post("/entries/3/2026-09-27", data={"count": 1})
    assert client.get("/habits").text.count('data-confirm="Delete “') == 12
    r = client.post("/habits/3/delete")
    assert r.status_code == 200 and "Run" not in r.text
    assert 'id="habit-3"' not in client.get("/day/2026-09-27").text
    assert client.post("/habits/3/delete").status_code == 404


def test_golden_day(client):
    # A single tap on a checked box still un-checks it straight away.
    client.post("/entries/3/2026-09-27", data={"count": 1})
    r = client.post("/entries/3/2026-09-27", data={"count": 0})
    assert 'class="habit-row" id="habit-3"' in r.text
    # The double-tap request (sent by golden.js) marks it done + gold.
    r = client.post("/entries/3/2026-09-27", data={"count": 1, "golden": "true"})
    assert 'class="habit-row done golden gold-pop" id="habit-3"' in r.text  # pops on the tap
    assert 'data-gold-key="3/2026-09-27" data-gold-count="1"' in r.text
    page = client.get("/day/2026-09-27").text
    assert 'class="habit-row done golden" id="habit-3"' in page  # no pop on page load
    assert "/static/golden.js" in page
    month = client.get("/month/2026-09").text
    assert 'class="cell done golden" id="cell-3-2026-09-27"' in month
    # One tap on a golden day un-checks it.
    r = client.post("/entries/3/2026-09-27", data={"count": 0, "view": "month"})
    assert 'class="cell" id="cell-3-2026-09-27"' in r.text


def test_static_files_are_versioned(client):
    # A content hash in the URL makes browsers load changed CSS/JS after a deploy.
    page = client.get("/day/2026-09-27").text
    assert re.search(r'href="/static/style\.css\?v=[0-9a-f]{10}"', page)
    assert re.search(r'src="/static/golden\.js\?v=[0-9a-f]{10}"', page)
    assert client.get(re.search(r'"(/static/style\.css\?v=\w+)"', page)[1]).status_code == 200


@pytest.mark.parametrize(
    ("url", "active"),
    [
        ("/month/2026-09", "Month"),
        ("/day/2026-09-27", "Today"),
        ("/habits", "Habits"),
        ("/account", "Account"),
    ],
)
def test_phone_tab_bar(client, url, active):
    page = client.get(url).text
    tabbar = page.split('<nav class="tabbar" aria-label="Main">')[1].split("</nav>")[0]
    assert tabbar.count("<a href=") == 4
    assert re.search(rf'aria-current="page">.*?<span>{active}</span>', tabbar, re.S)
    assert tabbar.count('aria-current="page"') == 1


def test_no_tab_bar_when_logged_out(anon_client):
    assert 'class="tabbar"' not in anon_client.get("/login").text
    assert 'class="tabbar"' not in anon_client.get("/join/not-a-token").text


def test_phone_extras(client):
    # Log out moves into Account on phones; the day header has a short date for them.
    assert 'class="mobile-only account-logout"' in client.get("/account").text
    # A past date, so it's never today (that would add " · today"), whatever the clock says.
    day = client.get("/day/2020-01-15").text
    assert '<span class="desktop-only">15 January 2020</span>' in day
    assert '<span class="mobile-only">15 Jan</span>' in day
    today = client.get(f"/day/{date.today()}").text
    assert re.search(r'<span class="mobile-only">\d{2} \w{3} · today</span>', today)


def test_month_grid_knows_its_day_count(client):
    # Phones lay each row out as a grid of --days columns (name on its own line above).
    assert client.get("/month/2026-09").text.count('<table class="month" style="--days: 30">') == 3
    assert '<table class="month" style="--days: 28">' in client.get("/month/2026-02").text


def test_year_page(client):
    client.post("/entries/1/2026-03-02", data={"count": 1, "golden": "true"})
    page = client.get("/year/2026").text
    assert page.count('class="yc') >= 2 * 365  # week strip + small calendars
    assert 'title="Mon 2 Mar · 7% done · ⭐ 1 golden"' in page
    assert all(t in page for t in ("Best streak", "Golden days", "Perfect days", "Average"))
    assert all(t in page for t in ("0%", "1–39%", "40–69%", "70–99%", "100%", "golden day"))
    assert 'href="/year/2025"' in page and 'href="/year/2027"' in page
    # Filter by category; someone else's (or an unknown) category is a 404.
    assert 'aria-current="page">Career' in client.get("/year/2026?category=2").text
    assert client.get("/year/2026?category=99").status_code == 404
    assert "Nothing tracked in 2019 yet" in client.get("/year/2019").text
    assert client.get("/year/1999").status_code == 422
    # Reached from the month page, and the tab bar keeps Month active.
    assert '<a href="/year/2026">← 2026</a>' in client.get("/month/2026-09").text
    assert re.search(r'aria-current="page">.*?<span>Month</span>', page, re.S)


def test_short_addresses_and_manifest(client, anon_client):
    assert (
        client.get("/today", follow_redirects=False).headers["location"] == f"/day/{date.today()}"
    )
    assert (
        client.get("/year", follow_redirects=False).headers["location"]
        == f"/year/{date.today().year}"
    )
    client.post("/logout")
    r = anon_client.get("/manifest.webmanifest")  # public: fetched without the session
    assert r.status_code == 200 and r.headers["content-type"].startswith(
        "application/manifest+json"
    )
    m = r.json()
    assert m["start_url"] == "/today" and m["display"] == "standalone"
    assert [s["url"] for s in m["shortcuts"]] == ["/today", "/year"]
    for icon in m["icons"]:
        assert anon_client.get(icon["src"]).status_code == 200
    assert '<link rel="manifest" href="/manifest.webmanifest">' in anon_client.get("/login").text
