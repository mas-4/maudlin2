import { QueryClient, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { getJSON, postJSON } from './api'

export const client = new QueryClient({
  defaultOptions: { queries: { staleTime: 15_000, refetchOnWindowFocus: true, retry: 1 } },
})

/** One GET route, cached by its path and parameters */
export function useJSON<T>(path: string, params?: Record<string, string | number | boolean | undefined | null>, options?: { enabled?: boolean; refetchInterval?: number }) {
  return useQuery<T>({ queryKey: [path, params ?? {}], queryFn: () => getJSON<T>(path, params), ...options })
}

/** A write: posted, then everything shown is fetched again (any change may touch any view of the index) */
export function useWrite<Body, Out = unknown>(path = '/workbench') {
  const qc = useQueryClient()
  return useMutation<Out, Error, Body>({
    mutationFn: (body) => postJSON<Out>(path, body),
    onSettled: () => qc.invalidateQueries(),
  })
}
