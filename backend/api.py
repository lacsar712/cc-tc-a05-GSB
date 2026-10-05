import os
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, g, jsonify, request
from jose import JWTError, jwt
from passlib.context import CryptContext

from sqlalchemy import inspect, text

from claimer import start as start_claimer
from models import (
    Base,
    ConvergenceLog,
    ReleaseFlow,
    SessionLocal,
    WorkZone,
    ZONE_CLOSED,
    ZONE_OPEN,
    ZONE_PENDING,
    engine,
    flow_dict,
    row_dict,
    zone_dict,
)

SECRET = os.environ.get("JWT_SECRET", "tunnelconv-dev-secret")
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

# perms: submit=可报送测缝 / 申请放行；approve=值班长点头权限
USERS = {
    "surveyor": {"perms": ["submit"], "password_hash": pwd.hash("surv123456")},
    "surveyor2": {"perms": ["submit"], "password_hash": pwd.hash("surv234567")},
    "boss": {"perms": ["approve"], "password_hash": pwd.hash("boss123456")},
    "inspector": {"perms": ["approve"], "password_hash": pwd.hash("insp123456")},
}

# 工区固定由专人负责，负责关系不随放行状态改变
SEED_ZONES = (
    ("一号工区", "surveyor"),
    ("二号工区", "surveyor2"),
    ("三号工区", "boss"),
)

app = Flask(__name__)


def ensure_schema():
    """对已存在的旧库幂等补列，避免旧数据卷里 convergence_logs 缺工区列。"""
    inspector = inspect(engine)
    if "convergence_logs" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("convergence_logs")}
        with engine.begin() as conn:
            if "zone_id" not in cols:
                conn.execute(text("ALTER TABLE convergence_logs ADD COLUMN zone_id INTEGER"))
            if "zone_name" not in cols:
                conn.execute(text("ALTER TABLE convergence_logs ADD COLUMN zone_name VARCHAR"))


def seed():
    Base.metadata.create_all(engine)
    ensure_schema()
    db = SessionLocal()
    try:
        if db.query(WorkZone).count() == 0:
            for name, owner in SEED_ZONES:
                db.add(WorkZone(name=name, owner=owner, status=ZONE_CLOSED))
        if db.query(ConvergenceLog).count() == 0:
            now = datetime.now(timezone.utc)
            for chainage, delta, expect in (("K12+180", 1.2, "合格"), ("K18+040", 5.6, "超限")):
                from rules import judge

                verdict, reason = judge(delta)
                assert verdict == expect
                db.add(
                    ConvergenceLog(
                        chainage=chainage,
                        delta_mm=delta,
                        status="done",
                        verdict=verdict,
                        reason=reason,
                        created_by="surveyor",
                        created_at=now,
                        processed_at=now,
                    )
                )
        db.commit()
    finally:
        db.close()


seed()
start_claimer()


def current_user():
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        payload = jwt.decode(auth[7:].strip(), SECRET, algorithms=["HS256"])
    except JWTError:
        return None
    sub = payload.get("sub")
    if sub not in USERS:
        return None
    return {"username": sub, "perms": payload.get("perms", [])}


def require_login(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"detail": "未登录"}), 401
        g.user = user
        return fn(*args, **kwargs)

    return wrapper


def require_perm(perm):
    messages = {
        "submit": "该账号无权报送测缝",
        "approve": "需要值班长点头权限",
    }

    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                return jsonify({"detail": "未登录"}), 401
            if perm not in user["perms"]:
                return jsonify({"detail": messages[perm]}), 403
            g.user = user
            return fn(*args, **kwargs)

        return wrapper

    return deco


def now_utc():
    return datetime.now(timezone.utc)


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "service": "tunnel-convergence-desk"})


@app.post("/api/auth/login")
def login():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""
    user = USERS.get(username)
    if not user or not pwd.verify(password, user["password_hash"]):
        return jsonify({"detail": "用户名或密码错误"}), 401
    exp = now_utc() + timedelta(hours=8)
    token = jwt.encode(
        {"sub": username, "perms": user["perms"], "exp": exp}, SECRET, algorithm="HS256"
    )
    return jsonify({"access_token": token, "username": username, "perms": user["perms"]})


@app.get("/api/logs")
@require_login
def list_logs():
    db = SessionLocal()
    try:
        rows = db.query(ConvergenceLog).order_by(ConvergenceLog.id.desc()).all()
        return jsonify([row_dict(r) for r in rows])
    finally:
        db.close()


