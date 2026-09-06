# Custom Heroic build

This source includes the selected features and packaging metadata.
See custom-build-provenance.json for the resolved commits.

Build on Linux with Node 22 and the packageManager version in package.json:

```sh
pnpm install --frozen-lockfile
pnpm exec install-electron
pnpm download-helper-binaries
pnpm codecheck
pnpm test --runInBand
pnpm exec electron-vite build
pnpm exec electron-builder --config electron-builder.custom.json --linux AppImage tar.xz --x64 --publish never
```
