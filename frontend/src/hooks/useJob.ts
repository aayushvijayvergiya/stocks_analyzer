import { useState, useEffect, useRef } from 'react'
import { toast } from 'sonner'
import type { JobResult, JobStatus } from '@/lib/types'

interface UseJobOptions<T> {
  jobId: string | null
  fetcher: (id: string) => Promise<JobResult<T>>
  intervalMs?: number
}

interface UseJobResult<T> {
  status: JobStatus | null
  progress: string | null
  result: { top_sectors: T[] } | null
  error: string | null
}

export function useJob<T>({ jobId, fetcher, intervalMs = 2000 }: UseJobOptions<T>): UseJobResult<T> {
  const [status, setStatus] = useState<JobStatus | null>(null)
  const [progress, setProgress] = useState<string | null>(null)
  const [result, setResult] = useState<{ top_sectors: T[] } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!jobId) return

    // Reset state for new job
    setStatus('pending')
    setProgress(null)
    setResult(null)
    setError(null)

    intervalRef.current = setInterval(async () => {
      try {
        const data = await fetcher(jobId)
        setStatus(data.status)
        setProgress(data.progress ?? null)

        if (data.status === 'completed') {
          setResult(data.result ?? null)
          clearInterval(intervalRef.current!)
        } else if (data.status === 'failed') {
          setError(data.error ?? 'Analysis failed')
          clearInterval(intervalRef.current!)
          toast.error(data.error ?? 'Analysis failed')
        }
      } catch (err: unknown) {
        const error = err as Error & { status?: number; retry_after?: number }
        if (error.status === 503) {
          toast.error('Service temporarily unavailable')
        } else {
          toast.error('Could not reach server')
        }
        clearInterval(intervalRef.current!)
      }
    }, intervalMs)

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [jobId, fetcher, intervalMs])

  return { status, progress, result, error }
}
