<template>
  <section>
    <div class="head">
      <div>
        <h1 class="page-title">Devices</h1>
        <p class="muted">Every device belongs to one infra (ALPHA or BRAVO) and one folder.</p>
      </div>
      <button class="btn primary" @click="openCreate">+ Add device</button>
    </div>

    <div v-if="error" class="banner" role="alert">
      <span>Can't reach the backend.</span>
      <button class="btn tiny" @click="refresh">Retry</button>
    </div>

    <div class="toolbar">
      <div class="tabs" role="group" aria-label="Infra">
        <button class="tab" :aria-pressed="infra === ''" @click="infra = ''">All<span class="n">{{ devices.length }}</span></button>
        <button v-for="i in INFRAS" :key="i" class="tab" :aria-pressed="infra === i" @click="infra = i">{{ i }}<span class="n">{{ countFor(i) }}</span></button>
      </div>
      <select v-model="folderFilter" class="input w-select" aria-label="Folder">
        <option value="">All folders</option>
        <option v-for="f in allFolders" :key="f" :value="f">{{ f }}</option>
      </select>
      <input v-model="query" class="input w-search" type="search" placeholder="Search name or IP" aria-label="Search devices">
    </div>

    <div v-if="rows.length" class="card table-wrap">
      <table class="table">
        <thead>
          <tr><th>Device</th><th>IP address</th><th>Infra</th><th>Folder</th><th>Vendor</th><th>Alerts on severity <span class="muted th-hint">(click to switch)</span></th><th class="r">Open alerts</th><th><span class="sr-only">Actions</span></th></tr>
        </thead>
        <tbody>
          <tr v-for="d in rows" :key="d.id">
            <td><b>{{ d.name }}</b></td>
            <td class="mono">{{ d.ip }}</td>
            <td><span class="badge" :class="d.infra.toLowerCase()">{{ d.infra }}</span></td>
            <td>{{ d.folder }}</td>
            <td class="muted">{{ d.vendor || '—' }}</td>
            <td class="sev-cell">
              <div class="sev-tabs" role="group" :aria-label="`Alert severities for ${d.name}`">
                <button
                  v-for="o in d.severity_options"
                  :key="o"
                  type="button"
                  class="sev-tab"
                  :aria-pressed="d.severities.includes(o)"
                  :disabled="savingSev.has(d.id)"
                  :title="d.severities.includes(o) ? `${o}: alerts on. Click to turn off` : `${o}: off. Click to turn on`"
                  @click="toggleSeverity(d, o)"
                >{{ o }}</button>
              </div>
              <span v-if="!d.severities.length" class="sev-none">No severity on: this device raises no alerts</span>
            </td>
            <td class="r"><span :class="{ hot: d.open_alerts > 0 }">{{ d.open_alerts }}</span></td>
            <td>
              <div class="row-actions">
                <button class="btn tiny" @click="rulesDialog.open(d)">Alert settings</button>
                <button class="btn tiny" @click="openEdit(d)">Edit</button>
                <button class="btn tiny danger" @click="askDelete(d)">Remove</button>
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else-if="!loading" class="card empty">
      <h3>No devices</h3>
      <p class="muted">{{ query ? `Nothing matches “${query}”.` : 'Add a device to start tracking its alerts.' }}</p>
    </div>

    <!-- add / edit -->
    <dialog ref="formDialog" class="sheet" @close="resetForm">
      <form class="sheet-body" novalidate @submit.prevent="save">
        <h2>{{ editing ? 'Edit device' : 'Add device' }}</h2>

        <div class="field">
          <label for="f-infra">Infra</label>
          <select id="f-infra" v-model="form.infra" class="input">
            <option v-for="i in INFRAS" :key="i" :value="i">{{ i }}</option>
          </select>
        </div>

        <div class="field">
          <label for="f-folder">Folder</label>
          <select id="f-folder" v-model="form.folder" class="input" @change="folderTouched = true">
            <option v-for="f in foldersFor(form.infra)" :key="f" :value="f">{{ f }}</option>
          </select>
          <span class="hint">Chosen automatically from the device name. Change it if it's wrong.</span>
        </div>

        <div class="field">
          <label for="f-name">Network device</label>
          <input id="f-name" ref="nameInput" v-model="form.name" class="input" :aria-invalid="Boolean(errors.name)" placeholder="e.g. BRAVO-CS01" maxlength="100" autocomplete="off">
          <span class="err" role="alert">{{ errors.name }}</span>
        </div>

        <div class="field">
          <label for="f-ip">IP address</label>
          <input id="f-ip" v-model="form.ip" class="input mono" :aria-invalid="Boolean(errors.ip)" placeholder="192.0.2.10" inputmode="decimal" autocomplete="off">
          <span class="err" role="alert">{{ errors.ip }}</span>
        </div>

        <div class="field">
          <label for="f-vendor">Vendor <span class="muted">(optional)</span></label>
          <select id="f-vendor" v-model="form.vendor" class="input">
            <option value="">Not set</option>
            <option v-for="v in VENDORS" :key="v" :value="v">{{ v }}</option>
          </select>
        </div>

        <div class="sheet-actions">
          <button type="button" class="btn" @click="formDialog.close()">Cancel</button>
          <button type="submit" class="btn primary" :disabled="saving">{{ saving ? 'Saving…' : editing ? 'Save changes' : 'Add device' }}</button>
        </div>
      </form>
    </dialog>

    <DeviceRulesDialog ref="rulesDialog" @changed="refresh" />

    <!-- remove -->
    <dialog ref="deleteDialog" class="sheet">
      <div class="sheet-body">
        <h2>Remove {{ toDelete?.name }}?</h2>
        <p class="muted">{{ toDelete?.ip }} will no longer appear in {{ toDelete?.infra }}. Past alerts from it stay in the database.</p>
        <div class="sheet-actions">
          <button class="btn" @click="deleteDialog.close()">Keep it</button>
          <button class="btn danger" :disabled="saving" @click="confirmDelete">Remove device</button>
        </div>
      </div>
    </dialog>
  </section>
