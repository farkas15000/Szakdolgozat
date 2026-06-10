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
          :poster-url="movie.poster_url"
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
import { ref, reactive, watch, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { moviesApi } from '@/api'
import MovieCard from '@/components/MovieCard.vue'

const route       = useRoute()
const router      = useRouter()
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

// ---------------------------------------------------------------------------
// URL → state (oldalbetöltés és böngésző vissza/előre)
// ---------------------------------------------------------------------------

function readFromQuery() {
  const q       = route.query
  filters.title     = q.title     ? String(q.title)             : ''
  filters.genre     = q.genre     ? String(q.genre)             : ''
  filters.year_from = q.year_from ? Number(q.year_from)         : null
  filters.year_to   = q.year_to   ? Number(q.year_to)           : null
  page.value        = q.page      ? Math.max(1, Number(q.page)) : 1
}

// ---------------------------------------------------------------------------
// state → URL
// ---------------------------------------------------------------------------

function pushQuery() {
  router.replace({
    query: {
      ...(filters.title             && { title:     filters.title }),
      ...(filters.genre             && { genre:     filters.genre }),
      ...(filters.year_from != null && { year_from: String(filters.year_from) }),
      ...(filters.year_to   != null && { year_to:   String(filters.year_to) }),
      ...(page.value > 1            && { page:      String(page.value) }),
    },
  })
}

// ---------------------------------------------------------------------------
// Eseménykezelők
// ---------------------------------------------------------------------------

let debounceTimer = null

function onFilterChange() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    page.value = 1
    pushQuery()
  }, 400)
}

function resetFilters() {
  Object.assign(filters, { title: '', genre: '', year_from: null, year_to: null })
  page.value = 1
  pushQuery()
}

function changePage(p) {
  page.value = p
  pushQuery()
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

// ---------------------------------------------------------------------------
// API hívás
// ---------------------------------------------------------------------------

async function loadMovies() {
  loading.value = true
  try {
    const params = {
      page:      page.value,
      page_size: 20,
      ...(filters.title             && { title:     filters.title }),
      ...(filters.genre             && { genre:     filters.genre }),
      ...(filters.year_from != null && { year_from: filters.year_from }),
      ...(filters.year_to   != null && { year_to:   filters.year_to }),
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

// ---------------------------------------------------------------------------
// URL változás figyelése (vissza/előre gomb)
// ---------------------------------------------------------------------------

watch(
  () => route.query,
  (newQ, oldQ) => {
    // Csak akkor reagál, ha ténylegesen változott valami
    if (JSON.stringify(newQ) !== JSON.stringify(oldQ)) {
      readFromQuery()
      loadMovies()
    }
  },
)

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

onMounted(() => {
  readFromQuery()
  loadMovies()
  loadGenres()
})
</script>
