"""放行门禁验收测试。

覆盖题目要求：
- 工区没经值班长点头，报测缝必须被退回（申请前/申请后未点头 都拦）。
- 点头动作与放行流水必须同一事务落库，只写一半时整体回滚。
- 自己不能给自己负责的工区点头（含带 foreman 权限的测量员）。
- 巡检员带 foreman 权限可以点头，但自己仍不能报送。
- 点头后送单进待认领，流水可查。
"""
import os
import tempfile
import time

import pytest

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp.name}"

from models import Base, ConvergenceLog, GateEvent, SessionLocal, ZoneGate, engine  # noqa: E402
import api  # noqa: E402  （import 即建表、种子、启认领线程）


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    api.seed()
    yield


@pytest.fixture()
def client():
    return api.app.test_client()


def login(client, username, password):
    r = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert r.status_code == 200, r.data
    return {"Authorization": "Bearer " + r.get_json()["access_token"]}


def submit_log(client, headers, zone="Z01", chainage="K1+001", delta=1.0):
    return client.post(
        "/api/logs",
        headers=headers,
        json={"zone_code": zone, "chainage": chainage, "delta_mm": delta},
    )


def events(zone_code):
    db = SessionLocal()
    try:
        return (
            db.query(GateEvent)
            .filter(GateEvent.zone_code == zone_code)
            .order_by(GateEvent.seq)
            .all()
        )
    finally:
        db.close()


def test_scenario_apply_then_approve_then_submit(client):
    """一号工区：没点头前送单退回；点头后再送进待认领，流水能查到。"""
    surv = login(client, "surveyor", "surv123456")

    # 申请前送单：退回
    r = submit_log(client, surv)
    assert r.status_code == 403
    assert "未经值班长点头" in r.get_json()["detail"]

    # 提交开放申请
    r = client.post("/api/zones/Z01/request", headers=surv)
    assert r.status_code == 201
    assert r.get_json()["status"] == "waiting"

    # 已申请但没点头：送单仍退回
    r = submit_log(client, surv)
    assert r.status_code == 403

    # 值班长 chief 点头（不是 Z01 负责人）
    chief = login(client, "chief", "chief12345")
    r = client.post("/api/zones/Z01/approve", headers=chief)
    assert r.status_code == 200
    assert r.get_json()["status"] == "open"

    # 点头后送单：进待认领
    r = submit_log(client, surv)
    assert r.status_code == 201
    body = r.get_json()
    assert body["status"] == "pending"
    log_id = body["id"]

    # 认领线程稍后出结论
    deadline = time.time() + 5
    while time.time() < deadline:
        db = SessionLocal()
        try:
            row = db.get(ConvergenceLog, log_id)
            if row.status == "done":
                assert row.verdict == "合格"
                break
        finally:
            db.close()
        time.sleep(0.2)
    else:
        pytest.fail("送单未被认领处理")

    # 放行流水可查：申请 + 点头 两条，顺序正确
    evs = events("Z01")
    assert [(e.seq, e.action, e.actor) for e in evs] == [
        (1, "request", "surveyor"),
        (2, "approve", "chief"),
    ]


def test_writer_with_foreman_perm_cannot_approve_own_zone(client):
    """带班测量员 lead 是 Z04 负责人且有 foreman 权限：仍不能给自己工区点头。"""
    lead = login(client, "lead", "lead123456")

    r = client.post("/api/zones/Z04/request", headers=lead)
    assert r.status_code == 201

    # 装饰器放行（确有 foreman 权限），服务层 owner 校验必须拦住
    r = client.post("/api/zones/Z04/approve", headers=lead)
    assert r.status_code == 403
    assert "不能给自己负责的工区点头" in r.get_json()["detail"]

    # 驳回自己工区同样拦
    r = client.post("/api/zones/Z04/reject", headers=lead)
    assert r.status_code == 403

    # 给别的工区可以点头
    other_surv = login(client, "surveyor", "surv123456")
    client.post("/api/zones/Z01/request", headers=other_surv)
    r = client.post("/api/zones/Z01/approve", headers=lead)
    assert r.status_code == 200
    assert r.get_json()["status"] == "open"

    # 双权限不影响报送：Z01 已放开，lead 作为测量员可送单
    r = submit_log(client, lead, zone="Z01", chainage="K9+999", delta=-2.0)
    assert r.status_code == 201


