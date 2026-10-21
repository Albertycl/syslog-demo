// Base URL of the Flask backend. Empty = same origin (nginx proxies /api to the backend).
// For local dev against another host: API_BASE_URL=http://my-host:5100 quasar dev
export const API_BASE = process.env.API_BASE_URL || ''
