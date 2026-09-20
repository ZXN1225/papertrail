import hashlib
import hmac
import re
import secrets
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import delete, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.profiles.contracts import ProfileInput, ProfileSnapshot
from app.profiles.models import limits, profiles, revisions, sessions


class DomainError(Exception):
    def __init__(self, status, code, message, details=None):
        self.status, self.code, self.message = status, code, message
        self.details = details or {}


def invisible():
    return DomainError(404, "NOT_FOUND", "需求不存在或会话已过期。")


class ProfileService:
    def __init__(self, engine, settings):
        self.engine, self.settings = engine, settings
        self.secret = settings.session_signing_secret.get_secret_value().encode()

    def mac(self, value):
        return hmac.new(self.secret, value.encode(), hashlib.sha256).hexdigest()

    def identity(self, cookie):
        if not cookie or len(cookie) > 200 or not self.secret:
            return None
        raw, _, signature = cookie.partition(".")
        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", raw):
            return None
        if not hmac.compare_digest(signature.encode(), self.mac("identity:" + raw).encode()):
            return None
        return hashlib.sha256(raw.encode()).hexdigest()

    def csrf(self, cookie):
        return self.mac("csrf:" + cookie)

    def authenticate(self, conn, cookie, lock=False):
        digest = self.identity(cookie)
        query = select(sessions).where(sessions.c.token_hash == digest)
        if lock:
            query = query.with_for_update()
        row = conn.execute(query).mappings().first() if digest else None
        if row is None or row["expires_at"] <= datetime.now(UTC):
            raise invisible()
        return row

    def snapshot(self, conn, profile_id, revision=None):
        query = select(revisions).where(revisions.c.profile_id == profile_id)
        if revision is not None:
            query = query.where(revisions.c.revision == revision)
        row = conn.execute(query.order_by(revisions.c.revision.desc()).limit(1)).mappings().first()
        if not row:
            raise invisible()
        return ProfileSnapshot(
            id=profile_id, **{k: row[k] for k in ("revision", "profile", "origins", "created_at")}
        )

    def state(self, conn, session, cookie):
        profile_id = conn.scalar(
            select(profiles.c.id).where(profiles.c.session_id == session["id"])
        )
        return {
            "expires_at": session["expires_at"],
            "csrf_token": self.csrf(cookie),
            "profile": self.snapshot(conn, profile_id) if profile_id else None,
        }

    def current(self, cookie):
        with self.engine.begin() as conn:
            session = self.authenticate(conn, cookie, lock=True)
            return self.state(conn, session, cookie)

    def create_session(self, conn):
        raw = secrets.token_urlsafe(32)
        cookie = raw + "." + self.mac("identity:" + raw)
        session = {
            "id": uuid4(),
            "token_hash": self.identity(cookie),
            "expires_at": datetime.now(UTC) + timedelta(hours=24),
        }
        conn.execute(insert(sessions).values(**session))
        return self.state(conn, session, cookie), cookie

    def bootstrap(self, cookie):
        with self.engine.begin() as conn:
            if self.identity(cookie):
                try:
                    session = self.authenticate(conn, cookie, lock=True)
                    return self.state(conn, session, cookie), None
                except DomainError:
                    pass
            return self.create_session(conn)

    def reset(self, cookie):
        with self.engine.begin() as conn:
            session = self.authenticate(conn, cookie, lock=True)
            conn.execute(delete(sessions).where(sessions.c.id == session["id"]))
            return self.create_session(conn)

    def remove(self, cookie):
        with self.engine.begin() as conn:
            session = self.authenticate(conn, cookie, lock=True)
            conn.execute(delete(sessions).where(sessions.c.id == session["id"]))

    def read(self, cookie, profile_id, revision=None):
        with self.engine.begin() as conn:
            session = self.authenticate(conn, cookie, lock=True)
            self.owned(conn, session, profile_id)
            return self.snapshot(conn, profile_id, revision)

    def owned(self, conn, session, profile_id):
        row = (
            conn.execute(
                select(profiles).where(
                    profiles.c.id == profile_id, profiles.c.session_id == session["id"]
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise invisible()
        return row

    def save(self, cookie, data, profile_id=None, expected_revision=None):
        with self.engine.begin() as conn:
            session = self.authenticate(conn, cookie, lock=True)
            now = datetime.now(UTC)
            explicit = data.model_fields_set
            origins = {}
            if profile_id is None:
                if conn.scalar(select(profiles.c.id).where(profiles.c.session_id == session["id"])):
                    raise DomainError(409, "PROFILE_EXISTS", "已有保存的需求，请重新读取后修改。")
                profile_id, revision = uuid4(), 1
                validated = data
                conn.execute(
                    insert(profiles).values(
                        id=profile_id, session_id=session["id"], revision=revision
                    )
                )
            else:
                current = self.owned(conn, session, profile_id)
                if current["revision"] != expected_revision:
                    raise DomainError(
                        409,
                        "REVISION_CONFLICT",
                        "另一页面已修改需求，请先读取最新版本。",
                        {"current_revision": str(current["revision"])},
                    )
                old = self.snapshot(conn, profile_id)
                merged = old.profile.model_dump(mode="json")
                changes = data.model_dump(mode="json", exclude_unset=True)
                if not changes:
                    raise DomainError(422, "INVALID_PROFILE", "请提供需要修改的字段。")
                origins = {k: v.model_dump(mode="json") for k, v in old.origins.items()}
                if "mode" in changes and changes["mode"] != merged["mode"]:
                    for name in ("pc_constraints", "laptop_constraints", "component_category"):
                        merged[name] = None
                        origins.pop(name, None)
                    merged["budget_scope"] = [
                        {"pc": "tower", "laptop": "laptop", "component": "component"}.get(
                            changes["mode"], "tower"
                        )
                    ]
                    origins.pop("budget_scope", None)
                # Nested constraints are merged so changing one field never drops another.
                for name in ("pc_constraints", "laptop_constraints"):
                    if isinstance(changes.get(name), dict):
                        changes[name] = {**(merged.get(name) or {}), **changes[name]}
                merged.update(changes)
                try:
                    validated = ProfileInput.model_validate(merged)
                except ValidationError as exc:
                    raise DomainError(
                        422, "INVALID_PROFILE", "需求字段无效，请检查预算与设备类型。"
                    ) from exc
                revision = current["revision"] + 1
                conn.execute(
                    update(profiles)
                    .where(profiles.c.id == profile_id, profiles.c.revision == expected_revision)
                    .values(revision=revision)
                )
            for name in validated.model_dump():
                if name in explicit or name not in origins:
                    chosen = name in explicit
                    origins[name] = {
                        "origin": "explicit" if chosen else "default",
                        "source": "form" if chosen else "system",
                        "message_id": None,
                        "confirmed_at": now.isoformat() if chosen else None,
                    }
            conn.execute(
                insert(revisions).values(
                    profile_id=profile_id,
                    revision=revision,
                    profile=validated.model_dump(mode="json"),
                    origins=origins,
                    created_at=now,
                )
            )
            return self.snapshot(conn, profile_id, revision)

    def rate_limit(self, key, maximum):
        now = datetime.now(UTC).timestamp()
        window = int(now // 60)
        statement = pg_insert(limits).values(key=self.mac("rate:" + key), window=window, count=1)
        statement = statement.on_conflict_do_update(
            index_elements=[limits.c.key, limits.c.window], set_={"count": limits.c.count + 1}
        ).returning(limits.c.count)
        # Commit even rejected attempts. All instances share this counter; no raw IPs stored.
        with self.engine.begin() as conn:
            count = conn.scalar(statement)
            conn.execute(delete(limits).where(limits.c.window < window - 2))
        if count > maximum:
            raise DomainError(
                429,
                "RATE_LIMITED",
                "操作过于频繁，请稍后再试。",
                {"retry_after": str(60 - int(now % 60))},
            )

    def cleanup(self):
        with self.engine.begin() as conn:
            result = conn.execute(
                delete(sessions).where(sessions.c.expires_at <= datetime.now(UTC))
            )
            return result.rowcount
