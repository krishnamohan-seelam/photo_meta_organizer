import { afterEach, beforeEach } from 'vitest'
import { cleanup } from '@testing-library/react'
import { useViewStore } from '../stores/useViewStore'

// Testing Library unmounts automatically only with test globals, which this project does not enable.
afterEach(() => cleanup())

// The view state (filters, view, inspected photo) starts from its defaults in every test.
beforeEach(() => useViewStore.setState(useViewStore.getInitialState(), true))
