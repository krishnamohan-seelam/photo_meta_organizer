// @vitest-environment node
import { execFileSync } from 'node:child_process'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

// The backend side (pytest, test_openapi_contract.py) checks openapi.json against the API; this
// checks src/api/schema.ts against openapi.json. Together: no hand-maintained drift (X-01).
describe('generated API types', () => {
  it('src/api/schema.ts is up to date with openapi.json (run `npm run gen:api`)', () => {
    const dir = mkdtempSync(join(tmpdir(), 'pmo-schema-'))
    try {
      const out = join(dir, 'schema.ts')
      const cli = join('node_modules', 'openapi-typescript', 'bin', 'cli.js')
      const args = [cli, 'openapi.json', '-o', out, '--default-non-nullable', 'false']
      execFileSync(process.execPath, args, { stdio: 'pipe' })
      const normalise = (text: string) => text.replace(/\r\n/g, '\n')
      expect(normalise(readFileSync('src/api/schema.ts', 'utf8'))).toBe(normalise(readFileSync(out, 'utf8')))
    } finally {
      rmSync(dir, { recursive: true, force: true })
    }
  }, 30_000)
})
