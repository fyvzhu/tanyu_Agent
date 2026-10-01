<template>
  <router-view />
</template>

<script setup>
</script>

<style>
@import './assets/styles/theme.css';

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  background: var(--bg-primary);
  color: var(--text-primary);
}

#app {
  width: 100%;
  height: 100vh;
  overflow: hidden;
}
</style>
