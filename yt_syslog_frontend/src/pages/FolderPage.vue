<template>
  <section>
    <div class="crumbs">
      <router-link to="/">Overview</router-link> ›
      <router-link :to="{ name: 'infra', params: { name } }">{{ name }}</router-link>
      <template v-if="folder">› {{ folder }}</template>
    </div>
    <h1 class="page-title">
      <span class="badge" :class="name.toLowerCase()">{{ name }}</span>
      {{ folder || 'All folders' }}
    </h1>

    <nav class="tabs folder-tabs" aria-label="Folders">
      <router-link class="tab" :to="{ name: 'infra', params: { name } }">All<span class="n">{{ infra.open_alerts }}</span></router-link>
      <router-link v-for="f in infra.folders" :key="f.name" class="tab" :to="{ name: 'infra', params: { name, folder: f.name } }">
        {{ f.name }}<span class="n">{{ f.open_alerts }}</span>
      </router-link>
    </nav>

    <AlertList :infra="name" :folder="folder" />
  </section>
</template>

<script setup>
import { computed } from 'vue'
import AlertList from 'components/AlertList.vue'
import { infraState } from 'src/composables/useInfras'

const props = defineProps({ name: { type: String, required: true }, folder: { type: String, default: '' } })
const infra = computed(() => infraState.list.find((i) => i.name === props.name) || { open_alerts: 0, folders: [] })
</script>

<style scoped>
.page-title { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.page-title .badge { font-size: 16px; padding: 3px 12px; }
.folder-tabs { margin-bottom: 16px; }
</style>
