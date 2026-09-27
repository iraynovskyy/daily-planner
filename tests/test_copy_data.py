from datetime import date

import pytest
from sqlmodel import Session, SQLModel

from app import copy_data, services
from app.db import make_engine


def test_copy_keeps_rows_and_ids(tmp_path):
    source = make_engine(f"sqlite:///{tmp_path / 'source.db'}")
    target = make_engine(f"sqlite:///{tmp_path / 'target.db'}")
    SQLModel.metadata.create_all(source)
    SQLModel.metadata.create_all(target)
    with Session(source) as s:
        services.seed_default_habits(s)
        habit = services.list_habits(s)[3]
        services.set_count(s, habit.id, date(2026, 9, 27), 2)
        habit_id = habit.id

    expected = copy_data.counts(source)
    assert copy_data.copy(source, target, replace=False) == expected
    with Session(target) as s:
        [item] = [i for i in services.get_day(s, date(2026, 9, 27)) if i.habit.id == habit_id]
        assert item.entry.count_done == 2

    with pytest.raises(SystemExit, match="not empty"):
        copy_data.copy(source, target, replace=False)
    assert copy_data.copy(source, target, replace=True) == expected
