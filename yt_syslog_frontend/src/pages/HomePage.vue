<template>
  <section>
    <div class="head">
      <div>
        <h1 class="page-title">Overview</h1>
        <p class="muted intro">Open alerts per folder. Click a folder to see its alerts.</p>
      </div>
      <div class="collect">
        <button class="btn" :disabled="collecting" @click="pull">{{ collecting ? 'Reading logs…' : 'Pull latest logs now' }}</button>
        <small class="muted">{{ noteText }}</small>
      </div>
    </div>

    <CollectorBanner />
    <div v-if="infraState.error" class="banner" role="alert">Can't reach the backend. Showing the last known numbers.</div>

    <div class="blocks">
      <div v-for="i in infraState.list" :key="i.name" class="block" :class="i.name.toLowerCase()">
        <header class="block-head">
          <router-link :to="{ name: 'infra', params: { name: i.name } }" class="block-title">{{ i.name }}</router-link>
          <span class="block-sum">
            <b>{{ i.open_alerts }}</b> open alerts · <b>{{ i.devices }}</b> devices
          </span>
        </header>

        <div class="folders">
          <router-link
            v-for="f in i.folders"
            :key="f.name"
            :to="{ name: 'infra', params: { name: i.name, folder: f.name } }"
            class="folder card"
          >
            <span class="f-name">{{ f.name }}</span>
            <span class="f-count" :class="{ has: f.open_alerts }">{{ f.open_alerts }}</span>
            <span class="f-label muted">open alerts · {{ f.devices }} devices</span>
            <span v-if="f.escalated" class="f-net">{{ f.escalated }} escalated to NET</span>
            <span v-if="f.paused" class="f-paused">⏸ {{ f.paused }} paused</span>
          </router-link>
          <p v-if="!i.folders.length" class="muted">No devices yet. <router-link :to="{ name: 'devices' }" class="link">Add devices</router-link></p>
        </div>
      </div>
    </div>

    <div v-if="paused.length" class="card latest paused-panel">
      <header class="latest-head">
        <h2>Paused alerts <span class="muted">({{ pausedTotal }})</span></h2>
        <router-link :to="{ name: 'paused' }" class="muted all">Manage paused and muted errors →</router-link>
      </header>
      <table class="table">
        <tbody>
          <tr v-for="a in paused" :key="a.id">
            <td class="c-sev"><span class="badge" :class="a.severity">{{ SEVERITY_LABEL[a.severity] }}</span></td>
            <td class="c-dev"><b>{{ a.host_name }}</b> <span class="badge" :class="(a.infra || '').toLowerCase()">{{ a.infra }}</span></td>
            <td class="c-msg"><span class="mono msg">{{ a.message }}</span></td>
            <td class="c-time"><span class="mono">until {{ exactTime(a.paused_until) }}</span><small class="muted">{{ a.paused_by }}</small></td>
          </tr>
        </tbody>
      </table>
    </div>

    <div class="card latest">
      <header class="latest-head">
        <h2>Latest alerts</h2>
      </header>
      <table v-if="latest.length" class="table">
        <tbody>
          <tr v-for="a in latest" :key="a.id">
            <td class="c-sev"><span class="badge" :class="a.severity">{{ SEVERITY_LABEL[a.severity] }}</span></td>
            <td class="c-time"><span class="mono">{{ exactTime(a.timestamp) }}</span></td>
            <td class="c-dev"><b>{{ a.host_name }}</b> <span class="badge" :class="(a.infra || '').toLowerCase()">{{ a.infra }}</span></td>
            <td class="c-msg"><span v-if="a.keyword" class="badge kw">Keyword: {{ a.keyword }}</span> <span class="mono msg">{{ a.message }}</span></td>
          </tr>
        </tbody>
      </table>
      <p v-else class="muted none">No open alerts. All quiet.</p>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import CollectorBanner from 'components/CollectorBanner.vue'
import { api, errorMessage } from 'src/lib/api'
import { SEVERITY_LABEL, exactTime } from 'src/lib/format'
import { collectorState } from 'src/composables/useCollector'
import { infraState, refreshInfras } from 'src/composables/useInfras'
import { usePolling } from 'src/composables/usePolling'
import { toast } from 'src/composables/useToast'

