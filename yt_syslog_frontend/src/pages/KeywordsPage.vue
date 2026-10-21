<template>
  <section>
    <h1 class="page-title">Keywords for all devices</h1>
    <p class="muted intro">
      Set a keyword once and it applies to every device you choose, including devices added later. For example, add <b>Login Success</b> as
      “never alert” to stop seeing it on any device.
    </p>

    <div v-if="error" class="banner" role="alert"><span>Can't reach the backend.</span><button class="btn tiny" @click="refresh">Retry</button></div>

    <form class="card add" @submit.prevent="apply">
      <div class="field grow">
        <label for="k-word">Keyword</label>
        <input id="k-word" v-model="form.keyword" class="input" placeholder="e.g. Login Success" maxlength="200" autocomplete="off" :aria-invalid="Boolean(formError)">
        <span class="hint">Matched as plain text inside the log message (upper/lower case matters).</span>
      </div>
      <fieldset class="field">
        <legend class="label">What should it do?</legend>
        <label class="radio"><input v-model="form.kind" type="radio" value="ignore"> Never alert when the message contains it</label>
        <label class="radio"><input v-model="form.kind" type="radio" value="alert"> Always alert when the message contains it</label>
      </fieldset>
      <div class="field">
        <span class="label">Apply to</span>
        <div class="scope">
          <select v-model="form.infra" class="input" aria-label="Infra" @change="form.folder = ''">
            <option value="">All devices (ALPHA and BRAVO)</option>
            <option v-for="i in INFRAS" :key="i" :value="i">{{ i }} only</option>
          </select>
          <select v-model="form.folder" class="input" aria-label="Folder" :disabled="!form.infra">
            <option value="">All folders</option>
            <option v-for="f in foldersFor(form.infra)" :key="f" :value="f">{{ f }}</option>
          </select>
        </div>
        <select v-model="form.vendor" class="input" aria-label="Vendor">
          <option value="">Any vendor</option>
          <option v-for="v in vendors" :key="v" :value="v">Only {{ v }} devices</option>
        </select>
        <span class="hint">{{ preview }}</span>
      </div>
      <div class="add-actions">
        <span class="err" role="alert">{{ formError }}</span>
        <button class="btn primary" :disabled="busy || !form.keyword.trim()">Apply keyword</button>
      </div>
    </form>

    <div class="toolbar">
      <input v-model="query" class="input w-search" type="search" placeholder="Search keywords or devices" aria-label="Search keywords">
      <div class="tabs" role="group" aria-label="Type">
        <button class="tab" :aria-pressed="kindFilter === ''" @click="kindFilter = ''">All<span class="n">{{ keywords.length }}</span></button>
        <button class="tab" :aria-pressed="kindFilter === 'ignore'" @click="kindFilter = 'ignore'">Never alert<span class="n">{{ countKind('ignore') }}</span></button>
        <button class="tab" :aria-pressed="kindFilter === 'alert'" @click="kindFilter = 'alert'">Always alert<span class="n">{{ countKind('alert') }}</span></button>
      </div>
    </div>

    <div v-if="rows.length" class="card table-wrap">
      <table class="table">
        <thead><tr>
          <th v-for="c in cols" :key="c.key" :class="{ r: c.right }" :aria-sort="ariaSort(c.key)"><button type="button" class="th-btn" @click="toggleSort(c.key)">{{ c.label }}<span class="arrow" aria-hidden="true">{{ arrow(c.key) }}</span></button></th>
          <th><span class="sr-only">Actions</span></th>
        </tr></thead>
        <tbody>
          <template v-for="k in sortedRows" :key="k.kind + k.keyword">
            <tr :class="'grp-' + group(k).key">
              <td><b class="kw" :title="shown(k.keyword) !== k.keyword ? 'Spaces at the start/end are part of the keyword' : ''">{{ shown(k.keyword) }}</b></td>
              <td><span class="badge" :class="k.kind === 'ignore' ? 'info' : 'warning'">{{ k.kind === 'ignore' ? 'Never alert' : 'Always alert' }}</span></td>
              <td><span class="grp-badge" :class="'grp-' + group(k).key">{{ group(k).label }}</span> {{ appliesTo(k) }}<small v-if="k.rule" class="muted"> · future devices included</small></td>
              <td class="r">{{ k.device_count }}</td>
              <td><div class="row-actions">
                <button class="btn tiny" @click="toggle(k)">{{ open === k.kind + k.keyword ? 'Hide devices' : 'Show devices' }}</button>
                <button class="btn tiny danger" @click="askRemove(k)">Remove everywhere</button>
              </div></td>
            </tr>
            <tr v-if="open === k.kind + k.keyword" class="detail"><td colspan="5">
              <div class="chips">
                <span v-for="d in k.devices" :key="d.id" class="chip" :class="{ removed: isRemoved(k, d.id) }">
                  <router-link :to="{ name: 'device', params: { id: d.id } }" class="chip-link">{{ d.name }} <small>{{ d.infra }} · {{ d.folder }}</small></router-link>
                  <button v-if="!isRemoved(k, d.id)" type="button" class="chip-x" :disabled="busy" :aria-label="`Remove ${shown(k.keyword)} from ${d.name}`" :title="`Remove from ${d.name}`" @click="stageRemove(k, d.id)">✕</button>
                  <button v-else type="button" class="chip-x undo" :disabled="busy" :aria-label="`Keep ${d.name}`" title="Keep this device" @click="unstageRemove(k, d.id)">Undo</button>
                </span>
                <span v-for="id in draftOf(k).add" :key="'n' + id" class="chip added">
                  + {{ deviceName(id) }}
                  <button type="button" class="chip-x" :disabled="busy" :aria-label="`Do not add ${deviceName(id)}`" title="Do not add" @click="unstageAdd(k, id)">✕</button>
                </span>
                <span v-if="!k.devices.length && !draftOf(k).add.length" class="muted small">No device uses this keyword.</span>
              </div>
              <div class="add-device">
                <select v-model.number="pick[k.kind + k.keyword]" class="input" :aria-label="`Device to add to ${shown(k.keyword)}`">
                  <option :value="0">Add a device…</option>
                  <option v-for="d in devicesWithout(k)" :key="d.id" :value="d.id">{{ d.name }} ({{ d.infra }} · {{ d.folder }})</option>
                </select>
                <button type="button" class="btn tiny" :disabled="busy || !pick[k.kind + k.keyword]" @click="stageAdd(k)">Add device</button>
                <button v-if="pick[k.kind + k.keyword]" type="button" class="btn tiny" @click="pick[k.kind + k.keyword] = 0">Cancel</button>
              </div>
              <div v-if="pending(k)" class="edit-bar" role="group" aria-label="Unsaved device changes">
                <span class="small">Not saved yet: <b>{{ draftOf(k).add.length }}</b> to add, <b>{{ draftOf(k).remove.length }}</b> to remove</span>
                <button type="button" class="btn tiny primary" :disabled="busy" @click="saveDraft(k)">Save changes</button>
                <button type="button" class="btn tiny" :disabled="busy" @click="cancelDraft(k)">Cancel</button>
              </div>
              <p v-if="k.rule" class="muted small">The rule still applies to devices added later, even if you remove a device here.</p>
            </td></tr>
          </template>
        </tbody>
      </table>
    </div>
    <div v-else-if="!loading" class="card empty"><h3>No keywords yet</h3><p class="muted">Add one above to start filtering across your devices.</p></div>

    <dialog ref="removeDialog" class="sheet">
      <div class="sheet-body">
        <h2>Remove {{ toRemove ? shown(toRemove.keyword) : '' }}?</h2>
        <p class="muted">It will be removed from all {{ toRemove?.device_count }} devices and won't be applied to new ones.</p>
        <div class="sheet-actions">
          <button class="btn" @click="removeDialog.close()">Keep it</button>
          <button class="btn danger" :disabled="busy" @click="confirmRemove">Remove everywhere</button>
        </div>
      </div>
    </dialog>
  </section>
