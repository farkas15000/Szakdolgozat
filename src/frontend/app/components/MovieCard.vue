<template>
  <div
    class="card cursor-pointer hover:shadow-md hover:border-primary-200
           transition-all duration-150 flex flex-col gap-2 overflow-hidden p-0"
    @click="$emit('click')"
  >
    <!-- Poster -->
    <div class="relative w-full bg-gray-100 aspect-[2/3] overflow-hidden">
      <img
        v-if="posterUrl && !imgError"
        :src="posterUrl"
        :alt="title"
        class="w-full h-full object-cover"
        loading="lazy"
        @error="imgError = true"
      />
      <!-- Fallback ha nincs poster -->
      <div
        v-else
        class="w-full h-full flex flex-col items-center justify-center
               bg-gradient-to-br from-gray-100 to-gray-200 text-gray-400"
      >
        <span class="text-4xl mb-2">🎬</span>
        <span class="text-xs text-center px-2 line-clamp-2">{{ posterUrl }}</span>
      </div>

      <!-- Score badge -->
      <span
        v-if="score !== undefined"
        class="absolute top-2 right-2 text-xs font-semibold
               bg-primary-600 text-white rounded-full px-2 py-0.5 shadow"
      >
        {{ (score * 100).toFixed(0) }}%
      </span>
    </div>

    <!-- Szöveg rész -->
    <div class="px-3 pb-3 flex flex-col gap-1 flex-1">
      <h3 class="text-sm font-medium leading-snug line-clamp-2">{{ title }}</h3>

      <p class="text-xs text-gray-400">{{ releaseYear ?? 'Ismeretlen év' }}</p>

      <div v-if="genres?.length" class="flex flex-wrap gap-1 mt-auto pt-1">
        <span
          v-for="g in genres.slice(0, 2)"
          :key="g"
          class="text-xs bg-gray-100 text-gray-600 rounded-full px-2 py-0.5"
        >
          {{ g }}
        </span>
        <span
          v-if="genres.length > 2"
          class="text-xs text-gray-400"
        >
          +{{ genres.length - 2 }}
        </span>
      </div>

      <p v-if="algorithm" class="text-xs text-gray-300 mt-1">{{ algorithm }}</p>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'

defineProps({
  movieId:     { type: Number,  required: true },
  title:       { type: String,  required: true },
  releaseYear: { type: Number,  default: null },
  genres:      { type: Array,   default: () => [] },
  score:       { type: Number,  default: undefined },
  algorithm:   { type: String,  default: '' },
  posterUrl:   { type: String,  default: null },
})

defineEmits(['click'])

const imgError = ref(false)
</script>