@app.post("/api/logs")
@require_perm("submit")
def create_log():
    body = request.get_json(silent=True) or {}
    chainage = (body.get("chainage") or "").strip()
    if not chainage:
        return jsonify({"detail": "桩号不能为空"}), 400
    try:
        delta_mm = float(body.get("delta_mm"))
    except (TypeError, ValueError):
        return jsonify({"detail": "收敛值必须是数字"}), 400

    db = SessionLocal()
    try:
        zone_id = body.get("zone_id")
        zone = db.get(WorkZone, zone_id) if zone_id is not None else None
        if zone is None:
            return jsonify({"detail": "报测必须选择工区"}), 400
        # 写口闸门：工区没经值班长点头，一律退回
        if zone.status != ZONE_OPEN:
            return jsonify({"detail": f"{zone.name}未经值班长点头放行，报测被退回"}), 403
        row = ConvergenceLog(
            chainage=chainage,
            delta_mm=delta_mm,
            status="pending",
            zone_id=zone.id,
            zone_name=zone.name,
            created_by=g.user["username"],
            created_at=now_utc(),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return jsonify(row_dict(row)), 201
    finally:
        db.close()


@app.get("/api/zones")
@require_login
def list_zones():
    db = SessionLocal()
    try:
        rows = db.query(WorkZone).order_by(WorkZone.id).all()
        return jsonify([zone_dict(r) for r in rows])
    finally:
        db.close()


@app.post("/api/zones/<int:zone_id>/apply")
@require_perm("submit")
def apply_zone(zone_id):
    """测量员提交开放申请；申请这一步同样进流水。"""
    db = SessionLocal()
    try:
        zone = db.get(WorkZone, zone_id)
        if zone is None:
            return jsonify({"detail": "工区不存在"}), 404
        if zone.status == ZONE_PENDING:
            return jsonify({"detail": f"{zone.name}已在等候值班长点头"}), 409
        if zone.status == ZONE_OPEN:
            return jsonify({"detail": f"{zone.name}已放开，无需重复申请"}), 409
        actor = g.user["username"]
        ts = now_utc()
        zone.status = ZONE_PENDING
        zone.applied_by = actor
        zone.applied_at = ts
        db.add(
            ReleaseFlow(
                zone_id=zone.id,
                zone_name=zone.name,
                action="apply",
                actor=actor,
                detail=f"{actor} 提交 {zone.name} 开放申请",
                created_at=ts,
            )
        )
        db.commit()
        db.refresh(zone)
        return jsonify(zone_dict(zone))
    finally:
        db.close()


@app.post("/api/zones/<int:zone_id>/approve")
@require_perm("approve")
def approve_zone(zone_id):
    """值班长点头：放行状态与流水同一事务、同一提交，缺一不可。"""
    actor = g.user["username"]
    db = SessionLocal()
    try:
        q = db.query(WorkZone).filter(WorkZone.id == zone_id)
        if engine.dialect.name == "postgresql":
            q = q.with_for_update(skip_locked=True)
        zone = q.first()
        if zone is None:
            return jsonify({"detail": "工区不存在"}), 404
        # 自己不能给自己负责的工区点头
        if zone.owner == actor:
            return jsonify({"detail": f"{zone.name}由你负责，不能给自己点头放行"}), 403
        if zone.status == ZONE_CLOSED:
            return jsonify({"detail": f"{zone.name}尚未提交开放申请，无对象可点头"}), 409
        if zone.status == ZONE_OPEN:
            return jsonify({"detail": f"{zone.name}已放行，不能重复点头"}), 409

        ts = now_utc()
        zone.status = ZONE_OPEN
        zone.opened_by = actor
        zone.opened_at = ts
        db.add(
            ReleaseFlow(
                zone_id=zone.id,
                zone_name=zone.name,
                action="approve",
                actor=actor,
                detail=f"值班长 {actor} 点头放行 {zone.name}（申请人 {zone.applied_by}）",
                created_at=ts,
            )
        )
        # 点头动作与流水一起落库：单一事务、单一提交
        db.commit()
        db.refresh(zone)
        return jsonify(zone_dict(zone))
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


@app.get("/api/release-flow")
@require_login
def list_release_flow():
    db = SessionLocal()
    try:
        rows = db.query(ReleaseFlow).order_by(ReleaseFlow.id).all()
        return jsonify([flow_dict(r) for r in rows])
    finally:
        db.close()
