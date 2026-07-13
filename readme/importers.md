# 数据同步管道

## 概述

`engine/importers/` 负责从 WeFlow 或 WeChatDataAnalysis (WCD) 同步微信数据，以及从截图 OCR 导入非微信平台的聊天记录。

## 核心文件

| 文件 | 行数 | 功能 |
|------|------|------|
| `__init__.py` | 16 | 包导出（统一对外接口：WeFlowClient/WCDClient/run_sync/show_status 等） |
| `weflow_client.py` | 142 | WeFlow HTTP API 客户端（纯 urllib，无第三方依赖） |
| `wcd_client.py` | 521 | WCD HTTP API 客户端（兼容 WeFlowClient 接口） |
| `sync.py` | 290 | 同步编排器：health check → contacts → conversations → 私聊消息 → moments，含 `show_status()` |
| `sync_contacts.py` | 45 | 联系人同步（list_contacts → UPSERT contacts 表） |
| `sync_conversations.py` | 54 | 会话同步（list_sessions → UPSERT conversations 表） |
| `sync_messages.py` | 184 | 消息同步（get_messages → UPSERT messages 表） |
| `sync_moments.py` | 122 | 朋友圈同步（get_moments_timeline → UPSERT moments 表） |
| `checkpoint.py` | 151 | 同步水位记录（增量同步的断点续传） |
| `db_init.py` | 312 | 数据库初始化（建表、索引、迁移） |
| `screenshot_import.py` | 482 | 截图 OCR 导入主流程（含 `prepare_import`/`confirm_and_import`/`import_from_file`） |
| `screenshot_parser.py` | 337 | 截图消息解析（识别发送者、时间、内容） |
| `ocr_engine.py` | 172 | RapidOCR 封装（ONNX Runtime，带 MD5 缓存） |

> 按人同步的 `sync_person()` 不在本包内，位于 `engine/agent/sync_agent.py`，作为 Agent 层入口调用本包的同步原语。

## 数据后端选择

通过 `config.yaml` 的 `weflow.backend` 字段切换：

| 值 | 客户端 | 默认端口 | 说明 |
|----|--------|---------|------|
| `"wcd"` | WCDClient | 10392 | WeChatDataAnalysis（推荐） |
| `"weflow"` | WeFlowClient | 5031 | WeFlow（旧方案） |

```python
# sync.py 中的自动选择逻辑
if config.weflow.backend == "wcd":
    client = WCDClient(base_url, token, timeout, decrypted_db_dir)
else:
    client = WeFlowClient(base_url, token, timeout)
```

两个客户端接口完全兼容，上层同步代码零改动。

## WCD 启动方式

使用 WeChatDataAnalysis (WCD) 作为后端时，需要先启动 API 服务：

```bash
cd _reference/WeChatDataAnalysis
uv run main.py
```

默认在 `127.0.0.1:10392` 启动，可以通过以下方式验证：

```bash
curl http://127.0.0.1:10392/api/health
# {"status":"healthy","service":"微信解密工具"}
```

**常见问题**：

| 问题 | 处理 |
|------|------|
| `uv` 命令不存在 | 先安装 uv：`pip install uv` 或 `winget install uv` |
| 端口被占用 | 修改 `output/runtime_settings.json` 中的端口配置 |
| 启动后 API 返回 404 | 确认 `main.py` 在工作目录 `_reference/WeChatDataAnalysis/` 下执行 |
| 密钥不存在 | 首次使用需获取密钥，见下方"密钥管理" |

**注意**：WCD 会在启动时自动加载 `account_keys.json` 中的缓存密钥。如果密钥文件不存在，首次需要调用 `/api/get_keys`（会重启微信并要求扫码），之后密钥会持久化。

## WCDClient 字段映射

WCD API 返回格式与 WeFlow 不同，WCDClient 内部做映射：

| WCD 字段 | WeFlow 字段 | 说明 |
|----------|------------|------|
| `username` | `id` | 联系人 ID |
| `type` | `localType` | 消息类型 |
| `isSent` | `isSend` | 是否自己发送 |
| `quoteServerId` | `replyToMessageId` | 引用消息 ID |
| `emojiMd5` + `emojiUrl` | (构造 XML) | 贴纸 → `<msg><emoji md5="..." cdnurl="..."/></msg>` |

**关键**：`list_contacts()` 返回的 dict 必须同时包含 `id` 和 `username` 字段（值相同）。`sync_contacts` 用 `c.get("username", "")` 作为联系人 ID 写入数据库。`list_sessions()` 只需 `username` 字段。

标签提取：WCD API 不返回 labels，WCDClient 直接读取解密后的 `contact.db`，通过 protobuf 解析 `extra_buffer` field 30 获取标签 ID，再查 `contact_label` 表得到标签名。

## 同步流程

