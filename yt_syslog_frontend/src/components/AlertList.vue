<template>
  <div>
    <div v-if="error" class="banner" role="alert">
      <span>Can't reach the backend.</span>
      <button class="btn tiny" @click="refresh">Retry</button>
    </div>

    <div class="toolbar">
      <div v-if="!fixedStatus" class="tabs" role="group" aria-label="Status">
        <button v-for="s in STATUSES" :key="s.key" class="tab" :aria-pressed="status === s.key" @click="status = s.key">{{ s.label }}</button>
      </div>
      <select v-if="!deviceId" v-model="deviceFilter" class="input w-select" aria-label="Device">
        <option :value="null">All devices ({{ devices.length }})</option>
        <option v-for="d in devices" :key="d.id" :value="d.id">{{ d.name }}{{ d.open_alerts ? ` · ${d.open_alerts} open` : '' }}</option>
      </select>
      <select v-model="severity" class="input w-select" aria-label="Severity">
        <option value="">All severities</option>
        <option v-for="s in SEVERITIES" :key="s" :value="s">{{ SEVERITY_LABEL[s] }}</option>
      </select>
      <label class="check-inline"><input v-model="keywordOnly" type="checkbox"> Keyword matches only</label>
      <label class="check-inline"><input v-model="escalatedOnly" type="checkbox"> Escalated to NET only</label>
      <input v-model="query" class="input w-search" type="search" placeholder="Search message or device" aria-label="Search alerts">
    </div>

    <div v-if="items.length" class="card table-wrap">
      <table class="table">
        <thead>
          <tr>
            <th class="c-check"><input type="checkbox" :checked="allSelected" :disabled="!selectable.length" aria-label="Select all on this page" @change="toggleAll"></th>
            <th>Severity</th><th>Time</th><th>Device</th><th>Message</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="a in items" :key="a.id" :class="{ done: a.acked, open: expanded === a.id }" @click="toggle(a.id)">
            <td class="c-check" @click.stop>
              <input v-model="selected" type="checkbox" :value="a.id" :disabled="a.acked" :aria-label="`Select alert on ${a.host_name}`">
            </td>
            <td><span class="badge" :class="a.severity">{{ SEVERITY_LABEL[a.severity] }}</span></td>
            <td class="c-time"><span>{{ clock(a.timestamp) }}</span><small class="muted">{{ timeAgo(a.timestamp) }}</small></td>
            <td class="c-dev">
              <router-link v-if="deviceIdFor(a)" :to="{ name: 'device', params: { id: deviceIdFor(a) } }" class="dev-link" @click.stop><b>{{ a.host_name }}</b></router-link>
              <b v-else>{{ a.host_name }}</b>
              <small class="mono muted">{{ a.host_address }}</small>
            </td>
            <td class="c-msg">
              <span class="flags">
                <span v-if="a.keyword" class="badge kw">Keyword: {{ a.keyword }}</span>
                <span v-if="a.escalated" class="badge net">Escalated to NET{{ a.escalated_by ? ` by ${a.escalated_by}` : '' }}</span>
                <span v-if="a.paused" class="badge paused">Paused until {{ clock(a.paused_until) }}{{ a.paused_by ? ` · ${a.paused_by}` : '' }}</span>
              </span>
              <span class="mono msg">{{ a.message }}</span>
              <small v-if="a.acked" class="muted">Acknowledged by {{ a.acked_by || 'unknown' }}</small>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else-if="!loading" class="card empty">
      <h3>{{ emptyTitle }}</h3>
      <p class="muted">{{ emptyText }}</p>
    </div>
    <p v-else class="muted">Loading alerts…</p>

    <div v-if="items.length" class="foot">
      <span class="muted">Showing {{ items.length }} of {{ total }}</span>
      <button v-if="items.length < total && limit < MAX_ROWS" class="btn" @click="limit = Math.min(limit + 100, MAX_ROWS)">Load more</button>
      <span v-else-if="items.length < total" class="muted">Showing the newest {{ MAX_ROWS }}. Narrow the filters to see the rest.</span>
    </div>

    <div v-if="canAct && selected.length" class="actions card" role="region" aria-label="Actions for selected alerts">
      <input :value="user.name" class="input who" :class="{ missing: !hasName }" placeholder="Your name (required)" aria-label="Your name" maxlength="40" @input="setName($event.target.value)">
      <span v-if="!hasName" class="need-name" role="alert">Enter your name to continue</span>
      <template v-if="status === 'paused'">
        <button class="btn primary" :disabled="busy || !hasName" @click="unpause(selected)">Unpause selected ({{ selected.length }})</button>
      </template>
      <template v-else>
        <button class="btn primary" :disabled="busy || !hasName" @click="ack(selected)">Acknowledge ({{ selected.length }})</button>
        <button class="btn" :disabled="busy || !hasName" @click="openPause">Pause…</button>
        <button class="btn" :disabled="busy || !hasName" @click="escalate(selected)">Escalate to NET</button>
        <button v-if="selectedEscalated" class="btn" :disabled="busy || !hasName" @click="unescalate(selected)">Undo escalate</button>
      </template>
      <button class="btn" @click="selected = []">Clear</button>
    </div>
    <div v-else-if="canAct && status === 'open' && openTotal" class="actions card">
      <span class="muted">Tick alerts to acknowledge, pause or escalate them.</span>
      <button class="btn" :disabled="busy || !hasName" :title="hasName ? '' : 'Enter your name (top right) first'" @click="ackAll">Acknowledge all {{ openTotal }} open</button>
    </div>

    <dialog ref="pauseDialog" class="sheet">
      <form class="sheet-body" @submit.prevent="confirmPause">
        <h2>Pause {{ selected.length }} alert{{ selected.length === 1 ? '' : 's' }}</h2>
        <p class="muted">They disappear from the open list until the time you choose, then come back if still unacknowledged.</p>
        <div class="quick">
          <button v-for="q in QUICK" :key="q.label" type="button" class="tab" @click="setQuick(q.hours)">{{ q.label }}</button>
        </div>
        <label class="mute-opt"><input v-model="muteSame" type="checkbox">
          <span><b>Also mute the same error</b> from these devices until then<br><small class="muted">New alerts that are identical apart from the time, process number or port won't alarm. They are kept under Paused alerts.</small></span>
        </label>
        <div class="field">
          <label for="p-until">Pause until</label>
          <input id="p-until" v-model="pauseUntil" class="input" type="datetime-local" required>
          <span class="err" role="alert">{{ pauseError }}</span>
        </div>
        <div class="sheet-actions">
          <button type="button" class="btn" @click="pauseDialog.close()">Cancel</button>
          <button type="submit" class="btn primary" :disabled="busy">Pause alerts</button>
        </div>
      </form>
    </dialog>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { api, errorMessage } from 'src/lib/api'
