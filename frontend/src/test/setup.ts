import { afterEach } from 'vitest'
import { cleanup } from '@testing-library/react'

// Testing Library unmounts automatically only with test globals, which this project does not enable.
afterEach(() => cleanup())