```
run_sync(config, mode='incremental')  # 默认增量，仅私聊
    │
    ├─ 1. health check（API 是否在线）
    ├─ 2. decrypt_databases（WCD：用缓存密钥刷新数据库快照，不重启微信）
    ├─ 3. sync_contacts（联系人 UPSERT）
    ├─ 4. sync_conversations（会话 UPSERT，自动判断 private/group/official）
    ├─ 5. 遍历所有私聊 session（WHERE type='private'）：
    │      sync_one_session(client, conn, session_id, since)
    │      ├─ 检查 checkpoint 水位（增量模式从上次继续）
    │      ├─ get_messages(talker, limit=500, offset=...)
    │      ├─ upsert_message()（ON CONFLICT 更新）
    │      ├─ 遇到空结果自动缩小 limit 重试（500→200→100，最多 3 次）
    │      └─ 更新 checkpoint
    └─ 6. sync_moments（朋友圈 timeline → moments + moment_interactions 表）
```

**数据库快照刷新**：WCD 后端在同步前自动调用 `/api/decrypt`（使用缓存密钥，不重启微信、不需要扫码）。解密节流：最近 30 分钟内成功解密过则自动跳过，标记文件 `output/.last_decrypt`。`force=True` 可强制解密。WeFlow 后端跳过此步骤。

**仅私聊**：消息同步默认只处理 `type='private'` 的会话（`wxid_` 开头或不含 `@` 的个人聊天）。群聊（`@chatroom`）和公众号（`gh_`）不会同步消息。

### 增量 vs 全量

- **incremental**（**默认**）：从 checkpoint 水位继续拉取，只拉新消息。日常使用此模式。
- **full**：忽略 checkpoint，从 offset=0 重新拉取全部。仅在数据修复时使用。

**原则：默认增量，尽量少用全量。** 全量同步耗时长（3000+ 秒），且数据通常不需要全量刷新。

### meta_only 模式

`run_sync(config, meta_only=True)` 只同步联系人和会话列表，不同步消息。用于快速刷新联系人搜索索引（约 1 秒）。

### 按人同步

`sync_person(name, mode='incremental')` 只同步指定联系人的消息。适合关注特定对象的增量更新。注意：按人同步不受私聊限制影响，可以同步任意指定会话。

> **位置**：`sync_person()` 定义在 `engine/agent/sync_agent.py`（Agent 层），不在 `engine/importers/`（同步原语层）。`engine/tools.py` 从 `sync_agent` 导入并对外暴露。

## 密钥管理

### WCD 密钥缓存机制

密钥存储在 `output/account_keys.json`（WCD 解密输出目录的父目录）。

1. **首次获取**：通过 `wx_key` 工具获取数据库密钥（需要微信扫码登录），或调用 WCD API `/api/get_keys`（会重启微信）
2. **持久化**：密钥保存到 `account_keys.json`，字段包括 `db_key`、`db_storage_path`、`image_xor_key`、`image_aes_key`
3. **重新解密**：当 WCD 联系人列表过期（新增好友不显示）时，用缓存密钥调用 `/api/decrypt` 重新解密

### 联系人列表过期的处理

WCD 的联系人来自解密后的数据库。新增微信好友后，WCD API 不会自动更新，需要手动重新解密：

```python
import json, urllib.request

# 读取缓存密钥
with open("output/account_keys.json") as f:
    keys = json.load(f)
account = list(keys.values())[0]

# 调用解密 API（不重启微信，不重新获取密钥）
data = json.dumps({
    "key": account["db_key"],
    "db_storage_path": account["db_key_source_db_storage_path"]
}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:10392/api/decrypt",
    data=data, headers={"Content-Type": "application/json"}, method="POST"
)
with urllib.request.urlopen(req, timeout=120) as resp:
    result = json.loads(resp.read())
# result: {"status": "completed", "success_count": 20, ...}
```

**判断是否需要重新解密**：WCD API `/api/chat/contacts` 返回的 `total` 少于微信实际好友数 → 需要重新解密。

**不要用 `/api/get_keys`**：该接口会重启微信并要求扫码，有封号风险。`/api/decrypt` 只用缓存密钥重新解密数据库文件，不影响微信运行。

### 配置示例

```yaml
weflow:
  backend: "wcd"
  base_url: "http://127.0.0.1:10392"
  decrypted_db_dir: "E:/Code/SalesCRM/_reference/WeChatDataAnalysis/output/databases"
```

`decrypted_db_dir` 指向 WCD 的解密输出目录，WCDClient 从中读取 `contact.db` 提取标签。

## 截图 OCR 导入

用于导入非微信平台（小红书、探探等）的聊天截图。

### 函数清单

| 函数 | 签名 | 作用 |
|------|------|------|
| `ensure_wechat_data` | `(conn, wxid) → (contact_info \| None, error \| None)` | 确保该联系人在本地数据库中且已有微信消息，返回联系人信息 |
| `prepare_import` | `(conn, wxid, screenshot_dir, platform="wechat", contact_info=None) → ImportPreview` | 执行 OCR 与解析，返回预览结果（不写入数据库） |
| `export_preview_json` | `(preview, output_path) → Path` | 将 ImportPreview 导出为 JSON 文件供用户编辑 |
| `confirm_and_import` | `(conn, preview) → ImportResult` | 用户确认预览后直接导入（程序内调用，无需 JSON 中转） |
| `import_from_file` | `(conn, preview_file) → ImportResult` | 从用户修改后的 JSON 预览文件导入消息 |
| `load_preview_json` | `(file_path) → (list[ParsedMessage], base_ts, wxid, platform)` | 解析用户编辑后的 JSON 预览文件 |

