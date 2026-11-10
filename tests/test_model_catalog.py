import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from constants import DEFAULT_MODEL, FLASH_MODEL, IMAGE_MODEL
from database import db, model_catalog as catalog
from database.models import ModelConfig, User


def google_model(name, actions=("generateContent",)):
    return SimpleNamespace(name="models/" + name, display_name=name,
                           supported_actions=list(actions))


class TestModelCatalog(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        self.addCleanup(self.engine.dispose)
        db.Base.metadata.create_all(self.engine)
        self.sessions = sessionmaker(bind=self.engine, autoflush=False)

    def test_seed_preserves_current_access_and_runs_once(self):
        with self.sessions() as session:
            self.assertEqual(catalog.get_default_model(session), DEFAULT_MODEL)
            self.assertTrue(catalog.can_use_model(session, DEFAULT_MODEL))
            self.assertFalse(catalog.can_use_model(session, FLASH_MODEL))
            self.assertTrue(catalog.can_use_model(session, FLASH_MODEL, True))
            self.assertFalse(catalog.can_use_model(session, IMAGE_MODEL))
            flash = catalog.get_model(session, FLASH_MODEL)
            catalog.set_model_access(session, flash.id, "disabled")
        with self.sessions() as session:
            catalog.ensure_catalog(session)
            self.assertFalse(catalog.can_use_model(session, FLASH_MODEL, True))
            self.assertEqual(len(catalog.list_models(session)), 3)

    def test_default_and_policy_changes_apply_in_a_new_session(self):
        with self.sessions() as session:
            flash = catalog.get_model(session, FLASH_MODEL)
            catalog.set_model_access(session, flash.id, "public")
            catalog.set_default_model(session, flash.id)
            old_default = catalog.get_model(session, DEFAULT_MODEL)
            catalog.set_model_access(session, old_default.id, "disabled")
        with self.sessions() as session:
            self.assertEqual(catalog.get_default_model(session), FLASH_MODEL)
            for saved in (DEFAULT_MODEL, "retired", IMAGE_MODEL):
                self.assertEqual(catalog.resolve_model(session, saved), FLASH_MODEL)
            self.assertEqual(catalog.resolve_model(session, IMAGE_MODEL, True), IMAGE_MODEL)

    def test_default_must_remain_public(self):
        with self.sessions() as session:
            default = catalog.get_model(session, DEFAULT_MODEL)
            for access in ("disabled", "whitelist"):
                with self.subTest(access=access), self.assertRaises(ValueError):
                    catalog.set_model_access(session, default.id, access)
            flash = catalog.get_model(session, FLASH_MODEL)
            with self.assertRaises(ValueError):
                catalog.set_default_model(session, flash.id)
            with self.assertRaises(ValueError):
                catalog.set_model_access(session, flash.id, "arbitrary")
            with self.assertRaises(ValueError):
                catalog.set_default_model(session, 999)
            self.assertTrue(catalog.can_use_model(session, DEFAULT_MODEL))
            self.assertEqual(catalog.get_default_model(session), DEFAULT_MODEL)

    def test_stale_sessions_cannot_disable_new_default(self):
        with self.sessions() as stale, self.sessions() as current:
            flash = catalog.get_model(stale, FLASH_MODEL)
            catalog.set_model_access(stale, flash.id, "public")
            # Keep both objects in the identity map as a real Telegram callback can.
            settings = stale.get(catalog.ModelCatalogSettings, 1)
            catalog.set_default_model(current, flash.id)
            self.assertEqual(settings.default_model, DEFAULT_MODEL)
            with self.assertRaises(ValueError):
                catalog.set_model_access(stale, flash.id, "disabled")
            self.assertTrue(catalog.can_use_model(stale, catalog.get_default_model(stale)))

    def test_concurrent_default_and_disable_preserve_public_default(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = create_engine(f"sqlite:///{Path(directory) / 'concurrent.db'}",
                                   connect_args={"check_same_thread": False, "timeout": 5})
            self.addCleanup(engine.dispose)
            db.Base.metadata.create_all(engine)
            sessions = sessionmaker(bind=engine)
            with sessions() as session:
                flash = catalog.get_model(session, FLASH_MODEL)
                model_id = flash.id
                catalog.set_model_access(session, model_id, "public")
            start = Barrier(2)

            def change(make_default):
                with sessions() as session:
                    # Seed the identity map before either concurrent write.
                    catalog.get_model(session, FLASH_MODEL)
                    catalog.get_default_model(session)
                    start.wait(timeout=5)
                    try:
                        if make_default:
                            catalog.set_default_model(session, model_id)
                        else:
                            catalog.set_model_access(session, model_id, "disabled")
                        return "ok"
                    except ValueError:
                        return "rejected"

            with ThreadPoolExecutor(max_workers=2) as executor:
                results = list(executor.map(change, (True, False)))
            self.assertCountEqual(results, ["ok", "rejected"])
            with sessions() as session:
                self.assertTrue(catalog.can_use_model(session, catalog.get_default_model(session)))

    def test_refresh_filters_specialized_models_and_disables_new_entries(self):
        items = [google_model("gemini-4-pro"), google_model("gemini-4-flash-image"),
                 google_model("gemini-nano-banana-2.1"), google_model("nano-banana-pro-preview"),
                 google_model("text-embedding-004", ("embedContent",)),
                 google_model("gemini-embedding-001", ("embedContent",)),
                 google_model("gemini-4-pro-tts"), google_model("gemini-4-live"),
                 google_model("gemini-4-native-audio"), google_model("gemini-4-computer-use"),
                 google_model("gemini-4-robotics"), google_model("gemini-3.5-transcribe"), google_model("veo-3"),
                 google_model("gemini-4-no-actions", ())]
        with self.sessions() as session:
            result = catalog.sync_catalog(session, items)
            self.assertEqual(result, {"added": 4, "updated": 0, "missing": 3, "total": 4})
            self.assertIsNotNone(catalog.get_last_sync(session))
            self.assertEqual(len(catalog.list_models(session)), 7)
            for name in ("gemini-4-pro", "gemini-4-flash-image", "gemini-nano-banana-2.1", "nano-banana-pro-preview"):
                self.assertFalse(catalog.can_use_model(session, name, True))
            self.assertTrue(catalog.get_model(session, "gemini-4-flash-image").supports_images)
            self.assertTrue(catalog.get_model(session, "gemini-nano-banana-2.1").supports_images)
            self.assertTrue(catalog.get_model(session, "nano-banana-pro-preview").supports_images)
            # The missing flag never retires the existing policy automatically.
            self.assertFalse(catalog.get_model(session, DEFAULT_MODEL).available)
            self.assertTrue(catalog.can_use_model(session, DEFAULT_MODEL))

    def test_refresh_preserves_admin_policy_default_and_model_ids(self):
        with self.sessions() as session:
            flash = catalog.get_model(session, FLASH_MODEL)
            flash_id = flash.id
            catalog.set_model_access(session, flash_id, "public")
            catalog.set_default_model(session, flash_id)
            catalog.sync_catalog(session, [google_model(FLASH_MODEL)])
            catalog.sync_catalog(session, [google_model(FLASH_MODEL)])
            flash = catalog.get_model(session, FLASH_MODEL)
            self.assertEqual(flash.id, flash_id)
            self.assertEqual(flash.access, "public")
            self.assertEqual(catalog.get_default_model(session), FLASH_MODEL)
            self.assertEqual(len(catalog.list_models(session)), 3)

    def test_failed_page_and_empty_response_leave_catalog_untouched(self):
        def failed_page():
            yield google_model("gemini-4-new")
            raise RuntimeError("Google page failed")
        with self.sessions() as session:
            catalog.ensure_catalog(session)
            with self.assertRaises(RuntimeError):
                catalog.sync_catalog(session, failed_page())
            with self.assertRaises(ValueError):
                catalog.sync_catalog(session, [])
            self.assertEqual(len(catalog.list_models(session)), 3)
            self.assertIsNone(catalog.get_last_sync(session))
            self.assertTrue(all(row.available for row in catalog.list_models(session)))

    def test_raw_google_rest_metadata_and_duplicate_entries(self):
        with self.sessions() as session:
            item = {"name": "models/gemini-4-pro", "displayName": "Gemini Pro",
                    "supportedGenerationMethods": ["generateContent", "countTokens"]}
            result = catalog.sync_catalog(session, [item, item])
            self.assertEqual(result["added"], 1)
            self.assertEqual(catalog.get_model(session, "gemini-4-pro").display_name, "Gemini Pro")

    def test_existing_database_migrates_without_changing_users_or_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = create_engine(f"sqlite:///{Path(directory) / 'old.db'}")
            self.addCleanup(engine.dispose)
            sessions = sessionmaker(bind=engine)
            with engine.begin() as connection:
                connection.exec_driver_sql("""CREATE TABLE users (
                    id BIGINT PRIMARY KEY, current_model VARCHAR, send_mode VARCHAR,
                    search_enabled BOOLEAN, pro_access BOOLEAN NOT NULL DEFAULT 0)""")
                connection.execute(text("INSERT INTO users VALUES (1, :name, 'manual', 0, 1)"),
                                   {"name": FLASH_MODEL})
            with patch.object(db, "engine", engine):
                db.init_db(Path(directory) / "missing-whitelist.txt")
                with sessions() as session:
                    user = session.get(User, 1)
                    self.assertEqual(user.current_model, FLASH_MODEL)
                    self.assertTrue(user.pro_access)
                    flash = catalog.get_model(session, FLASH_MODEL)
                    catalog.set_model_access(session, flash.id, "public")
                    catalog.set_default_model(session, flash.id)
                db.init_db(Path(directory) / "missing-whitelist.txt")
                with sessions() as session:
                    self.assertEqual(catalog.get_default_model(session), FLASH_MODEL)
                    self.assertEqual(session.query(ModelConfig).count(), 3)


if __name__ == "__main__":
    unittest.main()