import { SEVERITIES, SEVERITY_LABEL, clock, timeAgo } from 'src/lib/format'
import { infraState, refreshInfras } from 'src/composables/useInfras'
import { usePolling } from 'src/composables/usePolling'
import { setName, user } from 'src/composables/useUser'
import { toast } from 'src/composables/useToast'

const props = defineProps({
  infra: { type: String, default: '' },
  folder: { type: String, default: '' },
  deviceId: { type: Number, default: null },
  fixedStatus: { type: String, default: '' } // e.g. 'paused' for the Paused page
})
const emit = defineEmits(['loaded'])

const STATUSES = [
  { key: 'open', label: 'Open' }, { key: 'paused', label: 'Paused' },
  { key: 'acked', label: 'Acknowledged' }, { key: 'all', label: 'All' }
]
const QUICK = [{ label: '1 hour', hours: 1 }, { label: '4 hours', hours: 4 }, { label: 'Tomorrow 09:00', hours: 'tomorrow' }, { label: '1 week', hours: 168 }]

const MAX_ROWS = 500 // the most the backend returns for one list
const status = ref(props.fixedStatus || 'open')
const severity = ref('')
const query = ref('')
const deviceFilter = ref(null)
const keywordOnly = ref(false)
const escalatedOnly = ref(false)
const limit = ref(100)
const expanded = ref(null)
const selected = ref([])
const busy = ref(false)
const devices = ref([])
const items = ref([])
const total = ref(0)
const pauseDialog = ref(null)
const pauseUntil = ref('')
const muteSame = ref(true)
const pauseError = ref('')

