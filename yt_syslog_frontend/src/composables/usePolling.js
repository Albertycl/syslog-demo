import { onBeforeUnmount, onMounted, ref } from 'vue'

// Runs `fn` now and then every `ms` while the tab is visible. Runs never overlap: a refresh requested while one is
// in flight waits for it, so an older (slower) response can't overwrite newer data.
export function usePolling (fn, ms = 15000) {
  const loading = ref(true)
  const error = ref('')
  const updatedAt = ref(null)
  let timer = null
  let chain = Promise.resolve()
  let inflight = 0

  async function once () {
    inflight++
    try {
      await fn()
      error.value = ''
      updatedAt.value = new Date()
    } catch (e) {
      error.value = e?.response?.data?.error || 'Cannot reach the server.'
    } finally {
      inflight--
      loading.value = false
    }
  }
  const run = () => { chain = chain.then(once, once); return chain }

  onMounted(() => {
    run()
    // the timer never piles up requests behind a slow one
    timer = setInterval(() => { if (!document.hidden && inflight === 0) run() }, ms)
  })
  onBeforeUnmount(() => clearInterval(timer))

  return { loading, error, updatedAt, refresh: run }
}
