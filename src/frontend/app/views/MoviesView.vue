<template>
  <div>
    <h1 class="text-2xl font-semibold mb-6">Filmek</h1>

    <!-- Szűrők -->
    <div class="card mb-6">
      <div class="grid grid-cols-1 md:grid-cols-4 gap-3">
        <input
          v-model="filters.title"
          type="text"
          class="input-field"
          placeholder="Keresés cím alapján..."
          @input="onFilterChange"
        />

        <select v-model="filters.genre" class="input-field" @change="onFilterChange">
          <option value="">Minden műfaj</option>
          <option v-for="g in genres" :key="g" :value="g">{{ g }}</option>
        </select>

        <input
          v-model.number="filters.year_from"
          type="number"
          class="input-field"
          placeholder="Évtől"
          min="1888"
          :max="currentYear"
          @input="onFilterChange"
        />

        <input
          v-model.number="filters.year_to"
          type="number"
          class="input-field"
          placeholder="Évig"
          min="1888"
          :max="currentYear"
          @input="onFilterChange"
        />
      </div>
    </div>

    <!-- Betöltés skeleton -->
    <div v-if="loading" class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
      <div v-for="i in 12" :key="i" class="card animate-pulse h-36 bg-gray-100" />
    </div>

    <!-- Üres találat -->
    <div v-else-if="!movies.length" class="card text-center py-16">
      <p class="text-gray-500">Nincs a szűrőknek megfelelő film.</p>
      <button class="btn-secondary mt-3 text-sm" @click="resetFilters">
        Szűrők törlése
      </button>
    </div>

    <!-- Film lista -->
    <div v-else>
      <div class="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4">
        <MovieCard
          v-for="movie in movies"
          :key="movie.movie_id"
          :movie-id="movie.movie_id"
          :title="movie.title"
          :release-year="movie.release_year"
          :genres="movie.genres"
          @click="$router.push(`/movies/${movie.movie_id}`)"
        />
      </div>

      <!-- Lapozó -->
      <div class="flex items-center justify-center gap-3 mt-8">
        <button
          class="btn-secondary"
          :disabled="page === 1"
          @click="changePage(page - 1)"
        >
          ← Előző
        </button>
        <span class="text-sm text-gray-500">
          {{ page }} / {{ totalPages }} oldal
          <span class="text-gray-400">({{ total }} film)</span>
        </span>
        <button
          class="btn-secondary"
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
import { ref, reactive, onMounted } from 'vue'
import { moviesApi } from '@/api'
import MovieCard from '@/components/MovieCard.vue'

const currentYear = new Date().getFullYear()

const movies     = ref([])
const genres     = ref([])
const loading    = ref(false)
const page       = ref(1)
const totalPages = ref(1)
const total      = ref(0)

const filters = reactive({
  title:     '',
  genre:     '',
  year_from: null,
  year_to:   null,
})

let debounceTimer = null

function onFilterChange() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    page.value = 1
    loadMovies()
  }, 400)
}

function resetFilters() {
  Object.assign(filters, { title: '', genre: '', year_from: null, year_to: null })
  page.value = 1
  loadMovies()
}

function changePage(p) {
  page.value = p
  loadMovies()
}

async function loadMovies() {
  loading.value = true
  try {
    const params = {
      page:      page.value,
      page_size: 20,
      ...(filters.title     && { title:     filters.title }),
      ...(filters.genre     && { genre:     filters.genre }),
      ...(filters.year_from && { year_from: filters.year_from }),
      ...(filters.year_to   && { year_to:   filters.year_to }),
    }
    const { data } = await moviesApi.list(params)
    movies.value     = data.items
    total.value      = data.total
    totalPages.value = data.pages
  } finally {
    loading.value = false
  }
}

async function loadGenres() {
  const { data } = await moviesApi.genres()
  genres.value = data
}

onMounted(() => {
  loadMovies()
  loadGenres()
})
</script>
