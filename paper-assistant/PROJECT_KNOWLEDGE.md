# 论文助手 · RAG 知识库

## 项目身份

- **名称**：论文助手（Paper Assistant）
- **定位**：面向科研人员的 AI 辅助 Web 应用
- **技术栈**：Python 3.10+ / FastAPI / SQLite / Jinja2 / PyMuPDF / python-pptx / Anthropic Claude API / Dify 工作流
- **启动方式**：`pip install -r requirements.txt && cd paper-assistant && python main.py`
- **访问地址**：`http://127.0.0.1:8000`
- **默认端口**：8000（修改 `main.py` 底部 `uvicorn.run` 的 `port` 参数可更改）

---

## 目录结构

```
paper-assistant/
├── main.py           # FastAPI 应用入口，定义全部路由（页面路由 + API 端点）
├── config.py         # 全局配置：目录路径、API Key、Dify 工作流 Key
├── models.py         # SQLite 数据库操作：建表、论文 CRUD、PPT 记录 CRUD
├── parser.py         # PDF 解析：文本提取（parse_pdf）、图片提取（extract_images）
├── analyzer.py       # AI 能力：论文结构化分析、单篇对话、多篇对比、PPT 内容生成、通用助手
├── generator.py      # PPTX 生成：create_presentation（新建）、append_to_presentation（追加）
├── searcher.py       # 学术搜索：arXiv API + OpenAlex 引用数据 + RRF 排序
├── skills.py         # 图表生成和文本润色的 System Prompt 与请求构建函数
├── requirements.txt  # Python 依赖清单
├── papers.db         # SQLite 数据库文件（自动创建）
├── templates/        # Jinja2 模板（base.html 为基类，其他页面继承之）
│   ├── base.html     # 基础布局：侧边栏导航 + MathJax 数学公式渲染 + 浮动 AI 助手
│   ├── index.html    # 首页：PDF 上传区 + 论文库表格 + 多选生成 PPT
│   ├── detail.html   # 论文详情：标题/作者/摘要/梗概/公式/图表/章节结构
│   ├── deepread.html # 论文精读：左侧结构化信息 + 右侧单篇 AI 对话
│   ├── discuss.html  # 多论文讨论：左侧勾选论文 + 右侧多篇 AI 对比对话
│   ├── generate.html # PPT 配置：选择每篇页数（2-6）、追加到已有 PPT
│   ├── search.html   # 论文搜索：输入关键词 → arXiv 搜索 → RRF 滑块排序 → 导入
│   ├── figure.html   # 图表生成：输入描述+数据 → AI 输出 matplotlib 代码
│   ├── polish.html   # 文本润色：粘贴文本 → AI 按 Nature 标准润色
│   └── publish.html  # 彩蛋页（跳转外部链接，无实际功能）
├── static/
│   └── style.css     # 全局样式：布局/表格/聊天/弹窗/浮动控件
├── uploads/          # PDF 上传存储目录
├── uploads/images/   # 从 PDF 提取的内嵌图片（按 paper_id 分子目录）
└── output/           # 生成的 PPTX 文件输出目录
```

---

## 数据库 schema

### 表 `papers`

| 字段 | SQL类型 | 含义 | 备注 |
|------|---------|------|------|
| id | INTEGER PK | 论文唯一ID | 自增 |
| filename | TEXT | 原始PDF文件名 | 搜索导入的论文此字段为 `[search] <url>` |
| title | TEXT | 论文标题 | 优先取PDF元数据，其次AI解析补全 |
| authors | TEXT | 作者 | 逗号分隔 |
| year | INTEGER | 出版年份 | 从元数据或正文正则提取 |
| abstract | TEXT | 摘要 | PDF解析时正则提取，AI解析后可能覆写 |
| overview | TEXT | 中文论文梗概 | AI生成，4-5句话 |
| sections | TEXT | 章节结构 | JSON数组，每项含 heading/summary/key_points |
| formulas | TEXT | 核心公式 | JSON字符串数组，纯LaTeX表达式（无$包裹） |
| images | TEXT | 提取的图片元数据 | JSON数组，每项含 page/filename/width/height |
| proper_figures | TEXT | 图表描述 | JSON字符串数组，AI生成，最多3项 |
| full_text | TEXT | PDF全文 | 截取前30000字符 |
| status | TEXT | 当前状态 | `uploaded` / `processing` / `done` / `error` |
| created_at | TEXT | 创建时间 | datetime('now') |

