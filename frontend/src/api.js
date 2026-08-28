import axios from 'axios'

let accessToken = null
export const setAccessToken = (t) => { accessToken = t }
export const getAccessToken = () => accessToken

export let currentBranchId = localStorage.getItem('currentBranchId') || null
export const setCurrentBranchId = (id) => {
  currentBranchId = id
  if (id == null) localStorage.removeItem('currentBranchId')
  else localStorage.setItem('currentBranchId', String(id))
}

const api = axios.create({ baseURL: '/api' })

api.interceptors.request.use((cfg) => {
  if (accessToken) cfg.headers.Authorization = `Bearer ${accessToken}`
  return cfg
})

let onRefreshFail = null
export const setRefreshFailHandler = (fn) => { onRefreshFail = fn }

api.interceptors.response.use(null, async (error) => {
  const original = error.config
  if (error.response?.status === 401 && !original._retried && !original.url.includes('/auth/')) {
    original._retried = true
    try {
      const res = await axios.post('/auth/refresh/', {}, { withCredentials: true })
      setAccessToken(res.data.access_token)
      original.headers.Authorization = `Bearer ${res.data.access_token}`
      return api(original)
    } catch (e) {
      if (onRefreshFail) onRefreshFail()
    }
  }
  return Promise.reject(error)
})

export default api
