import React from 'react'
import { render } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { vi } from 'vitest'

/** A query client for one test: no retries, and nothing goes stale, so seeded data is not refetched. */
export function testQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } } })
}

/** Render with a query client; any request the test did not seed stays pending. */
export function renderWithQuery(ui: React.ReactElement, qc: QueryClient = testQueryClient()) {
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(() => {})))
  return { qc, ...render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>) }
}
