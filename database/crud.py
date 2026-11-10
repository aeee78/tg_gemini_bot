from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func
from sqlalchemy.orm import Session
from database.models import User, ChatSession, FileContext, MessageBuffer
from database.model_catalog import get_default_model


# User Operations
def get_user(db: Session, user_id: int):
    return db.query(User).filter(User.id == user_id).first()


def create_user(db: Session, user_id: int):
    db_user = User(id=user_id, current_model=get_default_model(db))
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def get_or_create_user(db: Session, user_id: int):
    user = get_user(db, user_id)
    if not user:
        user = create_user(db, user_id)
    return user


def record_user_activity(db: Session, telegram_user):
    """Refresh Telegram profile and UTC activity; date only new registrations."""
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    user = get_user(db, telegram_user.id)
    if user is None:
        user = User(id=telegram_user.id, registered_at=now, current_model=get_default_model(db))
        db.add(user)
    for field in ("first_name", "last_name", "username", "language_code"):
        setattr(user, field, getattr(telegram_user, field, None))
    user.last_active_at = now
    db.commit()
    db.refresh(user)
    return user


def has_pro_access(db: Session, user_id: int):
    user = get_user(db, user_id)
    return bool(user and user.pro_access)


def set_user_pro_access(db: Session, user_id: int, enabled: bool):
    user = get_or_create_user(db, user_id)
    user.pro_access = enabled
    db.commit()
    db.refresh(user)
    return user


def update_user_model(db: Session, user_id: int, model: str):
    user = get_or_create_user(db, user_id)
    user.current_model = model
    db.commit()
    db.refresh(user)
    return user


def switch_user_model(db: Session, user_id: int, model: str, history_json: str):
    """Commit model and portable history together, keeping files and buffer."""
    user = get_user(db, user_id)
    user.current_model = model
    chat = get_chat_session(db, user_id)
    if chat is None:
        db.add(ChatSession(user_id=user_id, history_json=history_json))
    else:
        chat.history_json = history_json
    db.commit()
    db.refresh(user)
    return user


def update_user_send_mode(db: Session, user_id: int, mode: str):
    user = get_or_create_user(db, user_id)
    user.send_mode = mode
    db.commit()
    db.refresh(user)
    return user


def update_user_search_enabled(db: Session, user_id: int, enabled: bool):
    user = get_or_create_user(db, user_id)
    user.search_enabled = enabled
    db.commit()
    db.refresh(user)
    return user


# Chat Session Operations
def get_chat_session(db: Session, user_id: int):
    return db.query(ChatSession).filter(ChatSession.user_id == user_id).first()


def save_chat_session(db: Session, user_id: int, history_json: str):
    session = get_chat_session(db, user_id)
    if not session:
        session = ChatSession(user_id=user_id, history_json=history_json)
        db.add(session)
    else:
        session.history_json = history_json
    db.commit()
    db.refresh(session)
    return session


def clear_chat_session(db: Session, user_id: int):
    session = get_chat_session(db, user_id)
    if session:
        db.delete(session)
        db.commit()


# File Context Operations
def add_file_context(
    db: Session,
    user_id: int,
    filename: str,
    mime_type: str,
    data: bytes,
    caption: str = None,
):
    # Ensure user exists
    get_or_create_user(db, user_id)
    file_ctx = FileContext(
        user_id=user_id,
        filename=filename,
        mime_type=mime_type,
        data=data,
        caption=caption,
    )
    db.add(file_ctx)
    db.commit()
    db.refresh(file_ctx)
    return file_ctx


def get_file_contexts(db: Session, user_id: int):
    return (
        db.query(FileContext)
        .filter(FileContext.user_id == user_id)
        .order_by(FileContext.id)
        .all()
    )


def clear_file_contexts(db: Session, user_id: int):
    db.query(FileContext).filter(FileContext.user_id == user_id).delete()
    db.commit()


# Message Buffer Operations
def add_to_buffer(
    db: Session,
    user_id: int,
    item_type: str,
    content: str = None,
    blob_data: bytes = None,
    filename: str = None,
    mime_type: str = None,
):
    get_or_create_user(db, user_id)
    item = MessageBuffer(
        user_id=user_id,
        item_type=item_type,
        content=content,
        blob_data=blob_data,
        filename=filename,
        mime_type=mime_type,
    )
    db.add(item)
    db.commit()
    return item


def get_buffer(db: Session, user_id: int):
    return (
        db.query(MessageBuffer)
        .filter(MessageBuffer.user_id == user_id)
        .order_by(MessageBuffer.id)
        .all()
    )


def clear_buffer(db: Session, user_id: int):
    db.query(MessageBuffer).filter(MessageBuffer.user_id == user_id).delete()
    db.commit()


# Admin queries

def get_admin_users(db: Session, only_pro=False, offset=0, limit=8):
    query = db.query(User)
    if only_pro:
        query = query.filter(User.pro_access.is_(True))
    total = query.count()
    users = query.order_by(User.last_active_at.desc(), User.id).offset(min(offset, total)).limit(limit).all()
    return total, users


def find_admin_users(db: Session, query: str):
    query = query.strip().removeprefix("@")
    if query.isdecimal():
        # Telegram IDs fit signed SQLite BIGINT.
        if len(query) > 19 or int(query) > 2**63 - 1:
            return []
        user = get_user(db, int(query))
        return [user] if user else []
    return db.query(User).filter(func.lower(User.username) == query.lower()).order_by(User.id).limit(20).all()


def get_admin_statistics(db: Session):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    total, pro, day, week, month = db.query(
        func.count(User.id),
        func.sum(case((User.pro_access.is_(True), 1), else_=0)),
        *(func.sum(case((User.last_active_at >= now - timedelta(days=days), 1), else_=0))
          for days in (1, 7, 30)),
    ).one()
    return {
        "total": total, "pro": pro or 0,
        "day": day or 0, "week": week or 0, "month": month or 0,
        "models": db.query(User.current_model, func.count(User.id)).group_by(User.current_model).order_by(User.current_model).all(),
    }