</template>

<script setup>
import { computed, reactive, ref } from 'vue'
import { api, errorMessage } from 'src/lib/api'
import { INFRAS } from 'src/lib/format'
import { refreshInfras } from 'src/composables/useInfras'
import { usePolling } from 'src/composables/usePolling'
import { useSort } from 'src/composables/useSort'
import { toast } from 'src/composables/useToast'

const keywords = ref([])
const totalDevices = ref(0)
const rulesData = ref([])
const folderMap = ref({})
const query = ref('')
const kindFilter = ref('')
const open = ref('')
const busy = ref(false)
const formError = ref('')
const form = reactive({ keyword: '', kind: 'ignore', infra: '', folder: '', vendor: '' })
const removeDialog = ref(null)
const toRemove = ref(null)

const { loading, error, refresh } = usePolling(async () => {
  const [s, r, f] = await Promise.all([api.keywordSummary(), api.rules(), api.folders()])
  keywords.value = s.keywords
  totalDevices.value = s.total_devices
  rulesData.value = r
  const m = {}
  for (const x of f) (m[x.infra] ||= []).push(x.name)
  folderMap.value = m
}, 30000)

const vendors = computed(() => [...new Set(rulesData.value.map((d) => d.vendor).filter(Boolean))].sort())
const foldersFor = (infra) => folderMap.value[infra] || []
const countKind = (k) => keywords.value.filter((x) => x.kind === k).length
const preview = computed(() => {
  const names = new Set(rulesData.value.filter((d) => (!form.infra || d.infra === form.infra) && (!form.folder || d.folder === form.folder) && (!form.vendor || d.vendor === form.vendor)).map((d) => d.name))
  return `Will apply to ${names.size} device${names.size === 1 ? '' : 's'}${form.infra || form.vendor ? '' : ' (every device, and any added later)'}.`
})
const rows = computed(() => {
  const q = query.value.trim().toLowerCase()
  return keywords.value.filter((k) => (!kindFilter.value || k.kind === kindFilter.value) &&
    (!q || k.keyword.toLowerCase().includes(q) || k.devices.some((d) => d.name.toLowerCase().includes(q))))
})
// Classification by what the keyword applies to: each vendor group gets its own label and row colour
const vendorOf = computed(() => Object.fromEntries(rulesData.value.map((d) => [d.name, d.vendor])))
const VENDOR_LABEL = { LTM: 'LTM', cisco: 'Cisco', paloalto: 'Palo Alto' }
const group = (k) => {
  if (k.all_devices) return { key: 'all', label: 'All devices' }
  // by the vendors of the devices the keyword really applies to (not by guessing from the scope text)
  const vendors = [...new Set((k.devices || []).map((d) => vendorOf.value[d.name]).filter(Boolean))].sort()
  if (vendors.length === 1) return { key: vendors[0] === 'paloalto' ? 'pan' : vendors[0].toLowerCase(), label: VENDOR_LABEL[vendors[0]] || vendors[0] }
  if (vendors.length > 1) return { key: 'mix', label: vendors.map((v) => VENDOR_LABEL[v] || v).join(' + ') }
  return { key: 'other', label: 'Chosen devices' }
}
const appliesTo = (k) => (k.all_devices ? '' : (k.scopes && k.scopes.length ? k.scopes.join('; ') : (k.rule ? k.rule.scope : '')))
const cols = [
  { key: 'keyword', label: 'Keyword' }, { key: 'type', label: 'Type' },
  { key: 'applies', label: 'Applies to' }, { key: 'devices', label: 'Devices', right: true },
]
const { sorted: sortedRows, toggle: toggleSort, ariaSort, arrow } = useSort(rows, {
  keyword: (k) => k.keyword.trim(), type: (k) => k.kind,
  applies: (k) => group(k).label + ' ' + appliesTo(k), devices: (k) => k.device_count,
}, 'applies', 'asc')
// a keyword with spaces at its edges (e.g. " ha ") is shown in quotes so the spaces are visible
const shown = (k) => (k !== k.trim() ? `"${k}"` : k)
const toggle = (k) => {
  const key = k.kind + k.keyword
  for (const x of Object.keys(drafts)) delete drafts[x]        // unsaved changes never outlive the open row
  pick[key] = 0
  open.value = open.value === key ? '' : key
}

