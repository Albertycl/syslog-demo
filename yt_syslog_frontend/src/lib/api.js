import axios from 'axios'
import { API_BASE } from 'src/config/api'
import { demandName, user } from 'src/composables/useUser'

const http = axios.create({ baseURL: `${API_BASE}/api`, timeout: 15000 })

export const NAME_REQUIRED = 'Enter your name (top right) before making changes.'

// Every change (POST/PUT/DELETE) carries the person's name so it can be logged; without a name nothing is sent.
http.interceptors.request.use((config) => {
  if ((config.method || 'get').toLowerCase() === 'get') return config
  const name = (user.name || '').trim()
  if (!name) {
    demandName()
    return Promise.reject(Object.assign(new Error(NAME_REQUIRED), { response: { data: { error: NAME_REQUIRED } }, nameRequired: true }))
  }
  config.headers['X-User'] = encodeURIComponent(name)
  return config
})

export const api = {
  infras: () => http.get('/infras').then((r) => r.data),
  devices: (infra, folder) => http.get('/devices', { params: { infra, folder } }).then((r) => r.data),
  createDevice: (body) => http.post('/devices', body).then((r) => r.data),
  updateDevice: (id, body) => http.put(`/devices/${id}`, body).then((r) => r.data),
  deleteDevice: (id) => http.delete(`/devices/${id}`),
  rules: () => http.get('/rules').then((r) => r.data),
  settings: (id) => http.get(`/devices/${id}/settings`).then((r) => r.data),
  setSeverities: (id, severities) => http.put(`/devices/${id}/severities`, { severities }).then((r) => r.data),
  addKeyword: (id, keyword) => http.post(`/devices/${id}/keywords`, { keyword }).then((r) => r.data),
  deleteKeyword: (id) => http.delete(`/keywords/${id}`),
  addIgnore: (id, keyword) => http.post(`/devices/${id}/ignore`, { keyword }).then((r) => r.data),
  deleteIgnore: (id) => http.delete(`/ignore/${id}`),
  alerts: (params) => http.get('/alerts', { params }).then((r) => r.data),
  ack: (ids, who) => http.post('/alerts/ack', { ids, who }).then((r) => r.data),
  pause: (ids, until, who, folder, mute_same) => http.post('/alerts/pause', { ids, until, who, folder, mute_same }).then((r) => r.data),
  pauseRules: () => http.get('/pause-rules').then((r) => r.data),
  deletePauseRule: (id, unpause) => http.delete(`/pause-rules/${id}`, { params: { unpause: unpause ? 1 : undefined } }).then((r) => r.data),
  unpause: (ids) => http.post('/alerts/unpause', { ids }).then((r) => r.data),
  escalate: (ids, who) => http.post('/alerts/escalate', { ids, who }).then((r) => r.data),
  unescalate: (ids) => http.post('/alerts/unescalate', { ids }).then((r) => r.data),
  autoAck: () => http.get('/auto-ack').then((r) => r.data),
  addAutoAck: (device_ids, start, end) => http.post('/auto-ack', { device_ids, start, end }).then((r) => r.data),
  deleteAutoAck: (id) => http.delete(`/auto-ack/${id}`),
  folders: (infra) => http.get('/folders', { params: { infra } }).then((r) => r.data),
  addFolder: (infra, name) => http.post('/folders', { infra, name }).then((r) => r.data),
  renameFolder: (id, name) => http.put(`/folders/${id}`, { name }).then((r) => r.data),
  deleteFolder: (id) => http.delete(`/folders/${id}`).then((r) => r.data),
  keywordSummary: () => http.get('/keyword-summary').then((r) => r.data),
  addKeywordRule: (body) => http.post('/keyword-rules', body).then((r) => r.data),
  removeKeywordRule: (kind, keyword) => http.post('/keyword-rules/remove', { kind, keyword }).then((r) => r.data),
  addKeywordDevice: (kind, keyword, device_id) => http.post('/keyword-devices', { kind, keyword, device_id }).then((r) => r.data),
  removeKeywordDevice: (kind, keyword, device_id) => http.post('/keyword-devices/remove', { kind, keyword, device_id }).then((r) => r.data),
  audit: (params) => http.get('/audit', { params }).then((r) => r.data),
  collectRuns: (limit, errors) => http.get('/collect/runs', { params: { limit, errors: errors ? 1 : undefined } }).then((r) => r.data),
  collectStatus: () => http.get('/collect/status').then((r) => r.data),
  collect: (minutes, dry_run) => http.post('/collect', { minutes, dry_run }, { timeout: 120000 }).then((r) => r.data)
}

export function errorMessage (e) {
  if (e?.response?.data?.error) return e.response.data.error
  if (e?.code === 'ECONNABORTED') return 'The server took too long to respond.'
  return 'Cannot reach the server.'
}
