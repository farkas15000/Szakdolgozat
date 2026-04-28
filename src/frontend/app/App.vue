<template>
  <div class="min-h-screen flex flex-col">
    <nav class="bg-white border-b border-gray-200 shadow-sm">
      <div class="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
        <RouterLink to="/" class="text-lg font-semibold text-primary-600">
          🎬 Filmajánló
        </RouterLink>

        <div class="flex items-center gap-4">
          <RouterLink
            to="/movies"
            class="text-sm text-gray-600 hover:text-gray-900 transition-colors"
          >
            Filmek
          </RouterLink>

          <template v-if="auth.isLoggedIn">
            <RouterLink
              to="/recommendations"
              class="text-sm text-gray-600 hover:text-gray-900 transition-colors"
            >
              Ajánlások
            </RouterLink>
            <RouterLink
              to="/ratings"
              class="text-sm text-gray-600 hover:text-gray-900 transition-colors"
            >
              Értékeléseim
            </RouterLink>
            <RouterLink
              to="/profile"
              class="text-sm text-gray-600 hover:text-gray-900 transition-colors"
            >
              Profilom
            </RouterLink>
            <span class="text-sm text-gray-400">|</span>
            <span class="text-sm text-gray-500">{{ auth.user?.display_name }}</span>
            <button class="btn-secondary text-xs py-1 px-3" @click="handleLogout">
              Kilépés
            </button>
          </template>

          <template v-else>
            <RouterLink to="/login" class="btn-secondary text-xs py-1 px-3">
              Belépés
            </RouterLink>
            <RouterLink to="/register" class="btn-primary text-xs py-1 px-3">
              Regisztráció
            </RouterLink>
          </template>
        </div>
      </div>
    </nav>

    <main class="flex-1 max-w-6xl mx-auto w-full px-4 py-6">
      <RouterView />
    </main>
  </div>
</template>

<script setup>
import { useAuthStore } from '@/stores/auth'
import { useRouter } from 'vue-router'

const auth   = useAuthStore()
const router = useRouter()

function handleLogout() {
  auth.logout()
  router.push('/login')
}
</script>
