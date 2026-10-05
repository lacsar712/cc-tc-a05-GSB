import os
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

DSN = os.environ.get("DATABASE_URL", "postgresql://app:app@localhost:54401/tunnelconv")
engine = create_engine(DSN, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine)

# 工区状态：closed 未申请 / pending 已申请待值班长点头 / open 已放开
ZONE_CLOSED = "closed"
ZONE_PENDING = "pending"
ZONE_OPEN = "open"


class Base(DeclarativeBase):
    pass


class WorkZone(Base):
    __tablename__ = "work_zones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    owner: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default=ZONE_CLOSED)
    applied_by: Mapped[str | None] = mapped_column(String, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    opened_by: Mapped[str | None] = mapped_column(String, nullable=True)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ReleaseFlow(Base):
    """放行流水：申请、点头每一步都落一行，只增不改。"""

    __tablename__ = "release_flow"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    zone_id: Mapped[int] = mapped_column(Integer, nullable=False)
    zone_name: Mapped[str] = mapped_column(String, nullable=False)
    action: Mapped[str] = mapped_column(String, nullable=False)  # apply / approve
    actor: Mapped[str] = mapped_column(String, nullable=False)
    detail: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ConvergenceLog(Base):
    __tablename__ = "convergence_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chainage: Mapped[str] = mapped_column(String, nullable=False)
    delta_mm: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    verdict: Mapped[str | None] = mapped_column(String, nullable=True)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    zone_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    zone_name: Mapped[str | None] = mapped_column(String, nullable=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


def zone_dict(row: WorkZone) -> dict:
    return {
        "id": row.id,
        "name": row.name,
        "owner": row.owner,
        "status": row.status,
        "applied_by": row.applied_by,
        "applied_at": row.applied_at.isoformat() if row.applied_at else None,
        "opened_by": row.opened_by,
        "opened_at": row.opened_at.isoformat() if row.opened_at else None,
    }


def flow_dict(row: ReleaseFlow) -> dict:
    return {
        "id": row.id,
        "zone_id": row.zone_id,
        "zone_name": row.zone_name,
        "action": row.action,
        "actor": row.actor,
        "detail": row.detail,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def row_dict(row: ConvergenceLog) -> dict:
    return {
        "id": row.id,
        "chainage": row.chainage,
        "delta_mm": row.delta_mm,
        "status": row.status,
        "verdict": row.verdict,
        "reason": row.reason,
        "zone_id": row.zone_id,
        "zone_name": row.zone_name,
        "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "processed_at": row.processed_at.isoformat() if row.processed_at else None,
    }
