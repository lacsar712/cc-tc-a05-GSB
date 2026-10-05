import os
from datetime import datetime, timedelta, timezone
from functools import wraps

from flask import Flask, g, jsonify, request
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.exc import IntegrityError

import gate as gate_service
from claimer import start as start_claimer
from gate import GateError
from models import (
    Base,
    ConvergenceLog,
    GateEvent,
    SessionLocal,
    WorkZone,
    ZoneGate,
    engine,
    gate_event_dict,
    row_dict,
    zone_dict,
)

SECRET = os.environ.get("JWT_SECRET", "tunnelconv-dev-secret")
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")

# role：writer 测量员（可报测缝）/ foreman 值班长（可点头）/ reader 巡检员（只读）
# perms：额外权限。巡检员 inspector 带着 foreman 权限时可以点头，但仍不是 writer、不能报送。
USERS = {
    "surveyor": {
        "role": "writer",
        "perms": [],
        "password_hash": pwd.hash("surv123456"),
    },
    "surveyor2": {
        "role": "writer",
        "perms": [],
        "password_hash": pwd.hash("surv234567"),
    },
    "inspector": {
        "role": "reader",
        "perms": ["foreman"],
        "password_hash": pwd.hash("insp123456"),
    },
    "chief": {
        "role": "foreman",
        "perms": ["foreman"],
        "password_hash": pwd.hash("chief12345"),
    },
    "lead": {
        # 带班测量员：既是测量员（能报送）又带值班长权限（能给别区点头），
        # 但给自己负责的工区点头照样被拦。
        "role": "writer",
        "perms": ["foreman"],
        "password_hash": pwd.hash("lead123456"),
    },
}

# 工区及其负责人（测量员）。负责人只能申请，不能给自己工区点头。
ZONES = [
    ("Z01", "一号工区", "surveyor"),
    ("Z02", "二号工区", "surveyor2"),
    ("Z03", "三号工区", "surveyor"),
    ("Z04", "四号工区", "lead"),
]

app = Flask(__name__)


