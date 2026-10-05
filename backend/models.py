import os
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DSN = os.environ.get("DATABASE_URL", "postgresql://app:app@localhost:54401/tunnelconv")
engine = create_engine(DSN, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


class WorkZone(Base):
    """工区。负责人（测量员）只能申请，不能给自己工区点头。"""

    __tablename__ = "work_zones"

    code: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_username: Mapped[str] = mapped_column(String(64), nullable=False)


class ZoneGate(Base):
    """工区写口当前状态：waiting（等点头）/ open（已放开）。"""

    __tablename__ = "zone_gates"

    zone_code: Mapped[str] = mapped_column(String(16), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="waiting")
    requested_by: Mapped[str] = mapped_column(String(64), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class GateEvent(Base):
    """放行流水：申请/点头/驳回/重开等每一步都留痕。"""

    __tablename__ = "gate_events"
    __table_args__ = (UniqueConstraint("zone_code", "seq", name="uq_gate_events_zone_seq"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    zone_code: Mapped[str] = mapped_column(String(16), nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    detail: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ConvergenceLog(Base):
    __tablename__ = "convergence_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    zone_code: Mapped[str] = mapped_column(String(16), nullable=False)
    chainage: Mapped[str] = mapped_column(String, nullable=False)
    delta_mm: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    verdict: Mapped[str | None] = mapped_column(String, nullable=True)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def zone_dict(zone: WorkZone, gate: ZoneGate | None) -> dict:
    return {
        "code": zone.code,
        "name": zone.name,
        "owner_username": zone.owner_username,
        "status": gate.status if gate else "closed",
        "requested_by": gate.requested_by if gate else None,
        "requested_at": gate.requested_at.isoformat() if gate and gate.requested_at else None,
        "decided_by": gate.decided_by if gate else None,
        "decided_at": gate.decided_at.isoformat() if gate and gate.decided_at else None,
    }


def gate_event_dict(ev: GateEvent) -> dict:
    return {
        "id": ev.id,
        "zone_code": ev.zone_code,
        "seq": ev.seq,
        "action": ev.action,
        "actor": ev.actor,
        "detail": ev.detail,
        "created_at": ev.created_at.isoformat() if ev.created_at else None,
    }


def row_dict(row: ConvergenceLog) -> dict:
    return {
        "id": row.id,
        "zone_code": row.zone_code,
        "chainage": row.chainage,
        "delta_mm": row.delta_mm,
        "status": row.status,
        "verdict": row.verdict,
        "reason": row.reason,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "processed_at": row.processed_at.isoformat() if row.processed_at else None,
    }