const hasName = computed(() => Boolean(user.name.trim()))

const canAct = computed(() => status.value !== 'acked')
const effectiveDevice = computed(() => props.deviceId || deviceFilter.value)
const selectable = computed(() => items.value.filter((a) => !a.acked))
const allSelected = computed(() => selectable.value.length > 0 && selectable.value.every((a) => selected.value.includes(a.id)))
const selectedEscalated = computed(() => items.value.some((a) => selected.value.includes(a.id) && a.escalated))

const infraRow = computed(() => infraState.list.find((i) => i.name === props.infra))
const openTotal = computed(() => {
  if (props.deviceId) return devices.value.find((d) => d.id === props.deviceId)?.open_alerts || 0
  if (!infraRow.value) return infraState.list.reduce((n, i) => n + i.open_alerts, 0)
  if (props.folder) return infraRow.value.folders.find((f) => f.name === props.folder)?.open_alerts || 0
  return infraRow.value.open_alerts
})

const scope = () => ({ infra: props.infra || undefined, folder: props.folder || undefined })
const deviceIdFor = (a) => devices.value.find((d) => d.ip === a.host_address)?.id ?? null

async function load () {
  const [, devs, page] = await Promise.all([
    refreshInfras(),
    api.devices(props.infra || undefined, props.folder || undefined),
    api.alerts({
      ...scope(), status: status.value, severity: severity.value || undefined,
      device_id: effectiveDevice.value || undefined, keyword: keywordOnly.value ? 1 : undefined,
      escalated: escalatedOnly.value ? 1 : undefined, q: query.value.trim() || undefined, limit: limit.value
    })
  ])
  devices.value = devs
  items.value = page.items
  total.value = page.total
  selected.value = selected.value.filter((id) => page.items.some((a) => a.id === id && !a.acked))
  emit('loaded', { devices: devs, total: page.total })
}

const { loading, error, refresh } = usePolling(load, 15000)

let debounce = null
watch([status, severity, deviceFilter, keywordOnly, escalatedOnly, limit], () => { selected.value = []; refresh() })
watch(query, () => { clearTimeout(debounce); debounce = setTimeout(refresh, 300) })
watch(() => [props.infra, props.folder, props.deviceId], () => {
  deviceFilter.value = null; severity.value = ''; query.value = ''; keywordOnly.value = false; escalatedOnly.value = false
  limit.value = 100; selected.value = []; expanded.value = null
  refresh()
})

const toggle = (id) => { expanded.value = expanded.value === id ? null : id }
const toggleAll = (e) => { selected.value = e.target.checked ? selectable.value.map((a) => a.id) : [] }

const filtered = computed(() => Boolean(severity.value || query.value.trim() || effectiveDevice.value || keywordOnly.value || escalatedOnly.value))
const emptyTitle = computed(() => {
  if (filtered.value) return 'No alerts match these filters'
  return { acked: 'Nothing acknowledged yet', paused: 'No paused alerts', open: 'No open alerts', all: 'No alerts' }[status.value]
})
const emptyText = computed(() => (filtered.value ? 'Clear a filter to see more.' : 'All quiet right now.'))

async function run (fn, doneMessage) {
  busy.value = true
  try {
    const r = await fn()
    if (doneMessage) toast(doneMessage(r))
    selected.value = []
    await refresh()
    return true
  } catch (e) {
    toast(errorMessage(e), 'err')
    return false
  } finally {
    busy.value = false
  }
}
const name = () => user.name.trim()
const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`
const ack = (ids) => run(() => api.ack(ids, name()), (r) => `${plural(r.acked, 'alert')} acknowledged`)
const unpause = (ids) => run(() => api.unpause(ids), (r) => `${plural(r.unpaused, 'alert')} unpaused`)
const escalate = (ids) => run(() => api.escalate(ids, name()), (r) => `${plural(r.escalated, 'alert')} escalated to NET`)
const unescalate = (ids) => run(() => api.unescalate(ids), (r) => `${plural(r.unescalated, 'alert')} un-escalated`)

async function ackAll () {
  if (!window.confirm(`Acknowledge all ${openTotal.value} open alerts?`)) return
  const page = await api.alerts({ ...scope(), status: 'open', device_id: props.deviceId || undefined, limit: 500 })
  await ack(page.items.map((a) => a.id))
  if (page.total > page.items.length) toast(`${page.total - page.items.length} more remain. Click again to continue.`)
}

// ---- pause
// The backend stores UTC+8 wall-clock time, so convert the browser's local choice to that zone.
const toStoredZone = (localValue) => new Date(new Date(localValue).getTime() + 8 * 3600 * 1000).toISOString().slice(0, 16).replace('T', ' ')
const toLocalInput = (ms) => { const d = new Date(ms); const p = (n) => String(n).padStart(2, '0'); return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}` }

