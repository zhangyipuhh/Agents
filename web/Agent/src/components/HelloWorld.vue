<script setup>
defineProps({
  msg: {
    type: String,
    required: true
  }
})
</script>

<template>
  <div class="hello">
    <h1>{{ msg }}</h1>
    <p>
      Welcome to Your Vue.js + Vite App
    </p>
  </div>
</template>

<style scoped>
.hello h1 {
  color: #42b883;
}
</style>
