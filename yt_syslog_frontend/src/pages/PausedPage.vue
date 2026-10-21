<template>
  <section>
    <h1 class="page-title">Paused alerts</h1>
    <p class="muted intro">
      Alerts hidden until a chosen time. They come back to the open list automatically when the time passes, or sooner if you unpause them.
      When you paused them you could also <b>mute the same error</b>: new alerts that repeat it are kept here without alarming.
    </p>

    <h2 class="sub">Muted errors <span v-if="rules.length" class="muted">({{ rules.length }})</span></h2>
    <div v-if="rules.length" class="card table-wrap muted-box">
      <table class="table">
        <thead><tr><th>Device</th><th>The error that is muted</th><th>Until</th><th>Muted by</th><th class="r">Paused now</th><th><span class="sr-only">Actions</span></th></tr></thead>
        <tbody>
          <tr v-for="r in rules" :key="r.id">
            <td class="nowrap"><router-link :to="{ name: 'device', params: { id: r.device_id } }"><b>{{ r.device_name }}</b></router-link> <span class="badge" :class="r.infra.toLowerCase()">{{ r.infra }}</span></td>
            <td class="mono msg" :title="r.sample">{{ r.signature }}</td>
            <td class="nowrap mono">{{ exactTime(r.until) }}</td>
            <td>{{ r.who }}</td>
            <td class="r">{{ r.covers_alerts }}</td>
            <td class="r"><button class="btn tiny" :disabled="busy" @click="release(r)">Stop muting</button></td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="muted none">Nothing is muted. Pause an alert with "Also mute the same error" ticked to mute it.</p>

    <h2 class="sub">Paused alerts</h2>
    <AlertList :key="listKey" fixed-status="paused" />
  </section>
</template>

<script setup>
import { ref } from 'vue'
import AlertList from 'components/AlertList.vue'
import { NAME_REQUIRED, api, errorMessage } from 'src/lib/api'
import { demandName, user } from 'src/composables/useUser'
import { exactTime } from 'src/lib/format'
import { refreshInfras } from 'src/composables/useInfras'
import { usePolling } from 'src/composables/usePolling'
import { toast } from 'src/composables/useToast'

const rules = ref([])
const busy = ref(false)
const listKey = ref(0) // bumping it reloads the paused-alerts list right after a mute is released
const { refresh } = usePolling(async () => { rules.value = await api.pauseRules() }, 15000)

async function release (r) {
  if (!user.name.trim()) { demandName(); toast(NAME_REQUIRED, 'err'); return } // before any question is asked
  const bring = r.covers_alerts > 0 && window.confirm(`Also bring back the ${r.covers_alerts} paused alert${r.covers_alerts === 1 ? '' : 's'} with this error?\n\nOK = bring them back and stop muting\nCancel = stop muting only`)
  busy.value = true
  try {
    const out = await api.deletePauseRule(r.id, bring)
    toast(`Stopped muting the error on ${r.device_name}${out.unpaused ? ` · ${out.unpaused} alert${out.unpaused === 1 ? '' : 's'} back in the open list` : ''}`)
    listKey.value++
    await Promise.all([refresh(), refreshInfras()])
  } catch (e) {
    toast(errorMessage(e), 'err')
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.intro { margin-bottom: 16px; max-width: 80ch; }
.sub { font-size: 18px; margin: 18px 0 8px; }
.none { margin-bottom: 8px; }
.table-wrap { overflow-x: auto; }
.table { width: 100%; border-collapse: collapse; min-width: 820px; }
.table th { text-align: left; font-size: 13px; color: var(--muted); font-weight: 600; padding: 10px 12px; border-bottom: 1px solid var(--line); background: #fafbfc; }
.table td { padding: 9px 12px; border-bottom: 1px solid var(--line); vertical-align: top; }
.table tbody tr:last-child td { border-bottom: 0; }
.msg { max-width: 520px; word-break: break-word; font-size: 13px; }
.nowrap { white-space: nowrap; }
.table th.r, .r { text-align: right; }
</style>
