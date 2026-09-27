from datetime import date, timedelta

import pytest
from sqlmodel import Session, SQLModel, create_engine, select

from app import services
from app.models import DailyEntry

DAY = date(2026, 9, 27)


def test_seed_is_idempotent(session):
    services.seed_default_habits(session)
    assert [h.name for h in services.list_habits(session)] == [
        "Workout",
        "Food",
        "Run",
        "AM / PM routine",
        "Bed by 11pm",
        "Learning videos",
        "Side project",
        "Deep work",
        "Ship something small",
        "Reading",
        "Tidy up",
        "No sugar",
    ]
    assert [c.name for c in services.list_categories(session)] == [
        "Base",
        "Career",
        "Good habits",
    ]


def test_get_day_creates_entries_lazily(session):
    items = services.get_day(session, DAY)
    assert len(items) == 12
    assert all(i.entry.count_done == 0 for i in items)
    assert services.progress(items) == 0


def test_set_count_is_clamped(session):
    food = services.list_habits(session)[1]
    assert services.set_count(session, food.id, DAY, 99).entry.count_done == 3
    assert services.set_count(session, food.id, DAY, -5).entry.count_done == 0


def test_days_are_independent(session):
    sport = services.list_habits(session)[0]
    services.set_count(session, sport.id, DAY, 1)
    other = services.get_day(session, date(2026, 9, 28))
    assert other[0].entry.count_done == 0


def test_progress(session):
    habits = services.list_habits(session)
    services.set_count(session, habits[0].id, DAY, 1)  # 1/1
    services.set_count(session, habits[1].id, DAY, 2)  # 2/3
    assert services.progress(services.get_day(session, DAY)) == 20  # 3 of 15


def test_deactivate_keeps_history(session):
    sport = services.list_habits(session)[0]
    services.set_count(session, sport.id, DAY, 1)
    services.set_active(session, sport.id, False)

    past = services.get_day(session, DAY)
    assert any(i.habit.id == sport.id and i.done for i in past)
    future = services.get_day(session, date(2026, 10, 1))
    assert all(i.habit.id != sport.id for i in future)


def test_create_habit_goes_to_end_of_first_category(session):
    new = services.create_habit(session, "  Read  ", 1, "")
    assert new.name == "Read" and new.unit is None
    names = [h.name for h in services.list_habits(session)]
    assert names[4:7] == ["Bed by 11pm", "Read", "Learning videos"]


def test_get_month_grid_is_read_only(session):
    food = services.list_habits(session)[1]
    services.set_count(session, food.id, DAY, 2)

    habits, days = services.get_month(session, 2026, 9)
    assert len(habits) == 12 and len(days) == 30
    assert days[26].day == DAY and days[26].items[1].entry.count_done == 2
    assert days[26].progress == 13  # 2 of 15
    assert days[0].progress == 0
    assert len(session.exec(select(DailyEntry)).all()) == 1  # viewing stores nothing


def test_get_month_shows_inactive_habit_only_with_history(session):
    sport = services.list_habits(session)[0]
    services.set_count(session, sport.id, DAY, 1)
    services.set_active(session, sport.id, False)

    assert sport in services.get_month(session, 2026, 9)[0]
    assert sport not in services.get_month(session, 2026, 10)[0]


def test_optional_habit_is_listed_last_and_ignored_by_progress(session):
    habits = services.list_habits(session)
    no_sugar = habits[-1]
    assert no_sugar.name == "No sugar" and no_sugar.optional

    services.set_count(session, no_sugar.id, DAY, 1)
    assert services.progress(services.get_day(session, DAY)) == 0
    for h in habits[:-1]:
        services.set_count(session, h.id, DAY, h.target_count)
    services.set_count(session, no_sugar.id, DAY, 0)
    assert services.progress(services.get_day(session, DAY)) == 100  # 100% without it


def test_optional_habit_stays_below_required_ones(session):
    good = services.list_categories(session)[-1]
    new = services.create_habit(session, "Walk", 1, None, category_id=good.id)
    good_ids = [h.id for h in services.list_habits(session) if h.category_id == good.id]
    assert services.reorder_habits(session, good_ids[-1:] + good_ids[:-1])  # No sugar to top
    assert services.list_habits(session)[-1].name == "No sugar"
    assert services.list_habits(session)[-2].id == new.id


def test_categories_have_their_own_progress(session):
    food = services.list_habits(session)[1]
    services.set_count(session, food.id, DAY, 3)

    day = services.day_by_category(session, services.get_day(session, DAY))
    assert [(g.category.name, g.progress) for g in day] == [
        ("Base", 38),  # 3 of 8
        ("Career", 0),
        ("Good habits", 0),
    ]
    habits, days = services.get_month(session, 2026, 9)
    month = services.month_by_category(session, habits, days)
    assert [len(g.habits) for g in month] == [5, 4, 3]
    assert month[0].days[26].progress == 38 and month[1].days[26].progress == 0


def test_reorder_inside_category(session):
    habits = services.list_habits(session)
    base = [h.id for h in habits if h.category_id == habits[0].category_id]
    assert services.reorder_habits(session, base[::-1])
    names = [h.name for h in services.list_habits(session)]
    assert names[:6] == [
        "Bed by 11pm",
        "AM / PM routine",
        "Run",
        "Food",
        "Workout",
        "Learning videos",  # other categories untouched
    ]


