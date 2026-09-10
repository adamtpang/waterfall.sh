import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';
const token = process.env.POSTHOG_PUBLIC_TOKEN;
if (!token) throw new Error('POSTHOG_PUBLIC_TOKEN is required to build the public tracker');
await build({entryPoints:[fileURLToPath(new URL('./entry.mjs', import.meta.url))], bundle:true, minify:true, format:'iife', target:'es2020', outfile:fileURLToPath(new URL('../site-analytics.js',import.meta.url)), define:{POSTHOG_PUBLIC_TOKEN:JSON.stringify(token)}});
