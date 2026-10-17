from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import Cookie, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db import models
from app.db.session import get_db
from app.domain.clock import parse_as_of


def get_session_id(
    fieldsense_session: Annotated[str | None, Cookie(alias="fieldsense_session")] = None,
    x_session_id: Annotated[str | None, Header(alias="X-Session-Id")] = None,
) -> str:
    return fieldsense_session or x_session_id or secrets.token_hex(16)


def get_current_user(
    db: Annotated[Session, Depends(get_db)],
    session_id: Annotated[str, Depends(get_session_id)],
    x_user_id: Annotated[str | None, Header(alias="X-User-Id")] = None,
) -> tuple[str, int, str]:
    """Returns (user_id, session_generation, session_id)."""
    sess = db.get(models.DemoSession, session_id)
    if x_user_id:
        if sess is None:
            sess = models.DemoSession(id=session_id, user_id=x_user_id, session_generation=1)
            db.add(sess)
        else:
            if sess.user_id != x_user_id:
                sess.user_id = x_user_id
                sess.session_generation += 1
        db.commit()
        return x_user_id, sess.session_generation, session_id
    if sess and sess.user_id:
        return sess.user_id, sess.session_generation, session_id
    raise HTTPException(status_code=401, detail="No demo user selected")


def get_clock(x_analysis_clock: Annotated[str | None, Header(alias="X-Analysis-Clock")] = None):
    return parse_as_of(x_analysis_clock)
