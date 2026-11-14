<template>
  <div v-if="loading" class="card animate-pulse h-12 mb-4" />

  <div
    v-else-if="profile"
    class="card mb-4 py-3 flex flex-wrap items-center gap-x-5 gap-y-2 text-sm"
    data-testid="taste-profile-bar"
  >
    <!-- Értékelések száma -->
    <div class="text-gray-600">
      <span class="font-semibold text-gray-900">{{ profile.rated_count }}</span>
      értékelt film
      <span class="text-gray-400">
        ({{ profile.liked_count }} kedvelt)
      </span>
    </div>

    <!-- Aktív ajánlómód -->
    <div class="flex items-center gap-2">
      <span class="text-gray-500">Aktív mód:</span>
      <span
        class="rounded-full px-2.5 py-0.5 text-xs font-medium"
        :class="modeInfo.badge"
        :title="modeInfo.tooltip"
      >
        {{ modeInfo.label }}
      </span>
    </div>

    <!-- Legerősebb profil-műfajok -->
    <div class="flex flex-wrap items-center gap-1.5">
      <span class="text-gray-500">Legerősebb műfajaid:</span>
      <template v-if="profile.top_genres.length">
        <span
          v-for="g in profile.top_genres"
          :key="g.name"
          class="text-xs bg-primary-50 text-primary-700 rounded-full px-2 py-0.5"
          :title="`${g.count} kedvelt film`"
        >
          {{ g.name }} <span class="opacity-60">· {{ g.count }}</span>
        </span>
      </template>
      <span v-else class="text-xs text-gray-400">
        még nincs kedvelt (4★ vagy több) film
      </span>
    </div>

    <!-- Útmutató a következő módhoz -->
    <p v-if="modeInfo.hint" class="w-full text-xs text-gray-400">
      {{ modeInfo.hint }}
    </p>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { recommendationsApi } from '@/api'

const profile = ref(null)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const { data } = await recommendationsApi.profile()
    profile.value = data
  } catch {
    profile.value = null   // az információs sáv nem kritikus: hiba esetén egyszerűen eltűnik
  } finally {
    loading.value = false
  }
}

const modeInfo = computed(() => {
  const p = profile.value
  if (!p) return {}
  const minSvd = p.min_ratings_for_svd

  switch (p.mode) {
    case 'hybrid':
      return {
        label: 'Hibrid',
        badge: 'bg-purple-50 text-purple-700',
        tooltip: 'Kollaboratív (SVD) és tartalomalapú pontszámok kombinációja.',
        hint: '',
      }
    case 'svd':
      return {
        label: 'Kollaboratív (SVD)',
        badge: 'bg-purple-50 text-purple-700',
        tooltip: 'Csak a kollaboratív modell pontszámai alapján.',
        hint: '',
      }
    case 'content_based': {
      let hint = ''
      if (p.rated_count < minSvd) {
        hint = `Még ${minSvd - p.rated_count} értékelés kell a hibrid módhoz.`
      } else if (!p.known_by_svd) {
        hint = 'A kollaboratív modell még nem ismer téged; a következő betanítás után válthat hibrid módra.'
      }
      return {
        label: 'Tartalomalapú',
        badge: 'bg-primary-50 text-primary-700',
        tooltip: 'A kedvelt (4★ vagy több) filmekhez hasonló filmeket ajánl.',
        hint,
      }
    }
    default:
      return {
        label: 'Cold-start',
        badge: 'bg-gray-100 text-gray-600',
        tooltip: 'Még nincs elég kedvelt film, ezért a legnépszerűbb filmeket ajánljuk.',
        hint: 'Értékelj legalább egy filmet 4★ vagy többre, hogy személyre szabott ajánlást kapj.',
      }
  }
})

onMounted(load)
defineExpose({ reload: load })
</script>
