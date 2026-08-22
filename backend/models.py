import os
from sqlalchemy import (
    create_engine, Column, Integer, String, Float,
    Boolean, DateTime, Text, ForeignKey
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
from datetime import datetime

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:////app/data/ledger.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), unique=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    display_name = Column(String(64), nullable=False)
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    permissions = relationship("AccountPermission", back_populates="user")
    transactions = relationship("Transaction", back_populates="creator")
    approvals = relationship("ApprovalRecord", back_populates="approver")


class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(128), unique=True, nullable=False)
    description = Column(String(256))
    balance = Column(Float, default=0.0)
    # 审批链存储为 JSON 字符串，格式: "[user_id1, user_id2, ...]"
    approval_chain = Column(Text, default="[]")
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    permissions = relationship("AccountPermission", back_populates="account")
    transactions = relationship("Transaction", back_populates="account")


class AccountPermission(Base):
    __tablename__ = "account_permissions"
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    can_spend = Column(Boolean, default=False)
    can_deposit = Column(Boolean, default=False)
    can_transfer = Column(Boolean, default=False)
    can_approve = Column(Boolean, default=False)
    can_view = Column(Boolean, default=True)

    account = relationship("Account", back_populates="permissions")
    user = relationship("User", back_populates="permissions")


class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Float, nullable=False)
    # type: spend | deposit | transfer_out | transfer_in
    type = Column(String(32), nullable=False)
    note = Column(String(512), default="")
    # status: pending | in_progress | approved | rejected
    status = Column(String(32), default="pending")
    # 转账关联流水 ID
    related_transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=True)
    # 当前审批步骤（0-indexed）
    current_step = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    account = relationship("Account", back_populates="transactions")
    creator = relationship("User", back_populates="transactions")
    approval_records = relationship("ApprovalRecord", back_populates="transaction")


class ApprovalRecord(Base):
    __tablename__ = "approval_records"
    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False)
    approver_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    step = Column(Integer, nullable=False)
    # action: approved | rejected
    action = Column(String(32), nullable=False)
    comment = Column(String(512), default="")
    acted_at = Column(DateTime, default=datetime.utcnow)

    transaction = relationship("Transaction", back_populates="approval_records")
    approver = relationship("User", back_populates="approvals")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """建表并创建默认 admin 用户"""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        import bcrypt
        existing = db.query(User).filter(User.username == "admin").first()
        if not existing:
            pwd_hash = bcrypt.hashpw("admin123".encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            admin = User(
                username="admin",
                password_hash=pwd_hash,
                display_name="管理员",
                is_admin=True,
            )
            db.add(admin)
            db.commit()
            print("✅ 默认管理员账号已创建: admin / admin123")
    finally:
        db.close()
