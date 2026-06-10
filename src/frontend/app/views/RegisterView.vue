<template>
  <div class="max-w-md mx-auto mt-16">
    <div class="card">
      <h1 class="text-xl font-semibold mb-6">Regisztráció</h1>

      <form class="space-y-4" @submit.prevent="handleSubmit">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">
            Megjelenítési név
          </label>
          <input
            v-model="form.displayName"
            type="text"
            class="input-field"
            placeholder="Kovács János"
            required
          />
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">E-mail</label>
          <input
            v-model="form.email"
            type="email"
            class="input-field"
            placeholder="pelda@email.hu"
            required
          />
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">
            Jelszó (min. 8 karakter)
          </label>
          <input
            v-model="form.password"
            type="password"
            class="input-field"
            placeholder="••••••••"
            required
            minlength="8"
          />
        </div>

        <p v-if="error" class="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">
          {{ error }}
        </p>

        <p v-if="success" class="text-sm text-green-700 bg-green-50 rounded-lg px-3 py-2">
          Sikeres regisztráció! Átirányítás...
        </p>

        <button type="submit" class="btn-primary w-full" :disabled="loading || success">
          <span v-if="loading">Regisztráció...</span>
          <span v-else>Regisztráció</span>
        </button>
      </form>

      <p class="mt-4 text-sm text-center text-gray-500">
        Már van fiókod?
        <RouterLink to="/login" class="text-primary-600 hover:underline">
          Lépj be
        </RouterLink>
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth   = useAuthStore()
const router = useRouter()

const form    = reactive({ displayName: '', email: '', password: '' })
const loading = ref(false)
const error   = ref('')
const success = ref(false)

async function handleSubmit() {
  error.value   = ''
  loading.value = true
  try {
    await auth.register(form.email, form.password, form.displayName)
    success.value = true
    // Auto-login regisztráció után
    await auth.login(form.email, form.password)
    router.push('/recommendations')
  } catch (e) {
    error.value = e.response?.data?.detail ?? 'Hiba történt. Próbáld újra.'
  } finally {
    loading.value = false
  }
}
</script>
