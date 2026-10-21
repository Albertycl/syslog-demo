import { reactive } from 'vue'
import { api } from 'src/lib/api'

// Health of the background collector (reads the demo log generator on a schedule), polled by the layout.
export const collectorState = reactive({ status: null, unreachable: false })

export async function refreshCollector () {
  try {
    collectorState.status = await api.collectStatus()
    collectorState.unreachable = false
  } catch {
    collectorState.unreachable = true
  }
}
