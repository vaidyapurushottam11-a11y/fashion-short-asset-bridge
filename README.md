# Fashion Short Asset Bridge

Dedicated asset-transfer, assembly, QA, and release pipeline for **No Face Style** fashion reels.

## Locked production rules

- Vertical 9:16 output at 1080x1920 / 30 fps.
- Final reel is completely silent: no narration, no music, no SFX, and no audio stream.
- Trending music is added natively in Instagram at posting time.
- Retention-first editing: strongest visual first, startup freezes trimmed, rapid first-three-second changes, deliberate crops/zooms, short readable overlays, and loop-aware endings.
- Magnific/Kling signed asset URLs are bridged through GitHub Releases before assembly.

## Production flow

1. Upload outfit references to the Magnific upload library.
2. Generate/approve stills and Kling fashion clips.
3. Create `requests/<reel-id>.json` mapping stable filenames to signed Magnific/Pikaso URLs.
4. `fashion-asset-transfer` downloads those URLs on GitHub Actions and publishes an asset Release.
5. Create a reel manifest under `manifests/` describing exact source trims, target durations, zooms, order, and overlays.
6. Create `assembly-requests/<reel-id>.json` pointing to the asset Release and manifest.
7. `assemble-fashion-reel` renders the silent Instagram-ready MP4, verifies there is **no audio stream**, runs technical QA, and publishes the final Reel + QA as a GitHub Release.

## Request formats

Asset transfer request:

```json
{
  "tag": "nfs-001-assets",
  "manifest": {
    "look-01.mp4": "SIGNED_MAGNIFIC_URL",
    "look-02.mp4": "SIGNED_MAGNIFIC_URL"
  }
}
```

Assembly request:

```json
{
  "reel_id": "nfs-001",
  "release_tag": "nfs-001-assets",
  "manifest": "manifests/nfs-001.json"
}
```

See `manifests/example.json` for the timeline schema.

## Editing model

Each clip entry can specify:

- `source_start` / `source_end`: remove Kling startup freeze or select the strongest movement.
- `target_seconds`: exact timeline duration.
- `zoom`: optional crop/punch-in for visual variation.

Global `overlays` specify hook/judgement/utility text with start/end timing and top/center/bottom safe-zone placement.

The final encode is H.264/YUV420p with `+faststart` and `-an`, making the delivered Reel intentionally silent for Instagram-native trending audio.
