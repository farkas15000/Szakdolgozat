<template>
  <div class="max-w-lg mx-auto space-y-6">
    <h1 class="text-2xl font-semibold">Profilom</h1>

    <!-- Alap adatok -->
    <div class="card space-y-1">
      <p class="text-xs font-medium text-gray-400 uppercase tracking-wide mb-3">
        Fiók adatok
      </p>
      <p class="text-sm text-gray-500">
        E-mail: <span class="font-medium text-gray-800">{{ auth.user?.email }}</span>
      </p>
      <p class="text-sm text-gray-500">
        Tag óta:
        <span class="font-medium text-gray-800">
          {{ auth.user?.created_at
            ? new Date(auth.user.created_at).toLocaleDateString('hu-HU')
            : '–' }}
        </span>
      </p>
    </div>

    <!-- Megjelenítési név módosítása -->
    <div class="card space-y-4">
      <p class="text-xs font-medium text-gray-400 uppercase tracking-wide">
        Megjelenítési név
      </p>

      <form @submit.prevent="saveDisplayName" class="space-y-3">
        <input
          v-model="displayName"
          type="text"
          class="input-field"
          placeholder="Megjelenítési név"
          required
        />

        <AlertMessage v-if="displayNameMsg" :type="displayNameMsgType">
          {{ displayNameMsg }}
        </AlertMessage>

        <button
          type="submit"
          class="btn-primary"
          :disabled="displayNameLoading || displayName === auth.user?.display_name"
        >
          <span v-if="displayNameLoading">Mentés...</span>
          <span v-else>Mentés</span>
        </button>
      </form>
    </div>

    <!-- Jelszó módosítása -->
    <div class="card space-y-4">
      <p class="text-xs font-medium text-gray-400 uppercase tracking-wide">
        Jelszó módosítása
      </p>

      <form @submit.prevent="savePassword" class="space-y-3">
        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">
            Jelenlegi jelszó
          </label>
          <input
            v-model="passwordForm.current"
            type="password"
            class="input-field"
            placeholder="••••••••"
            required
          />
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">
            Új jelszó (min. 8 karakter)
          </label>
          <input
            v-model="passwordForm.next"
            type="password"
            class="input-field"
            placeholder="••••••••"
            minlength="8"
            required
          />
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700 mb-1">
            Új jelszó megerősítése
          </label>
          <input
            v-model="passwordForm.confirm"
            type="password"
            class="input-field"
            placeholder="••••••••"
            required
          />
          <p
            v-if="passwordForm.confirm && passwordForm.next !== passwordForm.confirm"
            class="text-xs text-red-500 mt-1"
          >
            A két jelszó nem egyezik.
          </p>
        </div>

        <AlertMessage v-if="passwordMsg" :type="passwordMsgType">
          {{ passwordMsg }}
        </AlertMessage>

        <button
          type="submit"
          class="btn-primary"
          :disabled="passwordLoading || passwordForm.next !== passwordForm.confirm"
        >
          <span v-if="passwordLoading">Mentés...</span>
          <span v-else>Jelszó módosítása</span>
        </button>
      </form>
    </div>

    <!-- Fiók törlése -->
    <div class="card border-red-200 space-y-4">
      <p class="text-xs font-medium text-red-400 uppercase tracking-wide">
        Veszélyzóna
      </p>
      <p class="text-sm text-gray-600">
        A fiók törlése végleges és visszafordíthatatlan. Minden értékelésed,
        interakciód és ajánlásod törlődik.
      </p>

      <button
        v-if="!showDeleteConfirm"
        class="btn-secondary border-red-300 text-red-600 hover:bg-red-50"
        @click="showDeleteConfirm = true"
      >
        Fiók törlése
      </button>

      <!-- Megerősítő panel -->
      <div v-else class="space-y-3 border-t border-red-100 pt-4">
        <p class="text-sm font-medium text-red-600">
          Biztosan törölni szeretnéd a fiókodat? Add meg a jelszavadat a megerősítéshez.
        </p>

        <input
          v-model="deletePassword"
          type="password"
          class="input-field border-red-300 focus:border-red-500 focus:ring-red-500"
          placeholder="Jelszó megerősítéshez"
        />

        <AlertMessage v-if="deleteMsg" type="error">
          {{ deleteMsg }}
        </AlertMessage>

        <div class="flex gap-3">
          <button
            class="btn-primary bg-red-600 hover:bg-red-700 focus:ring-red-500"
            :disabled="deleteLoading || !deletePassword"
            @click="deleteAccount"
          >
            <span v-if="deleteLoading">Törlés...</span>
            <span v-else>Igen, törlöm a fiókomat</span>
          </button>
          <button
            class="btn-secondary"
            @click="showDeleteConfirm = false; deletePassword = ''; deleteMsg = ''"
          >
            Mégsem
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { profileApi } from '@/api'
import AlertMessage from '@/components/AlertMessage.vue'

const auth   = useAuthStore()
const router = useRouter()

// ---------------------------------------------------------------------------
// Megjelenítési név
// ---------------------------------------------------------------------------

const displayName        = ref(auth.user?.display_name ?? '')
const displayNameLoading = ref(false)
const displayNameMsg     = ref('')
const displayNameMsgType = ref('success')

async function saveDisplayName() {
  displayNameMsg.value = ''
  displayNameLoading.value = true
  try {
    await profileApi.updateDisplayName(displayName.value)
    await auth.fetchMe()
    displayNameMsg.value     = '✓ Megjelenítési név sikeresen módosítva.'
    displayNameMsgType.value = 'success'
  } catch (e) {
    displayNameMsg.value     = e.response?.data?.detail ?? 'Hiba történt.'
    displayNameMsgType.value = 'error'
  } finally {
    displayNameLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// Jelszó
// ---------------------------------------------------------------------------

const passwordForm    = reactive({ current: '', next: '', confirm: '' })
const passwordLoading = ref(false)
const passwordMsg     = ref('')
const passwordMsgType = ref('success')

async function savePassword() {
  passwordMsg.value = ''
  passwordLoading.value = true
  try {
    await profileApi.updatePassword(passwordForm.current, passwordForm.next)
    passwordMsg.value     = '✓ Jelszó sikeresen módosítva.'
    passwordMsgType.value = 'success'
    passwordForm.current  = ''
    passwordForm.next     = ''
    passwordForm.confirm  = ''
  } catch (e) {
    passwordMsg.value     = e.response?.data?.detail ?? 'Hiba történt.'
    passwordMsgType.value = 'error'
  } finally {
    passwordLoading.value = false
  }
}

// ---------------------------------------------------------------------------
// Fiók törlése
// ---------------------------------------------------------------------------

const showDeleteConfirm = ref(false)
const deletePassword    = ref('')
const deleteLoading     = ref(false)
const deleteMsg         = ref('')

async function deleteAccount() {
  deleteMsg.value     = ''
  deleteLoading.value = true
  try {
    await profileApi.deleteAccount(deletePassword.value)
    auth.logout()
    router.push('/login')
  } catch (e) {
    deleteMsg.value = e.response?.data?.detail ?? 'Hiba történt. Próbáld újra.'
  } finally {
    deleteLoading.value = false
  }
}

onMounted(() => {
  displayName.value = auth.user?.display_name ?? ''
})
</script>
