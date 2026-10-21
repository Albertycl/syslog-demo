<template>
  <section>
    <h1 class="page-title">Folders</h1>
    <p class="muted intro">Folders group devices by role inside ALPHA and BRAVO. Add your own, rename them, or delete one (its devices move to “Other”).</p>

    <div v-if="error" class="banner" role="alert"><span>Can't reach the backend.</span><button class="btn tiny" @click="refresh">Retry</button></div>

    <div class="blocks">
      <div v-for="i in INFRAS" :key="i" class="block" :class="i.toLowerCase()">
        <header class="block-head">
          <h2 class="block-title">{{ i }}</h2>
          <button class="btn tiny primary" @click="openAdd(i)">+ Add folder</button>
        </header>
        <ul class="list">
          <li v-for="f in byInfra(i)" :key="f.id" class="card row">
            <router-link :to="{ name: 'infra', params: { name: i, folder: f.name } }" class="fname">{{ f.name }}</router-link>
            <span class="muted">{{ f.devices }} device{{ f.devices === 1 ? '' : 's' }}</span>
            <span v-if="f.protected" class="muted note">catch-all</span>
            <span class="row-actions">
              <button class="btn tiny" :disabled="f.protected" @click="openRename(f)">Rename</button>
              <button class="btn tiny danger" :disabled="f.protected" @click="askDelete(f)">Delete</button>
            </span>
          </li>
        </ul>
      </div>
    </div>

    <dialog ref="nameDialog" class="sheet">
      <form class="sheet-body" novalidate @submit.prevent="saveName">
        <h2>{{ editing ? `Rename “${editing.name}”` : `Add folder to ${addInfra}` }}</h2>
        <div class="field">
          <label for="f-name">Folder name</label>
          <input id="f-name" ref="nameInput" v-model="name" class="input" maxlength="60" autocomplete="off" :aria-invalid="Boolean(nameError)">
          <span class="err" role="alert">{{ nameError }}</span>
        </div>
        <div class="sheet-actions">
          <button type="button" class="btn" @click="nameDialog.close()">Cancel</button>
          <button type="submit" class="btn primary" :disabled="busy">{{ editing ? 'Rename' : 'Add folder' }}</button>
        </div>
      </form>
    </dialog>

    <dialog ref="deleteDialog" class="sheet">
      <div class="sheet-body">
        <h2>Delete “{{ toDelete?.name }}”?</h2>
        <p class="muted">{{ toDelete?.devices ? `${toDelete.devices} device${toDelete.devices === 1 ? '' : 's'} will move to “Other”.` : 'It has no devices.' }}</p>
        <div class="sheet-actions">
          <button class="btn" @click="deleteDialog.close()">Keep it</button>
          <button class="btn danger" :disabled="busy" @click="confirmDelete">Delete folder</button>
        </div>
      </div>
    </dialog>
  </section>
</template>

<script setup>
import { nextTick, ref } from 'vue'
import { api, errorMessage } from 'src/lib/api'
import { INFRAS } from 'src/lib/format'
import { refreshInfras } from 'src/composables/useInfras'
import { usePolling } from 'src/composables/usePolling'
import { toast } from 'src/composables/useToast'

const folders = ref([])
const nameDialog = ref(null)
const deleteDialog = ref(null)
const nameInput = ref(null)
const editing = ref(null)
const addInfra = ref('')
const name = ref('')
const nameError = ref('')
const toDelete = ref(null)
const busy = ref(false)

const { error, refresh } = usePolling(async () => { folders.value = await api.folders() }, 30000)
const byInfra = (i) => folders.value.filter((f) => f.infra === i)

async function openAdd (infra) {
  editing.value = null; addInfra.value = infra; name.value = ''; nameError.value = ''
  nameDialog.value.showModal(); await nextTick(); nameInput.value?.focus()
}
async function openRename (f) {
  editing.value = f; name.value = f.name; nameError.value = ''
  nameDialog.value.showModal(); await nextTick(); nameInput.value?.select()
}
async function saveName () {
  if (!name.value.trim()) { nameError.value = 'Enter a folder name.'; return }
  busy.value = true
  try {
    if (editing.value) await api.renameFolder(editing.value.id, name.value.trim())
    else await api.addFolder(addInfra.value, name.value.trim())
    toast(editing.value ? 'Folder renamed' : `Folder “${name.value.trim()}” added`)
    nameDialog.value.close()
    await Promise.all([refresh(), refreshInfras()])
  } catch (e) {
    nameError.value = errorMessage(e)
  } finally {
    busy.value = false
  }
}
function askDelete (f) { toDelete.value = f; deleteDialog.value.showModal() }
async function confirmDelete () {
  busy.value = true
  try {
    const r = await api.deleteFolder(toDelete.value.id)
    toast(`“${r.deleted}” deleted${r.moved ? ` · ${r.moved} device${r.moved === 1 ? '' : 's'} moved to Other` : ''}`)
    deleteDialog.value.close()
    await Promise.all([refresh(), refreshInfras()])
  } catch (e) {
    toast(errorMessage(e), 'err')
  } finally {
    busy.value = false
  }
}
</script>

<style scoped>
.intro { margin-bottom: 16px; max-width: 70ch; }
.blocks { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; align-items: stretch; }
.block { border-radius: 12px; padding: 16px; background: var(--alpha-bg); border: 1px solid #f3cf99; --c: var(--alpha); }
.block.bravo { background: var(--bravo-bg); border-color: #a6dbe4; --c: var(--bravo); }
.block-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.block-title { font-size: 24px; font-weight: 800; color: var(--c); }
.list { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; }
.row { display: flex; align-items: center; gap: 12px; padding: 10px 12px; flex-wrap: wrap; }
.fname { font-weight: 700; flex: 1 1 140px; }
.fname:hover { text-decoration: underline; }
.note { font-size: 13px; }
.row-actions { display: flex; gap: 6px; margin-left: auto; }
@media (max-width: 1000px) { .blocks { grid-template-columns: 1fr; } }
</style>
