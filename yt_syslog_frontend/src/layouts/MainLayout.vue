<template>
  <div class="app">
    <header class="topbar">
      <router-link :to="landingPath" class="brand">Syslog</router-link>
      <span class="status"><i class="dot" :class="{ on: !error }" />{{ error ? 'Cannot reach the server' : 'Live' }}</span>
      <router-link v-if="collectorText" :to="{ name: 'collector' }" class="status collector" :class="{ bad: collectorBad }">{{ collectorText }}</router-link>
      <span class="spacer" />
      <label class="who-box" :class="{ need: user.needName && !user.name.trim() }">
        <span>Your name</span>
        <input id="user-name" :value="user.name" class="input who-input" type="text" maxlength="40" placeholder="required for any change" autocomplete="name" aria-label="Your name" @input="setName($event.target.value)">
      </label>
      <button class="sound-btn" :class="{ blocked: sound.blocked && sound.on }" :title="soundTitle" :aria-pressed="sound.on" @click="toggleSound">
        <span aria-hidden="true">{{ sound.on ? '🔔' : '🔇' }}</span>
        Alert sound: {{ sound.on ? 'On' : 'Off' }}
      </button>
    </header>

    <div class="body">
      <nav class="drawer" aria-label="Main navigation">
        <router-link :to="landingPath" class="item" exact-active-class="" :class="{ 'router-link-exact-active': onLanding }">Overview</router-link>
        <router-link :to="{ name: 'alerts' }" class="item">All alerts <span class="count" :class="{ has: totalOpen }">{{ totalOpen }}</span></router-link>

        <section
          v-for="i in infraState.list"
          :key="i.name"
          class="sec"
          :class="[`sec-${i.name.toLowerCase()}`]"
          :aria-label="i.name"
        >
          <h2>{{ i.name }}</h2>
          <router-link
            :to="{ name: 'infra', params: { name: i.name } }"
            class="item"
            :class="[`group-${i.name.toLowerCase()}`, { active: route.params.name === i.name }]"
          >
            {{ i.name }}
            <span class="count" :class="{ has: i.open_alerts }">{{ i.open_alerts }}</span>
          </router-link>
        </section>

        <section class="sec sec-manage" aria-label="Manage">
          <h2>Manage</h2>
          <router-link :to="{ name: 'keywords' }" class="item">Keywords (all devices)</router-link>
          <router-link :to="{ name: 'auto-ack' }" class="item">Auto-acknowledge</router-link>
          <router-link :to="{ name: 'folders' }" class="item">Folders</router-link>
          <router-link :to="{ name: 'log' }" class="item">Log (who changed what)</router-link>
          <router-link :to="{ name: 'collector' }" class="item">Collector runs <span v-if="collectorBad" class="count has">!</span></router-link>
          <router-link :to="{ name: 'paused' }" class="item">Paused alerts <span v-if="pausedTotal" class="count">{{ pausedTotal }}</span></router-link>
          <router-link :to="{ name: 'rules' }" class="item">Alert rules</router-link>
          <router-link :to="{ name: 'devices' }" class="item">Devices</router-link>
        </section>
      </nav>

      <main class="content">
        <router-view />
      </main>
    </div>

    <div class="toasts" aria-live="polite">
      <div v-for="t in toasts" :key="t.id" class="toast" :class="{ err: t.kind === 'err' }">{{ t.message }}</div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { timeAgo } from 'src/lib/format'
import { collectorState, refreshCollector } from 'src/composables/useCollector'
import { setName, user } from 'src/composables/useUser'
import { infraState, refreshInfras } from 'src/composables/useInfras'
import { usePolling } from 'src/composables/usePolling'
import { primeOnFirstGesture, sound, toggleSound } from 'src/composables/useSound'
import { toasts } from 'src/composables/useToast'

const route = useRoute()
const { error } = usePolling(refreshInfras, 15000)

const landingPath = '/'
const onLanding = computed(() => route.name === 'home')

// background collector health (shared with the front-page banner and the Collector runs page)
usePolling(refreshCollector, 15000)
const collector = computed(() => collectorState.status)
const collectorBad = computed(() => Boolean(collector.value && collector.value.enabled && (collector.value.last_ok === false || collector.value.stale)))
const collectorText = computed(() => {
  const c = collector.value
  if (!c || !c.enabled) return ''
  if (c.last_ok === false) return 'Log source error'
  if (c.stale) return `Collector stalled, last run ${timeAgo(c.last_run)}`
  if (!c.last_run) return 'Collector starting…'
  return `Collector: every ${c.interval_seconds >= 60 ? `${Math.round(c.interval_seconds / 60)} min` : `${c.interval_seconds} s`}, last run ${timeAgo(c.last_run)}`
})
const totalOpen = computed(() => infraState.list.reduce((n, i) => n + i.open_alerts, 0))
const pausedTotal = computed(() => infraState.list.reduce((n, i) => n + (i.paused || 0), 0))
primeOnFirstGesture()

const soundTitle = computed(() => {
  const hint = sound.blocked && sound.on ? ' Click anywhere on the page first to allow audio.' : ''
  return `Click to turn the alert sound on or off. It says "Alpha alert" or "Bravo alert".${hint}`
})
</script>
