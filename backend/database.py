"""Persistence: PostgreSQL in production (DATABASE_URL), SQLite for local development.

Sensitive payloads (OCR text, measurements, analyses) are stored as Fernet-encrypted
blobs. Only non-identifying metadata (type, status, timestamps, counts) is stored in clear
so the dashboard can aggregate without decrypting anything.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from cryptography.fernet import Fernet
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from backend.config import settings


def _load_key() -> bytes:
    if settings.encryption_key:
        return settings.encryption_key.encode()
    key_file = settings.storage_dir / ".key"
    if not key_file.exists():
        key_file.write_bytes(Fernet.generate_key())
        key_file.chmod(0o600)
    return key_file.read_bytes()


FERNET = Fernet(_load_key())


def encrypt_json(obj) -> bytes:
    return FERNET.encrypt(json.dumps(obj, default=str).encode())


def decrypt_json(blob: bytes | None):
    if not blob:
        return None
    return json.loads(FERNET.decrypt(blob).decode())


def _now():
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Report(Base):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
    file_sha256: Mapped[str] = mapped_column(String(64), index=True)  # duplicate detection only
    file_kind: Mapped[str] = mapped_column(String(10))  # pdf | image | csv
    report_type: Mapped[str] = mapped_column(String(20), default="UNKNOWN", index=True)
    panels: Mapped[str] = mapped_column(String(200), default="")  # comma-separated detected panels
    status: Mapped[str] = mapped_column(String(30), default="processing", index=True)
    report_date: Mapped[str | None] = mapped_column(String(20), nullable=True)
    n_measurements: Mapped[int] = mapped_column(Integer, default=0)
    n_uncertain: Mapped[int] = mapped_column(Integer, default=0)
    n_abnormal: Mapped[int] = mapped_column(Integer, default=0)
    file_stored: Mapped[bool] = mapped_column(Boolean, default=False)
    stored_path: Mapped[str | None] = mapped_column(String(300), nullable=True)
    ocr_blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)  # encrypted
    extraction_blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)  # encrypted
    analysis_blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)  # encrypted
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    audit: Mapped[list["AuditEvent"]] = relationship(back_populates="report", cascade="all, delete-orphan")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    action: Mapped[str] = mapped_column(String(40))
    detail_blob: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)  # encrypted
    report: Mapped[Report] = relationship(back_populates="audit")


connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db():
    Base.metadata.create_all(engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def add_audit(db, report_id: str, action: str, detail=None):
    db.add(AuditEvent(report_id=report_id, action=action, detail_blob=encrypt_json(detail) if detail else None))
