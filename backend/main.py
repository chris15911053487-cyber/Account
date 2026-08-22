import json
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List

from models import (
    get_db, init_db, User, Account, AccountPermission,
    Transaction, ApprovalRecord
)
from auth import (
    verify_password, hash_password, create_access_token,
    get_current_user, require_admin
)

app = FastAPI(title="多账户记账本", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


# ─── Pydantic Schemas ────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class UserCreate(BaseModel):
    username: str
    password: str
    display_name: str
    is_admin: bool = False

class UserUpdate(BaseModel):
    display_name: Optional[str] = None
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None
    password: Optional[str] = None

class AccountCreate(BaseModel):
    name: str
    description: Optional[str] = ""
    initial_balance: float = 0.0

class AccountUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class PermissionSet(BaseModel):
    user_id: int
    can_spend: bool = False
    can_deposit: bool = False
    can_transfer: bool = False
    can_approve: bool = False
    can_view: bool = True

class ApprovalChainUpdate(BaseModel):
    user_ids: List[int]

class TransactionCreate(BaseModel):
    account_id: int
    amount: float = Field(gt=0)
    type: str  # spend | deposit | transfer_out
    note: Optional[str] = ""
    target_account_id: Optional[int] = None  # 转账时必填

class ApprovalAction(BaseModel):
    action: str  # approved | rejected
    comment: Optional[str] = ""


# ─── Auth ────────────────────────────────────────────────────────────────────

@app.post("/api/auth/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username, User.is_active == True).first()
    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token({"sub": str(user.id)})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "is_admin": user.is_admin,
        }
    }

@app.get("/api/auth/me")
def me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "display_name": current_user.display_name,
        "is_admin": current_user.is_admin,
    }


# ─── Admin: User Management ──────────────────────────────────────────────────