</template>

<script setup>
import { computed, nextTick, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import DeviceRulesDialog from 'components/DeviceRulesDialog.vue'
import { api, errorMessage } from 'src/lib/api'
import { INFRAS, VENDORS, suggestFolder } from 'src/lib/format'
import { refreshInfras } from 'src/composables/useInfras'
import { usePolling } from 'src/composables/usePolling'
import { toast } from 'src/composables/useToast'

const route = useRoute()
const devices = ref([])
const infra = ref(INFRAS.includes(route.query.infra) ? route.query.infra : '')
const folderFilter = ref('')
const query = ref('')
const saving = ref(false)

const formDialog = ref(null)
const deleteDialog = ref(null)
const nameInput = ref(null)
const editing = ref(null)
const toDelete = ref(null)
const folderTouched = ref(false)
const form = reactive({ infra: 'ALPHA', folder: 'Other', name: '', ip: '', vendor: '' })
const errors = reactive({ name: '', ip: '' })

const folderMap = ref({})
const savingSev = ref(new Set())
const { loading, error, refresh } = usePolling(async () => {
  if (savingSev.value.size) return // don't overwrite a toggle that is still being saved
  const [rules, folders] = await Promise.all([api.rules(), api.folders()])
  devices.value = rules
  const m = {}
  for (const f of folders) (m[f.infra] ||= []).push(f.name)
  folderMap.value = m
}, 30000)

// Click a severity to switch it on/off and save at once (optimistic; reverted with a message if saving fails).
async function toggleSeverity (d, option) {
  const before = [...d.severities]
  const next = before.includes(option) ? before.filter((x) => x !== option) : [...before, option]
  d.severities = d.severity_options.filter((o) => next.includes(o)) // keep the vendor's own order
  savingSev.value = new Set(savingSev.value).add(d.id)
  try {
    const r = await api.setSeverities(d.id, d.severities)
    d.severities = r.severities
  } catch (e) {
    d.severities = before
    toast(`${d.name}: ${errorMessage(e)}`, 'err')
  } finally {
    const rest = new Set(savingSev.value); rest.delete(d.id); savingSev.value = rest
  }
}

const foldersFor = (infra) => folderMap.value[infra] || ['Other']
const allFolders = computed(() => [...new Set(Object.values(folderMap.value).flat())])
const countFor = (i) => devices.value.filter((d) => d.infra === i).length
const rows = computed(() => {
  const q = query.value.trim().toLowerCase()
  return devices.value.filter((d) =>
    (!infra.value || d.infra === infra.value) && (!folderFilter.value || d.folder === folderFilter.value) &&
    (!q || d.name.toLowerCase().includes(q) || d.ip.includes(q)))
})

watch(() => route.query.infra, (v) => { infra.value = INFRAS.includes(v) ? v : '' })
const pickFolder = (n, infra) => { const sug = suggestFolder(n); return foldersFor(infra).includes(sug) ? sug : 'Other' }
watch(() => form.name, (n) => { if (!editing.value && !folderTouched.value) form.folder = pickFolder(n, form.infra) })
watch(() => form.infra, (i) => { if (!foldersFor(i).includes(form.folder)) form.folder = pickFolder(form.name, i) })

function resetForm () {
  editing.value = null
  folderTouched.value = false
  Object.assign(form, { infra: infra.value || 'ALPHA', folder: 'Other', name: '', ip: '', vendor: '' })
  Object.assign(errors, { name: '', ip: '' })
}

async function openCreate () {
  resetForm()
  formDialog.value.showModal()
  await nextTick()
  nameInput.value?.focus()
}

function openEdit (d) {
  resetForm()
  editing.value = d
  folderTouched.value = true
  Object.assign(form, { infra: d.infra, folder: d.folder, name: d.name, ip: d.ip, vendor: d.vendor || '' })
  formDialog.value.showModal()
}

const rulesDialog = ref(null)

const IPV4 = /^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$/
function validate () {
  errors.name = form.name.trim() ? '' : 'Enter the device name.'
  errors.ip = IPV4.test(form.ip.trim()) ? '' : 'Enter a valid IPv4 address, e.g. 192.0.2.10.'
  return !errors.name && !errors.ip
}

async function save () {
  if (!validate()) return
  saving.value = true
  const body = { infra: form.infra, folder: form.folder, name: form.name.trim(), ip: form.ip.trim(), vendor: form.vendor }
  try {
    if (editing.value) await api.updateDevice(editing.value.id, body)
    else await api.createDevice(body)
    toast(editing.value ? `${body.name} updated` : `${body.name} added to ${body.infra} / ${body.folder}`)
    formDialog.value.close()
    await Promise.all([refresh(), refreshInfras()])
  } catch (e) {
    const msg = errorMessage(e)
    if (/IP/i.test(msg)) errors.ip = msg
    else if (/name/i.test(msg)) errors.name = msg
    else toast(msg, 'err')
  } finally {
    saving.value = false
  }
}

function askDelete (d) {
  toDelete.value = d
  deleteDialog.value.showModal()
}

async function confirmDelete () {
  saving.value = true
  try {
    await api.deleteDevice(toDelete.value.id)
    toast(`${toDelete.value.name} removed`)
    deleteDialog.value.close()
    await Promise.all([refresh(), refreshInfras()])
  } catch (e) {
    toast(errorMessage(e), 'err')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; margin-bottom: 16px; }
.toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 14px; }
.w-select { width: 190px; }
.w-search { width: 260px; margin-left: auto; }
.table-wrap { overflow-x: auto; }
.table { width: 100%; border-collapse: collapse; min-width: 1100px; }
.table th { text-align: left; font-size: 13px; color: var(--muted); font-weight: 600; padding: 10px 12px; border-bottom: 1px solid var(--line); background: #fafbfc; }
.table td { padding: 10px 12px; border-bottom: 1px solid var(--line); }
.table tbody tr:hover { background: #f8f9fb; }
.table tbody tr:last-child td { border-bottom: 0; }
.th-hint { font-weight: 400; font-size: 12px; }
.sev-cell { min-width: 300px; max-width: 420px; }
.sev-tabs { display: flex; flex-wrap: wrap; gap: 4px; }
.sev-tab { height: 26px; padding: 0 10px; border-radius: 99px; border: 1px solid var(--line-strong); background: #fff; color: var(--muted); font-size: 12px; font-weight: 600; }
.sev-tab:hover:not(:disabled) { border-color: var(--text); color: var(--text); }
.sev-tab[aria-pressed='true'] { background: #1d4ed8; border-color: #1d4ed8; color: #fff; }
.sev-tab[aria-pressed='true']:hover:not(:disabled) { background: #1740b8; }
.sev-tab:disabled { opacity: .6; cursor: progress; }
.sev-none { display: block; margin-top: 4px; font-size: 12px; font-weight: 600; color: var(--critical); }
.table th.r, .r { text-align: right; }
.hot { color: var(--critical); font-weight: 700; }
.row-actions { display: flex; gap: 6px; justify-content: flex-end; white-space: nowrap; }
.empty { padding: 40px 20px; text-align: center; display: grid; gap: 6px; }
.empty h3 { font-size: 20px; }
@media (max-width: 860px) { .w-select, .w-search { width: 100%; margin-left: 0; } }
</style>
