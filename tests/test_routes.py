import json
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
    assert "<summary>🗿 Base timeline</summary>" in page
    assert '<h3>Base<span class="cat-icon" aria-hidden="true">🗿</span></h3>' in page


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
        ("/year/2026", "Year"),
        ("/habits", "Habits"),
        ("/account", "Account"),
    ],
)
def test_phone_tab_bar(client, url, active):
    page = client.get(url).text
    tabbar = page.split('<nav class="tabbar" aria-label="Main">')[1].split("</nav>")[0]
    assert tabbar.count("<a href=") == 5
    assert [t for t in re.findall(r"<span>(\w+)</span>", tabbar)] == [
        "Year",
        "Month",
        "Today",
        "Habits",
        "Account",
    ]
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
    assert "Perfect days" in page and "Average" in page
    # A calm page: facts about the process, no streak or gold counters (gold stays as dots).
    assert "Best streak" not in page and "Golden days" not in page and "🔥" not in page
    assert all(t in page for t in ("0%", "1–39%", "40–69%", "70–99%", "100%", "golden day"))
    assert 'href="/year/2025?view=all"' in page and 'href="/year/2027?view=all"' in page
    # Filter by category; someone else's (or an unknown) category is a 404.
    assert 'aria-current="page">Career' in client.get("/year/2026?category=2").text
    assert client.get("/year/2026?category=99").status_code == 404
    assert "Nothing tracked in 2019 yet" in client.get("/year/2019").text
    assert client.get("/year/1999").status_code == 422
    # Reached from the month page (and the Year tab, which is active here).
    assert '<a href="/year/2026">← 2026</a>' in client.get("/month/2026-09").text
    assert re.search(r'aria-current="page">.*?<span>Year</span>', page, re.S)


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