def test_inspector_with_foreman_perm_approves_but_cannot_submit(client):
    """巡检员 inspector（reader + foreman 权限）：可点头，但不能报送。"""
    insp = login(client, "inspector", "insp123456")

    # Z02 种子里已是 waiting，inspector 可点头
    r = client.post("/api/zones/Z02/approve", headers=insp)
    assert r.status_code == 200
    assert r.get_json()["status"] == "open"

    # 巡检员不能报送（即便该工区已放开）
    r = submit_log(client, insp, zone="Z02")
    assert r.status_code == 403
    assert "仅测量员" in r.get_json()["detail"]

    # 纯值班长 chief 同样不能报送
    chief = login(client, "chief", "chief12345")
    r = submit_log(client, chief, zone="Z02")
    assert r.status_code == 403


def test_foreman_cannot_approve_zone_where_they_are_owner_via_service():
    """服务层直测：owner 自点头抛 GateError，不落任何库。"""
    import gate as gate_service
    from gate import GateError

    db = SessionLocal()
    try:
        gate_service.request_open(db, "Z04", "lead")
        db.commit()
        with pytest.raises(GateError) as ei:
            gate_service.approve(db, "Z04", "lead")
        assert ei.value.status == 403
        db.rollback()
    finally:
        db.close()

    db = SessionLocal()
    try:
        gate = db.get(ZoneGate, "Z04")
        assert gate.status == "waiting"  # 没有被改成 open
        evs = events("Z04")
        assert [e.action for e in evs] == ["request"]  # 无 approve 流水
    finally:
        db.close()


def test_approve_and_event_atomic_rollback(monkeypatch):
    """点头与流水必须同一事务：流水写入抛错时，门禁状态一起回滚。"""
    import gate as gate_service

    db = SessionLocal()
    try:
        gate_service.request_open(db, "Z01", "surveyor")
        db.commit()
    finally:
        db.close()

    def boom(*a, **k):
        raise RuntimeError("流水落库失败")

    monkeypatch.setattr(gate_service, "_add_event", boom)

    db = SessionLocal()
    try:
        with pytest.raises(RuntimeError):
            gate_service.approve(db, "Z01", "chief")
        db.rollback()
    finally:
        db.close()

    # 状态没变成 open，也没有半截 approve 流水
    db = SessionLocal()
    try:
        gate = db.get(ZoneGate, "Z01")
        assert gate.status == "waiting"
        assert gate.decided_by is None
        evs = events("Z01")
        assert [e.action for e in evs] == ["request"]
    finally:
        db.close()


def test_reject_keeps_write_gate_closed(client):
    """驳回后写口仍关；可重新申请。"""
    surv2 = login(client, "surveyor2", "surv234567")
    chief = login(client, "chief", "chief12345")

    r = client.post("/api/zones/Z02/reject", headers=chief)
    assert r.status_code == 200
    assert r.get_json()["status"] == "rejected"

    r = submit_log(client, surv2, zone="Z02")
    assert r.status_code == 403

    r = client.post("/api/zones/Z02/request", headers=surv2)
    assert r.status_code == 201
    assert r.get_json()["status"] == "waiting"


def test_only_owner_may_request(client):
    """测量员只能给自己负责的工区申请；非 foreman 不能点头。"""
    surv2 = login(client, "surveyor2", "surv234567")
    r = client.post("/api/zones/Z01/request", headers=surv2)
    assert r.status_code == 403

    # 纯测量员访问点头接口：装饰器 403
    r = client.post("/api/zones/Z02/approve", headers=surv2)
    assert r.status_code == 403


def test_unknown_zone_and_missing_fields(client):
    surv = login(client, "surveyor", "surv123456")
    r = submit_log(client, surv, zone="NOPE")
    assert r.status_code == 404
    r = client.post(
        "/api/logs",
        headers=surv,
        json={"chainage": "K1+001", "delta_mm": 1.0},
    )
    assert r.status_code == 400


def test_unauthenticated_blocked(client):
    assert client.get("/api/zones").status_code == 401
    assert submit_log(client, {}).status_code == 401
