<template>
  <section>
    <h1 class="page-title">Log</h1>
    <p class="muted intro">Every change made in the portal: who did it, when, and what. Acknowledging, pausing, severity changes, devices, keywords, folders and more.</p>

    <div v-if="error" class="banner" role="alert"><span>Can't reach the backend.</span><button class="btn tiny" @click="refresh">Retry</button></div>

    <div class="toolbar">
      <select v-model="who" class="input w-select" aria-label="Person">
        <option value="">Everyone</option>
        <option v-for="a in actors" :key="a" :value="a">{{ a }}</option>
      </select>
      <select v-model="action" class="input w-select" aria-label="Type of change">
        <option value="">All changes</option>
        <option v-for="g in GROUPS" :key="g.code" :value="g.code">{{ g.label }}</option>
      </select>
      <input v-model="query" class="input w-search" type="search" placeholder="Search the log (device, keyword, folder…)" aria-label="Search the log">
      <span class="muted count-note">{{ total }} entr{{ total === 1 ? 'y' : 'ies' }}</span>
    </div>

    <div v-if="items.length" class="card table-wrap">
      <table class="table">
        <thead><tr><th>When</th><th>Who</th><th>Change</th><th>What happened</th></tr></thead>
        <tbody>
          <template v-for="r in items" :key="r.id">
            <tr :class="{ open: openId === r.id }" @click="openId = openId === r.id ? null : r.id">
              <td class="mono nowrap">{{ exactTime(r.ts) }}</td>
              <td class="nowrap"><b>{{ r.actor }}</b></td>
              <td class="nowrap"><span class="badge" :class="kind(r.action)">{{ r.label }}</span></td>
              <td>{{ r.summary }}</td>
            </tr>
            <tr v-if="openId === r.id" class="detail"><td colspan="4">
              <div class="meta muted">Entry #{{ r.id }} · from {{ r.ip || 'unknown address' }}<template v-if="r.target_type"> · {{ r.target_type }}<template v-if="r.target_id"> #{{ r.target_id }}</template></template></div>
              <ul v-if="r.details && r.details.alerts && r.details.alerts.samples && r.details.alerts.samples.length" class="samples">
                <li v-for="x in r.details.alerts.samples" :key="x.id"><b>{{ x.device }}</b> <span class="mono">{{ x.message }}</span></li>
              </ul>
              <pre v-if="r.details" class="json">{{ pretty(r.details.request) }}</pre>
            </td></tr>
          </template>
        </tbody>
      </table>
    </div>
    <div v-else-if="!loading" class="card empty">
      <h3>No entries</h3>
      <p class="muted">{{ who || action || query ? 'Nothing matches these filters.' : 'Changes made in the portal will appear here.' }}</p>
    </div>

    <div v-if="items.length < total" class="more">
      <button v-if="limit < MAX_ROWS" class="btn" @click="limit = Math.min(limit + 100, MAX_ROWS)">Load more <span class="muted">{{ items.length }} / {{ total }}</span></button>
      <span v-else class="muted">Showing the newest {{ MAX_ROWS }} of {{ total }}. Filter by person, type or text to find older entries.</span>
    </div>
  </section>
</template>

<script setup>
import { ref, watch } from 'vue'
import { api } from 'src/lib/api'
import { exactTime } from 'src/lib/format'
import { usePolling } from 'src/composables/usePolling'

const GROUPS = [
  { code: 'alert.*', label: 'Alerts (acknowledge, pause, escalate)' }, { code: 'severity.*', label: 'Severity' },
  { code: 'device.*', label: 'Devices' }, { code: 'keyword.*', label: 'Keywords' }, { code: 'ignore.*', label: 'Ignore keywords' },
  { code: 'folder.*', label: 'Folders' }, { code: 'pause.*', label: 'Muted errors released' }, { code: 'autoack.*', label: 'Auto-acknowledge' }, { code: 'collector.*', label: 'Logs pulled manually' }
]
const items = ref([])
const actors = ref([])
const total = ref(0)
const who = ref('')
const action = ref('')
const query = ref('')
const MAX_ROWS = 500 // the most the backend returns for one list
const limit = ref(100)
const openId = ref(null)

const { loading, error, refresh } = usePolling(async () => {
  const r = await api.audit({ who: who.value || undefined, action: action.value || undefined, q: query.value.trim() || undefined, limit: limit.value })
  items.value = r.items
  actors.value = r.actors
  total.value = r.total
}, 15000)

let t = null
watch([who, action, limit], refresh)
watch(query, () => { clearTimeout(t); t = setTimeout(refresh, 300) })

const kind = (code) => (code.startsWith('alert.') ? 'notice' : code.includes('remove') || code.includes('rule.remove') ? 'critical' : code.startsWith('severity') ? 'warning' : 'info')
const pretty = (o) => JSON.stringify(o, null, 2)
</script>

<style scoped>
.intro { margin-bottom: 16px; max-width: 75ch; }
.toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 14px; }
.w-select { width: 230px; }
.w-search { width: 340px; }
.count-note { margin-left: auto; }
.table-wrap { overflow-x: auto; }
.table { width: 100%; border-collapse: collapse; min-width: 820px; }
.table th { text-align: left; font-size: 13px; color: var(--muted); font-weight: 600; padding: 10px 12px; border-bottom: 1px solid var(--line); background: #fafbfc; }
.table td { padding: 9px 12px; border-bottom: 1px solid var(--line); vertical-align: top; }
.table tbody tr { cursor: pointer; }
.table tbody tr:hover { background: #f8f9fb; }
.table tr.detail { cursor: default; background: #fafbfc; }
.nowrap { white-space: nowrap; }
.meta { font-size: 13px; margin-bottom: 6px; }
.samples { margin: 4px 0; padding-left: 18px; font-size: 13px; display: grid; gap: 3px; }
.json { margin: 6px 0 0; padding: 8px 10px; background: #fff; border: 1px solid var(--line); border-radius: 6px; font-size: 12px; white-space: pre-wrap; word-break: break-word; max-height: 220px; overflow: auto; }
.empty { padding: 40px 20px; text-align: center; display: grid; gap: 6px; }
.empty h3 { font-size: 20px; }
.more { display: flex; justify-content: center; margin: 14px 0; }
@media (max-width: 860px) { .w-select, .w-search { width: 100%; } .count-note { margin-left: 0; } }
</style>
