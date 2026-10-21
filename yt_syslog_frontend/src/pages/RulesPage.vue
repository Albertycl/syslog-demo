<template>
  <section>
    <h1 class="page-title">Alert rules</h1>
    <p class="muted intro">Every device and what is filtered for it: which severities become alerts, which keywords always alert, and which are ignored.</p>

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
      <select v-model="severityFilter" class="input w-select" aria-label="Severity">
        <option value="">Any severity</option>
        <option v-for="s in allSeverities" :key="s" :value="s">Alerts on {{ s }}</option>
      </select>
      <input v-model="query" class="input w-search" type="search" placeholder="Search device, IP or keyword" aria-label="Search rules">
    </div>

    <p class="muted summary" v-if="devices.length">
      {{ rows.length }} of {{ devices.length }} devices ·
      <span :class="{ warn: noAlerts > 0 }">{{ noAlerts }} with no severity ticked (they raise no alerts)</span>
    </p>

    <div v-if="rows.length" class="card table-wrap">
      <table class="table">
        <thead>
          <tr><th>Device</th><th>Infra / folder</th><th>Alerts on severity</th><th>Keywords that always alert</th><th>Keywords ignored</th><th><span class="sr-only">Actions</span></th></tr>
        </thead>
        <tbody>
          <tr v-for="d in rows" :key="d.id">
            <td class="c-dev"><b>{{ d.name }}</b><small class="mono muted">{{ d.ip }}</small></td>
            <td class="c-grp"><span class="badge" :class="d.infra.toLowerCase()">{{ d.infra }}</span> <span>{{ d.folder }}</span></td>
            <td>
              <div class="tags">
                <span v-for="s in d.severities" :key="s" class="tag">{{ s }}</span>
                <span v-if="!d.severities.length" class="badge critical">None, no alerts</span>
              </div>
            </td>
            <td><div class="tags"><span v-for="k in d.keywords" :key="k.id" class="tag kw">{{ k.keyword }}</span><span v-if="!d.keywords.length" class="muted">—</span></div></td>
            <td><div class="tags"><span v-for="k in d.ignore" :key="k.id" class="tag ign">{{ k.keyword }}</span><span v-if="!d.ignore.length" class="muted">—</span></div></td>
            <td class="r"><button class="btn tiny" @click="rulesDialog.open(d)">Edit rules</button></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div v-else-if="!loading" class="card empty">
      <h3>No devices match</h3>
      <p class="muted">Clear a filter to see more.</p>
    </div>

    <DeviceRulesDialog ref="rulesDialog" @changed="refresh" />
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import DeviceRulesDialog from 'components/DeviceRulesDialog.vue'
import { api } from 'src/lib/api'
import { INFRAS } from 'src/lib/format'
import { usePolling } from 'src/composables/usePolling'

const devices = ref([])
const infra = ref('')
const folderFilter = ref('')
const severityFilter = ref('')
const query = ref(String(useRoute().query.q || ''))
const rulesDialog = ref(null)

const folderNames = ref([])
const allFolders = computed(() => folderNames.value)
const { loading, error, refresh } = usePolling(async () => {
  const [r, f] = await Promise.all([api.rules(), api.folders()])
  devices.value = r
  folderNames.value = [...new Set(f.map((x) => x.name))]
}, 30000)

const countFor = (i) => devices.value.filter((d) => d.infra === i).length
const allSeverities = computed(() => [...new Set(devices.value.flatMap((d) => d.severities))])
const noAlerts = computed(() => devices.value.filter((d) => !d.severities.length).length)

const rows = computed(() => {
  const q = query.value.trim().toLowerCase()
  return devices.value.filter((d) =>
    (!infra.value || d.infra === infra.value) &&
    (!folderFilter.value || d.folder === folderFilter.value) &&
    (!severityFilter.value || d.severities.includes(severityFilter.value)) &&
    (!q || d.name.toLowerCase().includes(q) || d.ip.includes(q) ||
      d.keywords.some((k) => k.keyword.toLowerCase().includes(q)) || d.ignore.some((k) => k.keyword.toLowerCase().includes(q))))
})
</script>

<style scoped>
.intro { margin-bottom: 16px; max-width: 70ch; }
.toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 10px; }
.w-select { width: 190px; }
.w-search { width: 280px; margin-left: auto; }
.summary { margin-bottom: 10px; font-size: 14px; }
.summary .warn { color: var(--critical); font-weight: 600; }
.table-wrap { overflow-x: auto; }
.table { width: 100%; border-collapse: collapse; min-width: 900px; }
.table th { text-align: left; font-size: 13px; color: var(--muted); font-weight: 600; padding: 10px 12px; border-bottom: 1px solid var(--line); background: #fafbfc; }
.table td { padding: 10px 12px; border-bottom: 1px solid var(--line); vertical-align: top; }
.table tbody tr:hover { background: #f8f9fb; }
.table tbody tr:last-child td { border-bottom: 0; }
.c-dev b, .c-dev small { display: block; }
.c-grp { white-space: nowrap; }
.table th.r, .r { text-align: right; white-space: nowrap; }
.tags { display: flex; flex-wrap: wrap; gap: 4px; }
.tag { padding: 2px 9px; border-radius: 99px; background: var(--info-bg); color: var(--info); font-size: 13px; font-weight: 600; }
.tag.kw { background: #efe7ff; color: #5b2bb5; }
.tag.ign { background: #f1f1f1; color: #555; text-decoration: line-through; }
.empty { padding: 40px 20px; text-align: center; display: grid; gap: 6px; }
.empty h3 { font-size: 20px; }
@media (max-width: 860px) { .w-select, .w-search { width: 100%; margin-left: 0; } }
</style>
