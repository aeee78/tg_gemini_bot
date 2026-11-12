"""Aggregate recorded Gemini usage with explicit coverage for missing metadata."""
from sqlalchemy import case, func

from database.models import UsageRecord, User

TOKEN_COLUMNS = (
    'prompt_tokens', 'output_tokens', 'thinking_tokens',
    'cached_tokens', 'tool_tokens', 'total_tokens',
)


def aggregate_columns():
    return [
        func.count(UsageRecord.id).label('requests'),
        func.count(func.distinct(UsageRecord.user_id)).label('unique_users'),
        func.sum(case((UsageRecord.success.is_(True), 1), else_=0)).label('successes'),
        func.avg(UsageRecord.duration_seconds).label('duration'),
        *[expression for name in TOKEN_COLUMNS for expression in (
            func.sum(getattr(UsageRecord, name)).label(name),
            func.count(getattr(UsageRecord, name)).label(name + '_known'),
        )],
    ]


def filter_usage(query, since=None, until=None, user_id=None, operation=None):
    if since is not None:
        query = query.filter(UsageRecord.started_at >= since)
    if until is not None:
        query = query.filter(UsageRecord.started_at < until)
    if user_id is not None:
        query = query.filter(UsageRecord.user_id == user_id)
    if operation is not None:
        query = query.filter(UsageRecord.operation == operation)
    return query


def summary(db, since=None, until=None, user_id=None, operation=None):
    row = filter_usage(db.query(*aggregate_columns()), since, until, user_id, operation).one()
    result = dict(row._mapping)
    result['requests'] = result['requests'] or 0
    result['successes'] = result['successes'] or 0
    result['first_recorded_at'] = filter_usage(
        db.query(func.min(UsageRecord.started_at)), operation=operation,
    ).scalar()
    return result


def breakdown(db, group, since=None, until=None, user_id=None, page=0, page_size=8, operation=None):
    dimension = UsageRecord.model if group == 'models' else UsageRecord.user_id
    query = filter_usage(
        db.query(dimension.label('group_id'), *aggregate_columns()), since, until, user_id, operation,
    ).group_by(dimension)
    total_groups = query.count()
    pages = max(1, (total_groups + page_size - 1) // page_size)
    page = min(max(0, page), pages - 1)
    rows = query.order_by(func.count(UsageRecord.id).desc(), dimension).offset(page * page_size).limit(page_size).all()
    results = [dict(row._mapping) for row in rows]
    if group == 'users' and results:
        users = {u.id: u for u in db.query(User).filter(User.id.in_([r['group_id'] for r in results])).all()}
        for result in results:
            user = users.get(result['group_id'])
            name = ' '.join(filter(None, [user.first_name, user.last_name])) if user else ''
            username = f' @{user.username}' if user and user.username else ''
            result['label'] = f'{name}{username}'.strip() or str(result['group_id'])
    return results, page, pages