@app.get("/api/admin/users")
def list_users(db: Session = Depends(get_db), _: User = Depends(require_admin)):
    users = db.query(User).all()
    return [
        {
            "id": u.id, "username": u.username,
            "display_name": u.display_name,
            "is_admin": u.is_admin, "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in users
    ]

@app.post("/api/admin/users", status_code=201)
def create_user(req: UserCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if db.query(User).filter(User.username == req.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    user = User(
        username=req.username,
        password_hash=hash_password(req.password),
        display_name=req.display_name,
        is_admin=req.is_admin,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"id": user.id, "username": user.username, "display_name": user.display_name}

@app.patch("/api/admin/users/{user_id}")
def update_user(user_id: int, req: UserUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    if req.display_name is not None:
        user.display_name = req.display_name
    if req.is_active is not None:
        user.is_active = req.is_active
    if req.is_admin is not None:
        user.is_admin = req.is_admin
    if req.password:
        user.password_hash = hash_password(req.password)
    db.commit()
    return {"ok": True}


# ─── Accounts ────────────────────────────────────────────────────────────────

def _account_dict(a: Account, db: Session):
    chain = json.loads(a.approval_chain or "[]")
    perms = db.query(AccountPermission).filter(AccountPermission.account_id == a.id).all()
    return {
        "id": a.id, "name": a.name, "description": a.description,
        "balance": a.balance, "is_active": a.is_active,
        "approval_chain": chain,
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "permissions": [
            {
                "user_id": p.user_id, "can_spend": p.can_spend,
                "can_deposit": p.can_deposit, "can_transfer": p.can_transfer,
                "can_approve": p.can_approve, "can_view": p.can_view,
            }
            for p in perms
        ]
    }

@app.get("/api/accounts")
def list_accounts(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.is_admin:
        accounts = db.query(Account).filter(Account.is_active == True).all()
    else:
        perm_account_ids = [
            p.account_id for p in
            db.query(AccountPermission).filter(
                AccountPermission.user_id == current_user.id,
                AccountPermission.can_view == True
            ).all()
        ]
        accounts = db.query(Account).filter(
            Account.id.in_(perm_account_ids), Account.is_active == True
        ).all()
    return [_account_dict(a, db) for a in accounts]

@app.post("/api/accounts", status_code=201)
def create_account(req: AccountCreate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    if db.query(Account).filter(Account.name == req.name).first():
        raise HTTPException(status_code=400, detail="账户名已存在")
    account = Account(name=req.name, description=req.description, balance=req.initial_balance)
    db.add(account)
    db.commit()
    db.refresh(account)
    return _account_dict(account, db)

@app.patch("/api/accounts/{account_id}")
def update_account(account_id: int, req: AccountUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")
    if req.name:
        account.name = req.name
    if req.description is not None:
        account.description = req.description
    db.commit()
    return _account_dict(account, db)

@app.put("/api/accounts/{account_id}/permissions")
def set_permissions(account_id: int, req: PermissionSet, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")
    perm = db.query(AccountPermission).filter(
        AccountPermission.account_id == account_id,
        AccountPermission.user_id == req.user_id
    ).first()
    if perm:
        perm.can_spend = req.can_spend
        perm.can_deposit = req.can_deposit
        perm.can_transfer = req.can_transfer
        perm.can_approve = req.can_approve
        perm.can_view = req.can_view
    else:
        perm = AccountPermission(
            account_id=account_id, user_id=req.user_id,
            can_spend=req.can_spend, can_deposit=req.can_deposit,
            can_transfer=req.can_transfer, can_approve=req.can_approve,
            can_view=req.can_view,
        )
        db.add(perm)
    db.commit()
    return {"ok": True}

@app.put("/api/accounts/{account_id}/approval-chain")
def set_approval_chain(account_id: int, req: ApprovalChainUpdate, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    account = db.query(Account).filter(Account.id == account_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")
    account.approval_chain = json.dumps(req.user_ids)
    db.commit()
    return {"ok": True}

@app.delete("/api/accounts/{account_id}/permissions/{user_id}")
def remove_permission(account_id: int, user_id: int, db: Session = Depends(get_db), _: User = Depends(require_admin)):
    perm = db.query(AccountPermission).filter(
        AccountPermission.account_id == account_id,
        AccountPermission.user_id == user_id
    ).first()
    if perm:
        db.delete(perm)
        db.commit()
    return {"ok": True}


# ─── Transactions ────────────────────────────────────────────────────────────

def _tx_dict(t: Transaction, db: Session):
    records = db.query(ApprovalRecord).filter(ApprovalRecord.transaction_id == t.id).all()
    account = db.query(Account).filter(Account.id == t.account_id).first()
    creator = db.query(User).filter(User.id == t.created_by).first()
    return {
        "id": t.id,
        "account_id": t.account_id,
        "account_name": account.name if account else "",
        "created_by": t.created_by,
        "creator_name": creator.display_name if creator else "",
        "amount": t.amount,
        "type": t.type,
        "note": t.note,
        "status": t.status,
        "current_step": t.current_step,
        "related_transaction_id": t.related_transaction_id,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
        "approval_records": [
            {
                "id": r.id, "approver_id": r.approver_id,
                "step": r.step, "action": r.action,
                "comment": r.comment,
                "acted_at": r.acted_at.isoformat() if r.acted_at else None,
                "approver_name": db.query(User).filter(User.id == r.approver_id).first().display_name
                    if db.query(User).filter(User.id == r.approver_id).first() else "",
            }
            for r in records
        ]
    }

@app.get("/api/transactions")
def list_transactions(
    account_id: Optional[int] = None,
    tx_type: Optional[str] = None,
    tx_status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    q = db.query(Transaction)
    if not current_user.is_admin:
        viewable_ids = [
            p.account_id for p in
            db.query(AccountPermission).filter(
                AccountPermission.user_id == current_user.id,
                AccountPermission.can_view == True
            ).all()
        ]
        q = q.filter(Transaction.account_id.in_(viewable_ids))
    if account_id:
        q = q.filter(Transaction.account_id == account_id)
    if tx_type:
        q = q.filter(Transaction.type == tx_type)
    if tx_status:
        q = q.filter(Transaction.status == tx_status)
    txs = q.order_by(Transaction.created_at.desc()).all()
    return [_tx_dict(t, db) for t in txs]

@app.post("/api/transactions", status_code=201)
def create_transaction(req: TransactionCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    account = db.query(Account).filter(Account.id == req.account_id, Account.is_active == True).first()
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")

    # 权限检查
    if not current_user.is_admin:
        perm = db.query(AccountPermission).filter(
            AccountPermission.account_id == req.account_id,
            AccountPermission.user_id == current_user.id
        ).first()
        if req.type == "spend" and not (perm and perm.can_spend):
            raise HTTPException(status_code=403, detail="无支出权限")
        if req.type == "deposit" and not (perm and perm.can_deposit):
            raise HTTPException(status_code=403, detail="无充值权限")
        if req.type in ("transfer_out",) and not (perm and perm.can_transfer):
            raise HTTPException(status_code=403, detail="无转账权限")

    # 审批链
    chain = json.loads(account.approval_chain or "[]")
    initial_status = "pending" if chain else "approved"

    tx = Transaction(
        account_id=req.account_id,
        created_by=current_user.id,
        amount=req.amount,
        type=req.type,
        note=req.note,
        status=initial_status,
        current_step=0,
    )
    db.add(tx)
    db.flush()  # 获取 tx.id

    # 如无审批链，直接更新余额
    if not chain:
        _apply_balance(tx, account, db)

    # 转账：生成对应入账流水
    if req.type == "transfer_out":
        if not req.target_account_id:
            raise HTTPException(status_code=400, detail="转账需指定目标账户")
        target = db.query(Account).filter(Account.id == req.target_account_id, Account.is_active == True).first()
        if not target:
            raise HTTPException(status_code=404, detail="目标账户不存在")
        target_chain = json.loads(target.approval_chain or "[]")
        target_status = "pending" if target_chain else "approved"
        tx_in = Transaction(
            account_id=req.target_account_id,
            created_by=current_user.id,
            amount=req.amount,
            type="transfer_in",
            note=f"来自账户【{account.name}】的转账" + (f"：{req.note}" if req.note else ""),
            status=target_status,
            current_step=0,
            related_transaction_id=tx.id,
        )
        db.add(tx_in)
        db.flush()
        tx.related_transaction_id = tx_in.id
        if not target_chain:
            _apply_balance(tx_in, target, db)

    db.commit()
    db.refresh(tx)
    return _tx_dict(tx, db)

@app.get("/api/transactions/{tx_id}")
def get_transaction(tx_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="流水不存在")
    return _tx_dict(tx, db)


def _apply_balance(tx: Transaction, account: Account, db: Session):
    """将已审批通过的流水应用到余额"""
    if tx.type in ("deposit", "transfer_in"):
        account.balance += tx.amount
    elif tx.type in ("spend", "transfer_out"):
        account.balance -= tx.amount
    tx.status = "approved"


# ─── Approvals ───────────────────────────────────────────────────────────────

@app.get("/api/approvals/pending")
def pending_approvals(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """返回需要当前用户审批的流水"""
    pending_txs = db.query(Transaction).filter(
        Transaction.status.in_(["pending", "in_progress"])
    ).all()

    result = []
    for tx in pending_txs:
        account = db.query(Account).filter(Account.id == tx.account_id).first()
        if not account:
            continue
        chain = json.loads(account.approval_chain or "[]")
        if not chain:
            continue
        # 当前步骤的审批人是否是当前用户
        step = tx.current_step
        if step < len(chain) and chain[step] == current_user.id:
            # 检查该步骤未审批
            already = db.query(ApprovalRecord).filter(
                ApprovalRecord.transaction_id == tx.id,
                ApprovalRecord.step == step
            ).first()
            if not already:
                result.append(_tx_dict(tx, db))
    return result

@app.get("/api/approvals/all")
def all_approvals(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """管理员或审批链中的用户查看所有相关审批"""
    if current_user.is_admin:
        txs = db.query(Transaction).order_by(Transaction.created_at.desc()).all()
    else:
        # 查找当前用户在审批链中的账户
        accounts = db.query(Account).all()
        account_ids = []
        for acc in accounts:
            chain = json.loads(acc.approval_chain or "[]")
            if current_user.id in chain:
                account_ids.append(acc.id)
        txs = db.query(Transaction).filter(
            Transaction.account_id.in_(account_ids)
        ).order_by(Transaction.created_at.desc()).all()
    return [_tx_dict(t, db) for t in txs]

@app.post("/api/approvals/{tx_id}/action")
def approve_action(
    tx_id: int,
    req: ApprovalAction,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    tx = db.query(Transaction).filter(Transaction.id == tx_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail="流水不存在")
    if tx.status not in ("pending", "in_progress"):
        raise HTTPException(status_code=400, detail="流水不在待审批状态")

    account = db.query(Account).filter(Account.id == tx.account_id).first()
    chain = json.loads(account.approval_chain or "[]")
    step = tx.current_step

    if step >= len(chain) or chain[step] != current_user.id:
        raise HTTPException(status_code=403, detail="当前步骤不是你审批")

    already = db.query(ApprovalRecord).filter(
        ApprovalRecord.transaction_id == tx_id,
        ApprovalRecord.step == step
    ).first()
    if already:
        raise HTTPException(status_code=400, detail="已审批过该步骤")

    # 记录审批
    record = ApprovalRecord(
        transaction_id=tx_id,
        approver_id=current_user.id,
        step=step,
        action=req.action,
        comment=req.comment,
    )
    db.add(record)

    if req.action == "rejected":
        tx.status = "rejected"
        tx.updated_at = datetime.utcnow()
        # 如果有关联转账流水，也拒绝
        if tx.related_transaction_id:
            related = db.query(Transaction).filter(Transaction.id == tx.related_transaction_id).first()
            if related and related.status in ("pending", "in_progress"):
                related.status = "rejected"
                related.updated_at = datetime.utcnow()
    else:
        next_step = step + 1
        if next_step >= len(chain):
            # 全部审批通过
            _apply_balance(tx, account, db)
            tx.updated_at = datetime.utcnow()
            # 如果有关联转账入账流水，也处理
            if tx.related_transaction_id:
                related = db.query(Transaction).filter(Transaction.id == tx.related_transaction_id).first()
                if related:
                    related_account = db.query(Account).filter(Account.id == related.account_id).first()
                    related_chain = json.loads(related_account.approval_chain or "[]")
                    if not related_chain:
                        _apply_balance(related, related_account, db)
                    elif related.status in ("pending", "in_progress"):
                        related.current_step = 0
                        related.status = "pending"
        else:
            tx.current_step = next_step
            tx.status = "in_progress"
            tx.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(tx)
    return _tx_dict(tx, db)


# ─── Dashboard ───────────────────────────────────────────────────────────────

@app.get("/api/dashboard")
def dashboard(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.is_admin:
        accounts = db.query(Account).filter(Account.is_active == True).all()
    else:
        ids = [
            p.account_id for p in
            db.query(AccountPermission).filter(
                AccountPermission.user_id == current_user.id,
                AccountPermission.can_view == True
            ).all()
        ]
        accounts = db.query(Account).filter(Account.id.in_(ids), Account.is_active == True).all()

    total_balance = sum(a.balance for a in accounts)

    # 待审批数量
    pending_count = 0
    for tx in db.query(Transaction).filter(Transaction.status.in_(["pending", "in_progress"])).all():
        acc = db.query(Account).filter(Account.id == tx.account_id).first()
        if not acc:
            continue
        chain = json.loads(acc.approval_chain or "[]")
        step = tx.current_step
        if step < len(chain) and chain[step] == current_user.id:
            already = db.query(ApprovalRecord).filter(
                ApprovalRecord.transaction_id == tx.id, ApprovalRecord.step == step
            ).first()
            if not already:
                pending_count += 1

    # 最近10条流水
    if current_user.is_admin:
        recent_txs = db.query(Transaction).order_by(Transaction.created_at.desc()).limit(10).all()
    else:
        viewable_ids = [a.id for a in accounts]
        recent_txs = db.query(Transaction).filter(
            Transaction.account_id.in_(viewable_ids)
        ).order_by(Transaction.created_at.desc()).limit(10).all()

    return {
        "total_balance": total_balance,
        "account_count": len(accounts),
        "pending_approval_count": pending_count,
        "accounts": [
            {"id": a.id, "name": a.name, "balance": a.balance} for a in accounts
        ],
        "recent_transactions": [_tx_dict(t, db) for t in recent_txs],
    }
