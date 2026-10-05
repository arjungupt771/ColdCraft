import { useCallback, useRef, useState } from 'react'
import type { AsyncStatus } from '../types'
import { getErrorMessage } from '../lib/errors'

/** idle → loading → success | error, with retry of the last call. */
export function useAsyncAction<A extends unknown[], R>(fn: (...args: A) => Promise<R>) {
  const [status, setStatus] = useState<AsyncStatus>('idle')
  const [error, setError] = useState<string | null>(null)
  const lastArgs = useRef<A | null>(null)
  const fnRef = useRef(fn)
  fnRef.current = fn

  const run = useCallback(async (...args: A): Promise<R | undefined> => {
    lastArgs.current = args
    setStatus('loading')
    setError(null)
    try {
      const result = await fnRef.current(...args)
      setStatus('success')
      return result
    } catch (err) {
      setError(getErrorMessage(err))
      setStatus('error')
      return undefined
    }
  }, [])

  const retry = useCallback(() => (lastArgs.current ? run(...lastArgs.current) : Promise.resolve(undefined)), [run])
  const reset = useCallback(() => { setStatus('idle'); setError(null) }, [])

  return { status, error, run, retry, reset, isLoading: status === 'loading' }
}
