# Making a release

Users get the add-on from an extension repository whose address never changes:

```
https://github.com/modelllogik/bonsai-btk/releases/latest/download/index.json
```

GitHub forwards this address to the files of the release marked *Latest*. Blender reads
`index.json` there and downloads the zip next to it (the `archive_url` in the listing is
relative, `./bonsai_btk-<version>.zip`). So **every release carries two files: the zip
and its `index.json`.** No web server and no GitHub Pages are needed.

## Steps

1. **Version:** raise `version` in `bonsai_btk/blender_manifest.toml`. Update the status
   line and the roadmap in `README.md` and the *Stand* line in `docs/de/README.md`.
   Commit and push.
2. **Build into an empty folder for this version** (from the repository root):

   ```bash
   blender --command extension build --source-dir bonsai_btk --output-dir dist/0.2.2
   blender --command extension server-generate --repo-dir=dist/0.2.2
   ```

   The folder must hold only the new zip: `server-generate` lists every zip it finds.
   The result is `bonsai_btk-0.2.2.zip` and `index.json` (`dist/` is not checked in).
3. **Release on GitHub:** tag `v0.2.2` on the pushed commit, title and text, attach
   **both files**, leave *Set as a pre-release* off and *Set as the latest release* on.
   A pre-release is not *Latest*, so users would not see it.
4. **Check the address:** open the URL above in a browser. It must show the new version,
   and `archive_hash` must match the attached zip
   (`certutil -hashfile bonsai_btk-0.2.2.zip SHA256` on Windows, `sha256sum` elsewhere).
5. **Check the update** in a Blender test profile that has the repository added:
   *Get Extensions → ⌄ → Check for Updates*, then *Update*. Restart Blender and look at the
   version in the extension list.

## Rules

- **Never reuse a version number** and never replace a zip in a published release. Blender
  checks the size and hash from `index.json`; a changed zip fails to install. Fix by
  releasing the next patch version.
- **Do not rename the zip** after `server-generate`; the listing refers to the file name.
- **If `index.json` is missing from the latest release,** the address answers 404 and users
  get no updates. Attaching it to that release afterwards repairs it.
- **To withdraw a version,** release the next one. If an extension must not be installed
  at all, a `blender_repo.toml` with a `[[blocklist]]` entry next to the zip goes into
  `server-generate` (see `blender --command extension server-generate --help`).

## Tested

Sync, install and update through this address were run with Blender's extension command
line (`blender_ext.py`, Blender main as of 2026-11-09) against a server that forwards
`releases/latest/download/` like GitHub: install of 0.2.1, then a test 0.2.2 picked up
by *sync* and installed over it. The check in the Blender user interface is step 5 above.
