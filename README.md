# 页匠 AI｜PageCraft AI Studio — 电商商品图 AI 生成平台

Next.js 14 前端 + FastAPI 后端的 monorepo。上传商品图 → 三专家 LLM 流水线扩写 prompt → AI 生图（即梦 / 千问可切换）→ 一致性校验 → 图文混排叠加文字 → 导出。

## 功能总览

| 模块 | 功能 | 说明 |
|---|---|---|
| 商品会话 | 会话管理 | 创建 / 删除会话，上传 1~6 张商品实拍图作为资产容器 |
| | 类目识别 | LLM 自动识别商品类目，低置信度时给出候选供人工确认 |
| | 卖点提取 | 基于类目 + 用户描述提炼结构化卖点（RAG 视觉化词典辅助） |
| | 风格推荐 | 5 大风格（极简 ins / 日系和风 / 工业复古 / 赛博朋克 / 运动活力），RAG 推荐置顶 |
| 主图生成 | 一键 4 张 | 白底图 / 场景图 / 卖点特写 / 促销图，每张独立 prompt 可编辑、单独重生成 |
| | 三专家扩写 | 商品分析 → RAG 检索 → 视觉设计 → 质量评审（自动重试），提升出图质量 |
| | 图文混排 | 生成结果上叠加可拖拽文字（标题 / 卖点 / 价格），避免 AI 画中文乱码 |
| 详情页生成 | 自定义定位 | 自由添加 N 个详情图定位，批量生成，支持图文混排 |
| 文案创作 | 标题 / 主图文案 / 详情文案 | LLM 生成，结果回填图文混排快捷文案 |
| 设置 | 双厂商切换 | 语言模型（豆包 / 千问）与视觉模型（即梦 / 千问）独立选择，运行时即时生效 |
| 风格库 | 知识库浏览 | 查看 RAG 检索所用的风格模板（内置23种风格） |
| 通用 | 进度条 / 下载 | 单图与整批实时进度；单张下载 + 打包下载全部 |

## 使用教程

### 1. 环境准备

- Python 3.10+（后端 venv 已就绪则跳过）、Node.js 18+
- 复制环境变量模板并填入真实凭证：

```powershell
cd backend
copy .env.example .env   # PowerShell 用 Copy-Item 亦可
```

按所选厂商填写（详见模板内注释）：
- 火山引擎：`VOLCENGINE_AK/SK`（即梦生图）、`ARK_API_KEY` + `DOUBAO_MODEL`（豆包 LLM）
- 阿里云百炼：`DASHSCOPE_API_KEY`（千问 LLM + 生图共用），业务空间用户另改两个 `BASE_URL`
- `LLM_PROVIDER` / `IMAGE_PROVIDER` 决定默认厂商组合，之后可在设置页随时切换

### 2. 启动服务

```powershell
# 后端（端口 8000）
cd backend
.\venv\Scripts\python.exe -m uvicorn app.main:app --port 8000

# 前端（端口 3000，另开终端）
cd frontend
npm run dev
```

浏览器访问 `http://localhost:3000`。

### 3. 生成商品主图（核心流程）

1. **新建会话**：首页点「新建会话」，上传 1~6 张商品实拍图（JPEG/PNG/WebP）
2. **识别与提炼**：点「识别类目」→「提取卖点」，低置信度结果人工确认；可在 5 个风格中选用推荐的
3. **生成**：主图 Tab 点「生成 4 张主图」。每张图自动经历：三专家扩写（约 20~60s，进度条紫色）→ AI 生图（蓝色）→ 一致性校验 → 完成（绿色）
4. **人工干预**：不满意单张可改 prompt 后点「重生成」（直接用你改的 prompt，不再重复扩写）；一致性警告只提示不遮挡
5. **叠文字**：点卡片上「图文混排 · 编辑文字」，拖拽添加标题/卖点/价格（快捷文案来自文案 Tab），导出合成图
6. **保存**：hover 结果图点「下载」，或批次面板「下载全部（N 张）」。注意后端 `results/` 目录 7 天自动清理

> 无商品图直接生成会弹确认框，走文生图模式。

### 4. 详情页与文案

- **详情页 Tab**：添加定位（如「场景展示」「细节特写」）→ 批量生成 → 图文混排
- **文案 Tab**：生成标题 / 主图文案 / 详情文案，产出自动进入图文混排的快捷文案

### 5. 切换模型厂商

设置页（右上角「设置」）分「语言模型」「视觉模型」两组，各自下拉切换豆包/千问或即梦/千问，只显示所选厂商的配置项，保存后**立即生效无需重启**。设置页改的值优先于 .env；点字段旁的清除按钮回落 .env 默认值。

## 配置

- `backend/.env.example`：环境变量模板（含全部变量说明），复制为 `.env` 后填入真实值
- `backend/.env`：真实凭证与默认厂商，**不入库**（已在 .gitignore 屏蔽）
- 配置优先级：设置页（SQLite `app_settings`）> `.env` 默认值；清空设置页自定义值即回落 `.env`
- RAG 知识库位于 `backend/app/kb/`（markdown），向量库 Chroma 首次启动自动构建

## 测试

```powershell
cd backend
.\venv\Scripts\python.exe -m unittest discover -s tests

cd frontend
npx tsc --noEmit
```

## 目录结构

```
photo/
├── frontend/          # Next.js 14 + TypeScript + TailwindCSS
│   ├── app/           # 页面路由（工作区 / 设置 / 风格库 / 会话）
│   ├── components/    # session/ 为会话工作区组件（主图 / 详情 / 文案 / 图文混排）
│   └── lib/           # api.ts（后端接口封装 + 下载工具）
├── backend/           # FastAPI + Python
│   ├── app/
│   │   ├── api/       # 路由：sessions / tasks / settings / styles / uploads / ws
│   │   ├── services/  # llm（三专家）/ rag / jimeng / qwen / task_runner / graph / consistency
│   │   ├── models/    # Pydantic 模型
│   │   ├── kb/        # RAG 知识库（markdown）
│   │   └── config.py / database.py / main.py
│   ├── tests/         # 单元测试
│   ├── venv/          # Python 虚拟环境（不入库）
│   └── data/ uploads/ results/ logs/   # 运行时数据（不入库）
├── docs/              # 需求文档（v2 为现行）；archive/ 为历史归档
└── .trae/             # AI 协作文档
```
