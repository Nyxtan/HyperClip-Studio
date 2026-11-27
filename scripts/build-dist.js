const fs = require('fs');
const path = require('path');

const rootDir = path.resolve(__dirname, '..');
const distDir = path.resolve(rootDir, 'dist');

if (!fs.existsSync(distDir)) {
  fs.mkdirSync(distDir, { recursive: true });
}

function copyRecursive(src, dest) {
  if (!fs.existsSync(src)) return;
  const stat = fs.statSync(src);
  if (stat.isDirectory()) {
    if (!fs.existsSync(dest)) fs.mkdirSync(dest, { recursive: true });
    for (const child of fs.readdirSync(src)) {
      copyRecursive(path.join(src, child), path.join(dest, child));
    }
  } else {
    fs.copyFileSync(src, dest);
  }
}

// Copy top-level HTML & assets into dist
const filesToCopy = [
  'index.html',
  'studio.html',
  'ads.css',
  '_headers',
  'robots.txt',
  'sw.js',
  'hero_frame.jpg'
];

for (const f of filesToCopy) {
  const p = path.join(rootDir, f);
  if (fs.existsSync(p)) {
    fs.copyFileSync(p, path.join(distDir, f));
  }
}

// Copy directories
const dirsToCopy = ['assets', 'src', 'brand', 'models'];
for (const d of dirsToCopy) {
  copyRecursive(path.join(rootDir, d), path.join(distDir, d));
}

console.log('[build-dist] Successfully built clean web assets into dist/');
