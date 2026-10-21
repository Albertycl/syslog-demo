<template>
  <section>
    <div class="head">
      <div>
        <h1 class="page-title">Collector runs</h1>
        <p class="muted intro">
          Every scheduled (and manual) pull of new logs from the demo log generator. A run reads the last few minutes, matches the lines to your devices,
          and turns the ones that meet each device's rules into alerts.
        </p>
      </div>
      <div class="runbox">
        <label for="lookback" class="muted">Look back</label>
        <select id="lookback" v-model.number="lookback" class="input w-look" aria-label="Look back">
          <option v-for="o in LOOKBACKS" :key="o.minutes" :value="o.minutes">{{ o.label }}</option>
        </select>
        <button class="btn" :disabled="running" @click="runNow">{{ running ? 'Reading logs…' : 'Run now' }}</button>
      </div>
    </div>

    <CollectorBanner />
    <div v-if="error" class="banner" role="alert"><span>Can't reach the backend.</span><button class="btn tiny" @click="refresh">Retry</button></div>

    <div v-if="status" class="cards">
      <div class="card stat" :class="health.level">
        <span class="label">Status</span>
        <b class="big">{{ health.text }}</b>
        <small class="muted">{{ health.sub }}</small>
      </div>
      <div class="card stat">
        <span class="label">Schedule</span>
        <b class="big">{{ status.enabled ? `Every ${every}` : 'Off' }}</b>
        <small class="muted">{{ status.enabled ? `Each run reads the last ${status.window_minutes} min` : 'Set COLLECT_INTERVAL_SECONDS in .env' }}</small>
      </div>
      <div class="card stat">
        <span class="label">Last run</span>
        <b class="big mono">{{ status.last_run ? exactTime(status.last_run) : 'Never' }}</b>
        <small class="muted">Source: {{ status.elasticsearch }}</small>
      </div>
      <div class="card stat">
        <span class="label">Last 24 hours</span>
        <b class="big">{{ status.runs_24h }} runs</b>
        <small :class="status.failed_24h ? 'bad-text' : 'muted'">{{ status.failed_24h }} failed · {{ status.new_alerts_24h }} new alert{{ status.new_alerts_24h === 1 ? '' : 's' }}</small>
      </div>
    </div>

    <div class="toolbar">
      <div class="tabs" role="group" aria-label="Results">
        <button class="tab" :aria-pressed="!errorsOnly" @click="errorsOnly = false">All runs</button>
        <button class="tab" :aria-pressed="errorsOnly" @click="errorsOnly = true">Errors only<span v-if="status" class="n">{{ status.failed_24h }}</span></button>
      </div>
      <span class="muted">Showing the latest {{ runs.length }}. Click a row for details.</span>
    </div>
    <div class="legend muted">
      <div><b>Window</b> = how far back in the log source that run looked (5 min = logs from the 5 minutes before the run).</div>
      <div><b>Matched</b> = how many of the log lines came from one of your devices (matched by hostname, sender IP address or the device name in the message). The rest come from machines that are not in your device list and are skipped.</div>
    </div>

    <div v-if="runs.length" class="card table-wrap">
      <table class="table">
        <thead>
          <tr><th>Time</th><th>Result</th><th>By</th><th title="How far back in the log source this run looked">Window</th><th class="r">Log lines</th><th class="r" title="Log lines that came from one of your devices">Matched</th><th class="r">New alerts</th><th class="r">Auto-acked</th><th class="r">Ignored</th><th class="r">Below rules</th><th class="r">Took</th></tr>
        </thead>
        <tbody>
          <template v-for="r in runs" :key="r.id">
            <tr :class="{ bad: !r.ok, open: openId === r.id }" @click="openId = openId === r.id ? null : r.id">
              <td class="mono nowrap">{{ exactTime(r.started_at) }}</td>
              <td><span class="badge" :class="r.ok ? 'info ok' : 'critical'">{{ r.ok ? 'OK' : kindLabel(r.error_kind) }}</span></td>
              <td>{{ r.source === 'schedule' ? 'Schedule' : 'Manual' }}</td>
              <td>{{ r.minutes }} min</td>
              <td class="r">{{ r.ok ? r.scanned : '—' }}</td>
              <td class="r">{{ r.ok ? r.matched : '—' }}</td>
              <td class="r"><b :class="{ hot: r.new_alerts > 0 }">{{ r.ok ? r.new_alerts : '—' }}</b></td>
              <td class="r">{{ r.ok ? r.auto_acked : '—' }}</td>
              <td class="r">{{ r.ok ? r.ignored : '—' }}</td>
              <td class="r">{{ r.ok ? r.below_threshold : '—' }}</td>
              <td class="r muted">{{ r.duration_ms != null ? `${r.duration_ms} ms` : '—' }}</td>
            </tr>
            <tr v-if="openId === r.id" class="detail"><td colspan="11">
              <p v-if="!r.ok" class="err-msg"><b>{{ r.error_message }}</b></p>
              <p v-if="!r.ok && r.details.raw_error" class="mono muted small">{{ r.details.raw_error }}</p>
              <template v-if="r.ok">
                <p class="muted small">
                  {{ r.matched }} of {{ r.scanned }} log lines belonged to your devices · {{ r.unmatched }} did not (e.g. heartbeats from senders that are not in the inventory)
                  <template v-if="r.already_stored"> · {{ r.already_stored }} were already stored</template>
                  <template v-if="r.details.truncated"> · <b>more lines existed than were read in this window</b></template>
                </p>
                <div v-if="Object.keys(r.details.per_device || {}).length" class="chips">
                  <span class="muted small">New alerts by device:</span>
                  <router-link v-for="(n, name) in r.details.per_device" :key="name" :to="{ name: 'rules', query: { q: name } }" class="chip">{{ name }} <b>{{ n }}</b></router-link>
                </div>
                <div v-if="(r.details.ignored_top || []).length" class="ignored">
                  <p class="muted small"><b>{{ r.ignored }} line(s) were ignored (no alert created).</b> Each one contained a word that you set to "never alert" for that device. The ignored word and how many lines it hid:</p>
                  <ul class="samples">
                    <li v-for="(x, i) in r.details.ignored_top" :key="i">Ignored word <span class="badge kw">{{ x.keyword }}</span> hid <b>{{ x.count }} line{{ x.count === 1 ? '' : 's' }}</b> <span class="muted small">on {{ x.devices.join(', ') }}</span><br><span class="muted small">Example line:</span> <span class="mono">{{ x.sample }}</span></li>
                  </ul>
                </div>
                <p v-else-if="r.ignored" class="muted small">{{ r.ignored }} line(s) were ignored because of a "never alert" word (the word was not recorded for this older run).</p>
                <p v-if="(r.details.unmatched_top || []).length" class="muted small">Unmatched senders: {{ r.details.unmatched_top.map((x) => `${x[0]} (${x[1]})`).join(', ') }}</p>
                <ul v-if="(r.details.samples || []).length" class="samples">
                  <li v-for="(x, i) in r.details.samples" :key="i"><b>{{ x.device }}</b> <span class="badge info">{{ x.level }}</span> <span v-if="x.keyword" class="badge kw">Keyword: {{ x.keyword }}</span> <span class="mono">{{ x.message }}</span></li>
                </ul>
                <p v-if="(r.details.bad_docs || 0) + (r.details.rows_failed || 0)" class="err-msg small">
                  <b>{{ r.details.bad_docs || 0 }}</b> log line(s) could not be read and <b>{{ r.details.rows_failed || 0 }}</b> alert(s) could not be stored.
                </p>
                <p v-if="r.details.muted" class="muted small">{{ r.details.muted }} repeat(s) were kept as muted (same error as a paused alert).</p>
                <p v-if="!r.new_alerts && !r.auto_acked" class="muted small">No new alerts: nothing in this window met a device's severity or keyword rules.</p>
              </template>
            </td></tr>
          </template>
        </tbody>
      </table>
    </div>
    <div v-else-if="!loading" class="card empty">
      <h3>{{ errorsOnly ? 'No failed runs' : 'No runs yet' }}</h3>
      <p class="muted">{{ errorsOnly ? 'Every recorded run succeeded.' : 'The first run happens a few seconds after the backend starts.' }}</p>
    </div>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import CollectorBanner from 'components/CollectorBanner.vue'
