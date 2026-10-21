<template>
  <section class="classic">
    <div class="alert-toggle">
      <label class="toggle">
        <input type="checkbox" :checked="sound.on" @change="toggleSound">
        <span class="track" aria-hidden="true"><i /></span>
        <span>{{ sound.on ? 'alert on' : 'alert off' }}</span>
      </label>
    </div>

    <div class="cb-wrap"><CollectorBanner /></div>
    <div v-if="infraState.error" class="banner" role="alert">Can't reach the backend. Showing the last known numbers.</div>

    <div class="row">
      <div v-for="i in infraState.list" :key="i.name" class="col-6" :class="`bg-${i.name.toLowerCase()}`">
        <div class="title">{{ i.name }}</div>
        <div class="cards">
          <div v-for="f in i.folders" :key="f.name" class="card-q">
            <div class="section">
              <div class="name">
                <router-link :to="{ name: 'infra', params: { name: i.name, folder: f.name } }">{{ f.name }}</router-link>
              </div>
              <div class="avatars">
                <span v-if="f.open_alerts" class="avatar red blink" :title="`${f.open_alerts} open alerts`">{{ f.open_alerts }}</span>
                <span v-if="f.escalated" class="avatar yellow blink" :title="`${f.escalated} escalated to NET`">{{ f.escalated }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <p class="legend">
      <span class="avatar red small">n</span> open alerts &nbsp;
      <span class="avatar yellow small">n</span> escalated to NET
    </p>
  </section>
</template>

<script setup>
import CollectorBanner from 'components/CollectorBanner.vue'
import { infraState } from 'src/composables/useInfras'
import { sound, toggleSound } from 'src/composables/useSound'
</script>

<style scoped>
/* Reproduces the original landing page: solid colour blocks, big white titles, grey folder cards,
   blinking red (alerts) and yellow (escalate to NET) circles. */
.classic { font-family: Roboto, system-ui, -apple-system, 'Segoe UI', sans-serif; }
.cb-wrap { margin: 16px 24px 0; }
.alert-toggle { display: flex; justify-content: center; padding: 16px; }
.toggle { display: inline-flex; align-items: center; gap: 10px; cursor: pointer; font-size: 16px; }
.toggle input { position: absolute; opacity: 0; }
.track { width: 40px; height: 22px; border-radius: 11px; background: #bdbdbd; position: relative; transition: background .2s; }
.track i { position: absolute; top: 2px; left: 2px; width: 18px; height: 18px; border-radius: 50%; background: #fff; box-shadow: 0 1px 3px rgba(0, 0, 0, .4); transition: transform .2s; }
.toggle input:checked + .track { background: #2196f3; }
.toggle input:checked + .track i { transform: translateX(18px); }
.toggle input:focus-visible + .track { outline: 3px solid #93b4ff; outline-offset: 2px; }

.row { display: flex; flex-wrap: wrap; margin: 24px; }
.col-6 { width: 50%; padding-bottom: 8px; }
.bg-alpha { background: #fb8c00; }      /* orange-6 */
.bg-bravo { background: #d4e157; }     /* lime-5 */
.title { font-size: 3rem; line-height: 3.125rem; font-weight: 700; color: #fff; text-align: center; padding: 8px 0; letter-spacing: normal; }
.cards { display: flex; flex-wrap: wrap; justify-content: center; }
.card-q { width: calc(33.333% - 16px); margin: 8px; background: #eee; border-radius: 4px; box-shadow: 0 1px 5px rgba(0, 0, 0, .2), 0 2px 2px rgba(0, 0, 0, .14), 0 3px 1px -2px rgba(0, 0, 0, .12); }
.section { display: flex; align-items: center; gap: 8px; padding: 14px 12px 14px 16px; min-height: 92px; }
.name { flex: 1 1 auto; min-width: 0; font-size: 1.35rem; font-weight: 700; line-height: 2rem; overflow-wrap: normal; word-break: normal; }
.name a { color: #000; }
.name a:hover { text-decoration: underline; }
.avatars { flex: none; display: flex; justify-content: flex-end; gap: 8px; }
.avatar { display: inline-flex; align-items: center; justify-content: center; width: 48px; height: 48px; border-radius: 50%; color: #fff; font-size: 1.5rem; font-weight: 700; }
.avatar.red { background: #f44336; }
.avatar.yellow { background: #ffeb3b; color: #fff; text-shadow: 0 0 2px rgba(0, 0, 0, .5); }
.avatar.small { width: 24px; height: 24px; font-size: 12px; vertical-align: middle; }
.blink { animation: blink 1s ease-in-out infinite; }
@keyframes blink { 50% { opacity: .25; } }
.legend { margin: 0 24px 24px; color: var(--muted); font-size: 14px; }
@media (max-width: 1100px) { .col-6 { width: 100%; } .card-q { width: calc(50% - 16px); } }
</style>
