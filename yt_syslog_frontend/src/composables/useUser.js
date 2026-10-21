import { reactive } from 'vue'

// The person using the portal. Their name is sent with every change and recorded in the Log.
const KEY = 'syslog.who'
const read = () => { try { return window.localStorage.getItem(KEY) || '' } catch { return '' } }
const write = (v) => { try { window.localStorage.setItem(KEY, v) } catch { /* private mode */ } }

export const user = reactive({ name: read(), needName: false })

export function setName (v) {
  user.name = (v || '').slice(0, 40)
  user.needName = false
  write(user.name.trim())
}

// Called when something tries to change data without a name: highlight the box and move the cursor there.
export function demandName () {
  user.needName = true
  const el = document.getElementById('user-name')
  if (el) el.focus()
}