async function apply () {
  formError.value = ''
  if (!form.keyword.trim()) { formError.value = 'Enter a keyword.'; return }
  busy.value = true
  try {
    const r = await api.addKeywordRule({ keyword: form.keyword.trim(), kind: form.kind, infra: form.infra || undefined, folder: form.folder || undefined, vendor: form.vendor || undefined })
    const extra = r.auto_acked ? ` · ${r.auto_acked} existing alert${r.auto_acked === 1 ? '' : 's'} cleared` : ''
    toast(`${shown(r.keyword)} applied to ${r.devices} devices (${r.added} new)${extra}`)
    form.keyword = ''
    await Promise.all([refresh(), refreshInfras()])
  } catch (e) {
    formError.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}

function askRemove (k) { toRemove.value = k; removeDialog.value.showModal() }
const pick = reactive({})                // keyword -> device id chosen in "Add a device"
// Edits are staged and applied together with "Save changes"; "Cancel" throws them away.
const drafts = reactive({})
const keyOf = (k) => k.kind + k.keyword
const NO_DRAFT = { add: [], remove: [] }
const draftOf = (k) => drafts[keyOf(k)] || NO_DRAFT                 // read-only view (safe to use while rendering)
const draftFor = (k) => (drafts[keyOf(k)] ||= { add: [], remove: [] })  // creates the draft when a change is staged
const pending = (k) => { const d = drafts[keyOf(k)]; return Boolean(d && (d.add.length || d.remove.length)) }
const isRemoved = (k, id) => draftOf(k).remove.includes(id)
const deviceName = (id) => rulesData.value.find((d) => d.id === id)?.name || `#${id}`
const stageRemove = (k, id) => { if (!isRemoved(k, id)) draftFor(k).remove.push(id) }
const unstageRemove = (k, id) => { const d = draftFor(k); d.remove = d.remove.filter((x) => x !== id) }
const unstageAdd = (k, id) => { const d = draftFor(k); d.add = d.add.filter((x) => x !== id) }
function stageAdd (k) {
  const id = pick[keyOf(k)]
  if (id && !draftOf(k).add.includes(id)) draftFor(k).add.push(id)
  pick[keyOf(k)] = 0
}
const cancelDraft = (k) => { delete drafts[keyOf(k)]; pick[keyOf(k)] = 0 }
const devicesWithout = (k) => {
  const have = new Set(k.devices.map((d) => d.name))
  const staged = new Set(draftOf(k).add)
  const stagedNames = new Set([...staged].map(deviceName))
  const seen = new Set()
  return rulesData.value.filter((d) => {
    if (have.has(d.name) || staged.has(d.id) || stagedNames.has(d.name) || seen.has(d.name)) return false
    seen.add(d.name)                                     // devices that share a name share their keywords: list the name once
    return true
  }).sort((a, b) => a.name.localeCompare(b.name))
}
async function saveDraft (k) {
  if (busy.value) return
  const d = draftFor(k)
  busy.value = true
  let added = 0
  let removed = 0
  let gone = 0
  try {
    for (const id of [...d.remove]) {
      try { await api.removeKeywordDevice(k.kind, k.keyword, id); removed++ } catch (e) { if (e?.response?.status === 404) gone++; else throw e }
      d.remove = d.remove.filter((x) => x !== id)         // done: it no longer belongs to the unsaved changes
    }
    for (const id of [...d.add]) {
      try { await api.addKeywordDevice(k.kind, k.keyword, id); added++ } catch (e) { if (e?.response?.status === 404) gone++; else throw e }
      d.add = d.add.filter((x) => x !== id)
    }
    toast(`${shown(k.keyword)}: ${added} device(s) added, ${removed} removed${gone ? `, ${gone} no longer exist` : ''}`)
    delete drafts[keyOf(k)]
  } catch (e) {
    toast(`${errorMessage(e)} (${added} added, ${removed} removed; the rest is still unsaved)`, 'err')
  } finally {
    busy.value = false
    await refresh()
  }
}

async function confirmRemove () {
  busy.value = true
  try {
    await api.removeKeywordRule(toRemove.value.kind, toRemove.value.keyword)
    toast(`${shown(toRemove.value.keyword)} removed from all devices`)
    removeDialog.value.close()
    await refresh()
  } catch (e) {
    toast(errorMessage(e), 'err')
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.intro { margin-bottom: 16px; max-width: 75ch; }
.add { display: grid; grid-template-columns: minmax(240px, 1.4fr) minmax(260px, 1.2fr) minmax(260px, 1.4fr); gap: 18px 24px; padding: 18px; margin-bottom: 20px; align-items: start; }
.add fieldset { border: 0; padding: 0; margin: 0; }
.radio { display: flex; align-items: center; gap: 8px; margin: 4px 0; }
.radio input { width: 18px; height: 18px; }
.scope { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px; }
.field > select.input { margin-bottom: 4px; }
.add-actions { grid-column: 1 / -1; display: flex; justify-content: flex-end; align-items: center; gap: 14px; }
.toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 14px; }
.w-search { width: 300px; }
.table-wrap { overflow-x: auto; }
.table { width: 100%; border-collapse: collapse; min-width: 720px; }
.table th { text-align: left; font-size: 13px; color: var(--muted); font-weight: 600; padding: 10px 12px; border-bottom: 1px solid var(--line); background: #fafbfc; }
.table td { padding: 10px 12px; border-bottom: 1px solid var(--line); }
.table tbody tr:last-child td { border-bottom: 0; }
.kw { font-family: var(--mono); font-size: 14px; }
.table th.r, .r { text-align: right; }
.row-actions { display: flex; gap: 6px; justify-content: flex-end; white-space: nowrap; }
.detail td { background: #fafbfc; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; }
.chip { padding: 3px 10px; border-radius: 99px; background: var(--info-bg); font-size: 13px; font-weight: 600; }
.chip small { font-weight: 400; color: var(--muted); }
.chip { display: inline-flex; align-items: center; gap: 4px; }
.chip-link { color: inherit; text-decoration: none; }
.chip-x { all: unset; cursor: pointer; font-size: 11px; line-height: 1; padding: 3px 5px; border-radius: 99px; color: var(--muted); }
.chip-x:hover { background: #f3d2cf; color: var(--critical); }
.chip-x:focus-visible { outline: 2px solid var(--accent, #2f6fed); }
.chip-x:disabled { opacity: .4; cursor: default; }
.chip.removed { background: #fbe3e0; }
.chip.removed .chip-link { text-decoration: line-through; color: var(--muted); }
.chip.added { background: #dff3e6; font-weight: 600; }
.chip-x.undo { font-size: 12px; font-weight: 600; color: var(--info); }
.edit-bar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-top: 12px; padding: 8px 12px; border: 1px dashed var(--line); border-radius: 8px; background: #fffdf3; }
.add-device { display: flex; gap: 8px; align-items: center; margin-top: 10px; flex-wrap: wrap; }
.add-device .input { min-width: 240px; max-width: 100%; }
.chip:hover { background: #dfe4ea; }
.empty { padding: 40px 20px; text-align: center; display: grid; gap: 6px; }
.empty h3 { font-size: 20px; }
@media (max-width: 980px) { .add { grid-template-columns: 1fr; } .w-search { width: 100%; } }
.grp-ltm td { background: rgba(47, 111, 237, 0.07); }
.grp-cisco td { background: rgba(31, 138, 76, 0.08); }
.grp-pan td { background: rgba(232, 135, 58, 0.10); }
.grp-mix td { background: rgba(130, 80, 200, 0.08); }
.grp-badge { display: inline-block; padding: 1px 9px; border-radius: 99px; font-size: 12px; font-weight: 700; margin-right: 6px; border: 1px solid currentColor; }
.grp-badge.grp-ltm { color: #1f55c0; }
.grp-badge.grp-cisco { color: #17703d; }
.grp-badge.grp-pan { color: #9a4f0d; }
.grp-badge.grp-mix { color: #6a3fb0; }
.grp-badge.grp-all, .grp-badge.grp-other { color: var(--muted); }
</style>