function setQuick (h) {
  if (h === 'tomorrow') { const d = new Date(); d.setDate(d.getDate() + 1); d.setHours(9, 0, 0, 0); pauseUntil.value = toLocalInput(d.getTime()) } else pauseUntil.value = toLocalInput(Date.now() + h * 3600 * 1000)
}
function openPause () { pauseError.value = ''; setQuick(4); pauseDialog.value.showModal() }
async function confirmPause () {
  if (new Date(pauseUntil.value).getTime() <= Date.now()) { pauseError.value = 'Choose a time in the future.'; return }
  const ok = await run(() => api.pause(selected.value, toStoredZone(pauseUntil.value), name(), props.folder || props.infra, muteSame.value),
    (r) => `${plural(r.paused, 'alert')} paused${r.muted_rules ? ` · same error muted (${r.muted_rules})` : ''}`)
  if (ok) pauseDialog.value.close()
}
</script>

<style scoped>
.toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 14px; }
.w-select { width: 220px; }
.w-search { width: 260px; margin-left: auto; }
.check-inline { display: inline-flex; align-items: center; gap: 8px; font-weight: 600; font-size: 14px; }
.check-inline input { width: 18px; height: 18px; }
.table-wrap { overflow-x: auto; }
.table { width: 100%; border-collapse: collapse; min-width: 760px; }
.table th { text-align: left; font-size: 13px; color: var(--muted); font-weight: 600; padding: 10px 12px; border-bottom: 1px solid var(--line); background: #fafbfc; }
.table td { padding: 10px 12px; border-bottom: 1px solid var(--line); vertical-align: top; }
.table tbody tr { cursor: pointer; }
.table tbody tr:hover { background: #f8f9fb; }
.table tbody tr:last-child td { border-bottom: 0; }
.table tr.done { color: var(--muted); background: #fafafa; }
.c-check { width: 44px; text-align: center; }
.c-check input { width: 18px; height: 18px; }
.c-time, .c-dev { white-space: nowrap; }
.c-time span, .c-time small, .c-dev b, .c-dev small, .c-msg small { display: block; }
.dev-link:hover b { text-decoration: underline; }
.flags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 4px; }
.badge.kw { background: #efe7ff; color: #5b2bb5; }
.badge.net { background: #ffe4cc; color: #9a4a00; }
.badge.paused { background: #e8eef7; color: #33507a; }
.msg { display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; word-break: break-word; line-height: 1.45; }
tr.open .msg { -webkit-line-clamp: unset; white-space: pre-wrap; }
.empty { padding: 40px 20px; text-align: center; display: grid; gap: 6px; }
.empty h3 { font-size: 20px; }
.foot { display: flex; gap: 12px; align-items: center; justify-content: space-between; margin: 12px 0 84px; }
.actions { position: sticky; bottom: 12px; display: flex; flex-wrap: wrap; gap: 10px; padding: 12px; align-items: center; box-shadow: 0 6px 24px rgba(20, 28, 40, .12); }
.who { flex: 1 1 220px; max-width: 320px; }
.who.missing { border-color: var(--critical); }
.need-name { color: var(--critical); font-weight: 600; font-size: 14px; }
.quick { display: flex; flex-wrap: wrap; gap: 6px; }
.mute-opt { display: flex; gap: 10px; align-items: flex-start; padding: 10px 12px; border: 1px solid var(--line); border-radius: 8px; background: #fafbfc; }
.mute-opt input { width: 18px; height: 18px; margin-top: 3px; }
@media (max-width: 860px) { .w-select, .w-search { width: 100%; margin-left: 0; } .actions { position: static; } .foot { margin-bottom: 16px; } }
</style>
