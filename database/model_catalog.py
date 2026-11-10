"""Persistent model access policy, independent from Google catalog refreshes."""
from datetime import datetime, timezone
import re

from sqlalchemy import update
from sqlalchemy.dialects.sqlite import insert

from constants import AVAILABLE_MODELS, DEFAULT_MODEL, MODEL_ALIASES, PREMIUM_MODELS
from database.models import ModelCatalogSettings, ModelConfig

ACCESS_LEVELS = frozenset({"public", "whitelist", "admin", "disabled"})


def ensure_catalog(session):
    """Seed the previous hard-coded policy once; never overwrite admin choices."""
    if session.get(ModelCatalogSettings, 1) is not None:
        return
    for name in AVAILABLE_MODELS:
        session.execute(insert(ModelConfig).values(
            name=name, display_name=MODEL_ALIASES.get(name, name),
            access="whitelist" if name in PREMIUM_MODELS else "public",
            available=True, supports_images="-image" in name,
        ).on_conflict_do_nothing(index_elements=["name"]))
    session.execute(insert(ModelCatalogSettings).values(
        id=1, default_model=DEFAULT_MODEL,
    ).on_conflict_do_nothing(index_elements=["id"]))
    session.commit()


def list_models(session, include_disabled=True, is_admin=False):
    ensure_catalog(session)
    query = session.query(ModelConfig)
    if not include_disabled:
        visible = ("public", "whitelist", "admin") if is_admin else ("public", "whitelist")
        query = query.filter(ModelConfig.access.in_(visible))
    return query.order_by(ModelConfig.name).all()


def get_model(session, name):
    ensure_catalog(session)
    return session.query(ModelConfig).filter(ModelConfig.name == name).first()


def get_model_by_id(session, model_id):
    ensure_catalog(session)
    return session.get(ModelConfig, model_id)


def get_default_model(session):
    ensure_catalog(session)
    return session.get(ModelCatalogSettings, 1).default_model


def get_last_sync(session):
    ensure_catalog(session)
    return session.get(ModelCatalogSettings, 1).last_synced_at


def can_use_model(session, name, has_pro_access=False, is_admin=False):
    model = get_model(session, name)
    return bool(model and (model.access == "public" or
                          (model.access == "whitelist" and (has_pro_access or is_admin)) or
                          (model.access == "admin" and is_admin)))


def resolve_model(session, name, has_pro_access=False, is_admin=False):
    return name if can_use_model(session, name, has_pro_access, is_admin) else get_default_model(session)


def _lock_settings(session):
    # Serialize the default/access invariant across concurrent Telegram callbacks.
    # SQLite has no SELECT FOR UPDATE; acquire its write lock before reading.
    session.execute(update(ModelCatalogSettings).where(
        ModelCatalogSettings.id == 1,
    ).values(id=1))
    session.expire_all()


def set_model_access(session, model_id, access):
    if access not in ACCESS_LEVELS:
        raise ValueError("Неизвестный уровень доступа.")
    ensure_catalog(session)
    try:
        _lock_settings(session)
        model = session.get(ModelConfig, model_id)
        if model is None:
            raise ValueError("Модель не найдена. Обнови список.")
        if model.name == get_default_model(session) and access != "public":
            raise ValueError("Сначала выбери другую модель по умолчанию: текущая должна быть доступна всем.")
        model.access = access
        session.commit()
        return model
    except Exception:
        session.rollback()
        raise


def set_default_model(session, model_id):
    ensure_catalog(session)
    try:
        _lock_settings(session)
        model = session.get(ModelConfig, model_id)
        if model is None:
            raise ValueError("Модель не найдена. Обнови список.")
        if model.access != "public":
            raise ValueError("Модель по умолчанию должна быть доступна всем.")
        session.get(ModelCatalogSettings, 1).default_model = model.name
        session.commit()
        return model
    except Exception:
        session.rollback()
        raise


def _field(model, snake, camel=None):
    if isinstance(model, dict):
        return model.get(snake, model.get(camel))
    return getattr(model, snake, None)


def _catalog_entry(model):
    name = _field(model, "name")
    if not isinstance(name, str):
        return None
    name = name.removeprefix("models/")
    # The bot uses Gemini's generateContent chat API; specialized APIs have
    # incompatible request/response contracts even if they appear in models.list.
    if not re.fullmatch(r"(?:gemini-|nano-banana-)[A-Za-z0-9._-]{1,190}", name):
        return None
    if any(part in name.lower() for part in (
        "embedding", "-tts", "-live", "native-audio", "robotics", "computer-use", "-transcribe",
    )):
        return None
    actions = _field(model, "supported_actions", "supportedGenerationMethods") or []
    if not any(isinstance(action, str) and action.replace("_", "").lower() == "generatecontent"
               for action in actions):
        return None
    display_name = _field(model, "display_name", "displayName")
    return {
        "name": name,
        "display_name": display_name[:200] if isinstance(display_name, str) and display_name else name,
        "supports_images": "-image" in name or "nano-banana" in name,
    }


def sync_catalog(session, models):
    """Refresh metadata atomically, preserving access and the selected default.

    Consume all pages before opening a write transaction so a failed later API
    page cannot disable models or leave a partial snapshot. Missing entries stay
    usable according to their existing policy: absence is not proof of retirement.
    """
    entries = {}
    for item in models:
        entry = _catalog_entry(item)
        if entry:
            entries[entry["name"]] = entry
    if not entries:
        raise ValueError("Google не вернул совместимых моделей. Сохранённый список не изменён.")
    ensure_catalog(session)
    try:
        _lock_settings(session)
        existing = {model.name: model for model in session.query(ModelConfig).all()}
        added = 0
        for name, entry in entries.items():
            model = existing.get(name)
            if model is None:
                session.add(ModelConfig(**entry, access="disabled", available=True))
                added += 1
            else:
                model.display_name = entry["display_name"]
                model.supports_images = entry["supports_images"]
                model.available = True
        missing = 0
        for name, model in existing.items():
            if name not in entries:
                model.available = False
                missing += 1
        session.get(ModelCatalogSettings, 1).last_synced_at = datetime.now(timezone.utc).replace(tzinfo=None)
        session.commit()
        return {"added": added, "updated": len(entries) - added, "missing": missing, "total": len(entries)}
    except Exception:
        session.rollback()
        raise
