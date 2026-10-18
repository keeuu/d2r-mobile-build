# D2R Mobile · GitHub Actions Builds

**English** | [简体中文](README.zh-CN.md)

[![Build IPA](https://github.com/keeuu/d2r-mobile-build/actions/workflows/pack.yml/badge.svg)](https://github.com/keeuu/d2r-mobile-build/actions/workflows/pack.yml)

Build unsigned IPAs and the required game data with GitHub Actions, using the **NO_XCODE** approach from [jhaizhou-ops/d2r-mobile](https://github.com/jhaizhou-ops/d2r-mobile). Download a build from Releases or run your own build below.

> **Updating an existing install:** install the new IPA over the app — **do not uninstall first** — and your game data does not need to be downloaded again. Do not use builds made from upstream v1.0.16: upstream withdrew that release because items could be lost from the personal stash and duplicated by the iCloud shared-stash merge.

## Download and install

Open the **[latest Release](https://github.com/keeuu/d2r-mobile-build/releases/latest)**. Download an IPA from **Assets**, then use the links in the release notes to download the required game data:

**Already have game data installed?** Read [Updating and reusing game data](#4-updating-and-reusing-game-data) before downloading it again.

| File | Where | Purpose |
| --- | --- | --- |
| `D2RMobile-v1.0.18.ipa` | Assets | iOS 26+; sign and install with a tool listed below |
| `D2RMobile-v1.0.18-ios18.ipa` | Assets | iOS 18–25, Metal 3 compatibility build |
| `Legacy-Device-Pack.zip` | Legacy Device Pack link in the release notes | Additional textures for A16 and earlier devices; about 1 GB |
| `D2R-Mobile-Resources.zip.001`, `.002`, `.003` | Game data links in the release notes | Download all three resource parts, totaling about 5.42 GB |
| `Resources-Parts-SHA256SUMS.txt`, `Resources-SHA256SUMS.txt` | Game data links in the release notes | Verify the parts and combined ZIP |
| `RESOURCE-INSTALL.txt` | Assets | Resource combining and import instructions |

The `Source code` archives are build scripts, not the installation package.

### 1. Install the IPA

Choose by system: **iOS 26+** uses `D2RMobile-v1.0.18.ipa`; **iOS 18–25** uses `D2RMobile-v1.0.18-ios18.ipa`. The compatibility build can also be tested on iOS 26+ when investigating graphics problems; it is not a confirmed fix for system crashes.

Both packages support **A17 Pro and newer chips, M-series iPads, and A16 and earlier chips with the matching Legacy Device Pack**. Older devices still need enough memory; support does not guarantee every model runs reliably.

Choose an IPA installer:

| Tool | Setup |
| --- | --- |
| [Sideloadly](https://sideloadly.io/) | macOS / Windows |
| [iloader](https://iloader.app/) | macOS / Windows / Linux |
| [AltStore Classic](https://faq.altstore.io/altstore-classic/your-altstore) | Set up AltServer on a Mac or Windows PC first |
| [SideStore](https://sidestore.io/) | Initial setup uses a computer; install IPAs on the phone afterward |

Follow the tool's official setup instructions, import the selected IPA, and complete the trust setup prompted by iOS. The two variants share an app identifier, so installing one replaces the other. **The IPA requires the game data described below.**

### 2. Combine and extract the game data

Place all three parts and both checksum files in the same directory.

On macOS, open a terminal in that directory and run:

```sh
shasum -a 256 -c Resources-Parts-SHA256SUMS.txt
cat D2R-Mobile-Resources.zip.001 D2R-Mobile-Resources.zip.002 D2R-Mobile-Resources.zip.003 > D2R-Mobile-Resources.zip
shasum -a 256 -c Resources-SHA256SUMS.txt
```

On Linux, use `sha256sum -c` instead of `shasum -a 256 -c`.

On Windows, open **Command Prompt (cmd)** in the directory and run:

```bat
copy /b D2R-Mobile-Resources.zip.001+D2R-Mobile-Resources.zip.002+D2R-Mobile-Resources.zip.003 D2R-Mobile-Resources.zip
```

Extract the combined ZIP to get a `D2R Mobile Resources` folder containing **18 `.data` files, about 5.56 GB**.

### 3. Import the game data and launch

Connect your iPhone by cable. In **Finder → iPhone → Files → D2R Mobile**, drag in the entire `D2R Mobile Resources` folder. Alternatively, place the folder in **Files → On My iPhone → D2R Mobile** on the phone.

For **A16 and earlier devices**, also download `Legacy-Device-Pack.zip` from the link in this IPA Release. Extract it and copy the entire `Legacy Device Pack` folder beside `D2R Mobile Resources` inside the app. Use the pack linked by your IPA Release; both system variants share that pack. A17 Pro and newer devices and M-series iPads do not need it.

Open the app and tap **Retry**. On the first launch, wait for shader compilation to finish. The reference time is **about 6 minutes on iPhone 17 Pro Max**; other devices vary. The current v1.0.18 package has not yet been verified on a physical device.

### 4. Updating and reusing game data

**Game data already imported for an earlier build of this repository can be reused; you do not need to download it again.** The release notes state the **Resource ID** of the data a build needs. If it matches the data on your phone, only the IPA changes.

If the `D2R Mobile Resources` folder is already imported on your phone, just install the new IPA over the existing app with the same app identifier. Your resources and saves are usually preserved; no resource import is needed. **Do not uninstall the app first, as this deletes them.** If you have only downloaded the resources, combine, extract and import them using steps 2 and 3 above.

For future updates, check the new Release's resource requirements before replacing your game data. If your device needs a Legacy Device Pack, use the pack linked in the IPA Release.

## Matching versions

| Component | Version |
| --- | --- |
| Upstream | v1.0.18 |
| Switch update | `1.0.34.0` / `v2228224` |
| Internal game version | `3.3.94012` |
| Required edition | Includes Reign of the Warlock |

## Run your own build

### 1. Fork the repository

Click **Fork** to create your copy, then open **Actions** and enable workflows if prompted. Use game files and keys you are authorized to use.

This README and the badge link to `keeuu/d2r-mobile-build`. If you fork the repository, replace `keeuu` with your own account in those links, and in the release instructions above, so they point at your Releases rather than someone else's.

### 2. Move to a new upstream release

The build repository pins the upstream release in exactly one place, `build-config.json`: the source commit and the SHA256 of both upstream **shell build inputs**. The workflows read the commit from that file, so the checked-out source and the shell cannot drift apart.

Upstream publishes a new release every few days. One command moves the pin:

```bash
python scripts/bump_upstream.py            # the latest upstream release
python scripts/bump_upstream.py v1.0.19    # or one specific tag
python scripts/bump_upstream.py --check    # re-verify the current pin, change nothing
```

Nothing is written until the new release passes every check the build itself will rely on: both shell build inputs must match the release's own `SHA256SUMS.txt`; both shells must report the same program requirement, shader digest and content manifest, so one generated payload can serve both; the pinned source must still provide every file the build reads; and `romfs_validate.c` must still list 18 resource archives. Then it rewrites `build-config.json` and both READMEs and runs the test suite.

The shell also records the exact `spirv-cross` build its shaders were translated with, and only that build's output is accepted. The tool pins that build too, so a release that moves the toolchain also moves `spirv_commit`; the next run then rebuilds the tools and re-translates the shaders instead of failing on a shader digest mismatch.

If the tool reports that the game version moved, the published Data no longer matches and the next build has to regenerate and re-upload the resource archives — pass a fresh `input_revision` for that. If the game version did not move, the existing Data is reused and nothing is re-uploaded.

After it succeeds:

```bash
git add -A && git commit -m "Update pinned upstream to v1.0.19" && git push
```

then run the **Build D2R Mobile IPA** workflow with `publish_release` enabled.

### 3. Configure the input

In your repository, open **Settings → Secrets and variables → Actions → New repository secret**. Name it **`GAME_INPUT_MANIFEST`** and paste the complete JSON below. The download URLs and SHA256 values are already filled in:

```json
{
  "kind": "packages",
  "files": [
    {
      "name": "game.torrent",
      "url": "https://gamegula.com/index.php?do=download&id=405",
      "sha256": "016f7c907deb1f4cd6098a7cd06823907a589ff2502aa2c8b341a89ccf984266",
      "select": [1, 2]
    }
  ],
  "key_archive": {
    "url": "https://drive.google.com/uc?export=download&id=147IsDRRJNF_VMT6Fj50glrnqAeb7oR_1",
    "sha256": "b73573af5eae6c9f7739ca9931cebf04774cf2ba9d6ee98f2f04c2dc88fca71c"
  }
}
```

The torrent contains the base game and update, selected by `select: [1, 2]`. `key_archive` is the ZIP containing extraction keys. No separate `PROD_KEYS` Secret is needed with this configuration.

### 4. Run the build

Open **Actions → Build D2R Mobile IPA → Run workflow**, select `main`, and use:

| Input | Setting |
| --- | --- |
| `publish_release` | `true` for a Release; uncheck for an Actions-only test build |
| `prepare_only` | `false` — leave unchecked |
| `input_revision` | `game-3.3.94012-v1` — change when replacing game files or editing the torrent download entry |

**Run this workflow once.** It builds both IPA variants with legacy-device support and publishes the Release automatically. Existing game data is reused without recompressing or uploading it; missing or changed game data is packaged and published automatically. The matching Legacy Device Pack is also generated once and reused by later builds when its inputs and conversion settings match.

After success, open **Releases in your own repository**. The release notes provide direct links to the required game data parts and checksums, even when those files are hosted in an earlier Release. Download and import them as described above. If the resource identifier matches the game data already on your phone, updating the IPA does not require downloading it again.

Keep the releases and assets that host the referenced game data and Legacy Device Pack so the download links remain available.

The Actions run summary also links to the IPAs and game data. The IPA artifact contains both installation packages, resource download information (`resources.json` and `legacy-resources.json`), and import instructions, and is retained for **3 days**.

Compiled tools and shader outputs are cached by their own dependencies. Updating the app version alone does not invalidate them. Both IPA variants share one generated game payload; each retains its own official executable and minimum iOS version.


## Test changes from source

Open **Actions → Build from source (test) → Run workflow**. `source_repository` accepts the upstream repository or your fork; `source_ref` accepts a branch, tag or commit. Leave the ref empty to use the pinned release. To test local patches, commit `*.patch` files under `source-patches/` in this build repository and run the workflow from that branch; patches are applied to the selected source before generating and compiling anything.

This workflow generates matching game content on Linux, then compiles both native App variants on **macOS 26**, requiring an Xcode with **iOS 26.4 or later SDK**. It does not download an upstream shell IPA. Game inputs use the same Secret configuration above; compatible Data and Legacy Device Pack are reused. Shaders are supplied as source and compiled on the phone, as with the release packages.

Download the `D2RMobile-source-ios26.0-*` or `D2RMobile-source-ios18.0-*` artifact from the run, then sign and install the IPA over the existing app. The artifacts are retained for 7 days. Reports record the source commit, patch digest and build environment. Source tests do not publish a Release and have not been verified on a physical device.
