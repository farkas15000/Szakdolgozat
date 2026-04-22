// src/stores/auth.js
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api'

export const useAuthStore = defineStore('auth', () => {
  const accessToken  = ref(localStorage.getItem('access_token') ?? null)
  const refreshToken = ref(localStorage.getItem('refresh_token') ?? null)
  const user         = ref(null)

  const isLoggedIn = computed(() => !!accessToken.value)

  function _saveTokens(access, refresh) {
    accessToken.value  = access
    refreshToken.value = refresh
    localStorage.setItem('access_token',  access)
    localStorage.setItem('refresh_token', refresh)
  }

  async function register(email, password, displayName) {
    const { data } = await authApi.register({
      email,
      password,
      display_name: displayName,
    })
    return data
  }

  async function login(email, password) {
    const { data } = await authApi.login({ email, password })
    _saveTokens(data.access_token, data.refresh_token)
    await fetchMe()
  }

  async function refresh() {
    const { data } = await authApi.refresh(refreshToken.value)
    _saveTokens(data.access_token, data.refresh_token)
  }

  async function fetchMe() {
    const { data } = await authApi.me()
    user.value = data
  }

  function logout() {
    accessToken.value  = null
    refreshToken.value = null
    user.value         = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
  }

  // Oldalbetöltéskor visszatöltjük a usert ha van token
  if (accessToken.value) {
    fetchMe().catch(() => logout())
  }

  return {
    accessToken, refreshToken, user, isLoggedIn,
    register, login, refresh, fetchMe, logout,
  }
})
