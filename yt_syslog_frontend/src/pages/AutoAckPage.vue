<template>
  <section>
    <h1 class="page-title">Auto-acknowledge</h1>
    <p class="muted intro">
      During a window you choose, alerts from the selected devices are acknowledged automatically, for example during planned maintenance.
      Alerts that are already open inside the window are acknowledged straight away.
    </p>

    <div v-if="error" class="banner" role="alert"><span>Can't reach the backend.</span><button class="btn tiny" @click="refresh">Retry</button></div>

    <form class="card add" @submit.prevent="create">
      <div class="when">
        <div class="field"><label for="a-start">From</label><input id="a-start" v-model="start" class="input" type="datetime-local" required></div>
        <div class="field"><label for="a-end">Until</label><input id="a-end" v-model="end" class="input" type="datetime-local" required></div>
        <div class="quick">
          <button v-for="q in QUICK" :key="q.label" type="button" class="tab" @click="setQuick(q.hours)">{{ q.label }}</button>
        </div>
      </div>

      <div class="pick">
        <div class="pick-head">
          <span class="label">Devices ({{ chosen.length }} selected)</span>
          <div class="tabs" role="group" aria-label="Infra">
            <button type="button" class="tab" :aria-pressed="infra === ''" @click="infra = ''">All</button>
            <button v-for="i in INFRAS" :key="i" type="button" class="tab" :aria-pressed="infra === i" @click="infra = i">{{ i }}</button>
          </div>
          <select v-model="folder" class="input w-select" aria-label="Folder">
            <option value="">All folders</option>
            <option v-for="f in folderOptions" :key="f" :value="f">{{ f }}</option>
          </select>
          <input v-model="search" class="input w-search" type="search" placeholder="Filter devices" aria-label="Filter devices">
          <button type="button" class="btn tiny" @click="selectVisible">Select all shown ({{ visible.length }})</button>
          <button type="button" class="btn tiny" :disabled="!chosen.length" @click="chosen = []">Clear</button>
        </div>
        <div class="grid">
          <label v-for="d in visible" :key="d.id" class="dev" :class="{ on: chosen.includes(d.id) }">
            <input v-model="chosen" type="checkbox" :value="d.id">
            <span><b>{{ d.name }}</b><small class="muted">{{ d.infra }} · {{ d.folder }}</small></span>
          </label>
          <p v-if="!visible.length" class="muted">No device matches.</p>
        </div>
      </div>

      <div class="add-actions">
        <span class="err" role="alert">{{ formError }}</span>
        <button class="btn primary" :disabled="busy || !chosen.length">Start auto-ack for {{ chosen.length }} device{{ chosen.length === 1 ? '' : 's' }}</button>
      </div>
    </form>

    <h2 class="sub">Windows</h2>
    <div class="tabs filters" role="group" aria-label="State">
      <button v-for="s in STATES" :key="s.key" class="tab" :aria-pressed="stateFilter === s.key" @click="stateFilter = s.key">{{ s.label }}<span class="n">{{ countState(s.key) }}</span></button>
    </div>

    <div v-if="rows.length" class="card table-wrap">
      <table class="table">
        <thead><tr><th>Device</th><th>Infra / folder</th><th>From</th><th>Until</th><th>State</th><th><span class="sr-only">Actions</span></th></tr></thead>
        <tbody>
          <tr v-for="w in rows" :key="w.id">
            <td><router-link v-if="w.device_id" :to="{ name: 'device', params: { id: w.device_id } }"><b>{{ w.device_name }}</b></router-link><b v-else>{{ w.device_name }}</b></td>
            <td>{{ w.infra }} · {{ w.folder }}</td>
            <td>{{ clock(w.start) }}</td>
            <td>{{ clock(w.end) }}</td>
            <td><span class="badge" :class="{ active: 'warning', upcoming: 'notice', ended: 'info' }[w.state]">{{ { active: 'Active now', upcoming: 'Upcoming', ended: 'Ended' }[w.state] }}</span></td>
            <td class="r"><button class="btn tiny danger" @click="remove(w)">{{ w.state === 'ended' ? 'Delete' : 'Cancel' }}</button></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else-if="!loading" class="card empty"><h3>No windows</h3><p class="muted">Nothing is being auto-acknowledged.</p></div>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { api, errorMessage } from 'src/lib/api'
import { INFRAS, clock } from 'src/lib/format'
import { refreshInfras } from 'src/composables/useInfras'
import { usePolling } from 'src/composables/usePolling'
import { toast } from 'src/composables/useToast'

const STATES = [{ key: 'current', label: 'Active + upcoming' }, { key: 'ended', label: 'Ended' }, { key: 'all', label: 'All' }]
const QUICK = [{ label: 'Next 1 hour', hours: 1 }, { label: 'Next 2 hours', hours: 2 }, { label: 'Next 4 hours', hours: 4 }, { label: 'Next 24 hours', hours: 24 }]

