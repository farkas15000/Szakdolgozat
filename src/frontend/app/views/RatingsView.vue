<template>
  <div>
    <h1 class="text-2xl font-semibold mb-6">Értékeléseim</h1>

    <div v-if="loading" class="space-y-3">
      <div v-for="i in 5" :key="i" class="card animate-pulse h-16 bg-gray-100" />
    </div>

    <div v-else-if="!ratings.length" class="card text-center py-16">
      <p class="text-4xl mb-4">⭐</p>
      <p class="text-gray-600">Még nem értékeltél egyetlen filmet sem.</p>
      <RouterLink to="/movies" class="btn-primary mt-4 inline-flex text-sm">
        Filmek böngészése
      </RouterLink>
    </div>

    <div v-else>
      <p class="text-sm text-gray-400 mb-4">{{ total }} értékelt film</p>

      <div class="space-y-3">
        <div
          v-for="r in ratings"
          :key="r.id"
          class="card flex items-center justify-between gap-4"
        >
          <RouterLink
            :to="`/movies/${r.movie_id}`"
            class="text-sm font-medium hover:text-primary-600 transition-colors"
          >
            Film #{{ r.movie_id }}
          </RouterLink>

          <div class="flex items-center gap-3">
            <StarRating :model-value="r.rating" readonly />
            <span class="text-sm text-gray-500">{{ r.rating }}/5</span>
            <button
              class="text-xs text-red-400 hover:text-red-600 transition-colors"
              @click="deleteRating(r.movie_id)"
            >
              Törlés
            </button>
          </div>
        </div>
      </div>

      <!-- Lapozó -->
      <div class="flex items-center justify-center gap-3 mt-6">
        <button
          class="btn-secondary text-sm"
          :disabled="page === 1"
          @click="changePage(page - 1)"
        >
          ← Előző
        </button>
        <span class="text-sm text-gray-500">{{ page }} / {{ totalPages }}</span>
        <button
          class="btn-secondary text-sm"
          :disabled="page === totalPages"
          @click="changePage(page + 1)"
        >
          Következő →
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { ratingsApi } from '@/api'
import StarRating from '@/components/StarRating.vue'

const ratings    = ref([])
const loading    = ref(false)
const page       = ref(1)
const totalPages = ref(1)
const total      = ref(0)

async function loadRatings() {
  loading.value = true
  try {
    const { data } = await ratingsApi.list({ page: page.value, page_size: 20 })
    ratings.value    = data.items
    total.value      = data.total
    totalPages.value = data.pages
  } finally {
    loading.value = false
  }
}

async function deleteRating(movieId) {
  await ratingsApi.remove(movieId)
  ratings.value = ratings.value.filter((r) => r.movie_id !== movieId)
  total.value -= 1
}

function changePage(p) {
  page.value = p
  loadRatings()
}

onMounted(loadRatings)
</script>
