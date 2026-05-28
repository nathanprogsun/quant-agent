import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { threadApi } from "@/core/threads";
import type { ThreadCreateParams, ThreadUpdateParams } from "@/core/threads";

export function useThreads() {
  return useQuery({
    queryKey: ["threads"],
    queryFn: () => threadApi.listThreads(),
  });
}

export function useThread(threadId: string | null) {
  return useQuery({
    queryKey: ["threads", threadId],
    queryFn: () => threadApi.getThread(threadId!),
    enabled: !!threadId,
  });
}

export function useCreateThread() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (params?: ThreadCreateParams) =>
      threadApi.createThread(params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["threads"] });
    },
  });
}

export function useUpdateThread() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      threadId,
      params,
    }: {
      threadId: string;
      params: ThreadUpdateParams;
    }) => threadApi.updateThread(threadId, params),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["threads"] });
    },
  });
}

export function useDeleteThread() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (threadId: string) => threadApi.deleteThread(threadId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["threads"] });
    },
  });
}
