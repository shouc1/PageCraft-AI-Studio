"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Package, Plus, Trash2, Library } from "lucide-react";
import { AppHeader } from "@/components/layout/AppHeader";
import {
  ApiError,
  createSession,
  deleteSession,
  listSessions,
  type Session,
} from "@/lib/api";

export default function HomePage() {
  const router = useRouter();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    listSessions()
      .then(setSessions)
      .catch(() => setSessions([]))
      .finally(() => setLoading(false));
  }, []);

  const handleCreate = useCallback(async () => {
    if (creating) return;
    setCreating(true);
    try {
      const session = await createSession({ name: "未命名商品" });
      router.push(`/sessions/${session.id}`);
    } catch (e) {
      if (e instanceof ApiError && e.status === 0) {
        alert("创建会话失败：无法连接后端服务，请确认后端已启动（127.0.0.1:8000）");
      } else {
        alert(`创建会话失败：${e instanceof Error ? e.message : "未知错误"}`);
      }
    } finally {
      setCreating(false);
    }
  }, [creating, router]);

  const handleDelete = useCallback(
    async (e: React.MouseEvent, sessionId: string) => {
      e.preventDefault();
      e.stopPropagation();
      if (!confirm("确定删除该会话？关联图片与卖点资产会一并移除。")) return;
      try {
        await deleteSession(sessionId);
        setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      } catch {
        alert("删除失败");
      }
    },
    []
  );

  return (
    <main className="min-h-screen bg-slate-50">
      <AppHeader />

      <div className="mx-auto max-w-5xl p-6">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-xl font-semibold text-slate-900">商品会话</h1>
            <p className="mt-1 text-sm text-slate-500">
              主图 / 详情页 / 文案共享同一份商品资产，共 {sessions.length} 个会话
            </p>
          </div>
          <button
            className="flex h-10 items-center gap-2 rounded-lg bg-ink px-4 text-sm font-medium text-white transition hover:bg-slate-800 disabled:bg-slate-400"
            disabled={creating}
            onClick={handleCreate}
            type="button"
          >
            <Plus className="h-4 w-4" />
            {creating ? "创建中..." : "新建会话"}
          </button>
        </div>

        {loading ? (
          <p className="text-sm text-slate-500">加载中...</p>
        ) : sessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-slate-300 bg-white py-16 text-center">
            <Package className="mb-3 h-10 w-10 text-slate-300" />
            <p className="text-sm font-medium text-slate-700">暂无商品会话</p>
            <p className="mt-1 text-xs text-slate-500">
              新建会话后上传商品图，即可开始主图生成
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {sessions.map((session) => (
              <Link
                className="group rounded-lg border border-line bg-white p-4 transition hover:shadow-md"
                href={`/sessions/${session.id}`}
                key={session.id}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <h2 className="truncate text-base font-semibold text-slate-900">
                        {session.name || "未命名商品"}
                      </h2>
                      {session.category && (
                        <span className="shrink-0 rounded bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700">
                          {session.category}
                        </span>
                      )}
                    </div>
                    <p className="mt-2 flex items-center gap-4 text-xs text-slate-500">
                      <span className="inline-flex items-center gap-1">
                        图片 {session.images.length}/6
                      </span>
                      <span className="inline-flex items-center gap-1">
                        卖点 {session.selling_points.length}
                      </span>
                      {session.style && (
                        <span className="inline-flex items-center gap-1">
                          <Library className="h-3 w-3" />
                          {session.style}
                        </span>
                      )}
                    </p>
                    <p className="mt-1.5 text-xs text-slate-400">
                      {new Date(session.updated_at).toLocaleString("zh-CN")}
                    </p>
                  </div>

                  <button
                    className="rounded p-1.5 text-slate-400 transition hover:bg-red-50 hover:text-red-600"
                    onClick={(e) => handleDelete(e, session.id)}
                    title="删除会话"
                    type="button"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}