const latest = ref([])
const paused = ref([])
const pausedTotal = ref(0)
usePolling(async () => {
  latest.value = (await api.alerts({ status: 'open', limit: 8 })).items
  const p = await api.alerts({ status: 'paused', limit: 8 })
  paused.value = p.items
  pausedTotal.value = p.total
}, 15000)

const collecting = ref(false)
const collectNote = ref('')
const schedule = computed(() => {
  const c = collectorState.status
  if (!c || !c.enabled) return 'Pulls the latest logs from the demo log generator.'
  const every = c.interval_seconds >= 60 ? `${Math.round(c.interval_seconds / 60)} min` : `${c.interval_seconds} s`
  return `Runs by itself every ${every} (each run reads the last ${c.window_minutes} min and catches up after any gap). This button runs it now.`
})
const noteText = computed(() => collectNote.value || schedule.value)
async function pull () {
  collecting.value = true
  try {
    const r = await api.collect(collectorState.status?.window_minutes || 5, false)
    collectNote.value = `Last pull: ${r.matched_to_a_device} log lines matched your devices → ${r.new_open_alerts} new alert${r.new_open_alerts === 1 ? '' : 's'}` +
      (r.ignored_by_keyword ? `, ${r.ignored_by_keyword} ignored by keyword` : '') + `, ${r.below_severity_threshold} below severity threshold.`
    toast(r.new_open_alerts ? `${r.new_open_alerts} new alert${r.new_open_alerts === 1 ? '' : 's'}` : 'All quiet: no new alerts')
    latest.value = (await api.alerts({ status: 'open', limit: 8 })).items
    await refreshInfras()
  } catch (e) {
    toast(errorMessage(e), 'err')
  } finally {
    collecting.value = false
  }
}
</script>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; margin-bottom: 20px; }
.intro { margin-bottom: 0; }
.collect { display: grid; gap: 4px; justify-items: end; max-width: 420px; text-align: right; }
.f-net { font-size: 13px; font-weight: 700; color: #9a4a00; }
.f-paused { font-size: 13px; font-weight: 700; color: #33507a; }
.paused-panel { margin-top: 20px; border-left: 4px solid #6b7fa6; }
.paused-panel .c-time small { display: block; }
.latest { margin-top: 20px; padding: 16px; }
.latest-head { display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 8px; }
.latest-head h2 { font-size: 18px; }
.latest .table { width: 100%; border-collapse: collapse; }
.latest .table td { padding: 8px 10px; border-top: 1px solid var(--line); vertical-align: top; }
.latest .c-sev, .latest .c-time, .latest .c-dev { white-space: nowrap; }
.latest .msg { display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical; overflow: hidden; word-break: break-word; }
.badge.kw { background: #efe7ff; color: #5b2bb5; }
.none { padding: 8px 0; }
.blocks { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; align-items: stretch; }
.block { display: flex; flex-direction: column; border-radius: 12px; padding: 16px; --c: var(--alpha); background: var(--alpha-bg); border: 1px solid #f3cf99; }
.block.bravo { --c: var(--bravo); background: var(--bravo-bg); border-color: #a6dbe4; }
.block-head { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: baseline; gap: 4px 16px; margin-bottom: 14px; }
.block-title { font-size: 28px; font-weight: 800; color: var(--c); }
.block-title:hover { text-decoration: underline; }
.block-sum { color: var(--muted); }
.block-sum b { color: var(--text); }
.folders { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 12px; }
.folder { display: grid; gap: 4px; padding: 14px; align-content: start; }
.folder:hover { border-color: var(--c); box-shadow: 0 0 0 1px var(--c); }
.f-name { font-weight: 700; font-size: 17px; }
.f-count { font-size: 34px; font-weight: 800; line-height: 1.1; color: var(--muted); }
.f-count.has { color: var(--critical); }
.f-label { font-size: 14px; }
.f-sev { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
.link { color: var(--primary); text-decoration: underline; }
@media (max-width: 1100px) { .blocks { grid-template-columns: 1fr; } }
</style>
