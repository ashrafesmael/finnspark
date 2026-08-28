import { useEffect, useState } from 'react'
import api from '../api'

export function useFetch(url, deps = [], enabled = true) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [tick, setTick] = useState(0)
  const reload = () => setTick((x) => x + 1)

  useEffect(() => {
    if (!enabled || !url) return
    let alive = true
    setLoading(true)
    api.get(url).then((res) => {
      if (alive) { setData(res.data); setError(null) }
    }).catch((e) => {
      if (alive) setError(e.response?.data?.detail || e.message)
    }).finally(() => { if (alive) setLoading(false) })
    return () => { alive = false }
  }, [url, enabled, tick, ...deps])

  return { data, loading, error, reload }
}