### 导入流程

```
Step 1: ensure_wechat_data(conn, wxid)
    │  确保该联系人在本地数据库中 + 已有微信消息
    │  内部自动：查本地 → 没找到 → sync_contacts + sync_conversations → 再查
    │  → 找到后检查是否有微信消息，没有则 sync_one_session
    │  → 返回 (contact_info, error)
    │
    │  ⚠️ 联系人找不到？
    │  → 检查 WCD 联系人数量是否与微信一致
    │  → 不一致：用缓存密钥调 /api/decrypt 重新解密（见"密钥管理"）
    │  → 仍然找不到：确认微信号是否正确
    │
Step 2: 截图放到 data/input/<名字>/ 目录下
    │
Step 3: prepare_import(conn, wxid, screenshot_dir, platform, contact_info)
    │  → OCR → 解析 → ImportPreview
    │  → export_preview_json(preview, output_path)
    │
Step 4: 用户编辑 JSON 预览文件
    │  → 修正 OCR 错字、删除 UI 元素、修正 sender
    │
Step 5: import_from_file(conn, preview_path)
    │  → 写入 messages 表（platform 字段标记来源）
    │
    │  或者：confirm_and_import(conn, preview)
    │  → 不经过 JSON 中转，直接用 ImportPreview 对象写入
```

**关键契约**：
1. 文件名排序 = 聊天时间顺序
2. 外部导入消息放在微信第一条消息之前 2 小时
3. 先导出 JSON 预览，用户编辑确认后才写入
4. 通过 wxid 唯一标识联系人
5. `prepare_import` 的 `contact_info` 参数由 `ensure_wechat_data` 返回，用于提取 display_name

**长截图处理**：OCR 引擎自动分片（高度 > 30000px 时按 30000px 切片），无需手动处理。

## 数据库表

| 表 | 主键 | 说明 |
|---|------|------|
| `contacts` | id (TEXT) | 联系人（nickname/remark/alias/display_name/labels） |
| `conversations` | id (TEXT) | 会话（type: private/group/official） |
| `messages` | id (TEXT) | 消息（conversation_id/sender_id/content/timestamp/type） |
| `attachments` | id (TEXT) | 附件（message_id/media_path） |
| `moments` | id (TEXT) | 朋友圈动态 |
| `moment_interactions` | id (TEXT) | 朋友圈互动（likes/comments） |
| `sync_state` | - | 同步水位记录 |
| `sync_log` | auto | 同步日志 |
| `contact_excludes` | wxid (TEXT) | 手动排除记录 |
| `contact_merges` | canonical_wxid (TEXT) | 账号合并记录 |
| `people` | id (TEXT) | 身份目录-自然人 |
| `contact_accounts` | id (TEXT) | 身份目录-微信号 |
| `contact_aliases` | person_id+type+value | 身份目录-别名 |
| `contact_identity_log` | id (TEXT) | 身份操作日志 |
| `schema_version` | version (INTEGER) | 数据库迁移版本记录 |

## 注意事项

1. **API 必须在线**：同步前会 health check，失败则抛 `SyncError`。
2. **仅同步私聊**：`run_sync()` 只处理 `type='private'` 的会话（个人聊天）。群聊和公众号的消息不会被同步。如需同步非私聊会话，直接调用 `sync_one_session()`。
3. **消息 ID 兜底**：如果 API 没返回 `serverId`，用内容 MD5 生成 ID。
4. **空结果重试**：WeFlow API 不稳定，相同参数有时返回 0 条消息有时返回数据。`sync_messages._fetch_messages_with_retry` 会自动缩小 limit（500→200→100）重试最多 3 次，只要某次返回非空即停止。
5. **会话类型判断**：`sync_conversations.py` 不信任 API 的 type 字段（全为 0），改用 session_id 模式判断：
   - `@chatroom` 在 session_id 中 → `group`
   - `gh_` 开头 → `official`
   - `wxid_` 开头 **或** session_id 不含 `@` → `private`
   - 其他 → 回退到 API type 字段映射
6. **OCR 缓存**：OCR 结果按图片 MD5 缓存在 `data/cache/ocr/`，避免重复识别。缓存超过 500MB 时自动清理最旧文件。
7. **WCD 联系人过期**：WCD 的联系人列表来自解密后的数据库快照，新增好友不会自动出现。需要调用 `/api/decrypt` 用缓存密钥重新解密。不要调用 `/api/get_keys`（会重启微信）。
8. **WCDClient 字段兼容**：`list_contacts()` 返回的 dict 必须包含 `username` 字段（`sync_contacts` 用它作为联系人 ID）。`list_sessions()` 同理。
