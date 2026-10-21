<template>
  <section>
    <h1 class="page-title">All alerts</h1>
    <p class="muted intro">Alerts from ALPHA and BRAVO together. Use the filters to narrow them down.</p>
    <AlertList />
  </section>
</template>

<script setup>
import AlertList from 'components/AlertList.vue'
</script>

<style scoped>
.intro { margin-bottom: 16px; max-width: 70ch; }
</style>
