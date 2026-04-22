<template>
  <div
    class="card cursor-pointer hover:shadow-md hover:border-primary-200
           transition-all duration-150 flex flex-col gap-2"
    @click="$emit('click')"
  >
    <div class="flex items-start justify-between gap-2">
      <h3 class="text-sm font-medium leading-snug line-clamp-2">{{ title }}</h3>
      <span
        v-if="score !== undefined"
        class="text-xs bg-primary-50 text-primary-700 rounded-full px-2 py-0.5 shrink-0"
      >
        {{ (score * 100).toFixed(0) }}%
      </span>
    </div>

    <p class="text-xs text-gray-400">{{ releaseYear ?? 'Ismeretlen év' }}</p>

    <div v-if="genres?.length" class="flex flex-wrap gap-1 mt-auto">
      <span
        v-for="g in genres.slice(0, 3)"
        :key="g"
        class="text-xs bg-gray-100 text-gray-600 rounded-full px-2 py-0.5"
      >
        {{ g }}
      </span>
    </div>

    <p v-if="algorithm" class="text-xs text-gray-300 mt-1">{{ algorithm }}</p>
  </div>
</template>

<script setup>
defineProps({
  movieId:     { type: Number, required: true },
  title:       { type: String, required: true },
  releaseYear: { type: Number, default: null },
  genres:      { type: Array,  default: () => [] },
  score:       { type: Number, default: undefined },
  algorithm:   { type: String, default: '' },
})

defineEmits(['click'])
</script>