import { api, errorMessage } from 'src/lib/api'
import { exactTime } from 'src/lib/format'
import { collectorState, refreshCollector } from 'src/composables/useCollector'
import { refreshInfras } from 'src/composables/useInfras'
import { usePolling } from 'src/composables/usePolling'
import { toast } from 'src/composables/useToast'

const LOOKBACKS = [{ minutes: 5, label: 'Last 5 minutes' }, { minutes: 60, label: 'Last hour' }, { minutes: 360, label: 'Last 6 hours' }, { minutes: 1440, label: 'Last 24 hours' }]
const lookback = ref(5)
const runs = ref([])
const errorsOnly = ref(false)
const openId = ref(null)
const running = ref(false)
const status = computed(() => collectorState.status)

const { loading, error, refresh } = usePolling(async () => {
  const [r] = await Promise.all([api.collectRuns(100, errorsOnly.value), refreshCollector()])
  runs.value = r
}, 15000)
watch(errorsOnly, refresh)

const every = computed(() => (status.value.interval_seconds >= 60 ? `${Math.round(status.value.interval_seconds / 60)} min` : `${status.value.interval_seconds} s`))
const health = computed(() => {
  const s = status.value
  if (!s.enabled) return { level: '', text: 'Schedule off', sub: 'Runs only when you press Run now' }
  if (s.last_ok === false) return { level: 'bad', text: 'Failing', sub: s.error_message }
  if (s.stale) return { level: 'warn', text: 'Stalled', sub: 'The collector has not run recently' }
  if (s.last_ok === null) return { level: '', text: 'Starting', sub: 'Waiting for the first run' }
  return { level: 'good', text: 'Healthy', sub: 'The log source answered on the last run' }
})
const KIND = { unreachable: 'Unreachable', timeout: 'Timed out', certificate: 'Certificate', auth: 'Login rejected', forbidden: 'Not allowed', server: 'ES error', other: 'Error' }
const kindLabel = (k) => KIND[k] || 'Error'

