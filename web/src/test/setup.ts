// Runs before every test file (vite.config.ts): unmount what a test rendered, and start each
// test logged out.
import { cleanup } from '@testing-library/react'
import { afterEach, beforeEach } from 'vitest'

beforeEach(() => {
  window.sessionStorage.clear()
})

afterEach(() => {
  cleanup()
})
