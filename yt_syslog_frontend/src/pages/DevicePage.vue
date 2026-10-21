<template>
  <section>
    <div v-if="failed" class="card empty"><h3>Device not found</h3><router-link to="/" class="btn primary">Back to overview</router-link></div>
    <template v-else-if="info">
      <div class="crumbs">
        <router-link to="/">Overview</router-link> ›
        <router-link :to="{ name: 'infra', params: { name: info.device.infra } }">{{ info.device.infra }}</router-link> ›
        <router-link :to="{ name: 'infra', params: { name: info.device.infra, folder: info.device.folder } }">{{ info.device.folder }}</router-link> ›
        {{ info.device.name }}
      </div>
      <div class="head">
        <div>
          <h1 class="page-title">
            <span class="badge" :class="info.device.infra.toLowerCase()">{{ info.device.infra }}</span>
            {{ info.device.name }}
          </h1>
          <p class="muted"><span class="mono">{{ info.device.ip }}</span> · {{ info.device.folder }}<template v-if="info.device.vendor"> · {{ info.device.vendor }}</template></p>
        </div>
        <button class="btn" @click="rules.open(info.device)">Alert settings</button>
      </div>

      <div class="card rules">
        <div><span class="label">Alerts on</span>
          <div class="tags"><span v-for="s in info.severities" :key="s" class="tag">{{ s }}</span><span v-if="!info.severities.length" class="badge critical">None, no alerts</span></div>
        </div>
        <div><span class="label">Keywords that always alert</span>
          <div class="tags"><span v-for="k in info.keywords" :key="k.id" class="tag kw">{{ k.keyword }}</span><span v-if="!info.keywords.length" class="muted">None</span></div>
        </div>
        <div><span class="label">Keywords ignored</span>
          <div class="tags"><span v-for="k in info.ignore" :key="k.id" class="tag ign">{{ k.keyword }}</span><span v-if="!info.ignore.length" class="muted">None</span></div>
        </div>
      </div>

      <AlertList :device-id="info.device.id" :infra="info.device.infra" />
      <DeviceRulesDialog ref="rules" @changed="load" />
    </template>
    <p v-else class="muted">Loading…</p>
  </section>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue'
import AlertList from 'components/AlertList.vue'
import DeviceRulesDialog from 'components/DeviceRulesDialog.vue'
import { api } from 'src/lib/api'

const props = defineProps({ id: { type: [String, Number], required: true } })
const info = ref(null)
const failed = ref(false)
const rules = ref(null)

async function load () {
  try {
    info.value = await api.settings(Number(props.id))
    failed.value = false
  } catch {
    failed.value = true
  }
}
onMounted(load)
watch(() => props.id, load)
</script>

<style scoped>
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; flex-wrap: wrap; margin-bottom: 14px; }
.page-title { display: flex; align-items: center; gap: 12px; }
.page-title .badge { font-size: 16px; padding: 3px 12px; }
.rules { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; padding: 14px 16px; margin-bottom: 16px; }
.label { display: block; font-size: 13px; font-weight: 600; color: var(--muted); margin-bottom: 6px; }
.tags { display: flex; flex-wrap: wrap; gap: 4px; }
.tag { padding: 2px 9px; border-radius: 99px; background: var(--info-bg); color: var(--info); font-size: 13px; font-weight: 600; }
.tag.kw { background: #efe7ff; color: #5b2bb5; }
.tag.ign { background: #f1f1f1; color: #555; text-decoration: line-through; }
.empty { padding: 40px 20px; text-align: center; display: grid; gap: 10px; justify-items: center; }
</style>