def seed():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        if db.query(WorkZone).count() == 0:
            for code, name, owner in ZONES:
                db.add(WorkZone(code=code, name=name, owner_username=owner))
            db.flush()
            now = datetime.now(timezone.utc)

            # Z02：已申请、正等候点头（左边等候名单里有东西）
            g2 = ZoneGate(
                zone_code="Z02",
                status="waiting",
                requested_by="surveyor2",
                requested_at=now - timedelta(minutes=5),
            )
            db.add(g2)
            db.flush()
            db.add(
                GateEvent(
                    zone_code="Z02",
                    seq=1,
                    action="request",
                    actor="surveyor2",
                    detail="surveyor2 提交开放申请",
                    created_at=now - timedelta(minutes=5),
                )
            )

            # Z03：已点头放开（右边已放开清单里有东西，流水两条）
            g3 = ZoneGate(
                zone_code="Z03",
                status="open",
                requested_by="surveyor",
                requested_at=now - timedelta(minutes=30),
                decided_by="chief",
                decided_at=now - timedelta(minutes=28),
            )
            db.add(g3)
            db.flush()
            db.add_all(
                [
                    GateEvent(
                        zone_code="Z03",
                        seq=1,
                        action="request",
                        actor="surveyor",
                        detail="surveyor 提交开放申请",
                        created_at=now - timedelta(minutes=30),
                    ),
                    GateEvent(
                        zone_code="Z03",
                        seq=2,
                        action="approve",
                        actor="chief",
                        detail="值班长 chief 点头放行",
                        created_at=now - timedelta(minutes=28),
                    ),
                ]
            )

            from rules import judge

            for zone_code, chainage, delta, expect in (
                ("Z03", "K12+180", 1.2, "合格"),
                ("Z03", "K18+040", 5.6, "超限"),
            ):
                verdict, reason = judge(delta)
                assert verdict == expect
                db.add(
                    ConvergenceLog(
                        zone_code=zone_code,
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
    return {
        "username": sub,
        "role": payload.get("role"),
        "perms": payload.get("perms") or [],
    }


def has_permission(user, perm: str) -> bool:
    return user["role"] == perm or perm in (user.get("perms") or [])


def require_login(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"detail": "未登录"}), 401
        g.user = user
        return fn(*args, **kwargs)

    return wrapper


def require_writer(fn):
    """报测缝写口：仅测量员角色。带着 foreman 权限的巡检员依然被拦在这里。"""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            return jsonify({"detail": "未登录"}), 401
        if user["role"] != "writer":
            return jsonify({"detail": "仅测量员可提交收敛读数"}), 403
        g.user = user
        return fn(*args, **kwargs)

    return wrapper


def require_permission(perm: str):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            user = current_user()
            if user is None:
                return jsonify({"detail": "未登录"}), 401
            if not has_permission(user, perm):
                if perm == "foreman":
                    return jsonify({"detail": "仅值班长可点头放行"}), 403
                return jsonify({"detail": "无权限"}), 403
            g.user = user
            return fn(*args, **kwargs)

        return wrapper

    return deco


@app.errorhandler(GateError)
def handle_gate_error(exc: GateError):
    return jsonify({"detail": exc.detail}), exc.status


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
    exp = datetime.now(timezone.utc) + timedelta(hours=8)
    token = jwt.encode(
        {
            "sub": username,
            "role": user["role"],
            "perms": user["perms"],
            "exp": exp,
        },
        SECRET,
        algorithm="HS256",
    )
    return jsonify(
        {
            "access_token": token,
            "username": username,
            "role": user["role"],
            "perms": user["perms"],
        }
    )


@app.get("/api/zones")
@require_login
def list_zones():
    db = SessionLocal()
    try:
        gates = {g.zone_code: g for g in db.query(ZoneGate).all()}
        zones = db.query(WorkZone).order_by(WorkZone.code).all()
        return jsonify([zone_dict(z, gates.get(z.code)) for z in zones])
    finally:
        db.close()


@app.post("/api/zones/<zone_code>/request")
@require_login
def request_zone(zone_code):
    """测量员为自己负责的工区提交开放申请；申请落库同时写流水。"""
    user = g.user
    if user["role"] != "writer":
        return jsonify({"detail": "仅测量员可提交开放申请"}), 403
    db = SessionLocal()
    try:
        zone = db.get(WorkZone, zone_code)
        if zone is not None and zone.owner_username != user["username"]:
            return jsonify({"detail": "只能为自己负责的工区提交申请"}), 403
        try:
            gate = gate_service.request_open(db, zone_code, user["username"])
            db.commit()
        except GateError:
            db.rollback()
            raise
        except IntegrityError:
            db.rollback()
            return jsonify({"detail": f"工区 {zone_code} 的申请正在处理中，请勿重复提交"}), 409
        db.refresh(gate)
        zone = db.get(WorkZone, zone_code)
        return jsonify(zone_dict(zone, gate)), 201
    finally:
        db.close()


def _decide(zone_code: str, action: str):
    user = g.user
    db = SessionLocal()
    try:
        try:
            if action == "approve":
                gate = gate_service.approve(db, zone_code, user["username"])
            else:
                gate = gate_service.reject(db, zone_code, user["username"])
            db.commit()  # 状态与流水同一事务提交，任一失败整体回滚
        except GateError:
            db.rollback()
            raise
        db.refresh(gate)
        zone = db.get(WorkZone, zone_code)
        return jsonify(zone_dict(zone, gate))
    finally:
        db.close()


@app.post("/api/zones/<zone_code>/approve")
@require_permission("foreman")
def approve_zone(zone_code):
    return _decide(zone_code, "approve")


@app.post("/api/zones/<zone_code>/reject")
@require_permission("foreman")
def reject_zone(zone_code):
    return _decide(zone_code, "reject")


@app.get("/api/gate-events")
@require_login
def list_gate_events():
    zone_code = (request.args.get("zone") or "").strip() or None
    db = SessionLocal()
    try:
        q = db.query(GateEvent)
        if zone_code:
            q = q.filter(GateEvent.zone_code == zone_code)
        rows = q.order_by(GateEvent.id.desc()).limit(200).all()
        return jsonify([gate_event_dict(r) for r in rows])
    finally:
        db.close()


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
@require_writer
def create_log():
    body = request.get_json(silent=True) or {}
    zone_code = (body.get("zone_code") or "").strip()
    chainage = (body.get("chainage") or "").strip()
    if not zone_code:
        return jsonify({"detail": "必须选择工区"}), 400
    if not chainage:
        return jsonify({"detail": "桩号不能为空"}), 400
    try:
        delta_mm = float(body.get("delta_mm"))
    except (TypeError, ValueError):
        return jsonify({"detail": "收敛值必须是数字"}), 400
    db = SessionLocal()
    try:
        zone = db.get(WorkZone, zone_code)
        if zone is None:
            return jsonify({"detail": "工区不存在"}), 404

        # 真正的写口门禁：没经值班长点头，这里直接退回，单进不了待认领。
        gate = db.get(ZoneGate, zone_code)
        if gate is None or gate.status != "open":
            return (
                jsonify(
                    {
                        "detail": f"工区 {zone_code} 未经值班长点头放行，报测缝被退回",
                        "gate": gate.status if gate else "closed",
                    }
                ),
                403,
            )

        row = ConvergenceLog(
            zone_code=zone_code,
            chainage=chainage,
            delta_mm=delta_mm,
            status="pending",
            created_by=g.user["username"],
            created_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return jsonify(row_dict(row)), 201
    finally:
        db.close()