### 表 `presentations`

| 字段 | SQL类型 | 含义 | 备注 |
|------|---------|------|------|
| id | INTEGER PK | 记录ID | 自增 |
| name | TEXT | 汇报名称 | 格式：`组会汇报 YYYYMMDD_HHMMSS` |
| paper_ids | TEXT | 论文ID列表 | JSON数组 |
| slides_json | TEXT | 幻灯片内容 | JSON，含每页 title/bullets |
| pptx_path | TEXT | 文件路径 | 相对于 output/ 目录 |
| created_at | TEXT | 创建时间 | datetime('now') |

---

## 配置项（config.py）

| 变量名 | 默认值 | 作用 |
|--------|--------|------|
| BASE_DIR | paper-assistant 目录 | 项目根路径 |
| UPLOAD_DIR | {BASE_DIR}/uploads | PDF 上传目录 |
| OUTPUT_DIR | {BASE_DIR}/output | PPTX 输出目录 |
| IMAGES_DIR | {BASE_DIR}/uploads/images | PDF 图片提取目录 |
| DATABASE_PATH | {BASE_DIR}/papers.db | SQLite 数据库路径 |
| CLAUDE_API_KEY | 内置 | Anthropic Claude API 密钥 |
| DIFY_BASE_URL | http://localhost/v1 | Dify 服务基础 URL |
| DIFY_PAPER_ANALYSIS_KEY | 内置 | Dify 论文解析工作流 |
| DIFY_SLIDE_GEN_KEY | 内置 | Dify PPT 幻灯片生成工作流 |
| DIFY_CHAT_ASSISTANT_KEY | 内置 | Dify 浮动聊天助手工作流 |

所有配置项均可通过同名环境变量覆盖。AI 调用优先级：Dify 工作流 Key 非空时走 Dify，否则 fallback 到 Claude API 直接调用。

---

## 完整 API 清单

### 页面（返回 HTML）

- `GET /` — 首页
- `GET /paper/{paper_id}` — 论文详情
- `GET /generate?paper_ids=1,2,3` — PPT 生成配置页
- `GET /deepread` — 论文精读入口（自动跳转到第一篇 available 论文）
- `GET /deepread/{paper_id}` — 指定论文的精读页
- `GET /discuss` — 多论文讨论页
- `GET /search` — 论文搜索页
- `GET /figure` — 图表生成页
- `GET /polish` — 文本润色页
- `GET /publish` — 彩蛋页

### 数据操作

- `POST /upload` — 上传 PDF（multipart form，字段名 `file`）
- `POST /delete/{paper_id}` — 删除论文及 PDF 文件
- `POST /generate` — 生成组会 PPT（form：paper_ids / slide_count / append_to）
- `GET /download/{filename}` — 下载已生成的 PPTX
- `GET /images/{paper_id}/{filename}` — 访问 PDF 提取图片

### AI 功能（JSON 请求/响应）

- `POST /deepread/analyze/{paper_id}` — 触发 AI 解析论文，返回 `{"status":"done"}` 或 `{"error":"..."}`
- `POST /deepread/chat/{paper_id}` — 单篇论文对话，body: `{messages:[], question:"", system_prompt:""}`，返回 `{"response":"..."}`
- `POST /discuss/chat` — 多篇论文对比对话，body: `{paper_ids:[], messages:[], question:"", system_prompt:""}`，返回 `{"response":"..."}`
- `POST /api/search` — 搜索论文，body: `{query:"", limit:10}`，返回 `{"results":[{...}]}`
- `POST /api/search/import` — 导入搜索结果，body: `{paper:{title, authors, year, abstract, url}}`，返回 `{"paper_id":..., "status":"imported"}`
- `POST /api/figure` — 生成图表代码，body: `{description:"", data:"", extra_prompt:""}`，返回 `{"code":"..."}`
- `POST /api/polish` — 润色文本，body: `{text:"", extra_prompt:""}`，返回 `{"result":"..."}`
- `POST /api/chat-assistant` — 通用 AI 助手（浮动控件），body: `{question:"", messages:[], conversation_id:""}`，返回 `{"response":"...", "conversation_id":"..."}`

