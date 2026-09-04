const esbuild = require('esbuild')
const fs = require('fs')
const nodePath = require('path')

const isWatch = process.argv.includes('--watch')

const extensionBuild = {
  entryPoints: ['src/extension.ts'],
  bundle: true,
  outfile: 'dist/extension.js',
  external: ['vscode'],
  format: 'cjs',
  platform: 'node',
  target: 'node18',
  sourcemap: isWatch,
  minify: false,
}

const webviewBuild = {
  entryPoints: {
    'notebook-webview': 'src/notebook/webview/main.ts',
  },
  bundle: true,
  outdir: 'dist',
  format: 'iife',
  platform: 'browser',
  target: 'es2022',
  sourcemap: isWatch,
  minify: false,
  loader: {
    '.css': 'css',
  },
}

function copyNotebookAssets() {
  const srcAssets = 'src/notebook/assets'
  const dstAssets = 'dist/assets'
  if (!fs.existsSync(srcAssets)) {
    throw new Error(`Missing required notebook assets: ${srcAssets}`)
  }
  fs.rmSync(dstAssets, { recursive: true, force: true })
  fs.cpSync(srcAssets, dstAssets, {
    recursive: true,
    filter: (src) => {
      const normalized = src.split(nodePath.sep).join('/')
      return !normalized.includes('/assets/_remark_build')
    },
  })
}

async function main() {
  fs.mkdirSync('dist', { recursive: true })
  copyNotebookAssets()

  if (isWatch) {
    const extensionContext = await esbuild.context(extensionBuild)
    const webviewContext = await esbuild.context(webviewBuild)
    await Promise.all([extensionContext.watch(), webviewContext.watch()])
    console.log('Watching extension and webview sources...')
    return
  }

  await Promise.all([
    esbuild.build(extensionBuild),
    esbuild.build(webviewBuild),
  ])
  console.log('Built artifact-only extension and copied notebook assets.')
}

main().catch((error) => {
  console.error(error)
  process.exit(1)
})
