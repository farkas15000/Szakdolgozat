<template>
  <div>
    <div class="flex items-center justify-between mb-6">
      <h1 class="text-2xl font-semibold">Ajánlott filmek</h1>
      <button class="btn-secondary text-sm" :disabled="loading" @click="loadRecommendations(true)">
        <span v-if="loading">Frissítés...</span>
        <span v-else>🔄 Frissítés</span>
      </button>
    </div>

    <!-- Betöltés -->
    <div v-if="loading" class="grid grid-cols-2 md:grid-cols-4 gap-4">
      <div
        v-for="i in 8"
        :key="i"
        class="card animate-pulse h-48 bg-gray-100"
      />
    </div>

    <!-- Üres állapot -->
    <div v-else-if="!recommendations.length" class="card text-center py-16">
      <p class="text-4xl mb-4">🎬</p>
      <p class="text-gray-600 font-medium">Még nincsenek ajánlásaid.</p>
      <p class="text-sm text-gray-400 mt-2">
        Értékelj néhány filmet, hogy személyre szabott ajánlásokat kaphass!
      </p>
      <RouterLink to="/movies" class="btn-primary mt-4 inline-flex">
        Filmek böngészése
      </RouterLink>
    </div>

    <!-- Ajánlások listája -->
    <div v-else>
      <p class="text-sm text-gray-400 mb-4">
        Forrás: <span class="font-medium">{{ sourceLabel }}</span>
        &nbsp;·&nbsp; {{ recommendations.length }} ajánlás
      </p>

      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        <MovieCard
          v-for="rec in recommendations"
          :key="rec.id"
          :movie-id="rec.movie_id"
          :title="rec.title"
          :release-year="rec.release_year"
          :score="rec.score"
          :algorithm="rec.algorithm"
          :poster-url="rec.poster_url"
          @click="handleCardClick(rec)"
        />
      </div>
    </div>

    <!-- Hiba -->
    <div
      v-if="error"
      class="mt-4 text-sm text-red-600 bg-red-50 rounded-lg px-4 py-3"
    >
      {{ error }}
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { recommendationsApi } from '@/api'
import MovieCard from '@/components/MovieCard.vue'

const router          = useRouter()
const recommendations = ref([])
const loading         = ref(false)
const error           = ref('')
const source          = ref('')

const sourceLabel = computed(() => {
  const map = {
    precomputed: 'Előre számolt',
    realtime:    'Valós idejű',
    none:        'Nincs adat',
  }
  return map[source.value] ?? source.value
})

async function loadRecommendations(refresh = false) {
  loading.value = true
  error.value   = ''
  try {
    const { data } = await recommendationsApi.list({ top_n: 20, refresh })
    recommendations.value = data.items
    source.value          = data.source
  } catch (e) {
    error.value = 'Nem sikerült betölteni az ajánlásokat. Próbáld újra.'
  } finally {
    loading.value = false
  }
}

async function handleCardClick(rec) {
  // Kattintás rögzítése aszinkron (nem blokkolja a navigációt)
  recommendationsApi.click(rec.id).catch(() => {})
  // Interakció rögzítése
  router.push(`/movies/${rec.movie_id}`)
}

onMounted(() => loadRecommendations(true))
</script>
