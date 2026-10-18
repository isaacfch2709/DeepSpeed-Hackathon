# Static assets

Everything here except this file is copied verbatim into `assets/` by
`build.py`.

`favicon.png` is the team's own favicon, taken byte for byte from
[NTUDeepSpeed.github.io](https://github.com/NTUDeepSpeed/NTUDeepSpeed.github.io)
at `public/favicon.png` — 512x512, the lion on the brand black `#0A0A0B`. The
team site declares it the same way, as a single `rel="icon" type="image/png"`.
Do not regenerate or re-crop it: if the team changes their favicon, copy the
new file over this one so both sites stay identical.

The mascot does not appear anywhere else in the UI. The design system's rule is
that the lion is a logo, not an icon, and the favicon is one of the two places
it is allowed below 64px. The header carries the wordmark instead.

`track1-circuit.png` and `track2-circuit.png` are the two circuits, one per
track card on the landing page. They are the source pictures reduced to 8-bit
greyscale — both were already neutral, so nothing but weight was lost — with
two deliberate changes:

- **Track 1** is the `icra26` occupancy grid: dark walls, a white drivable
  corridor, grey everywhere else. It is untouched apart from the greyscale
  conversion. Because it is ink on paper, `docs.css` flips it with
  `filter: invert(1)` in the dark theme, which is why its plate is tagged
  `.paper` — the corridor then reads as track-black and the walls as chalk.
- **Track 2** is a top-down screenshot of the ICRA 2026 compete circuit in
  AutoDRIVE. The window title bar is cropped off, the dead margin around the
  circuit is trimmed, and the scene's blown-out spotlight is rolled off above
  luminance 100 so it peaks at 196 instead of 255. Without that the plate is a
  white glare next to Track 1's. No geometry is altered.

Replacing either one is a matter of dropping in a new file and correcting the
`w`/`h` in that track's `map` block in `site.json`.

`deepspeed-info-talk-17-sep-2026.pdf` is the deck from the recruitment and
hackathon info talk given on 17 September 2026, 31 slides, exactly as
presented. The landing page links to it twice — once to open and once to
download — and `app.js` loads it into an inline viewer on a wide screen. It is
the heaviest thing the site serves, so nothing fetches it until a reader asks.

`info-talk-cover.jpg` is the plate for it: page 2 of that PDF — the title
slide, not the attendance QR code on page 1 — rendered at 144 dpi to
1440x810 and saved as a progressive JPEG at quality 82. It is a photograph of
crumpled paper under flat orange type, so JPEG holds it in a seventh of what
PNG costs, and the grain survives. Nothing is cropped or recoloured: the plate
is 16/9, exactly as the slide is.

Replacing either with a later talk means dropping the new file in, renaming it
to its own date, re-rendering the cover from the new page 2, and correcting the
`talk` block in `site.json`: the file names, the date, the slide count, the
size and the cover's dimensions and alt text are all quoted on the page.
