import { reactive } from 'vue'
import { API_BASE } from 'src/config/api'

// One voice clip per infra: "Alpha alert" and "Bravo alert". The switch is plain On / Off.
const CLIPS = { ALPHA: 'alpha_alert.mp3', BRAVO: 'bravo_alert.mp3' }
const ORDER = ['ALPHA', 'BRAVO']

const KEY = 'syslog.sound'
const read = () => { try { return window.localStorage.getItem(KEY) } catch { return null } }
const write = (v) => { try { window.localStorage.setItem(KEY, v) } catch { /* private mode */ } }

export const sound = reactive({
  on: read() !== 'off', // older saved choices ('all', 'urgent') count as On
  blocked: false // the browser refused to play until the user interacts with the page
})

const players = {}
const player = (infra) => {
  if (!players[infra]) {
    players[infra] = new Audio(`${API_BASE}/static/sounds/${CLIPS[infra]}`)
    players[infra].preload = 'auto'
  }
  return players[infra]
}

// Plays one clip and resolves when it has finished (or immediately if the browser blocks audio).
async function playClip (infra) {
  try {
    const a = player(infra)
    a.muted = false
    a.currentTime = 0
    await a.play()
    sound.blocked = false
    await new Promise((resolve) => {
      a.addEventListener('ended', resolve, { once: true })
      a.addEventListener('error', resolve, { once: true })
      setTimeout(resolve, 4000) // never wait longer than a clip can take
    })
    return true
  } catch {
    sound.blocked = true
    return false
  }
}

let chain = Promise.resolve() // clips never overlap: alerts queue up behind each other

// Say "Alpha alert" and/or "Bravo alert", ALPHA first, for the infras that just got new alerts.
export function playAlerts (infras) {
  const wanted = ORDER.filter((i) => infras.includes(i))
  chain = chain.then(async () => { for (const i of wanted) { if (!(await playClip(i))) break } })
  return chain
}

export function toggleSound () {
  sound.on = !sound.on
  write(sound.on ? 'on' : 'off')
  if (sound.on) playAlerts(ORDER) // the click is the user gesture that unlocks audio; also a preview of both voices
}

export function setSound (on) {
  if (sound.on !== on) toggleSound()
}

// Browsers only allow audio after a gesture. The first click anywhere silently primes both clips,
// so later alerts can play even if the user never touched the sound switch.
export function primeOnFirstGesture () {
  const prime = async () => {
    window.removeEventListener('pointerdown', prime)
    window.removeEventListener('keydown', prime)
    for (const infra of ORDER) {
      try {
        const a = player(infra)
        a.muted = true
        await a.play()
        a.pause()
        a.currentTime = 0
        a.muted = false
        sound.blocked = false
      } catch { /* still blocked: the top bar will say so */ }
    }
  }
  window.addEventListener('pointerdown', prime)
  window.addEventListener('keydown', prime)
}