def test_year_focus_view(client):
    page = client.get("/year/2026").text  # nothing picked yet: opens on All
    assert page.index(">All<") < page.index(">Focus<") < page.index(">Base<")  # All · Focus · Base…
    assert 'href="/year/2026?view=all" aria-current="page">All' in page
    empty = client.get("/year/2026?focus=1").text
    assert '<details class="focus-pick" open>' in empty and "No habits in Focus yet" in empty
    r = client.post("/habits/focus", data={"year": 2026, "ids": [1, 6]}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/year/2026?focus=1"
    picked = client.get("/year/2026?focus=1").text
    assert "Choose habits · 2 picked" in picked and '<details class="focus-pick bottom">' in picked
    # Picked once, rarely changed: the panel sits under the grid, not above it.
    assert picked.index('class="year-grid"') < picked.index('class="focus-pick bottom"')
    assert empty.index('class="focus-pick"') < empty.index("No habits in Focus yet")
    assert 'aria-current="page" title="Only the habits you picked">Focus' in picked
    assert 'href="/year/2025?focus=1"' in picked  # year arrows stay in Focus
    # Once something is picked, the page opens on Focus; All stays one tap away.
    assert 'class="focus-chip" aria-current="page"' in client.get("/year/2026").text
    all_view = client.get("/year/2026?view=all").text
    # In All, the Focus habits (1 and 6) carry the gold dot; in Focus itself they don't need it.
    for habit in (1, 2, 6):
        client.post(f"/entries/{habit}/2026-09-27", data={"count": 1})
    all_view = client.get("/year/2026?view=all").text
    assert all_view.count(' in-focus"') == 2
    assert "in-focus" not in client.get("/year/2026?focus=1").text
    assert 'aria-current="page">All' in all_view and 'href="/year/2025?view=all"' in all_view
    assert client.post("/habits/focus", data={"year": 2026, "ids": [999]}).status_code == 400


def test_category_icon_can_be_changed(client):
    assert 'name="icon" value="🗿"' in client.get("/habits").text
    client.post("/categories/2", data={"name": "Career", "icon": " 🧗 ", "with_icon": "true"})
    assert (
        '<h3>Career<span class="cat-icon" aria-hidden="true">🧗</span></h3>'
        in client.get("/day/2026-09-27").text
    )
    client.post(
        "/categories/2", data={"name": "Career", "icon": "", "with_icon": "true"}
    )  # cleared
    assert "<h3>Career</h3>" in client.get("/day/2026-09-27").text
    client.post("/categories/1", data={"name": "Basics"})  # no icon field: icon kept
    assert (
        '<h3>Basics<span class="cat-icon" aria-hidden="true">🗿</span></h3>'
        in client.get("/day/2026-09-27").text
    )


def test_zoom_links_between_year_month_and_day(client):
    month = client.get("/month/2026-09").text
    assert '<a href="/year/2026">← 2026</a>' in month and '<a href="/today">Today →</a>' in month
    this_year = date.today().year
    year = client.get(f"/year/{this_year}").text
    assert f'<a href="/month/{date.today():%Y-%m}">{date.today():%B %Y} →</a>' in year
    assert '<a href="/month/2019-12">December 2019 →</a>' in client.get("/year/2019").text
    assert '<a href="/month/2099-01">January 2099 →</a>' in client.get("/year/2099").text
    assert '<a href="/month/2026-09">← September 2026</a>' in client.get("/day/2026-09-27").text


def test_export_csv(client):
    client.post("/entries/2/2026-09-26", data={"count": 2})
    client.post("/entries/1/2026-09-27", data={"count": 1, "golden": "true"})
    r = client.get("/account/export.csv")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert 'attachment; filename="daily-planner-tester-' in r.headers["content-disposition"]
    lines = r.content.decode("utf-8-sig").splitlines()
    assert lines == [
        "date,category,habit,done,target,golden",
        "2026-09-26,Base,Food,2,3,",
        "2026-09-27,Base,Workout,1,1,yes",
    ]
    assert r.content.startswith("﻿".encode())  # BOM: Excel reads the names right


# --- Ukrainian ------------------------------------------------------------------------------------


def _english_texts():
    """Every text the pages and scripts show (what `_()` and `t()` are called with)."""
    import glob

    texts = set()
    for path in glob.glob("app/templates/**/*.html", recursive=True):
        src = open(path, encoding="utf-8").read()
        texts |= {m.group(2) for m in re.finditer(r"""(?<![\w.])_\(\s*(["'])(.*?)\1""", src)}
        texts |= {m.group(2) for m in re.finditer(r"""(?<![\w.])t\(\s*(["'])(.*?)\1""", src)}
    for path in glob.glob("app/static/*.js"):
        src = open(path, encoding="utf-8").read()
        texts |= {m.group(2) for m in re.finditer(r"""(?<![\w.])t\(\s*(["'])(.*?)\1""", src)}
    return texts


def test_every_text_has_a_ukrainian_translation():
    from app import i18n, services

    texts = _english_texts() | set(services.NOTE_KINDS.values())
    texts |= {c.capitalize() for c in services.HIGHLIGHTS}
    missing = sorted(t for t in texts if t not in i18n.UK)
    assert missing == []
    assert set(i18n.JS_TEXTS) <= set(i18n.UK)


def test_language_switch(client, session):
    from app.models import User

    page = client.get("/day/2026-10-01").text
    assert '<html lang="en">' in page and "Thursday" in page and "01 October 2026" in page
    r = client.post(
        "/language", data={"lang": "uk", "next": "/day/2026-10-01"}, follow_redirects=False
    )
    assert r.status_code == 303 and r.headers["location"] == "/day/2026-10-01"
    page = client.get("/day/2026-10-01").text
    assert '<html lang="uk">' in page and "Четвер" in page and "1 жовтня 2026" in page
    assert ">Звички</a>" in page and ">Сьогодні</span>" in page and "Загалом · 0% виконано" in page
    assert "<h2>Жовтень</h2>" in client.get("/month/2026-10").text
    account = client.get("/account").text
    assert 'value="uk" lang="uk"\n            aria-pressed="true">Українська' in account
    # Saved on the user: it survives logging out and back in.
    assert session.get(User, 1).language == "uk"
    client.post("/logout")
    assert "Увійти" in client.get("/login").text
    client.cookies.clear()
    assert ">Log in</h2>" in client.get("/login").text.replace("<h2>", ">")
    client.post("/login", data={"username": "tester", "password": "correct horse battery"})
    assert "Четвер" in client.get("/day/2026-10-01").text
    assert client.post("/language", data={"lang": "fr"}).status_code == 400


def test_browser_language_and_messages(anon_client):
    uk = {"Accept-Language": "uk-UA,uk;q=0.9,en;q=0.8"}
    page = anon_client.get("/login", headers=uk).text.replace("&#39;", "'")  # HTML-escaped '
    assert "Ім'я користувача" in page
    r = anon_client.post("/login", data={"username": "x", "password": "y"}, headers=uk)
    assert "Неправильне ім'я користувача або пароль." in r.text.replace("&#39;", "'")
    assert "Username" in anon_client.get("/login").text  # no preference: English


def test_month_timeline_gets_the_days_before_the_month(client):
    client.post("/entries/1/2026-09-30", data={"count": 1})
    page = client.get("/month/2026-10").text
    lead = json.loads(re.search(r"data-lead-in='([^']*)'", page)[1])  # Base: habits 1-5
    assert set(lead) == {"1", "2", "3", "4", "5"} and len(lead["1"]) == 6
    assert lead["1"][-1] == [1, 1]
    assert page.count("data-lead-in=") == 3  # one per category


def test_must_dropdown(client):
    page = client.get("/day/2026-10-01").text
    assert 'hx-get="/must" hx-trigger="load"' in page and "must.js" in page
    closed = client.get("/must").text
    assert '<details class="must" id="must">' in closed and "Nothing you must do" in closed
    r = client.post("/must", data={"text": "Book the doctor"})
    assert '<details class="must" id="must" open>' in r.text and "Book the doctor" in r.text
    item = re.search(r'data-must-id="(\d+)"', r.text)[1]
    r = client.post(f"/must/{item}/done", data={"done": "true"})
    assert 'class="done"' in r.text and "Mark not done: Book the doctor" in r.text
    assert "Send it" in client.post(f"/must/{item}", data={"text": "Send it"}).text
    assert client.post("/must/order", data={"ids": [item]}).status_code == 204
    assert "Nothing you must do" in client.post(f"/must/{item}/delete").text
    assert client.post(f"/must/{item}/delete").status_code == 404
    assert client.post("/must", data={"text": ""}).status_code == 422
