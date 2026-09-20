import { JSDOM } from 'jsdom';

const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>');
globalThis.window = dom.window;
globalThis.document = dom.window.document;
Object.defineProperty(globalThis, 'navigator', { value: dom.window.navigator, configurable: true });

const { default: mermaid } = await import('mermaid');
import fs from 'fs';

mermaid.initialize({
    startOnLoad: false,
    theme: 'neutral',
    securityLevel: 'loose'
});

const html = fs.readFileSync('../DOCS/c4-architecture.html', 'utf8');

const regex = /<pre class="mermaid" id="([^"]+)">([\s\S]*?)<\/pre>/g;
let match;

while ((match = regex.exec(html)) !== null) {
    const id = match[1];
    const code = match[2].trim();
    console.log(`\nTesting diagram [${id}]...`);
    try {
        await mermaid.parse(code);
        console.log(`✅ Diagram [${id}] parsed successfully!`);
    } catch (err) {
        console.error(`❌ Diagram [${id}] failed:`);
        console.error(err.message);
        if (err.hash) {
            console.error('Line:', err.hash.line);
            console.error('Expected:', err.hash.expected);
            console.error('Token:', err.hash.token);
            console.error('Text:', err.hash.text);
            console.error('Loc:', err.hash.loc);
        }
    }
}
