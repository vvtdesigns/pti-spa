"""
Database layer for the PTI Stations Performance Analysis app.

Works with either:
- A cloud Postgres database (recommended for "same data on laptop + phone"),
  configured via a DATABASE_URL secret (e.g. a free Supabase project).
- A local SQLite file (data/pti.db), used automatically when no DATABASE_URL
  is configured -- handy for trying the app out on one machine before you
  deploy it.

All the rest of the app talks to the functions in this file only; it never
opens a DB connection directly.
"""
from __future__ import annotations

import os
import datetime as dt
from typing import Optional

from sqlalchemy import (
    create_engine, String, Integer, Float, Date, DateTime, ForeignKey,
    LargeBinary, UniqueConstraint, select, func
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker, Session, selectinload
)


def _database_url() -> str:
    """
    Resolve the DB connection string.

    Priority:
    1. st.secrets["DATABASE_URL"]  (set this on Streamlit Community Cloud)
    2. environment variable DATABASE_URL (useful for local runs / other hosts)
    3. local SQLite file under ./data/pti.db (zero-config fallback)
    """
    try:
        import streamlit as st  # imported lazily so db.py works outside Streamlit too
        if "DATABASE_URL" in st.secrets:
            return st.secrets["DATABASE_URL"]
    except Exception:
        pass

    env_url = os.environ.get("DATABASE_URL")
    if env_url:
        return env_url

    os.makedirs("data", exist_ok=True)
    return "sqlite:///data/pti.db"


class Base(DeclarativeBase):
    pass


class Station(Base):
    __tablename__ = "stations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name_ar: Mapped[str] = mapped_column(String(200), unique=True)
    name_en: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True)

    metrics: Mapped[list["StationMetric"]] = relationship(back_populates="station")


class Period(Base):
    __tablename__ = "periods"
    __table_args__ = (UniqueConstraint("period_start", "period_end", name="uq_period_range"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    period_start: Mapped[dt.date] = mapped_column(Date)
    period_end: Mapped[dt.date] = mapped_column(Date)
    label: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    source_filename: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)
    uploaded_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    complaints: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    complaints_resolved: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    absher_success_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    metrics: Mapped[list["StationMetric"]] = relationship(back_populates="period", cascade="all, delete-orphan")


class StationMetric(Base):
    __tablename__ = "station_metrics"
    __table_args__ = (UniqueConstraint("period_id", "station_id", name="uq_period_station"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    period_id: Mapped[int] = mapped_column(ForeignKey("periods.id"))
    station_id: Mapped[int] = mapped_column(ForeignKey("stations.id"))

    appointments: Mapped[int] = mapped_column(Integer, default=0)
    attendance: Mapped[int] = mapped_column(Integer, default=0)
    absence: Mapped[int] = mapped_column(Integer, default=0)
    first_time: Mapped[int] = mapped_column(Integer, default=0)
    retest_1: Mapped[int] = mapped_column(Integer, default=0)
    retest_2: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)

    period: Mapped["Period"] = relationship(back_populates="metrics")
    station: Mapped["Station"] = relationship(back_populates="metrics")

    @property
    def pass_pct(self) -> float:
        total = self.passed + self.failed
        return (self.passed / total * 100.0) if total else 0.0

    @property
    def absence_pct(self) -> float:
        return (self.absence / self.appointments * 100.0) if self.appointments else 0.0

    @property
    def attendance_pct(self) -> float:
        return (self.attendance / self.appointments * 100.0) if self.appointments else 0.0


class Settings(Base):
    """Single-row table holding company branding, shared across every device."""
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    company_name_ar: Mapped[str] = mapped_column(String(200), default="شركة مسار المتحدة")
    company_name_en: Mapped[str] = mapped_column(String(200), default="Massar United Co.")
    logo_png: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    default_language: Mapped[str] = mapped_column(String(5), default="ar")
    pass_pct_alert_threshold: Mapped[float] = mapped_column(Float, default=60.0)
    absence_pct_alert_threshold: Mapped[float] = mapped_column(Float, default=15.0)


_engine = None
_SessionLocal: Optional[sessionmaker] = None


def get_engine():
    global _engine
    if _engine is None:
        url = _database_url()
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(url, connect_args=connect_args, pool_pre_ping=True)
    return _engine


def get_session() -> Session:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return _SessionLocal()


def init_db():
    """Create tables if they don't exist yet, and seed a default settings row + logo."""
    Base.metadata.create_all(get_engine())
    with get_session() as s:
        settings = s.get(Settings, 1)
        if settings is None:
            settings = Settings(id=1)
            logo_path = os.path.join(os.path.dirname(__file__), "assets", "logo_cropped.png")
            if os.path.exists(logo_path):
                with open(logo_path, "rb") as f:
                    settings.logo_png = f.read()
            s.add(settings)
            s.commit()


def get_settings() -> Settings:
    with get_session() as s:
        settings = s.get(Settings, 1)
        if settings is None:
            init_db()
            settings = s.get(Settings, 1)
        # detach-safe copy of scalar fields is unnecessary since expire_on_commit=False
        return settings


def get_or_create_station(session: Session, name_ar: str, name_en: Optional[str] = None) -> Station:
    """
    Look up a station by its Arabic name, creating it if needed.

    name_en is only used the first time a station is created (a new sheet
    re-uploading the same station won't overwrite a name someone already
    set in Settings). If not given, falls back to the curated mapping in
    station_names.py so known stations always have a proper English name
    -- new/unrecognized stations are left blank until a human fills one in
    (the Upload page prompts for this), rather than ever guessing.
    """
    name_ar = name_ar.strip()
    stmt = select(Station).where(Station.name_ar == name_ar)
    station = session.execute(stmt).scalar_one_or_none()
    if station is None:
        from station_names import KNOWN_STATION_NAMES_EN
        resolved_en = name_en or KNOWN_STATION_NAMES_EN.get(name_ar)
        station = Station(name_ar=name_ar, name_en=resolved_en)
        session.add(station)
        session.flush()
    return station


def known_station_names() -> set[str]:
    with get_session() as s:
        return {row[0] for row in s.execute(select(Station.name_ar)).all()}


def _eager_period_stmt():
    return select(Period).options(
        selectinload(Period.metrics).selectinload(StationMetric.station)
    )


def list_periods() -> list[Period]:
    """All periods, oldest first, with metrics + station eagerly loaded so
    callers can use them after the session closes."""
    with get_session() as s:
        stmt = _eager_period_stmt().order_by(Period.period_start)
        return list(s.execute(stmt).unique().scalars())


def get_period_with_metrics(period_id: int) -> Optional[Period]:
    with get_session() as s:
        stmt = _eager_period_stmt().where(Period.id == period_id)
        return s.execute(stmt).unique().scalar_one_or_none()