---

## 功能模块

### 模块1：PDF 上传与基础解析

- 用户通过首页 `<form>` 上传 `.pdf` 文件
- `parser.py:parse_pdf()` 使用 PyMuPDF 打开文件：
  - 从 PDF metadata 提取 title 和 author
  - 遍历所有页面拼接全文文本
  - 若 metadata 无标题，取首段 >20 字符的非 URL/arXiv/DOI 行作为标题
  - 正则匹配 `abstract` 段落提取摘要（100-3000 字符），失败则取首段适长段落
  - 从 metadata 或正文前 3000 字符中匹配四位数字年份
  - 全文截取前 30000 字符存入 `full_text` 字段
- `parser.py:extract_images()` 提取 PDF 内嵌图片：
  - 过滤宽/高 < 100px 的图标和装饰元素
  - 按图片内容哈希去重，保存到 `uploads/images/{paper_id}/`
  - 返回图片元数据 JSON 数组
- 入库后 status 为 `uploaded`，用户需前往精读页手动触发 AI 解析

### 模块2：AI 论文结构化分析

- 入口：精读页点击"开始解析"→ `POST /deepread/analyze/{paper_id}`
- `analyzer.py:analyze_paper()` 调用链路：
  1. 若 `DIFY_PAPER_ANALYSIS_KEY` 非空 → `_dify_call()` → Dify 工作流 API `POST /workflows/run`
  2. 否则 → Claude Sonnet 4.6 API 直接调用
  3. 响应文本经 `_parse_json()` 去 markdown fence 后解析为 dict
- AI 返回包含：title / authors / year / abstract / overview（中文梗概）/ sections（数组，每项 heading+summary+key_points）/ formulas（LaTeX 数组，最多3个，纯公式无 $ 包裹）/ figures（图表描述数组，最多3个）
- 解析成功 status → `done`，失败 → `error`
- 注意：`sections` 存储格式为 JSON 数组（也可能为 `{sections:[...]}` 对象，由 `_parse_sections()` 兼容）

### 模块3：单篇论文 AI 对话

- 入口：精读页右侧聊天区 → `POST /deepread/chat/{paper_id}`
- `analyzer.py:chat_about_paper()` 实现：
  1. 构建论文上下文字符串（标题、作者、年份、摘要、梗概、章节结构、公式、图表描述）
  2. 将上下文作为首轮 user message 发给 Claude
  3. 拼接前端传来的 messages 对话历史
  4. 追加当前 question
  5. 调用 Claude Sonnet 4.6，支持自定义 System Prompt
- 默认 System Prompt（`CHAT_SYSTEM_PROMPT`）定义在 analyzer.py，包含完整论文研读方法论
- 对话仅走 Claude API，不走 Dify
- 支持 MathJax 渲染回复中的 LaTeX 公式

### 模块4：组会 PPT 生成

- 流程：首页勾选论文 → 配置页选择页数（2-6）和追加选项 → 提交生成
- `analyzer.py:generate_slide_content()` 获取幻灯片 JSON：
  1. 若 `DIFY_SLIDE_GEN_KEY` 非空 → Dify 工作流
  2. 否则 → Claude API（`_slide_prompt_for_count()` 根据页数构造不同的幻灯片模板）
- 页数对应的幻灯片结构：
  - 2页：Overview & Background / Method & Results
  - 3页：Problem & Motivation / Algorithm & Innovation / Experiments & Results
  - 4页：Background & Motivation / Algorithm Design / Experimental Evaluation / Conclusion & Discussion
  - 5页：Motivation / Method Overview / Algorithm Details / Experiments / Conclusion
  - 6页：Motivation / Related Work / Method Overview / Technical Details / Experiments & Analysis / Conclusion & Contribution
- `generator.py` 生成 PPTX：
  - `create_presentation()` — 新建，含封面页 + 每篇论文的内容页 + 图表页
  - `append_to_presentation()` — 追加到已有文件，先插入分隔页再追加新内容
