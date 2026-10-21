<template>
  <div v-if="problem" class="cbanner" :class="problem.level" role="alert">
    <div class="cb-text">
      <b>{{ problem.title }}</b>
      <span>{{ problem.message }}</span>
      <small>{{ problem.detail }}</small>
    </div>
    <router-link :to="{ name: 'collector' }" class="btn tiny">See collector runs</router-link>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { collectorState } from 'src/composables/useCollector'
import { exactTime } from 'src/lib/format'

// Shown on the front page when the collector cannot read its log source (or has stopped running).
const problem = computed(() => {
  const s = collectorState.status
  if (!s || !s.enabled) return null
  const when = (t) => (t ? exactTime(t) : 'never')
  if (s.last_ok === false) {
    return {
      level: 'bad', title: 'Log source cannot be read',
      message: s.error_message || 'The last collection failed.',
      detail: `Last attempt ${when(s.last_run)} · last successful ${when(s.last_success)}. No new alerts are coming in until this is fixed.`
    }
  }
  if (s.stale) {
    return {
      level: 'warn', title: 'The collector has stopped running',
      message: `It should run every ${Math.round(s.interval_seconds / 60) || 1} min but its last run was ${when(s.last_run)}.`,
      detail: 'New alerts are not being collected. Check that the backend is running.'
    }
  }
  if (s.last_problems > 0) {
    return {
      level: 'warn', title: 'The last collection skipped some lines',
      message: `${s.last_problems} log line${s.last_problems === 1 ? '' : 's'} could not be processed or stored.`,
      detail: 'Open Collector runs and click the run for details.'
    }
  }
  if (s.last_truncated) {
    return {
      level: 'warn', title: 'The last collection could not read every log line',
      message: 'More lines arrived than one run reads, so some may have been skipped.',
      detail: 'This happens during a log storm. Check the Collector runs page.'
    }
  }
  return null
})
</script>

<style scoped>
.cbanner { display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; padding: 14px 16px; border-radius: 8px; margin-bottom: 16px; }
.cbanner.bad { background: #fde8e6; border: 1px solid #f0b4ae; color: #7a1710; }
.cbanner.warn { background: #fff6cc; border: 1px solid #e6cf6a; color: #5c4300; }
.cb-text { display: grid; gap: 2px; min-width: 0; }
.cb-text b { font-size: 16px; }
.cb-text small { opacity: .85; }
</style>
