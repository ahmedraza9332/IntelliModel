"""Google Sign-In and session cookie endpoints."""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Response
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token
from pydantic import BaseModel, Field

from auth.db import (
    UserRecord,
    create_session,
    delete_session_by_raw_token,
    get_connection,
    get_user_for_session_token,
    upsert_user_from_google,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

SESSION_COOKIE_NAME = "im_session"


def _google_client_ids() -> list[str]:
    """One or more OAuth client IDs (comma-separated) trusted as JWT `aud`."""
    raw = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "").strip()
    if not raw:
        return []
    return [x.strip() for x in raw.split(",") if x.strip()]


def _cookie_secure() -> bool:
    return os.environ.get("INTELLIMODEL_COOKIE_SECURE", "").lower() in (
        "1",
        "true",
        "yes",
    )


class GoogleAuthRequest(BaseModel):
    """Body from `@react-oauth/google` (field name `credential`)."""

    credential: str = Field(..., min_length=20)


class UserResponse(BaseModel):
    id: int
    email: Optional[str]
    email_verified: bool
    name: Optional[str]
    picture_url: Optional[str]
    created_at: str
    updated_at: str


def _verify_google_credential(token: str) -> dict:
    ids = _google_client_ids()
    if not ids:
        raise HTTPException(
            status_code=503,
            detail="Server is missing GOOGLE_OAUTH_CLIENT_ID — cannot verify Google tokens.",
        )
    request = google_requests.Request()
    for aud in ids:
        try:
            return id_token.verify_oauth2_token(token, request, aud)
        except ValueError:
            continue
    raise HTTPException(
        status_code=401,
        detail="Invalid or expired Google credential.",
    )


@router.post("/google", response_model=UserResponse)
def auth_google(response: Response, body: GoogleAuthRequest) -> UserResponse:
    claims = _verify_google_credential(body.credential)
    sub = claims.get("sub")
    if not sub or not isinstance(sub, str):
        raise HTTPException(status_code=401, detail="Token missing subject (sub).")

    email = claims.get("email")
    if email is not None and not isinstance(email, str):
        email = str(email)

    email_verified = bool(claims.get("email_verified", False))
    name = claims.get("name")
    if name is not None and not isinstance(name, str):
        name = str(name)
    picture = claims.get("picture")
    if picture is not None and not isinstance(picture, str):
        picture = str(picture)

    conn = get_connection()
    try:
        user = upsert_user_from_google(
            conn,
            google_sub=sub,
            email=email,
            email_verified=email_verified,
            name=name,
            picture_url=picture,
        )
        raw_session = create_session(conn, user.id)
    finally:
        conn.close()

    max_age = 60 * 60 * 24 * 30
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=raw_session,
        max_age=max_age,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(),
        path="/",
    )
    return UserResponse(**user.public_dict())


@router.get("/me", response_model=UserResponse)
def auth_me(request: Request) -> UserResponse:
    raw = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw:
        raise HTTPException(status_code=401, detail="Not signed in.")
    conn = get_connection()
    try:
        user = get_user_for_session_token(conn, raw)
    finally:
        conn.close()
    if user is None:
        raise HTTPException(status_code=401, detail="Session expired or invalid.")
    return UserResponse(**user.public_dict())


@router.post("/logout")
def auth_logout(request: Request, response: Response) -> dict:
    raw = request.cookies.get(SESSION_COOKIE_NAME)
    if raw:
        conn = get_connection()
        try:
            delete_session_by_raw_token(conn, raw)
        finally:
            conn.close()
    response.delete_cookie(
        SESSION_COOKIE_NAME,
        path="/",
        samesite="lax",
        secure=_cookie_secure(),
    )
    return {"status": "ok"}


def get_current_user_optional(request: Request) -> Optional[UserRecord]:
    """Dependency helper: return signed-in user or None."""
    raw = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw:
        return None
    conn = get_connection()
    try:
        return get_user_for_session_token(conn, raw)
    finally:
        conn.close()
