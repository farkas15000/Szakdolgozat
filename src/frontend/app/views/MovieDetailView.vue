<template>
  <div v-if="loading" class="card animate-pulse h-64" />

  <div v-else-if="movie">
    <!-- Fejléc -->
    <div class="card mb-6">
      <div class="flex items-start justify-between gap-4">
        <div>
          <h1 class="text-2xl font-semibold">{{ movie.title }}</h1>
          <p class="text-gray-500 mt-1">
            {{ movie.release_year ?? 'Ismeretlen év' }}
            <span v-if="movie.imdb_id" class="ml-2">
              · <a
                :href="`https://www.imdb.com/title/${movie.imdb_id}`"
                target="_blank"
                class="text-primary-600 hover:underline text-sm"
              >IMDb</a>
            </span>
          </p>
          <div class="flex flex-wrap gap-1 mt-3">
            <span
              v-for="g in movie.genres"
              :key="g.genre_id"
              class="text-xs bg-primary-50 text-primary-700 rounded-full px-2 py-0.5"
            >
              {{ g.name }}
            </span>
          </div>
        </div>

        <!-- Értékelés widget -->
        <div v-if="auth.isLoggedIn" class="card shrink-0 min-w-[180px] text-center">
          <p class="text-sm font-medium text-gray-700 mb-2">
            {{ existingRating ? 'Értékelésed' : 'Értékeld ezt a filmet' }}
          </p>
          <StarRating
            v-model="selectedRating"
            @update:model-value="saveRating"
          />
          <button
            v-if="existingRating"
            class="mt-2 text-xs text-red-500 hover:underline"
            @click="deleteRating"
          >
            Értékelés törlése
          </button>
          <p v-if="ratingMsg" class="text-xs mt-2" :class="ratingMsgColor">
            {{ ratingMsg }}
          </p>
        </div>
      </div>
    </div>

    <!-- Visszajelzés gombok (implicit feedback) -->
    <div v-if="auth.isLoggedIn" class="flex gap-3 mb-6">
      <button
        class="btn-secondary text-sm"
        :class="{ 'opacity-50': interactionSent }"
        :disabled="interactionSent"
        @click="recordInteraction('watchlist_add')"
      >
        ❤️ Mentés
      </button>
    </div>
  </div>

  <div v-else class="card text-center py-16">
    <p class="text-gray-500">A film nem található.</p>
    <RouterLink to="/movies" class="btn-secondary mt-3 inline-flex text-sm">
      Vissza a filmekhez
    </RouterLink>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { moviesApi, ratingsApi, interactionsApi } from '@/api'
import { useAuthStore } from '@/stores/auth'
import StarRating from '@/components/StarRating.vue'

const route = useRoute()
const auth  = useAuthStore()

const movie          = ref(null)
const loading        = ref(false)
const selectedRating = ref(0)
const existingRating = ref(null)
const ratingMsg      = ref('')
const ratingMsgColor = ref('text-green-600')
const interactionSent = ref(false)

async function loadMovie() {
  loading.value = true
  try {
    const { data } = await moviesApi.get(route.params.id)
    movie.value = data
    // Implicit feedback – megtekintés rögzítése
    if (auth.isLoggedIn) {
      interactionsApi.record({
        movie_id:   data.movie_id,
        event_type: 'view',
      }).catch(() => {})
    }
  } finally {
    loading.value = false
  }
}

async function loadMyRating() {
  if (!auth.isLoggedIn) return
  try {
    const { data } = await ratingsApi.list({ page_size: 100 })
    const found = data.items.find((r) => r.movie_id === Number(route.params.id))
    if (found) {
      existingRating.value = found
      selectedRating.value = found.rating
    }
  } catch {}
}

async function saveRating(value) {
  ratingMsg.value = ''
  try {
    if (existingRating.value) {
      const { data } = await ratingsApi.update(movie.value.movie_id, { rating: value })
      existingRating.value = data
    } else {
      const { data } = await ratingsApi.create({
        movie_id: movie.value.movie_id,
        rating:   value,
      })
      existingRating.value = data
    }
    ratingMsg.value      = '✓ Elmentve'
    ratingMsgColor.value = 'text-green-600'
  } catch {
    ratingMsg.value      = 'Hiba történt'
    ratingMsgColor.value = 'text-red-500'
  }
}

async function deleteRating() {
  try {
    await ratingsApi.remove(movie.value.movie_id)
    existingRating.value = null
    selectedRating.value = 0
    ratingMsg.value      = '✓ Törölve'
    ratingMsgColor.value = 'text-gray-500'
  } catch {
    ratingMsg.value      = 'Hiba történt'
    ratingMsgColor.value = 'text-red-500'
  }
}

async function recordInteraction(eventType) {
  interactionSent.value = true
  try {
    await interactionsApi.record({
      movie_id:   movie.value.movie_id,
      event_type: eventType,
    })
  } catch {
    interactionSent.value = false
  }
}

onMounted(() => {
  loadMovie()
  loadMyRating()
})
</script>
