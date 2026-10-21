export const INFRAS = ['ALPHA', 'BRAVO']
export const FOLDERS = ['Routers', 'Switches', 'OOB', 'LTM', 'Firewall', 'Other']
export const SEVERITIES = ['critical', 'error', 'warning', 'notice', 'info']
export const VENDORS = ['cisco', 'LTM', 'firewall', 'fortigate', 'paloalto', 'arbor']

const rtf = typeof Intl !== 'undefined' ? new Intl.RelativeTimeFormat('en', { numeric: 'auto' }) : null

// Backend timestamps are naive and already in UTC+8 (see model.utc_8), so read them as local wall time.
export function parseTime (iso) {
  return iso ? new Date(iso) : null
}

export function timeAgo (iso, now = Date.now()) {
  const d = parseTime(iso)
  if (!d || Number.isNaN(d.getTime())) return '—'
  const sec = Math.round((d.getTime() - now) / 1000)
  const abs = Math.abs(sec)
  if (abs < 45) return 'just now'
  if (abs < 3600) return rtf.format(Math.round(sec / 60), 'minute')
  if (abs < 86400) return rtf.format(Math.round(sec / 3600), 'hour')
  if (abs < 86400 * 30) return rtf.format(Math.round(sec / 86400), 'day')
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
}

const ZONE = 'Asia/Taipei' // UTC+8, the zone alert timestamps are stored in; same wall-clock time for every viewer

export function clock (iso) {
  const d = parseTime(iso)
  if (!d || Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('en-GB', { timeZone: ZONE, day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
}

// Full date and time to the second, e.g. "14 Oct 2026, 16:06:46"
export function exactTime (iso) {
  const d = parseTime(iso)
  if (!d || Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString('en-GB', { timeZone: ZONE, day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
}

export const SEVERITY_LABEL = {
  critical: 'Critical', error: 'Error', warning: 'Warning', notice: 'Notice', info: 'Info'
}

// Mirrors the backend's default_folder(): suggests a folder from the device name until the user picks one.
export function suggestFolder (name = '') {
  const n = name.toUpperCase()
  if (n.includes('LTM')) return 'LTM'
  if (/(^|-)FW\d/.test(n)) return 'Firewall'
  if (n.includes('OOB')) return 'OOB'
  if (/(^|-)(BR|ER)\d/.test(n) && !n.includes('ER2S')) return 'Routers'
  if (/(^|-)(CS|IS|OS)\d|C\d-CS|ER2S|OS2S|IS3S/.test(n)) return 'Switches'
  return 'Other'
}