def test_reorder_subset_keeps_hidden_habits_in_place(session):
    sport, food, run = services.list_habits(session)[:3]
    services.set_active(session, food.id, False)  # e.g. not shown on a future day
    assert services.reorder_habits(session, [run.id, sport.id])
    assert [h.name for h in services.list_habits(session)][:3] == ["Run", "Food", "Workout"]


def test_reorder_rejects_bad_input(session):
    habits = services.list_habits(session)
    assert not services.reorder_habits(session, [])
    assert not services.reorder_habits(session, [habits[0].id, habits[-1].id])  # 2 categories
    assert not services.reorder_habits(session, [habits[0].id, 999])
    assert not services.reorder_habits(session, [habits[0].id, habits[0].id])


def test_change_habit_category(session):
    sport = services.list_habits(session)[0]
    good = services.list_categories(session)[-1]
    services.update_habit(session, sport.id, "Workout", 1, "10 min", category_id=good.id)
    assert services.list_habits(session)[-2].name == "Workout"  # above optional No sugar
    assert services.update_habit(session, sport.id, "Workout", 1, None, category_id=99) is None


def test_default_note_blocks(session):
    blocks = services.note_blocks(session)
    assert [(kind, title, len(notes)) for kind, title, notes in blocks] == [
        ("tip", "Own Tips (to Grow)", 2),
        ("idea", "Ideas (to Grow)", 2),
        ("comfort", "Comfort (Life)", 3),
    ]
    note = services.create_note(session, "tip", "  Sleep 8h  ")
    assert note.text == "Sleep 8h" and len(services.list_notes(session, "tip")) == 3
    services.delete_note(session, note.id)
    assert len(services.list_notes(session, "tip")) == 2


def test_notes_reorder_and_move_between_blocks(session):
    tips = services.list_notes(session, "tip")
    ideas = services.list_notes(session, "idea")
    assert services.reorder_notes(
        session, {"tip": [tips[1].id], "idea": [tips[0].id] + [n.id for n in ideas]}
    )
    assert [n.id for n in services.list_notes(session, "tip")] == [tips[1].id]
    assert [n.id for n in services.list_notes(session, "idea")][0] == tips[0].id
    # New notes go to the end of their block.
    new = services.create_note(session, "idea", "Last")
    assert services.list_notes(session, "idea")[-1].id == new.id
    assert not services.reorder_notes(session, {"other": [new.id]})
    assert not services.reorder_notes(session, {})


def test_seed_reads_the_given_file(tmp_path):
    seed = tmp_path / "seed.toml"
    seed.write_text(
        '[[category]]\nname = "Solo"\nicon = "⭐"\n'
        'habits = [{ name = "Stretch", target = 2, unit = "min", optional = true }]\n'
        '[[note]]\nkind = "idea"\ntext = "Hello"\n'
    )
    engine = create_engine("sqlite://")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        services.seed_default_habits(s, seed)
        [cat] = services.list_categories(s)
        [habit] = services.list_habits(s)
        assert (cat.name, cat.icon) == ("Solo", "⭐")
        assert (habit.name, habit.target_count, habit.unit, habit.optional) == (
            "Stretch",
            2,
            "min",
            True,
        )
        assert [n.text for n in services.list_notes(s, "idea")] == ["Hello"]


def test_streaks(session):
    food = services.list_habits(session)[1]  # 3 checks a day
    for back in (0, 1, 2, 5, 6, 7, 8):
        services.set_count(session, 1, DAY - timedelta(days=back), 1)
    services.set_count(session, food.id, DAY - timedelta(days=1), 3)
    services.set_count(session, food.id, DAY, 2)  # not all 3: today doesn't count yet
    streaks = services.streaks(session, DAY)
    assert streaks[1] == services.Streak(current=3, best=4)
    # An unfinished today keeps yesterday's run alive...
    assert streaks[food.id] == services.Streak(current=1, best=1)
    # ...but a missed yesterday ends it; later days are ignored.
    assert services.streaks(session, DAY + timedelta(days=2))[1].current == 0
    assert services.streaks(session, DAY - timedelta(days=5))[1] == services.Streak(4, 4)
    assert services.streaks(session, DAY, food.id) == {food.id: streaks[food.id]}
    assert 3 not in streaks  # never done


def test_delete_category(session):
    base, career, good = services.list_categories(session)
    services.set_count(session, 6, DAY, 1)  # Learning videos (Career) has history
    empty = services.create_category(session, "Empty")
    assert services.delete_category(session, empty.id) is not None

    with pytest.raises(ValueError):
        services.delete_category(session, career.id)  # has habits, no target
    with pytest.raises(ValueError):
        services.delete_category(session, career.id, career.id)
    assert services.delete_category(session, career.id, 99) is None
    assert services.delete_category(session, 99) is None

    services.delete_category(session, career.id, base.id)
    names = [h.name for h in services.list_habits(session) if h.category_id == base.id]
    assert names[-4:] == ["Learning videos", "Side project", "Deep work", "Ship something small"]
    assert [c.name for c in services.list_categories(session)] == ["Base", "Good habits"]
    assert services.get_day(session, DAY)[5].entry.count_done == 1  # history kept

    services.delete_category(session, good.id, base.id)
    with pytest.raises(ValueError):
        services.delete_category(session, base.id)  # last one stays


def test_delete_habit_removes_history(session):
    services.set_count(session, 1, DAY, 1)
    assert services.delete_habit(session, 1) is not None
    assert services.delete_habit(session, 1) is None
    assert 1 not in {h.id for h in services.list_habits(session)}
    assert session.exec(select(DailyEntry).where(DailyEntry.habit_id == 1)).first() is None
