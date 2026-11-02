import os
import unittest
from unittest import mock

os.environ.setdefault("DATABASE_URL", "sqlite://")

from sqlalchemy import create_engine, func, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.models import Base, User  # noqa: E402
from app.services import telegram_auth  # noqa: E402
from app.services.telegram_auth import TelegramAccount, get_current_user  # noqa: E402


class NewUserRaceTests(unittest.TestCase):
    """Параллельные первые запросы нового пользователя не должны давать 500."""

    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, autoflush=False)
        self.account = TelegramAccount(telegram_user_id=142203444, username="u", first_name="U")

    def test_lost_race_returns_existing_user(self):
        # Параллельный запрос уже создал пользователя...
        other = self.Session()
        other.add(User(telegram_user_id=142203444, username="u", first_name="U"))
        other.commit()
        winner_id = other.scalar(select(User.id))
        other.close()

        # ...а этот запрос успел проверить «нет такого» до коммита соседа.
        db = self.Session()
        real_scalar = db.scalar
        calls = {"n": 0}

        def scalar(stmt, *a, **kw):
            calls["n"] += 1
            return None if calls["n"] == 1 else real_scalar(stmt, *a, **kw)

        with mock.patch.object(telegram_auth, "validate_telegram_init_data", return_value=self.account), \
                mock.patch.object(db, "scalar", side_effect=scalar):
            user = get_current_user("init", db)

        self.assertEqual(user.id, winner_id)
        self.assertEqual(self.Session().scalar(select(func.count(User.id))), 1)

    def test_new_user_created(self):
        db = self.Session()
        with mock.patch.object(telegram_auth, "validate_telegram_init_data", return_value=self.account):
            user = get_current_user("init", db)
        self.assertEqual(user.telegram_user_id, 142203444)


if __name__ == "__main__":
    unittest.main()
