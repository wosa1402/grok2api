# Grok DeepSearch 逆向分析报告

> 抓取时间: 2026-02-25
> 方法: 通过 MCP Chrome 服务注入 fetch 拦截器，对比普通聊天与 DeepSearch 的请求 payload

---

## 1. API Endpoint

普通聊天和 DeepSearch **使用同一个 endpoint**：

```
POST https://grok.com/rest/app-chat/conversations/new
```

---

## 2. Payload 对比

### 普通聊天 Payload

```json
{
  "temporary": false,
  "message": "test normal chat",
  "fileAttachments": [],
  "imageAttachments": [],
  "disableSearch": false,
  "enableImageGeneration": true,
  "returnImageBytes": false,
  "returnRawGrokInXaiRequest": false,
  "enableImageStreaming": true,
  "imageGenerationCount": 2,
  "forceConcise": false,
  "toolOverrides": {},
  "enableSideBySide": true,
  "sendFinalMetadata": true,
  "isReasoning": false,
  "disableTextFollowUps": false,
  "responseMetadata": {},
  "disableMemory": false,
  "forceSideBySide": false,
  "modelMode": "MODEL_MODE_EXPERT",
  "isAsyncChat": false,
  "disableSelfHarmShortCircuit": false,
  "deviceEnvInfo": {
    "darkModeEnabled": true,
    "devicePixelRatio": 1,
    "screenWidth": 1920,
    "screenHeight": 1080,
    "viewportWidth": 1920,
    "viewportHeight": 939
  }
}
```

### DeepSearch Payload (专家模式)

```json
{
  "temporary": false,
  "message": "test deepsearch chat",
  "fileAttachments": [],
  "imageAttachments": [],
  "disableSearch": false,
  "enableImageGeneration": true,
  "returnImageBytes": false,
  "returnRawGrokInXaiRequest": false,
  "enableImageStreaming": true,
  "imageGenerationCount": 2,
  "forceConcise": false,
  "toolOverrides": {},
  "enableSideBySide": true,
  "sendFinalMetadata": true,
  "isReasoning": false,
  "workspaceIds": [
    "1735c097-cfe2-42ec-809d-b2cd8e806e9d"
  ],
  "disableTextFollowUps": false,
  "responseMetadata": {},
  "disableMemory": false,
  "forceSideBySide": false,
  "modelMode": "MODEL_MODE_EXPERT",
  "isAsyncChat": false,
  "disableSelfHarmShortCircuit": false,
  "deviceEnvInfo": {
    "darkModeEnabled": true,
    "devicePixelRatio": 1,
    "screenWidth": 1920,
    "screenHeight": 1080,
    "viewportWidth": 1920,
    "viewportHeight": 939
  }
}
```

---

## 3. 关键差异

| 字段 | 普通聊天 | DeepSearch |
|---|---|---|
| `workspaceIds` | **不存在** | `["1735c097-cfe2-42ec-809d-b2cd8e806e9d"]` |

**唯一的区别就是 `workspaceIds` 字段。**

其他字段完全相同：
- `disableSearch` 相同 (`false`)
- `isReasoning` 相同 (`false`)
- endpoint 相同 (`/rest/app-chat/conversations/new`)

---

## 4. 多模型 + DeepSearch 测试结果

通过在 Grok 网页端切换不同模型模式，并启用 DeepSearch 后发送消息，抓取到以下结果：

| 选择的模式 | 实际发送的 modelMode | workspaceIds | modelName | 备注 |
|---|---|---|---|---|
| 快速模式 (Fast) + DeepSearch | `MODEL_MODE_FAST` | 有 | (not set) | 先开启 DeepSearch 再切换快速模式，保持 Fast 模式 |
| 专家模式 (Expert) + DeepSearch | `MODEL_MODE_EXPERT` | 有 | (not set) | 正常组合 |
| Grok 4.20 (Beta) + DeepSearch | `MODEL_MODE_GROK_420` | 有 | (not set) | 保持了 4.20 模式 |
| Heavy 模式 + DeepSearch | 未测试 | - | - | 需要 SuperGrok 订阅 |

### 关键结论

1. **DeepSearch 不限于特定模型** —— 它可以和任意模型模式组合使用（Fast / Expert / Grok 4.20 均已验证）
2. **核心机制就是在 payload 中添加 `workspaceIds`** 字段，其他参数保持原模型的设置
3. 操作顺序会影响前端行为：先选快速模式再点 DeepSearch 会被升级为专家模式，但**先点 DeepSearch 再切快速模式则保持 `MODEL_MODE_FAST`**
4. `modelName` 字段在所有测试中均未设置（前端不传），由 `modelMode` 决定使用的模型
5. `isReasoning` 在所有 DeepSearch 测试中均为 `false`

---

## 5. DeepSearch Workspace ID 来源

DeepSearch 的 workspace ID 来自 **页面内嵌的 feature flags**（存储在 localStorage 的 `xai-ff-bu` 键中）：

