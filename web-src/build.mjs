// ── ContextFlow 前端构建脚本 ────────────────────────────
// 用 esbuild + esbuild-plugin-vue3 把 src/main.js 打包成单文件 IIFE，
// 输出到 ../web/static/app.js（后端 aiohttp 只服务该目录）。
//
// 用法： cd web-src && npm install && npm run build
// 备选插件：若 esbuild-plugin-vue3 报兼容问题，改用 esbuild-plugin-vue-next
//           （同样的 onResolve/onLoad 签名，仅替换 import 即可）。

import { build } from 'esbuild';
import vuePluginPkg from 'esbuild-plugin-vue3';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

// 该插件是 CommonJS，用默认导入解构
const vuePlugin = vuePluginPkg.vuePlugin || vuePluginPkg.default || vuePluginPkg;

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const outdir = path.resolve(__dirname, '..', 'web', 'static');
const outfile = path.join(outdir, 'app.js');

await build({
  entryPoints: [path.resolve(__dirname, 'src', 'main.js')],
  bundle: true,
  format: 'iife',          // 单文件，不依赖 importmap
  platform: 'browser',
  target: ['es2020'],
  minify: true,
  sourcemap: false,
  outfile,
  plugins: [vuePlugin()],
  // marked.min.js 走 vendor <script>，不进 bundle
  external: [],
  logLevel: 'info',
});

console.log(`\n✅ 构建完成 → ${outfile}`);
