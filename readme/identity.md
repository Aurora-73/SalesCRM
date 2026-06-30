# 身份目录

## 概述

`engine/identity/` 实现 Person→Account→Alias 三级身份映射。一个自然人可以有多个微信号（Account），每个微信号可以有多个别名（Alias）。所有工具函数通过人名查找联系人时，都依赖这个模块。

## 核心文件

| 文件 | 行数 | 功能 |
|------|------|------|
| `engine/identity/directory.py` | 533 | 身份目录全部实现 |
| `engine/identity/__init__.py` | ~20 | 导出公共接口 |

## 数据模型

### IdentityAccount（微信号）

```python
@dataclass(frozen=True)
class IdentityAccount:
    id: str              # acct_{hash}
    person_id: str       # 所属 person
    wxid: str            # 微信原始 ID（如 wxid_xxx）
    conversation_id: str # 会话 ID（通常 = wxid）
    display_name: str    # 显示名
    remark: str          # 备注
    nickname: str        # 微信昵称
    active: bool         # 是否活跃
```

### IdentityPerson（自然人）

```python
@dataclass(frozen=True)
class IdentityPerson:
    id: str              # person_{hash}
    display_name: str    # 主显示名
    real_name: str       # 真实姓名（可选）
    note: str            # 备注
    accounts: list[IdentityAccount]  # 该人的所有微信号
    aliases: list[dict]  # 别名列表 [{type, value, sensitivity, source}]
```

### ResolveResult（查找结果）

```python
@dataclass
class ResolveResult:
    found: bool
    person: IdentityPerson | None
    candidates: list[IdentityPerson]  # 模糊匹配时的候选列表
    message: str
```

## 数据库表

| 表 | 主键 | 说明 |
|---|------|------|
| `people` | id (TEXT) | 自然人（canonical_name/real_name/note） |
| `contact_accounts` | id (TEXT) | 微信号映射（person_id/wxid/conversation_id/display_name） |
| `contact_aliases` | person_id + type + value | 别名（display_name/wxid_suffix/remark/nickname） |
| `contact_identity_log` | id (TEXT) | 操作日志（merge/link/alias 等） |

## 关键函数

### bootstrap_identity

```python
def bootstrap_identity(conn: sqlite3.Connection) -> dict[str, int]:
    """从 contacts/conversations 表初始化身份目录。

    为每个联系人创建 person + account + 别名。
    返回 {'people': N, 'accounts': N, 'aliases': N}。
    """
```

首次运行或 contacts 表更新后调用。幂等操作，重复调用不会创建重复记录。

### resolve_contact

```python
def resolve_contact(conn: sqlite3.Connection, query: str) -> ResolveResult:
    """统一查找入口。

    按以下顺序尝试：
    1. person_id 精确匹配
    2. wxid 精确匹配
    3. alias 精确匹配（display_name/remark/nickname/wxid_suffix）
    4. alias 模糊匹配（LIKE %keyword%）
    """
```

这是所有工具函数查找联系人的核心函数。`query` 可以是人名、wxid、备注、昵称中的任意一个。

### merge_people

```python
def merge_people(conn, keep_person_id: str, merge_person_id: str) -> bool:
    """合并两个人为一个人。

    将 merge_person 的所有 account 和 alias 转移到 keep_person，
    删除 merge_person 记录。
    """
```

用于处理同一人有多个微信号的情况。

### link_account

```python
def link_account(conn, person_id: str, wxid: str) -> bool:
    """将一个微信号链接到指定 person。

    用于新发现的微信号归属到已有人物。
    """
```

### audit_identity

```python
def audit_identity(conn) -> dict[str, list[dict]]:
    """审计身份目录，返回：
    - duplicates: 同名不同 person 的疑似重复
    - orphans: 没有 account 的 person
    - unlinked: 没有 person 的 account
    """
```

## 数据流

```
tools.py: chat('小溪')
    ↓
core.py: _resolve_person(conn, '小溪')
    ↓
identity.resolve_contact(conn, '小溪')
    ↓
1. people 表查 person_id
2. contact_accounts 表查 wxid
3. contact_aliases 表查别名
    ↓
返回 IdentityPerson（含 accounts 列表）
    ↓
chat.py: 用 person.accounts[0].conversation_id 查消息
```

## 别名系统

每个 person 可以有多种类型的别名：

| type | 来源 | 示例 |
|------|------|------|
| `display_name` | bootstrap 时自动创建 | "小溪" |
| `remark` | bootstrap 时从 contacts.remark 创建 | "陈医生" |
| `nickname` | bootstrap 时从 contacts.nickname 创建 | "xxx" |
| `wxid_suffix` | bootstrap 时自动创建（wxid 后 6 位） | "qjgp22" |
| `manual` | 用户手动添加 | "阿琳" |

`normalize_alias()` 会将查询字符串统一转小写、去空格，确保匹配不受大小写影响。

## 注意事项

1. **bootstrap 必须先跑**：如果 `people` 表为空，所有 `resolve_contact` 都会失败。`sync(meta_only=True)` 会自动触发 bootstrap。
2. **person_id 生成规则**：`person_{wxid 的前 8 位 MD5}`，确定性生成，同一 wxid 永远得到同一 person_id。
3. **frozen dataclass**：`IdentityPerson` 和 `IdentityAccount` 是 frozen 的，不能修改。要改只能通过 `add_alias`/`set_display_name` 等函数操作数据库。
4. **多账号场景**：一个人有多个微信号时，`person.accounts` 会包含多个 account。`agent_chat` 默认用第一个 account 的 conversation_id。