```json
{
  "config": {
    "deepsearch_workspace_id": {
      "workspaceId": "1735c097-cfe2-42ec-809d-b2cd8e806e9d"
    }
  }
}
```

### 获取方式

Feature flags 被嵌入在页面的 inline `<script>` 标签中（SSR 渲染），随页面加载自动写入 localStorage。

**注意**：此 workspace ID 可能是：
- 全局固定值（所有用户相同）—— 可能性更高
- 每个用户独立值 —— 需要进一步验证

---

## 6. 实现建议

### 方案：为现有模型添加 DeepSearch 变体

由于 DeepSearch 可以和任意模型模式组合，建议为需要支持的模型各添加一个 `-deepsearch` 变体：

#### 6.1 在 `ModelInfo` 中新增 `is_deepsearch` 标记

```python
class ModelInfo(BaseModel):
    # ... 现有字段 ...
    is_deepsearch: bool = False
```

#### 6.2 在 `model.py` 中添加 DeepSearch 模型变体

```python
ModelInfo(
    model_id="grok-3-deepsearch",
    grok_model="grok-3",
    model_mode="MODEL_MODE_EXPERT",
    tier=Tier.BASIC,
    cost=Cost.HIGH,
    display_name="GROK-3-DEEPSEARCH",
    is_deepsearch=True,
),
ModelInfo(
    model_id="grok-4.20-beta-deepsearch",
    grok_model="grok-420",
    model_mode="MODEL_MODE_GROK_420",
    tier=Tier.BASIC,
    cost=Cost.HIGH,
    display_name="GROK-4.20-BETA-DEEPSEARCH",
    is_deepsearch=True,
),
# 可按需为其他模型添加 deepsearch 变体
```

#### 6.3 在 `app/services/reverse/app_chat.py` 的 `build_payload` 中添加 `workspaceIds` 支持

```python
@staticmethod
def build_payload(
    message: str,
    model: str,
    mode: str = None,
    file_attachments: List[str] = None,
    tool_overrides: Dict[str, Any] = None,
    model_config_override: Dict[str, Any] = None,
    workspace_ids: List[str] = None,  # 新增
) -> Dict[str, Any]:
    # ... 现有代码 ...

    if workspace_ids:
        payload["workspaceIds"] = workspace_ids

    return payload
```

#### 6.4 在调用链中传递 `workspace_ids`

在 `GrokChatService.chat_openai()` 中根据 `model_info.is_deepsearch` 决定是否传入：

```python
workspace_ids = None
if model_info.is_deepsearch:
    workspace_ids = [DEEPSEARCH_WORKSPACE_ID]
```

#### 6.5 配置 DeepSearch Workspace ID

在 `config.toml` 或环境变量中添加配置项：

```toml
[deepsearch]
workspace_id = "1735c097-cfe2-42ec-809d-b2cd8e806e9d"
```

---

## 7. API 实际验证结果

> 验证时间: 2026-02-27
> 方法: 使用独立测试脚本（`test_deepsearch_full.py`），参考项目的 curl_cffi + 完整浏览器指纹模拟方式，直接调用 Grok API
> 完整原始数据: `deepsearch_results/` 目录

### 三种模型 + DeepSearch 均验证成功 (HTTP 200)

| 模型模式 | 状态 | 响应行数 | 思考长度 | 输出长度 | `grok:render` 引用 | webSearch | xSearch |
|---|---|---|---|---|---|---|---|
| `MODEL_MODE_FAST` | 200 | 1184 | 1,363 chars | 2,140 chars | **无** | 5 条 | 0 条 |
| `MODEL_MODE_EXPERT` | 200 | 2549 | 6,654 chars | 18,939 chars | **有** (大量) | 7 条 | 1 条 |
| `MODEL_MODE_GROK_420` | 200 | 2468 | 20,201 chars | 5,006 chars | **无** | 33 条 | 5 条 |

### DeepSearch 响应流中的特殊字段

相比普通聊天，DeepSearch 响应包含以下额外字段：

| 字段 | 说明 | Fast | Expert | Grok 4.20 |
|---|---|---|---|---|
| `webSearchResults` | 网页搜索结果（结构化） | 5 条 | 7 条 | **33 条** |
| `xSearchResults` | X/Twitter 搜索结果 | 无 | 1 条 | **5 条** |
| `toolUsageCard` | 工具使用卡片 | 有 | 有 | 有 |
| `toolUsageCardId` | 工具使用卡片 ID | 有 | 有 | 有 |
| `cardAttachment` | 引用卡片附件数据 | 无 | **49 条** | 无 |
| `survey` | 用户调查字段 | 无 | 有 | 无 |
| `rolloutId` | A/B 测试标识 | 无 | 无 | 有 |
| `messageStepId` | 多步骤消息标识 | 无 | 有 | 有 |
| `isThinking` | 思考状态标记 | 有 | 有 | 有 |
| `uiLayout` | UI 布局指令 | 有 | 有 | 有 |

### 各模式完整响应 keys

