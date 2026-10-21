const INFRAS = ['ALPHA', 'BRAVO']

const routes = [
  {
    path: '/',
    component: () => import('layouts/MainLayout.vue'),
    children: [
      { path: '', name: 'home', component: () => import('pages/HomePage.vue') },
      {
        path: 'infra/:name/:folder?',
        name: 'infra',
        component: () => import('pages/FolderPage.vue'),
        props: true,
        beforeEnter: (to) => {
          const upper = String(to.params.name).toUpperCase()
          if (!INFRAS.includes(upper)) return { path: '/404' }
          if (upper !== to.params.name) return { name: 'infra', params: { ...to.params, name: upper } }
        }
      },
      { path: 'log', name: 'log', component: () => import('pages/LogPage.vue') },
      { path: 'collector', name: 'collector', component: () => import('pages/CollectorPage.vue') },
      { path: 'alerts', name: 'alerts', component: () => import('pages/AllAlertsPage.vue') },
      { path: 'original', name: 'original', component: () => import('pages/ClassicHomePage.vue') },
      { path: 'device/:id', name: 'device', component: () => import('pages/DevicePage.vue'), props: true },
      { path: 'keywords', name: 'keywords', component: () => import('pages/KeywordsPage.vue') },
      { path: 'auto-ack', name: 'auto-ack', component: () => import('pages/AutoAckPage.vue') },
      { path: 'folders', name: 'folders', component: () => import('pages/FoldersPage.vue') },
      { path: 'paused', name: 'paused', component: () => import('pages/PausedPage.vue') },
      { path: 'rules', name: 'rules', component: () => import('pages/RulesPage.vue') },
      { path: 'devices', name: 'devices', component: () => import('pages/DevicesPage.vue') }
    ]
  },
  { path: '/:catchAll(.*)*', component: () => import('pages/ErrorNotFound.vue') }
]

export default routes
