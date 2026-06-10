<template>
  <div class="max-w-md mx-auto mt-16">
    <div class="card">
      <h1 class="text-xl font-semibold mb-6">Bejelentkezés</h1>

      <form class="space-y-4" @submit.prevent="handleSubmit">
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
          <label class="block text-sm font-medium text-gray-700 mb-1">Jelszó</label>
          <input
            v-model="form.password"
            type="password"
            class="input-field"
            placeholder="••••••••"
            required
          />
        </div>

        <p v-if="error" class="text-sm text-red-600 bg-red-50 rounded-lg px-3 py-2">
          {{ error }}
        </p>

        <button type="submit" class="btn-primary w-full" :disabled="loading">
          <span v-if="loading">Belépés...</span>
          <span v-else>Belépés</span>
        </button>
      </form>

      <p class="mt-4 text-sm text-center text-gray-500">
        Még nincs fiókod?
        <RouterLink to="/register" class="text-primary-600 hover:underline">
          Regisztrálj
        </RouterLink>
      </p>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth   = useAuthStore()
const router = useRouter()
const route  = useRoute()

const form    = reactive({ email: '', password: '' })
const loading = ref(false)
const error   = ref('')

async function handleSubmit() {
  error.value   = ''
  loading.value = true
  try {
    await auth.login(form.email, form.password)
    const redirect = route.query.redirect || '/recommendations'
    router.push(redirect)
  } catch (e) {
    error.value = e.response?.data?.detail ?? 'Hiba történt. Próbáld újra.'
  } finally {
    loading.value = false
  }
}
</script>
