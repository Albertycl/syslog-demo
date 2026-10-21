import { computed, ref } from 'vue'

// Click-to-sort for a table. `accessors` maps a column key to a function returning the value to sort by.
// Clicking the active column flips the direction; clicking another column sorts it ascending.
export function useSort (rows, accessors, defaultKey = '', defaultDir = 'asc') {
  const sortKey = ref(defaultKey)
  const sortDir = ref(defaultDir)

  const sorted = computed(() => {
    const get = accessors[sortKey.value]
    if (!get) return rows.value
    const dir = sortDir.value === 'asc' ? 1 : -1
    return [...rows.value].sort((a, b) => {
      const x = get(a)
      const y = get(b)
      const c = typeof x === 'number' && typeof y === 'number'
        ? x - y
        : String(x ?? '').localeCompare(String(y ?? ''), undefined, { numeric: true, sensitivity: 'base' })
      return c * dir
    })
  })

  function toggle (key) {
    if (sortKey.value === key) sortDir.value = sortDir.value === 'asc' ? 'desc' : 'asc'
    else { sortKey.value = key; sortDir.value = 'asc' }
  }
  const ariaSort = (key) => (sortKey.value === key ? (sortDir.value === 'asc' ? 'ascending' : 'descending') : 'none')
  const arrow = (key) => (sortKey.value === key ? (sortDir.value === 'asc' ? '▲' : '▼') : '↕')

  return { sorted, sortKey, sortDir, toggle, ariaSort, arrow }
}
