import os
import random
import unittest
from datetime import datetime, timedelta

os.environ.setdefault("DATABASE_URL", "sqlite://")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine, event, select  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db.session import get_db  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402
    Archetype,
    Base,
    Item,
    ItemRarity,
    ListType,
    Product,
    RewardEvent,
    ShadeGroup,
    TrackedItem,
    User,
    UserCharacter,
    UserItem,
)
from app.services.character import (  # noqa: E402
    compute_archetype,
    evaluate_character,
    grant_purchase_reward,
    seed_items,
)
from app.services.telegram_auth import get_current_user  # noqa: E402


def make_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    # pysqlite: корректные SAVEPOINT (рецепт из доков SQLAlchemy).
    @event.listens_for(engine, "connect")
    def _connect(dbapi_connection, _record):
        dbapi_connection.isolation_level = None

    @event.listens_for(engine, "begin")
    def _begin(conn):
        conn.exec_driver_sql("BEGIN")

    Base.metadata.create_all(engine)
    return engine


class ArchetypeTests(unittest.TestCase):
    def test_top_is_type_second_is_accent(self):
        groups = ["goth"] * 5 + ["bold"] * 3 + ["glitter"] * 2
        result = compute_archetype(groups)
        self.assertEqual(result.archetype, Archetype.goth)
        self.assertEqual(result.accent, Archetype.bold)

    def test_chameleon_when_nobody_above_three_of_ten(self):
        groups = ["bold", "bold", "goth", "goth", "nude", "nude", "pastel", "pastel", "glow", "glitter"]
        self.assertEqual(compute_archetype(groups).archetype, Archetype.chameleon)

    def test_four_of_ten_is_enough(self):
        groups = ["glow"] * 4 + ["nude"] * 3 + ["bold"] * 3
        self.assertEqual(compute_archetype(groups).archetype, Archetype.glow)

    def test_ignores_unknown_and_null(self):
        groups = [None] * 8 + ["pastel", "pastel", "nope"]
        result = compute_archetype(groups)
        self.assertEqual(result.archetype, Archetype.pastel)
        self.assertEqual(result.classified, 2)
        # Второго цвета нет — акцент совпадает с типом.
        self.assertEqual(result.accent, Archetype.pastel)

    def test_empty_shelf_is_chameleon(self):
        result = compute_archetype([None, None])
        self.assertEqual(result.archetype, Archetype.chameleon)
        self.assertIsNone(result.accent)

    def test_ties_are_stable_regardless_of_order(self):
        a = compute_archetype(["glitter"] * 4 + ["bold"] * 4 + ["nude"] * 2)
        b = compute_archetype(["nude"] * 2 + ["bold"] * 4 + ["glitter"] * 4)
        self.assertEqual(a.archetype, Archetype.bold)
        self.assertEqual(a.accent, Archetype.glitter)
        self.assertEqual((a.archetype, a.accent), (b.archetype, b.accent))


