from sqlalchemy.orm import Session
from database.models import User, ChatSession, FileContext, MessageBuffer
from constants import DEFAULT_MODEL, SEND_MODE_IMMEDIATE

# User Operations
def get_user(db: Session, user_id: int):
    return db.query(User).filter(User.id == user_id).first()

def create_user(db: Session, user_id: int):
    db_user = User(id=user_id)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

def get_or_create_user(db: Session, user_id: int):
    user = get_user(db, user_id)
    if not user:
        user = create_user(db, user_id)
    return user

def update_user_model(db: Session, user_id: int, model: str):
    user = get_or_create_user(db, user_id)
    user.current_model = model
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
def add_file_context(db: Session, user_id: int, filename: str, mime_type: str, data: bytes, caption: str = None):
    # Ensure user exists
    get_or_create_user(db, user_id)
    file_ctx = FileContext(
        user_id=user_id,
        filename=filename,
        mime_type=mime_type,
        data=data,
        caption=caption
    )
    db.add(file_ctx)
    db.commit()
    db.refresh(file_ctx)
    return file_ctx

def get_file_contexts(db: Session, user_id: int):
    return db.query(FileContext).filter(FileContext.user_id == user_id).all()

def clear_file_contexts(db: Session, user_id: int):
    db.query(FileContext).filter(FileContext.user_id == user_id).delete()
    db.commit()

# Message Buffer Operations
def add_to_buffer(db: Session, user_id: int, item_type: str, content: str = None, blob_data: bytes = None, filename: str = None, mime_type: str = None):
    get_or_create_user(db, user_id)
    item = MessageBuffer(
        user_id=user_id,
        item_type=item_type,
        content=content,
        blob_data=blob_data,
        filename=filename,
        mime_type=mime_type
    )
    db.add(item)
    db.commit()
    return item

def get_buffer(db: Session, user_id: int):
    return db.query(MessageBuffer).filter(MessageBuffer.user_id == user_id).all()

def clear_buffer(db: Session, user_id: int):
    db.query(MessageBuffer).filter(MessageBuffer.user_id == user_id).delete()
    db.commit()