- PPTX 样式：16:9 宽屏（13.333×7.5英寸），蓝色主题 #1A56DB，标题 30pt，正文 20pt，深灰色 #222222
- 文件命名：`group_meeting_YYYYMMDD_HHMMSS.pptx`
- 若某篇论文的幻灯片生成失败（JSON 解析异常），跳过该论文，其余继续生成

### 模块5：多论文对比讨论

- 入口：侧边栏 → 多论文讨论 → `GET /discuss`
- 仅展示 status=done 的论文，至少需选择 2 篇
- `analyzer.py:chat_about_multiple_papers()` 实现：
  1. 为每篇论文构建结构化上下文（标注 `[论文N]` 编号）
  2. 拼接对话历史
  3. 调用 Claude Sonnet 4.6，使用 `MULTI_CHAT_SYSTEM_PROMPT`
- System Prompt 核心规则：强制 `[论文N]` 标注来源 / 主动横向对比 / 对比性问题用表格 / 区分事实与推断（推断标"推断："）
- 支持从 URL 参数 `papers` 预选论文
- 对话仅走 Claude API，不走 Dify

### 模块6：学术论文搜索

- 入口：侧边栏 → 谷歌搜索 → `GET /search`
- `searcher.py:search_papers()` 实现：
  1. 调用 arXiv API（`http://export.arxiv.org/api/query?search_query=all:{query}`），获取 30 篇候选
  2. 若 arXiv 无结果 → fallback 到 CrossRef API
  3. `_enrich_citations()` 逐篇查询 OpenAlex API 补充 `cited_by_count`
  4. 结果返回给前端
- 前端 RRF 排序：滑块 α ∈ [0,1] 调节时间/引用权重，`score = α × (1/date_rank) + (1-α) × (1/cite_rank)`，纯前端计算，实时重排，显示 Top 10
- 导入功能：`POST /api/search/import` 将选中论文入库，并自动触发 AI 解析（用标题+作者+年份+摘要构建伪全文）

### 模块7：科研图表生成

- 入口：侧边栏 → 图表生成 → `GET /figure`
- `POST /api/figure` → `skills.py:figure_prompt()` 构建 prompt → `analyzer.py:call_claude()` 调用 Claude
- System Prompt（`FIGURE_SYSTEM_PROMPT`）规定：Nature 期刊标准 / matplotlib / Arial 7pt / 移除右上边框 / 低饱和度配色 / 输出 SVG+PDF+TIFF / 仅输出纯 Python 代码
- 用户可提供 CSV/JSON 数据（可选），未提供时 AI 使用演示数据

### 模块8：学术文本润色

- 入口：侧边栏 → 文本润色 → `GET /polish`
- `POST /api/polish` → `skills.py:polish_prompt()` 构建 prompt → `analyzer.py:call_claude()` 调用 Claude
- System Prompt（`POLISH_SYSTEM_PROMPT`）规定：Nature 期刊编辑标准 / 语言服务于论述 / 不编造数据 / 中文输入翻译为地道英语 / 避免 em dash / 仅输出润色后文本

### 模块9：浮动 AI 助手

- 位置：所有页面右下角蓝色圆形按钮（💬），z-index: 9000
- 点击弹出 380×520 聊天窗口，再次点击或按 ESC 或点击窗口外部关闭
- `POST /api/chat-assistant` → `analyzer.py:chat_assistant()` → Dify 工作流 `POST /workflows/run`（输入键 `query`）
- 后端将最近 8 条消息拼成对话历史嵌入 query，支持多轮上下文感知
- 前端自动存储 `conversation_id` 实现会话持续
- 回复中 LaTeX 由 MathJax 自动渲染
- 输入框自适应高度（最大 80px），Enter 发送 / Shift+Enter 换行

---

## AI 调用架构

```
用户请求
  ↓
analyzer.py 各函数
  ↓
检查 Dify Key 是否非空
  ├── 是 → _dify_call(api_key, inputs)
  │         ↓
  │       POST {DIFY_BASE_URL}/workflows/run (或 /chat-messages)
  │         ↓
  │       返回文本（从 outputs.result / outputs.text / answer 提取）
  │
  └── 否 → Anthropic SDK (_ANTHROPIC_CLIENT.messages.create)
            ↓
          模型: claude-sonnet-4-6, max_tokens: 2048-4096
            ↓
          返回 TextBlock.text
```

