"""工区放行门禁：测量员申请、值班长点头/驳回。

铁律：门禁状态变更与放行流水必须在同一个事务里落库，
只写进一半（状态改了没流水，或反过来）一律整体回滚。
"""
from datetime import datetime, timezone

from sqlalchemy import func

from models import GateEvent, WorkZone, ZoneGate


class GateError(Exception):
    def __init__(self, detail: str, status: int = 400):
        super().__init__(detail)
        self.detail = detail
        self.status = status


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _next_seq(db, zone_code: str) -> int:
    last = (
        db.query(func.max(GateEvent.seq))
        .filter(GateEvent.zone_code == zone_code)
        .scalar()
    )
    return (last or 0) + 1


def _locked_gate(db, zone_code: str):
    """锁住该工区门禁行，序列化并发的申请/点头（PG 上行锁，SQLite 下为空操作）。"""
    return (
        db.query(ZoneGate)
        .filter(ZoneGate.zone_code == zone_code)
        .with_for_update()
        .first()
    )


def _add_event(db, zone_code: str, action: str, actor: str, detail: str | None = None):
    db.add(
        GateEvent(
            zone_code=zone_code,
            seq=_next_seq(db, zone_code),
            action=action,
            actor=actor,
            detail=detail,
            created_at=_now(),
        )
    )


def request_open(db, zone_code: str, username: str) -> ZoneGate:
    zone = db.get(WorkZone, zone_code)
    if zone is None:
        raise GateError("工区不存在", 404)
    gate = _locked_gate(db, zone_code)
    if gate is not None and gate.status == "open":
        raise GateError(f"工区 {zone_code} 已放开，无需重复申请", 409)
    if gate is not None and gate.status == "waiting":
        raise GateError(f"工区 {zone_code} 已提交申请，正等候值班长点头", 409)
    if gate is None:
        gate = ZoneGate(zone_code=zone_code)
        db.add(gate)
    gate.status = "waiting"
    gate.requested_by = username
    gate.requested_at = _now()
    gate.decided_by = None
    gate.decided_at = None
    db.flush()
    _add_event(db, zone_code, "request", username, f"{username} 提交开放申请")
    return gate


def approve(db, zone_code: str, foreman: str) -> ZoneGate:
    """值班长点头：门禁放开 + 流水，同一事务。负责人不能给自己工区点头。"""
    zone = db.get(WorkZone, zone_code)
    if zone is None:
        raise GateError("工区不存在", 404)
    if zone.owner_username == foreman:
        raise GateError("不能给自己负责的工区点头放行", 403)
    gate = _locked_gate(db, zone_code)
    if gate is None:
        raise GateError(f"工区 {zone_code} 尚未提交开放申请", 409)
    if gate.status == "open":
        raise GateError(f"工区 {zone_code} 已放开", 409)
    if gate.status != "waiting":
        raise GateError(f"工区 {zone_code} 当前不在等候名单中", 409)
    gate.status = "open"
    gate.decided_by = foreman
    gate.decided_at = _now()
    db.flush()  # 状态先落库到本事务；紧接着写流水，失败则整体回滚
    _add_event(db, zone_code, "approve", foreman, f"值班长 {foreman} 点头放行")
    return gate


def reject(db, zone_code: str, foreman: str) -> ZoneGate:
    zone = db.get(WorkZone, zone_code)
    if zone is None:
        raise GateError("工区不存在", 404)
    if zone.owner_username == foreman:
        raise GateError("不能给自己负责的工区点头放行", 403)
    gate = _locked_gate(db, zone_code)
    if gate is None or gate.status != "waiting":
        raise GateError(f"工区 {zone_code} 没有等候处理的申请", 409)
    gate.status = "rejected"
    gate.decided_by = foreman
    gate.decided_at = _now()
    db.flush()
    _add_event(db, zone_code, "reject", foreman, f"值班长 {foreman} 驳回申请")
    return gate
