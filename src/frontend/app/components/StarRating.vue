<template>
  <div class="flex gap-1">
    <button
      v-for="star in 5"
      :key="star"
      type="button"
      class="text-xl transition-colors"
      :class="star <= hovered || star <= modelValue
        ? 'text-yellow-400' : 'text-gray-300'"
      :disabled="readonly"
      @mouseenter="!readonly && (hovered = star)"
      @mouseleave="!readonly && (hovered = 0)"
      @click="!readonly && $emit('update:modelValue', star)"
    >★</button>
  </div>
</template>

<script setup>
import { ref } from 'vue'
defineProps({
  modelValue: { type: Number, default: 0 },
  readonly:   { type: Boolean, default: false },
})
defineEmits(['update:modelValue'])
const hovered = ref(0)
</script>