特殊说明：
- `chat_assistant()` 始终走 Dify Workflow API，无 Claude fallback
- 浮动助手的工作流输出字段名可能非标准（如 `hh`），代码已做 fallback：依次尝试 `result` → `text` → outputs 第一个值
- Dify 请求超时 600 秒，Claude API 超时 600 秒

---

## 前端公共机制

- **MathJax**：base.html `<head>` 引入 MathJax 3，配置行内 `$...$` 和块级 `$$...$$`；每次 AI 回复渲染后调用 `MathJax.typesetPromise()`
- **侧边栏**：固定左侧 220px，z-index: 100；小屏（<768px）收缩为 60px 仅图标
- **Loading 遮罩**：index.html 定义的 `showLoading()` 函数，z-index: 9999；在上传提交时触发
- **Lightbox**：deepread.html 和 detail.html 定义，点击图片放大，z-index: 9999，ESC 关闭
- **浮动助手**：base.html 定义，z-index: 9000（低于 lightbox 高于侧边栏），ESC 关闭时先检查 lightbox 是否存在
- **对话通用模式**：打字指示器（.typing-dots 三圆点动画）、多轮消息数组、isWaiting 发送锁

---

## System Prompt 速览

| 常量 | 定义位置 | 用途 | 模型 |
|------|----------|------|------|
| SYSTEM_PROMPT | analyzer.py | 论文结构化分析 / PPT 内容生成 | Claude Sonnet 4.6 |
| CHAT_SYSTEM_PROMPT | analyzer.py | 单篇论文对话（论文研读方法论） | Claude Sonnet 4.6 |
| MULTI_CHAT_SYSTEM_PROMPT | analyzer.py | 多篇论文对比讨论 | Claude Sonnet 4.6 |
| FIGURE_SYSTEM_PROMPT | skills.py | 科研图表 matplotlib 代码生成 | Claude Sonnet 4.6 |
| POLISH_SYSTEM_PROMPT | skills.py | 学术文本 Nature 标准润色 | Claude Sonnet 4.6 |
| _slide_prompt_for_count() | analyzer.py | 按页数构造 PPT 幻灯片模板 | Claude Sonnet 4.6 |

---

## 常见问题

**Q: 上传 PDF 后首页不显示论文？**
检查 `uploads/` 目录写入权限、PDF 是否损坏。查看终端错误日志。

**Q: AI 解析一直显示"处理中"（status=processing）？**
检查 CLAUDE_API_KEY 或 Dify 工作流 Key 是否有效。精读页每 5 秒自动刷新轮询状态。

**Q: AI 解析返回 status=error？**
通常是 API Key 无效、额度耗尽、或论文文本超过 token 限制（full_text 截取前 30000 字符）。

**Q: 生成的 PPT 内容缺少某篇论文？**
AI 可能对该论文返回了不完整 JSON（JSONDecodeError / KeyError），该论文被跳过。查看终端错误日志确认具体原因。

**Q: 论文精读页的 AI 对话不可用？**
此功能仅走 Claude API（不走 Dify），确认 CLAUDE_API_KEY 有效且网络能访问 api.anthropic.com。

**Q: 浮动 AI 助手对话无响应或报错？**
浮动助手仅走 Dify Workflow API（`DIFY_CHAT_ASSISTANT_KEY`），确认 Key 有效且 DIFY_BASE_URL 可访问。当前 Key 对应的是 Workflow 类型 App（非 Chat 类型），使用 `/workflows/run` 端点。

**Q: 图表生成的代码本地运行报错？**
需安装 matplotlib。代码默认使用演示数据，替换为实际数据再运行。

**Q: 搜索不到论文？**
arXiv API 对中文支持有限，尝试英文关键词。确认网络能访问 `export.arxiv.org` 和 `api.openalex.org`。

**Q: 端口 8000 被占用？**
修改 `main.py` 底部 `uvicorn.run(app, host="127.0.0.1", port=8000)` 中的端口号。

**Q: 如何切换 Dify 和 Claude API？**
将 config.py 中对应功能的 Dify Key 设为空字符串即自动 fallback 到 Claude API。反之设为有效 Key 则走 Dify。
