"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  getTask,
  regenerateTask,
  type GenerateImagesResponse,
  type Task,
} from "@/lib/api";

/**
 * 主图 / 详情页共用的批量生成 + 子任务轮询 + 单张重生成逻辑。
 * runBatch 接收一个返回 GenerateImagesResponse 的异步调用（缺省注入 kind 等参数）。
 */
export function useBatchGeneration() {
  const [generating, setGenerating] = useState(false);
  const [subtasks, setSubtasks] = useState<Task[]>([]);
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const idsRef = useRef<string[]>([]);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const pollSubtasks = useCallback(async () => {
    const ids = idsRef.current;
    if (ids.length === 0) return;
    const list = (
      await Promise.all(ids.map((id) => getTask(id).catch(() => null)))
    ).filter((t): t is Task => t !== null);
    setSubtasks(list);
    if (
      list.length === ids.length &&
      list.every((t) => t.status === "done" || t.status === "failed")
    ) {
      stopPolling();
      setGenerating(false);
    }
  }, [stopPolling]);

  const startPolling = useCallback(
    (ids: string[]) => {
      idsRef.current = ids;
      stopPolling();
      void pollSubtasks();
      pollTimerRef.current = setInterval(() => void pollSubtasks(), 2000);
    },
    [pollSubtasks, stopPolling]
  );

  useEffect(() => () => stopPolling(), [stopPolling]);

  const runBatch = useCallback(
    async (run: () => Promise<GenerateImagesResponse>) => {
      setGenerating(true);
      setSubtasks([]);
      try {
        const res = await run();
        setSubtasks(res.subtask_ids.map((id) => ({ id }) as Task));
        startPolling(res.subtask_ids);
        return res;
      } catch (err) {
        setGenerating(false);
        throw err;
      }
    },
    [startPolling]
  );

  const regenerate = useCallback(
    async (taskId: string) => {
      await regenerateTask(taskId);
      setSubtasks((prev) =>
        prev.map((t) =>
          t.id === taskId ? { ...t, status: "pending", progress: 0 } : t
        )
      );
      startPolling(idsRef.current);
    },
    [startPolling]
  );

  const doneCount = subtasks.filter((t) => t.status === "done").length;

  return { generating, subtasks, doneCount, runBatch, regenerate };
}