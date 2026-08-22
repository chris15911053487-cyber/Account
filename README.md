# 💰 多账户记账本

一个支持多账户、细粒度权限管理和多级审批流程的记账 Web 应用，使用 FastAPI + SQLite 后端、纯 HTML/JS 前端，通过 Docker Compose 一键部署。

## 功能特性

### 核心功能
- **流水记录**：支持支出、流入、账户间转账三种类型，通过表单提交生成流水记录
- **多级审批**：每个账户可独立配置审批链，流水按顺序流转，全部审批人通过后才生效更新余额
- **多账户管理**：支持创建多个资金账户，账户间可自由转账（生成关联出入两条流水）
- **细粒度权限**：每个账户可单独为不同用户授权（查看 / 充值 / 支出 / 转账 / 审批）

### 用户体验
- 现代卡片风 UI，支持深色 / 浅色主题切换
- 完整移动端适配：底部 Tab 栏、侧滑抽屉菜单、底部弹出 Sheet 弹窗
- 管理员预创建账号，无开放注册

## 技术栈

| 层级 | 技术 |
|------|------|
| 后端 | Python 3.11 + FastAPI + SQLAlchemy |
| 数据库 | SQLite（持久化挂载到宿主机） |
| 认证 | JWT（python-jose） + bcrypt 密码哈希 |
| 前端 | 原生 HTML / CSS / JavaScript |
| 部署 | Docker Compose（Nginx + FastAPI） |

## 项目结构

```
Account/
├── docker-compose.yml          # 一键部署配置
├── data/                       # SQLite 数据库持久化目录（自动创建）
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── models.py               # 数据库模型
│   ├── auth.py                 # JWT 认证
│   └── main.py                 # FastAPI 路由与业务逻辑
└── frontend/
    ├── Dockerfile
    ├── nginx.conf              # 静态文件服务 + 反向代理
    └── html/
        ├── style.css           # 公共样式（含响应式）
        ├── utils.js            # 公共工具库
        ├── login.html          # 登录页
        ├── dashboard.html      # 仪表盘
        ├── accounts.html       # 账户管理（权限 + 审批链配置）
        ├── admin-users.html    # 用户管理（管理员专用）
        ├── transactions.html   # 流水记录列表
        ├── new-transaction.html # 新建流水表单
        └── approvals.html      # 审批中心
```

## 快速开始

### 前置要求
- Docker 20.10+
- Docker Compose v2+

### 启动

```bash
git clone git@github.com:chris15911053487-cyber/Account.git
cd Account
docker compose up --build -d
```

访问 `http://your-server-ip:8093`

### 默认账号

| 用户名 | 密码 | 角色 |
|--------|------|------|
| admin | admin123 | 管理员 |

> ⚠️ 生产环境请登录后立即修改默认密码，并在 `docker-compose.yml` 中更换 `SECRET_KEY`。

## 使用指南

### 1. 初始配置（管理员）

1. 用 `admin / admin123` 登录
2. 进入「用户管理」创建用户账号
3. 进入「账户管理」创建资金账户
4. 在账户详情中配置权限矩阵（哪些用户可以支出/充值/转账/审批）
5. 配置审批链（按顺序添加审批人，留空则提交后直接生效）

### 2. 日常记账

1. 点击「新建流水」或底部导航「＋记账」
2. 选择类型（支出 / 流入 / 转账）
3. 选择账户、填写金额和备注
4. 提交后流水进入待审批状态

### 3. 审批流程

1. 审批人登录后在「审批中心」查看待审批列表
2. 点击通过或拒绝，可填写审批意见
3. 所有审批节点通过后，账户余额自动更新

## API 文档

后端启动后访问 `http://your-server-ip:8093/api/docs` 查看完整 Swagger 文档。

## 数据持久化

SQLite 数据库文件存储在宿主机 `./data/ledger.db`，容器重建后数据不会丢失。

## 环境变量

在 `docker-compose.yml` 的 `backend` 服务下可配置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `SECRET_KEY` | `super-secret-key-change-in-production` | JWT 签名密钥，生产环境必须修改 |
| `DATABASE_URL` | `sqlite:////app/data/ledger.db` | 数据库连接地址 |

## License

MIT
