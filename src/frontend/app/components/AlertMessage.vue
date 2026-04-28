<template>
  <div
    class="text-sm rounded-lg px-3 py-2"
    :class="type === 'success'
      ? 'text-green-700 bg-green-50'
      : 'text-red-600 bg-red-50'"
  >
    <slot />
  </div>
</template>

<script setup>
defineProps({
  type: {
    type: String,
    default: 'success',
    validator: (v) => ['success', 'error'].includes(v),
  },
})
</script>
