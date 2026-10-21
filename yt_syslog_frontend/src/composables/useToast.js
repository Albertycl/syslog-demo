import { reactive } from 'vue'

export const toasts = reactive([])
let seq = 0

export function toast (message, kind = 'ok') {
  const t = { id: ++seq, message, kind }
  toasts.push(t)
  setTimeout(() => {
    const i = toasts.findIndex((x) => x.id === t.id)
    if (i >= 0) toasts.splice(i, 1)
  }, 4200)
}
