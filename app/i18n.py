"""Interface languages: English (the source text) and Ukrainian.

Templates write the English text and call `_("…")`; the Ukrainian comes from `UK` below, and a
text missing there simply stays English. Placeholders use str.format: `_("{n} habits", n=3)`.
Dates get their own helpers because Ukrainian needs the genitive month ("1 жовтня").
A user's choice is stored on the user and kept in the session as `lang`.
"""

from datetime import date

from starlette.requests import Request

from app.auth import MIN_PASSWORD_LENGTH

LANGUAGES = {"en": "English", "uk": "Українська"}
DEFAULT = "en"


def lang_of(request: Request) -> str:
    """The session's language, else a browser asking for Ukrainian gets it, else English."""
    lang = request.session.get("lang") if "session" in request.scope else None
    if lang in LANGUAGES:
        return lang
    accepted = request.headers.get("accept-language", "").lower()
    return "uk" if accepted.startswith("uk") else DEFAULT


def gettext(lang: str, text: str, /, **values: object) -> str:
    out = UK.get(text, text) if lang == "uk" else text
    return out.format(**values) if values else out


# --- dates ------------------------------------------------------------------------------------

_EN_DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
_UK_DAYS = ["Понеділок", "Вівторок", "Середа", "Четвер", "П'ятниця", "Субота", "Неділя"]
_UK_DAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Нд"]
_EN_MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]  # fmt: skip
_UK_MONTHS = [
    "Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень",
    "Липень", "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень",
]  # fmt: skip
_UK_MONTHS_OF = [  # genitive: "1 жовтня"
    "січня", "лютого", "березня", "квітня", "травня", "червня",
    "липня", "серпня", "вересня", "жовтня", "листопада", "грудня",
]  # fmt: skip
_UK_MONTHS_SHORT = [
    "січ", "лют", "бер", "квіт", "трав", "черв", "лип", "серп", "вер", "жовт", "лист", "груд",
]  # fmt: skip


def weekday(d: date, lang: str, short: bool = False) -> str:
    if lang == "uk":
        return (_UK_DAYS_SHORT if short else _UK_DAYS)[d.weekday()]
    name = _EN_DAYS[d.weekday()]
    return name[:3] if short else name


def month_name(month: int, lang: str, short: bool = False) -> str:
    """Nominative month name ("October" / "Жовтень"), for titles."""
    if lang == "uk":
        return _UK_MONTHS_SHORT[month - 1].capitalize() if short else _UK_MONTHS[month - 1]
    name = _EN_MONTHS[month - 1]
    return name[:3] if short else name


def fmt_date(d: date, style: str, lang: str) -> str:
    """Dates as the pages show them:
    full        01 October 2026      · 1 жовтня 2026
    short       01 Oct               · 1 жовт
    month_year  October 2026         · Жовтень 2026
    day_month   Thu 1 Oct            · Чт 1 жовт
    long        Thursday 1 October   · Четвер, 1 жовтня
    title       Thu, 01 Oct 2026     · Чт, 1 жовтня 2026
    """
    m = d.month - 1
    if lang == "uk":
        return {
            "full": f"{d.day} {_UK_MONTHS_OF[m]} {d.year}",
            "short": f"{d.day} {_UK_MONTHS_SHORT[m]}",
            "month_year": f"{_UK_MONTHS[m]} {d.year}",
            "day_month": f"{_UK_DAYS_SHORT[d.weekday()]} {d.day} {_UK_MONTHS_SHORT[m]}",
            "long": f"{_UK_DAYS[d.weekday()]}, {d.day} {_UK_MONTHS_OF[m]}",
            "title": f"{_UK_DAYS_SHORT[d.weekday()]}, {d.day} {_UK_MONTHS_OF[m]} {d.year}",
        }[style]
    return {
        "full": d.strftime("%d %B %Y"),
        "short": d.strftime("%d %b"),
        "month_year": d.strftime("%B %Y"),
        "day_month": f"{d:%a} {d.day} {d:%b}",
        "long": f"{d:%A} {d.day} {d:%B}",
        "title": d.strftime("%a, %d %b %Y"),
    }[style]


# --- Ukrainian --------------------------------------------------------------------------------
# Informal "ти", as most Ukrainian apps; no gendered verbs; counts as "label: {n}" so no plural
# forms are needed ("днів: 269" reads right for any number).