const windows = ref([])
const devices = ref([])
const chosen = ref([])
const infra = ref('')
const folder = ref('')
const search = ref('')
const stateFilter = ref('current')
const start = ref('')
const end = ref('')
const busy = ref(false)
const formError = ref('')

const pad = (n) => String(n).padStart(2, '0')
const toLocalInput = (ms) => { const d = new Date(ms); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}` }
// the backend stores UTC+8 wall-clock time
const toStoredZone = (v) => new Date(new Date(v).getTime() + 8 * 3600 * 1000).toISOString().slice(0, 16).replace('T', ' ')
function setQuick (h) { start.value = toLocalInput(Date.now()); end.value = toLocalInput(Date.now() + h * 3600 * 1000) }
setQuick(2)

const { loading, error, refresh } = usePolling(async () => {
  const [w, a, b] = await Promise.all([api.autoAck(), api.devices('ALPHA'), api.devices('BRAVO')])
  windows.value = w
  devices.value = [...a, ...b]
}, 30000)

const folderOptions = computed(() => [...new Set(devices.value.filter((d) => !infra.value || d.infra === infra.value).map((d) => d.folder))])
watch(infra, () => { folder.value = '' })
const visible = computed(() => {
  const q = search.value.trim().toLowerCase()
  return devices.value.filter((d) => (!infra.value || d.infra === infra.value) && (!folder.value || d.folder === folder.value) && (!q || d.name.toLowerCase().includes(q) || d.ip.includes(q)))
})
const selectVisible = () => { chosen.value = [...new Set([...chosen.value, ...visible.value.map((d) => d.id)])] }

const countState = (k) => windows.value.filter((w) => k === 'all' || (k === 'ended' ? w.state === 'ended' : w.state !== 'ended')).length
const rows = computed(() => windows.value.filter((w) => stateFilter.value === 'all' || (stateFilter.value === 'ended' ? w.state === 'ended' : w.state !== 'ended')))

async function create () {
  formError.value = ''
  if (new Date(end.value) <= new Date(start.value)) { formError.value = 'The end must be after the start.'; return }
  busy.value = true
  try {
    const r = await api.addAutoAck(chosen.value, toStoredZone(start.value), toStoredZone(end.value))
    toast(`Auto-ack set for ${r.devices} device${r.devices === 1 ? '' : 's'}${r.auto_acked ? ` · ${r.auto_acked} open alert${r.auto_acked === 1 ? '' : 's'} acknowledged now` : ''}`)
    chosen.value = []
    await Promise.all([refresh(), refreshInfras()])
  } catch (e) {
    formError.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}

async function remove (w) {
  try {
    await api.deleteAutoAck(w.id)
    toast(`Auto-ack for ${w.device_name} ${w.state === 'ended' ? 'deleted' : 'cancelled'}`)
    await refresh()
  } catch (e) {
    toast(errorMessage(e), 'err')
  }
}
</script>

<style scoped>
.intro { margin-bottom: 16px; max-width: 75ch; }
.add { display: grid; gap: 18px; padding: 18px; margin-bottom: 24px; }
.when { display: flex; flex-wrap: wrap; gap: 14px 18px; align-items: end; }
.when .field { width: 230px; }
.quick { display: flex; flex-wrap: wrap; gap: 6px; }
.pick-head { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 10px; }
.w-select { width: 170px; }
.w-search { width: 220px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 6px; max-height: 300px; overflow: auto; padding: 4px; border: 1px solid var(--line); border-radius: 8px; }
.dev { display: flex; gap: 10px; align-items: center; padding: 8px 10px; border-radius: 6px; cursor: pointer; }
.dev:hover { background: #f0f2f5; }
.dev.on { background: #e6eeff; }
.dev input { width: 18px; height: 18px; }
.dev b, .dev small { display: block; }
.add-actions { display: flex; justify-content: flex-end; align-items: center; gap: 14px; }
.sub { font-size: 18px; margin-bottom: 10px; }
.filters { margin-bottom: 12px; }
.table-wrap { overflow-x: auto; }
.table { width: 100%; border-collapse: collapse; min-width: 700px; }
.table th { text-align: left; font-size: 13px; color: var(--muted); font-weight: 600; padding: 10px 12px; border-bottom: 1px solid var(--line); background: #fafbfc; }
.table td { padding: 10px 12px; border-bottom: 1px solid var(--line); }
.table tbody tr:last-child td { border-bottom: 0; }
.table th.r, .r { text-align: right; }
.empty { padding: 40px 20px; text-align: center; display: grid; gap: 6px; }
.empty h3 { font-size: 20px; }
</style>