**Fast:**
```
finalMetadata, isSoftStop, isThinking, llmInfo, messageTag, modelResponse,
responseId, token, toolUsageCard, toolUsageCardId, uiLayout, userResponse,
webSearchResults
```

**Expert:**
```
cardAttachment, finalMetadata, isSoftStop, isThinking, llmInfo, messageStepId,
messageTag, modelResponse, responseId, survey, token, toolUsageCard, toolUsageCardId,
uiLayout, userResponse, webSearchResults, xSearchResults
```

**Grok 4.20:**
```
finalMetadata, isSoftStop, isThinking, llmInfo, messageStepId, messageTag,
modelResponse, responseId, rolloutId, token, toolUsageCard, toolUsageCardId,
uiLayout, userResponse, webSearchResults, xSearchResults
```

### 内联引用标记分析

**只有 Expert 模式的输出包含 `grok:render` 内联引用标记**：

```xml
<grok:render card_id="6b619a" card_type="citation_card" type="render_inline_citation">
  <argument name="citation_id">35</argument>
</grok:render>
```

| 检测项 | Fast | Expert | Grok 4.20 |
|---|---|---|---|
| `grok:render` 标签 | 无 | **有** | 无 |
| `citation_card` 标签 | 无 | **有** | 无 |
| `xai:tool_usage_card` 标签 (输出中) | 无 | 无 | 无 |
| `cardAttachment` 数量 | 0 | **49** | 0 |

> **注意**: `xai:tool_usage_card` 标签出现在 **thinking 内容** 中（而非 token 输出），所有模式的 thinking 都包含工具调用记录。

### Thinking 中的工具调用

DeepSearch 的 thinking 阶段包含搜索工具调用，格式为 `<xai:tool_usage_card>` 标签：

| 工具名称 | 说明 | Fast | Expert | Grok 4.20 |
|---|---|---|---|---|
| `web_search` | 网页搜索 | 有 | 有 | 有 (大量) |
| `web_search_with_snippets` | 带摘要的网页搜索 | 有 | 无 | 无 |
| `browse_page` | 浏览并提取网页内容 | 无 | 有 | 有 (大量) |
| `x_keyword_search` | X 关键词搜索 | 无 | 有 | 有 |
| `x_semantic_search` | X 语义搜索 | 无 | 无 | 有 |
| `chatroom_send` | 内部聊天室消息 | 无 | 无 | 有 |

Thinking 中的工具调用示例：
```xml
<xai:tool_usage_card>
  <xai:tool_usage_card_id>3930f4f2-49ef-4905-9f9a-0e4e26775428</xai:tool_usage_card_id>
  <xai:tool_name>web_search</xai:tool_name>
  <xai:tool_args><![CDATA[{"query":"最新 AI 新闻 2026年2月","num_results":10}]]></xai:tool_args>
</xai:tool_usage_card>
```

### `webSearchResults` 数据结构

每条搜索结果的结构：
```json
{
  "url": "https://example.com/article",
  "title": "文章标题",
  "preview": "文章摘要预览...",
  "searchEngineText": "",
  "description": "",
  "siteName": "",
  "metadataTitle": "",
  "creator": "",
  "image": "",
  "favicon": "",
  "citationId": ""
}
```

### 模式差异总结

1. **Fast 模式**: 最轻量，仅做基础网页搜索(5条)，思考最短(1.3K)，输出简洁(2.1K)，**无引用标记、无 X 搜索**
2. **Expert 模式**: 输出最长(18.9K)，包含 `grok:render` 内联引用(49个 cardAttachments)，有 X 搜索，有 `survey` 字段
3. **Grok 4.20 模式**: 搜索最深(33条 web + 5条 X)，思考最深(20.2K)，使用最多工具(含 browse_page、chatroom_send)，输出适中(5K)，**无引用标记**

### 输出格式差异

- **Fast**: 纯中文回答，末尾附 `**Key Citations:**` 列表（纯 URL 链接）
- **Expert**: 英文回答，内联 `grok:render` 引用标签，末尾附 `**Key Citations:**` 列表（含链接和说明）
- **Grok 4.20**: 中文回答，末尾附 `**Key Citations:**` 列表（含链接、标题和日期）

> **项目实现注意**: 如果配置 `app.filter_tags` 包含 `grok:render`，会过滤掉 Expert 的内联引用标记；如需保留引用信息，请确保不要过滤该标签，或在过滤前提取引用数据。

---

## 8. 待验证事项

1. **workspace ID 是否全局通用** —— 需要用不同账号验证
2. **rate-limits 请求** —— DeepSearch 发送时同时请求了 `POST /rest/rate-limits`，payload 为 `{"requestKind": "DEFAULT", "modelName": "grok-3"}`
3. **Heavy 模式 + DeepSearch** —— 是否支持（需要 SuperGrok 订阅验证）
4. **DeepSearch 是否有独立的 rate limit** —— 翻译文件中出现 `{{modelName}} with DeepSearch` 的限额提示，说明 DeepSearch 有独立计数
