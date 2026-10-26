# 项目目录整理计划（c:\work\photo）

## Context

项目历经多轮功能迭代（双厂商接入、三专家扩写、图文混排、下载功能等），根目录与子目录积累了构建产物、缓存、旧日志、重复依赖和过时文档，影响维护效率并占用约 2.4GB 冗余空间。用户要求「整理文件夹，让项目更好维护」。

**明确不做**：不动 `backend/app/`、`frontend/app|components|lib` 代码结构与 import 路径（重构风险高收益低）；不动运行时数据（`data/`、`uploads/`、`results/`、`data.db`、`.env`、`backend/models/` 嵌入模型）。

## Step 1：安全清理（直接删，预计释放 ~120MB）

- `frontend/.next/`（83.5MB 构建产物，dev/build 自动重建）
- `frontend/tsconfig.tsbuildinfo`、`frontend/dev.log`、`frontend/dev.err.log`
- 全部 `__pycache__/`（backend/app、tests 等）
- `backend/logs/` 旧轮转日志（保留最近 1 个 app.log）

## Step 2：用户已确认项（AskUserQuestion 已答复）

1. **`backend/.pkgs/`（1.16GB）→ 删除** ✅。已验证：无 PYTHONPATH/sys.path 注入，venv site-packages 已装 chromadb 1.5.9 等同名包。删除后跑依赖导入验证兜底
2. **根 `.git/`（假仓库，仅含 trae-ai-tob 日志）→ 移入 `docs/archive/trae-logs/` 后删除原目录** ✅
3. **空 `.agents/` → 删**（随整理一并执行）
4. **`docs/需求分析.md`（v1）→ 归档至 `docs/archive/需求分析-v1.md`** ✅
5. git init：**用户未选**，仅补根 .gitignore 备用，不执行 init

## Step 3：结构优化

1. 建 `docs/archive/`：归档 v1 需求文档 + `docs/superpowers/plans/` 旧计划
2. 补根 `.gitignore`（参考 `backend/.gitignore`）：`.next/`、`node_modules/`、`__pycache__/`、`venv/`、`.pkgs/`、`*.log`、`*.tsbuildinfo`、`.env`、`backend/{data,uploads,results,logs,models}/`
3. 补根 `README.md`：项目简介、前后端启动命令、目录结构说明
4. 可选：git init——用户未选，不执行

## Step 4：验证（清理后必须执行）

```powershell
# 1. 后端依赖完整性（.pkgs 删除后兜底验证）
cd c:\work\photo\backend
.\venv\Scripts\python.exe -c "import chromadb, aiohttp, uvicorn; print('deps ok')"
# 2. 后端全量单测（44 条基线）
.\venv\Scripts\python.exe -m unittest discover -s tests
# 3. 后端启动冒烟
.\venv\Scripts\python.exe -m uvicorn app.main:app --port 8000
# 4. 前端启动（.next 自动重建）+ tsc
cd c:\work\photo\frontend
npm run dev
npx tsc --noEmit
```

## 执行顺序

Step 1 → Step 2 提问 → 按用户选择执行删除/归档 → Step 3 → Step 4 验证 → 汇报释放空间与遗留建议