_MIN = MIN_PASSWORD_LENGTH

UK: dict[str, str] = {
    # navigation and common words
    "Year": "Рік",
    "Month": "Місяць",
    "Today": "Сьогодні",
    "Habits": "Звички",
    "Account": "Акаунт",
    "Log in": "Увійти",
    "Log out": "Вийти",
    "Main": "Головне меню",
    "Language": "Мова",
    "Switch light / dark theme": "Перемкнути світлу / темну тему",
    "Light / dark": "Світла / темна",
    "Save": "Зберегти",
    "Edit": "Змінити",
    "Close": "Закрити",
    "Cancel": "Скасувати",
    "Delete": "Видалити",
    "Add": "Додати",
    "Copy": "Копіювати",
    "Copied ✓": "Скопійовано ✓",
    "today": "сьогодні",
    "optional": "необов'язкова",
    "inactive": "вимкнена",
    "golden": "золотий",
    "times": "разів",
    # day and month pages
    "Overall · ": "Загалом · ",
    "{n}% done": "{n}% виконано",
    "No habits yet.": "Звичок ще немає.",
    "Add some": "Додай кілька",
    "Habit": "Звичка",
    "Done": "Виконано",
    "Highlight": "Колір",
    "Drag to reorder": "Перетягни, щоб змінити порядок",
    "Move {name}: drag, or focus and press ↑/↓": "Перемістити «{name}»: перетягни або вибери й натисни ↑/↓",
    "Double-tap for a golden day ★": "Подвійний тап — золотий день ★",
    "{n} days in a row · best {best}": "Днів поспіль: {n} · рекорд: {best}",
    "{name} timeline": "{name}: графік",
    "All {name}": "{name}: усе",
    "Toggle lines": "Показати чи сховати лінії",
    "{name}: daily completion for {month}. Use the arrow keys to step through the days.": (
        "{name}: виконання по днях, {month}. Стрілками можна переходити між днями."
    ),
    # highlight colours
    "Highlight row": "Виділити рядок кольором",
    "Highlight colour": "Колір рядка",
    "Highlight colour for {name}": "Колір рядка для «{name}»",
    "No highlight": "Без кольору",
    "Blue": "Синій",
    "Green": "Зелений",
    "Amber": "Бурштиновий",
    "Rose": "Рожевий",
    "Violet": "Фіолетовий",
    # notes
    "Own Tips (to Grow)": "Власні поради (для росту)",
    "Ideas (to Grow)": "Ідеї (для росту)",
    "Comfort (Life)": "Затишок (життя)",
    "{n} notes": "Нотаток: {n}",
    "Nothing here yet.": "Тут поки порожньо.",
    "Add to {title}…": "Додати в «{title}»…",
    "New note for {title}": "Нова нотатка в «{title}»",
    "Add note": "Додати нотатку",
    "Edit note": "Редагувати нотатку",
    "Edit note: {text}": "Редагувати нотатку: {text}",
    "Delete note: {text}": "Видалити нотатку: {text}",
    "Delete this note?": "Видалити цю нотатку?",
    "Double-click to edit": "Двічі клацни, щоб редагувати",
    "Drag to reorder or move to another block": "Перетягни, щоб змінити порядок або перенести в інший блок",
    "Move note: drag, or focus and press ↑/↓ (←/→ to another block)": (
        "Перемістити нотатку: перетягни або вибери й натисни ↑/↓ (←/→ — в інший блок)"
    ),
    # timeline and rings (page scripts)
    "Show all": "Показати всі",
    "Hide all": "Сховати всі",
    "Show every habit's line": "Показати лінію кожної звички",
    "Keep only the overall line": "Залишити лише загальну лінію",
    "Chart style": "Вигляд графіка",
    "Trend": "Тренд",
    "Daily": "По днях",
    "7-day average: the direction you're heading": "Середнє за 7 днів: куди ти рухаєшся",
    "Each day's exact value": "Точне значення кожного дня",
    "7-day average": "середнє за 7 днів",
    "that day {pct}% · {done}/{target}": "того дня {pct}% · {done}/{target}",
    "week {pct}%": "тиждень {pct}%",
    "No ticks yet this month": "Цього місяця ще немає галочок",
    "The trend starts on day 3 — see Daily": "Тренд починається з 3-го дня — дивись «По днях»",
    "No progress to show yet": "Поки нічого показати",
    "Month to date": "Від початку місяця",
    "The rings fill in as you tick.": "Кола заповнюються, коли ставиш галочки.",
    # year page
    "at a glance": "одним поглядом",
    "Category": "Категорія",
    "All": "Усі",
    "Focus": "Фокус",
    "Only the habits you picked": "Лише вибрані тобою звички",
    "Choose habits · {n} picked": "Вибрати звички · вибрано: {n}",
    "Pick the habits you're working on now, one or many, to follow just them here.": (
        "Вибери звички, над якими працюєш зараз — одну чи кілька, — щоб стежити лише за ними."
    ),
    "No habits in Focus yet. Pick a few above and their year shows up here.": (
        "У фокусі ще немає звичок. Вибери кілька вище — і тут з'явиться їхній рік."
    ),
    "Perfect days": "Ідеальні дні",
    "every habit done": "усі звички виконано",
    "Average": "Середнє",
    "over {n} tracked days": "відстежено днів: {n}",
    "Every day of {year}": "Кожен день {year} року",
    "Mon": "Пн",
    "Wed": "Ср",
    "Fri": "Пт",
    "What the colours mean": "Що означають кольори",
    "golden day": "золотий день",
    "not tracked": "не відстежувалось",
    "nothing ticked yet": "ще нічого не відмічено",
    "{n} golden": "золотих: {n}",
    "A day's shade is how much of it you did, like the “Done” row of a month. Tap a day to open it.": (
        "Відтінок дня показує, скільки з нього виконано, — як рядок «Виконано» в місяці. "
        "Торкнись дня, щоб відкрити його."
    ),
    "Most consistent habits": "Найстабільніші звички",
    "In Focus": "У фокусі",
    "Show all {n} habits": "Показати всі ({n})",
    "Show top 3": "Показати топ-3",
    "Nothing tracked in {year} yet.": "У {year} році ще нічого не відмічено.",
    # habits page
    "These appear on every day's checklist, grouped by category. Drag ⠿ to reorder, tap Edit to "
    "change one. Deactivating keeps past history; optional habits don't count towards progress.": (
        "Ці звички з'являються в щоденному чек-листі, згруповані за категоріями. Перетягни ⠿, "
        "щоб змінити порядок, натисни «Змінити», щоб редагувати. Вимкнення зберігає історію; "
        "необов'язкові звички не впливають на прогрес."
    ),
    "Icon (an emoji)": "Іконка (емодзі)",
    "Icon: any emoji, or empty for none": "Іконка: будь-яке емодзі або порожньо — без іконки",
    "Category name": "Назва категорії",
    "Delete the “{name}” category?": "Видалити категорію «{name}»?",
    "Its {n} habit(s) and their history will move to the chosen category.": (
        "Її звички (кількість: {n}) разом з історією перейдуть у вибрану категорію."
    ),
    "Move its habits to": "Куди перенести звички",
    "Move habits to {name}": "Перенести звички в «{name}»",
    "Name": "Назва",
    "Times a day": "Разів на день",
    "Unit": "Одиниця",
    "e.g. min": "напр. хв",
    "Optional": "Необов'язкова",
    "Deactivate": "Вимкнути",
    "Activate": "Увімкнути",
    "Delete “{name}” and all its history for good? (Deactivate hides it but keeps the history.)": (
        "Видалити «{name}» разом з усією історією назавжди? "
        "(Вимкнення ховає звичку, але зберігає історію.)"
    ),
    "No habits in this category yet.": "У цій категорії ще немає звичок.",
    "Add habit": "Додати звичку",
    "Add category": "Додати категорію",
    "e.g. Read 20 pages": "напр. Прочитати 20 сторінок",
    "e.g. Health": "напр. Здоров'я",
    # account
    "Logged in as": "Вхід виконано як",
    "Your categories, habits, checks and notes are yours only.": (
        "Твої категорії, звички, галочки й нотатки бачиш лише ти."
    ),
    "Invite a friend": "Запросити друга",
    "Create a link and send it to a friend: they choose their own username and password and "
    "start with a fresh example set of categories and habits. Each link works once and expires "
    "after {n} days.": (
        "Створи посилання й надішли другові: він сам вибере ім'я користувача й пароль і почне "
        "з нового прикладу категорій і звичок. Кожне посилання спрацьовує один раз і діє {n} днів."
    ),
    "New invite link": "Нове запрошення",
    "copy it now, it won't be shown again:": "скопіюй зараз, більше його не покажуть:",
    "Invite link": "Посилання-запрошення",
    "Create invite link": "Створити запрошення",
    "Open invites": "Активні запрошення",
    "Created {created} · expires {expires}": "Створено {created} · діє до {expires}",
    "Revoke": "Відкликати",
    "Password": "Пароль",
    "Password changed.": "Пароль змінено.",
    "Change password": "Змінити пароль",
    "Current password": "Поточний пароль",
    "New password": "Новий пароль",
    "Repeat new password": "Повтори новий пароль",
    "at least {n} characters": "щонайменше {n} символів",
    "Your data": "Твої дані",
    "Every ticked habit by day — date, category, habit, ticks done of the target, golden — in a "
    "CSV file that opens in Excel or Google Sheets.": (
        "Кожна відмічена звичка по днях — дата, категорія, звичка, виконано з цілі, золото — "
        "у файлі CSV, що відкривається в Excel чи Google Таблицях."
    ),
    "Download my data (CSV)": "Завантажити мої дані (CSV)",
    # login and joining
    "Username": "Ім'я користувача",
    "No user yet. Create one in a terminal:": "Ще немає користувача. Створи його в терміналі:",
    "Join": "Приєднатися",
    "Join Daily Planner": "Приєднатися до Daily Planner",
    "This invite link is invalid, expired or already used.": (
        "Це запрошення недійсне, прострочене або вже використане."
    ),
    "Ask the person who sent it for a new one.": "Попроси нове в того, хто його надіслав.",
    "if you already have an account.": "якщо в тебе вже є акаунт.",
    "You were invited. Pick a username and password; you'll start with a few example "
    "categories and habits that you can change or delete.": (
        "Тебе запросили. Вибери ім'я користувача й пароль — почнеш із кількох прикладів "
        "категорій і звичок, які можна змінити чи видалити."
    ),
    "Repeat password": "Повтори пароль",
    "Create account": "Створити акаунт",
    # the header's Must list
    "Must": "Треба",
    "Must-do list": "Що треба зробити",
    "Something you must do…": "Що треба зробити…",
    "New must-do": "Нова справа",
    "Mark done: {text}": "Позначити виконаним: {text}",
    "Mark not done: {text}": "Повернути до невиконаних: {text}",
    "Edit: {text}": "Змінити: {text}",
    "Delete: {text}": "Видалити: {text}",
    "Nothing you must do. Add it above when something comes up.": (
        "Нічого обов'язкового. Додай угорі, коли щось з'явиться."
    ),
    # messages from the server
    "Wrong username or password.": "Неправильне ім'я користувача або пароль.",
    "Too many failed attempts. Try again in {n} min.": (
        "Забагато невдалих спроб. Спробуй знову за {n} хв."
    ),
    "Too many wrong passwords. Try again in {n} min.": (
        "Забагато неправильних паролів. Спробуй знову за {n} хв."
    ),
    "Passwords don't match.": "Паролі не збігаються.",
    "The new passwords don't match.": "Нові паролі не збігаються.",
    "Username must not be empty.": "Ім'я користувача не може бути порожнім.",
    f"Password must be at least {_MIN} characters.": f"Пароль має бути щонайменше {_MIN} символів.",
    "That username is already taken.": "Таке ім'я користувача вже зайняте.",
    "The current password isn't right.": "Поточний пароль неправильний.",
    f"The new password must be at least {_MIN} characters.": (
        f"Новий пароль має бути щонайменше {_MIN} символів."
    ),
    "The new password is the same as the current one.": "Новий пароль такий самий, як поточний.",
}

# Texts the page scripts show (timeline, rings, notes, small inline scripts): sent to the page.
JS_TEXTS = (
    "Show all",
    "Hide all",
    "Show every habit's line",
    "Keep only the overall line",
    "Chart style",
    "Trend",
    "Daily",
    "7-day average: the direction you're heading",
    "Each day's exact value",
    "7-day average",
    "that day {pct}% · {done}/{target}",
    "week {pct}%",
    "No ticks yet this month",
    "The trend starts on day 3 — see Daily",
    "No progress to show yet",
    "Month to date",
    "The rings fill in as you tick.",
    "optional",
    "Edit note",
    "Close",
    "Copied ✓",
    "Edit",
)
