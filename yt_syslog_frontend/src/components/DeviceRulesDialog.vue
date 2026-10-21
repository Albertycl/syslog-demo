<template>
  <dialog ref="dlg" class="sheet wide">
    <div v-if="settings" class="sheet-body">
      <h2>Alert settings <span class="muted dev">{{ device.name }}</span></h2>
      <p class="muted">These rules decide which of this device's log lines become alerts.</p>

      <section class="set">
        <h3>Severity</h3>
        <p class="muted">A message becomes an alert when its severity is ticked.</p>
        <div class="sev-grid">
          <label v-for="o in settings.severity_options" :key="o" class="check"><input v-model="chosen" type="checkbox" :value="o"> {{ o }}</label>
        </div>
        <div><button class="btn tiny primary" :disabled="busy" @click="saveSeverities">Save severity</button></div>
      </section>

      <section class="set">
        <h3>Keywords that always alert</h3>
        <p class="muted">A message containing one of these words becomes an alert, whatever its severity.</p>
        <ul class="chips">
          <li v-for="k in settings.keywords" :key="k.id">{{ k.keyword }}<button :aria-label="`Remove keyword ${k.keyword}`" @click="removeKeyword(k)">×</button></li>
          <li v-if="!settings.keywords.length" class="muted none">None yet</li>
        </ul>
        <form class="add-row" @submit.prevent="addKeyword">
          <input v-model="newKeyword" class="input" placeholder="Add a keyword, e.g. port-channel" maxlength="200" aria-label="New keyword">
          <button class="btn tiny" :disabled="busy || !newKeyword.trim()">Add</button>
        </form>
      </section>

      <section class="set">
        <h3>Keywords to ignore</h3>
        <p class="muted">A message containing one of these words never becomes an alert.</p>
        <ul class="chips">
          <li v-for="k in settings.ignore" :key="k.id">{{ k.keyword }}<button :aria-label="`Remove ignore keyword ${k.keyword}`" @click="removeIgnore(k)">×</button></li>
          <li v-if="!settings.ignore.length" class="muted none">None yet</li>
        </ul>
        <form class="add-row" @submit.prevent="addIgnore">
          <input v-model="newIgnore" class="input" placeholder="Add a keyword to ignore" maxlength="200" aria-label="New ignore keyword">
          <button class="btn tiny" :disabled="busy || !newIgnore.trim()">Add</button>
        </form>
      </section>

      <p v-if="error" class="err" role="alert">{{ error }}</p>
      <div class="sheet-actions"><button class="btn" @click="dlg.close()">Close</button></div>
    </div>
    <div v-else class="sheet-body"><p class="muted">Loading…</p></div>
  </dialog>
</template>

<script setup>
import { ref } from 'vue'
import { api, errorMessage } from 'src/lib/api'
import { toast } from 'src/composables/useToast'

// Call open(device) from the parent; `changed` fires after anything is saved so the parent can refresh.
const emit = defineEmits(['changed'])

const dlg = ref(null)
const device = ref(null)
const settings = ref(null)
const chosen = ref([])
const newKeyword = ref('')
const newIgnore = ref('')
const error = ref('')
const busy = ref(false)

async function open (d) {
  device.value = d
  settings.value = null
  error.value = ''
  newKeyword.value = ''
  newIgnore.value = ''
  dlg.value.showModal()
  try {
    settings.value = await api.settings(d.id)
    chosen.value = [...settings.value.severities]
  } catch (e) {
    dlg.value.close()
    toast(errorMessage(e), 'err')
  }
}

async function guarded (fn, done) {
  busy.value = true
  error.value = ''
  try {
    await fn()
    emit('changed')
    if (done) toast(done)
  } catch (e) {
    error.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}

const saveSeverities = () => guarded(async () => {
  const r = await api.setSeverities(device.value.id, chosen.value)
  settings.value.severities = r.severities
}, `Severity saved for ${device.value.name}`)

const addKeyword = () => guarded(async () => {
  settings.value.keywords.push(await api.addKeyword(device.value.id, newKeyword.value.trim()))
  newKeyword.value = ''
})
const removeKeyword = (k) => guarded(async () => {
  await api.deleteKeyword(k.id)
  settings.value.keywords = settings.value.keywords.filter((x) => x.id !== k.id)
})
const addIgnore = () => guarded(async () => {
  settings.value.ignore.push(await api.addIgnore(device.value.id, newIgnore.value.trim()))
  newIgnore.value = ''
})
const removeIgnore = (k) => guarded(async () => {
  await api.deleteIgnore(k.id)
  settings.value.ignore = settings.value.ignore.filter((x) => x.id !== k.id)
})

defineExpose({ open })
</script>

<style scoped>
dialog.wide { width: min(640px, calc(100vw - 24px)); }
.dev { font-weight: 500; font-size: 18px; margin-left: 6px; }
.set { display: grid; gap: 8px; padding-top: 14px; border-top: 1px solid var(--line); }
.set h3 { font-size: 16px; }
.sev-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 6px 12px; }
.check { display: flex; align-items: center; gap: 8px; }
.check input { width: 18px; height: 18px; }
.chips { list-style: none; margin: 0; padding: 0; display: flex; flex-wrap: wrap; gap: 6px; }
.chips li { display: inline-flex; align-items: center; gap: 6px; padding: 3px 4px 3px 10px; border-radius: 99px; background: var(--info-bg); font-size: 14px; }
.chips li.none { background: none; padding: 0; }
.chips button { width: 22px; height: 22px; border: 0; border-radius: 50%; background: #d5dae1; font-size: 15px; line-height: 1; }
.chips button:hover { background: var(--critical-bg); color: var(--critical); }
.add-row { display: flex; gap: 8px; }
.err { color: var(--critical); }
</style>