async function runNow () {
  running.value = true
  try {
    const r = await api.collect(lookback.value, false)
    toast(r.new_open_alerts ? `${r.new_open_alerts} new alert${r.new_open_alerts === 1 ? '' : 's'}` : 'Run finished: no new alerts')
    await Promise.all([refresh(), refreshInfras()])
  } catch (e) {
    toast(errorMessage(e), 'err')
    await refresh()
  } finally {
    running.value = false
  }
}
</script>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; margin-bottom: 14px; }
.intro { max-width: 80ch; }
.runbox { display: flex; align-items: center; gap: 8px; }
.w-look { width: 170px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 12px; margin-bottom: 18px; }
.stat { display: grid; gap: 4px; padding: 14px 16px; }
.stat .label { font-size: 13px; font-weight: 600; color: var(--muted); }
.stat .big { font-size: 20px; line-height: 1.25; }
.stat.good { border-left: 4px solid #16a34a; }
.stat.bad { border-left: 4px solid var(--critical); background: #fff7f6; }
.stat.warn { border-left: 4px solid #d9a400; background: #fffdf0; }
.bad-text { color: var(--critical); font-weight: 600; }
.toolbar { display: flex; flex-wrap: wrap; gap: 14px; align-items: center; margin-bottom: 12px; }
.table-wrap { overflow-x: auto; }
.table { width: 100%; border-collapse: collapse; min-width: 980px; }
.table th { text-align: left; font-size: 13px; color: var(--muted); font-weight: 600; padding: 10px 12px; border-bottom: 1px solid var(--line); background: #fafbfc; }
.table td { padding: 9px 12px; border-bottom: 1px solid var(--line); }
.table tbody tr { cursor: pointer; }
.table tbody tr:hover { background: #f8f9fb; }
.table tr.bad { background: #fff7f6; }
.table tr.detail { cursor: default; background: #fafbfc; }
.table tr.detail:hover { background: #fafbfc; }
.legend { display: grid; gap: 4px; margin: -4px 0 14px; font-size: 13px; max-width: 80ch; }
.table th.r, .table td.r { text-align: right; }
.nowrap { white-space: nowrap; }
.hot { color: var(--critical); }
.badge.ok { background: #e1f6e8; color: #14633a; }
.err-msg { color: #7a1710; margin-bottom: 4px; }
.small { font-size: 13px; margin: 4px 0; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 6px 0; }
.chip { padding: 2px 10px; border-radius: 99px; background: var(--info-bg); font-size: 13px; font-weight: 600; }
.samples { margin: 6px 0 0; padding-left: 18px; display: grid; gap: 4px; font-size: 13px; }
.samples .mono { word-break: break-word; }
.badge.kw { background: #efe7ff; color: #5b2bb5; }
.empty { padding: 40px 20px; text-align: center; display: grid; gap: 6px; }
.empty h3 { font-size: 20px; }
</style>
