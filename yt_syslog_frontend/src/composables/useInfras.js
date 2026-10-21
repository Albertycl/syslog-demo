import { reactive } from 'vue'
import { api } from 'src/lib/api'
import { INFRAS, SEVERITIES } from 'src/lib/format'
import { playAlerts, sound } from 'src/composables/useSound'
import { toast } from 'src/composables/useToast'

const blank = () => INFRAS.map((name) => ({
  name, devices: 0, open_alerts: 0, last_alert: null, newest_id: 0, folders: [],
  by_severity: Object.fromEntries(SEVERITIES.map((s) => [s, 0]))
}))

// One shared copy of the ALPHA / BRAVO summary, polled by the layout and read by every page.
export const infraState = reactive({ list: blank(), loaded: false, error: false })

let lastSeenId = null // newest open alert id we have already told the user about

async function announceNewAlerts (sinceId) {
  if (!sound.on) return
  const { items } = await api.alerts({ status: 'open', since_id: sinceId, limit: 50 })
  if (!items.length) return
  playAlerts([...new Set(items.map((a) => a.infra))]) // "Alpha alert" and/or "Bravo alert"
  const first = items.find((a) => a.keyword) || items[0]
  const kw = first.keyword ? ` · keyword “${first.keyword}”` : ''
  toast(items.length === 1
    ? `New ${first.infra} alert · ${first.host_name}${kw}`
    : `${items.length} new alerts · ${first.host_name}${kw}`)
}

export async function refreshInfras () {
  let list
  try {
    list = await api.infras()
  } catch (e) {
    infraState.error = true
    throw e
  }
  infraState.error = false
  infraState.list = list
  infraState.loaded = true

  const newest = Math.max(0, ...list.map((i) => i.newest_id))
  if (lastSeenId === null) { lastSeenId = newest; return } // first load: baseline only, stay quiet
  if (newest > lastSeenId) {
    const since = lastSeenId
    lastSeenId = newest // set before awaiting so overlapping refreshes don't announce twice
    try { await announceNewAlerts(since) } catch { /* a failed lookup must not break the poll */ }
  }
}