class RewardTests(unittest.TestCase):
    def setUp(self):
        self.engine = make_engine()
        self.Session = sessionmaker(bind=self.engine, autoflush=False)
        self.db = self.Session()
        seed_items(self.db)
        self.user = User(telegram_user_id=111)
        self.db.add(self.user)
        self.db.commit()
        self._product_seq = 0

    def tearDown(self):
        self.db.close()
        self.engine.dispose()

    def add_tracked(self, list_type, shade=None, created_at=None):
        self._product_seq += 1
        product = Product(
            name=f"p{self._product_seq}",
            canonical_key=f"k{self._product_seq}",
            shade_group=shade,
        )
        self.db.add(product)
        self.db.flush()
        self.db.add(
            TrackedItem(
                user_id=self.user.id,
                product_id=product.id,
                list_type=list_type,
                created_at=created_at or datetime.utcnow(),
            )
        )
        self.db.commit()

    def events(self):
        return self.db.scalars(
            select(RewardEvent).where(RewardEvent.user_id == self.user.id)
        ).all()

    def test_unlock_at_ten_shelf_items_once(self):
        for _ in range(9):
            self.add_tracked(ListType.shelf, ShadeGroup.goth)
        self.assertIsNone(evaluate_character(self.db, self.user).unlocked_at)

        self.add_tracked(ListType.shelf, ShadeGroup.goth)
        character = evaluate_character(self.db, self.user)
        self.assertIsNotNone(character.unlocked_at)
        self.assertEqual(character.archetype, Archetype.goth)

        seed = character.shape_seed
        self.assertIsNotNone(seed)
        self.assertGreater(seed, 0)

        evaluate_character(self.db, self.user)
        again = evaluate_character(self.db, self.user)
        self.assertEqual([e.reward_key for e in self.events()], ["unlock"])
        # Форма закреплена за пользователем и не меняется.
        self.assertEqual(again.shape_seed, seed)

    def test_locked_character_has_no_shape_yet(self):
        self.add_tracked(ListType.shelf, ShadeGroup.bold)
        self.assertIsNone(evaluate_character(self.db, self.user).shape_seed)

    def test_backfills_seed_for_previously_unlocked(self):
        character = evaluate_character(self.db, self.user)
        character.unlocked_at = datetime.utcnow()
        self.db.commit()
        self.assertIsNone(character.shape_seed)
        seed = evaluate_character(self.db, self.user).shape_seed
        self.assertIsNotNone(seed)
        self.assertEqual(evaluate_character(self.db, self.user).shape_seed, seed)

    def test_wishlist_quest_counts_only_after_unlock(self):
        old = datetime.utcnow() - timedelta(days=3)
        for _ in range(7):
            self.add_tracked(ListType.wishlist, created_at=old)
        for _ in range(10):
            self.add_tracked(ListType.shelf, ShadeGroup.bold)

        evaluate_character(self.db, self.user)
        self.assertNotIn("quest:first_item", [e.reward_key for e in self.events()])

        for _ in range(5):
            self.add_tracked(ListType.wishlist, created_at=datetime.utcnow() + timedelta(seconds=1))

        evaluate_character(self.db, self.user)
        evaluate_character(self.db, self.user)

        quest = [e for e in self.events() if e.reward_key == "quest:first_item"]
        self.assertEqual(len(quest), 1)
        self.assertEqual(quest[0].item.code, "clip")
        self.assertEqual(
            self.db.scalar(select(UserItem).where(UserItem.user_id == self.user.id)).item.code,
            "clip",
        )

    def test_purchase_reward_is_idempotent(self):
        first = grant_purchase_reward(self.db, self.user.id, "ORDER-1", rng=random.Random(1))
        again = grant_purchase_reward(self.db, self.user.id, "ORDER-1", rng=random.Random(2))
        self.assertTrue(first.created)
        self.assertFalse(again.created)
        self.assertEqual(first.event.id, again.event.id)
        self.assertEqual(len(self.events()), 1)

    def test_purchase_falls_back_to_evolution_when_rarity_exhausted(self):
        for item in self.db.scalars(select(Item)).all():
            self.db.add(UserItem(user_id=self.user.id, item_id=item.id, source="purchase"))
        self.db.commit()

        result = grant_purchase_reward(self.db, self.user.id, "ORDER-2", rng=random.Random(3))
        self.assertEqual(result.event.kind.value, "evolution")
        character = self.db.scalar(
            select(UserCharacter).where(UserCharacter.user_id == self.user.id)
        )
        self.assertEqual(character.evolution, 1)

    def test_rarity_weights_roughly_match(self):
        from app.services.character import roll_rarity

        rng = random.Random(42)
        rolls = [roll_rarity(rng) for _ in range(20000)]
        common = rolls.count(ItemRarity.common) / len(rolls)
        secret = rolls.count(ItemRarity.secret) / len(rolls)
        self.assertAlmostEqual(common, 0.70, delta=0.02)
        self.assertAlmostEqual(secret, 0.01, delta=0.005)


class CharacterApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = make_engine()
        Session = sessionmaker(bind=self.engine, autoflush=False)
        db = Session()
        seed_items(db)
        user = User(telegram_user_id=222)
        db.add(user)
        db.commit()
        self.user_id = user.id
        db.close()

        def override_db():
            session = Session()
            try:
                yield session
            finally:
                session.close()

        def override_user():
            session = Session()
            try:
                return session.get(User, self.user_id)
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = override_user
        self.Session = Session
        self.client = TestClient(app)

    def tearDown(self):
        app.dependency_overrides.clear()
        self.engine.dispose()

    def test_locked_status_and_unbox_conflict(self):
        data = self.client.get("/api/character").json()
        self.assertEqual(data["status"], "locked")
        self.assertEqual(data["quest"]["code"], "unlock")
        self.assertEqual(len(data["inventory"]), 10)
        self.assertEqual(self.client.post("/api/character/unbox").status_code, 409)

    def test_share_card_roundtrip(self):
        png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
        res = self.client.post(
            "/api/character/share-card",
            files={"file": ("card.png", png, "image/png")},
            headers={"x-forwarded-proto": "https"},
        )
        self.assertEqual(res.status_code, 200)
        url = res.json()["url"]
        self.assertTrue(url.startswith("https://"))
        path = url.split("testserver", 1)[1]
        image = self.client.get(path)
        self.assertEqual(image.status_code, 200)
        self.assertEqual(image.content, png)

        bad = self.client.post(
            "/api/character/share-card",
            files={"file": ("card.png", b"GIF89a", "image/png")},
        )
        self.assertEqual(bad.status_code, 400)

    def test_equip_only_owned_and_one_per_slot(self):
        self.assertEqual(
            self.client.post("/api/character/equip", json={"item_code": "clip"}).status_code,
            404,
        )
        db = self.Session()
        for code in ("clip", "bow"):
            item = db.scalar(select(Item).where(Item.code == code))
            db.add(UserItem(user_id=self.user_id, item_id=item.id, source="purchase"))
        db.commit()
        db.close()

        self.client.post("/api/character/equip", json={"item_code": "clip"})
        data = self.client.post("/api/character/equip", json={"item_code": "bow"}).json()
        self.assertEqual(data["equipped"]["head"], "bow")
        self.assertFalse(next(i for i in data["inventory"] if i["code"] == "clip")["equipped"])

        data = self.client.post(
            "/api/character/equip", json={"item_code": "bow", "equip": False}
        ).json()
        self.assertIsNone(data["equipped"]["head"])


if __name__ == "__main__":
    unittest.main()
