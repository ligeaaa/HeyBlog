import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./api";

export function useBlogs() {
  return useQuery({
    queryKey: ["blogs"],
    queryFn: api.blogs,
    refetchInterval: 5000,
  });
}

export function useStatus() {
  return useQuery({
    queryKey: ["status"],
    queryFn: api.status,
    refetchInterval: 4000,
  });
}

export function useStats() {
  return useQuery({
    queryKey: ["stats"],
    queryFn: api.stats,
    refetchInterval: 4000,
  });
}

export function useRuntimeStatus() {
  return useQuery({
    queryKey: ["runtime-status"],
    queryFn: api.runtimeStatus,
    refetchInterval: 1500,
  });
}

export function useRuntimeCurrent() {
  return useQuery({
    queryKey: ["runtime-current"],
    queryFn: api.runtimeCurrent,
    refetchInterval: 1500,
  });
}

export function useCrawlerActions() {
  const queryClient = useQueryClient();

  const invalidateAll = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["blogs"] }),
      queryClient.invalidateQueries({ queryKey: ["status"] }),
      queryClient.invalidateQueries({ queryKey: ["stats"] }),
      queryClient.invalidateQueries({ queryKey: ["runtime-status"] }),
      queryClient.invalidateQueries({ queryKey: ["runtime-current"] }),
    ]);
  };

  return {
    bootstrap: useMutation({
      mutationFn: api.bootstrap,
      onSuccess: invalidateAll,
    }),
    start: useMutation({
      mutationFn: api.startCrawler,
      onSuccess: invalidateAll,
    }),
    stop: useMutation({
      mutationFn: api.stopCrawler,
      onSuccess: invalidateAll,
    }),
    runBatch: useMutation({
      mutationFn: api.runBatch,
      onSuccess: invalidateAll,
    }),
    resetDatabase: useMutation({
      mutationFn: api.resetDatabase,
      onSuccess: invalidateAll,
    }),
  };
}
