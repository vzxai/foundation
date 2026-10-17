# Winds Out of Noise

A six-minute corecore film for an installation. It is made from public-domain archival and NASA footage, programmatic visuals, and a score that moves through noise, classical, hyperpop and post-hyperpop as stages of emergence. It loops: the film begins and ends in static.

The text is from the *God from First Principles* notes: winds out of noise, compression as the creator of identity, the rhizome and its territorialization, capitalism as a hyperstitional engine, recursive memetic structures as an alternative, and the shared region of mutually viable futures. On-screen footnotes attribute each idea to the thinker it comes from (Hegel, Schmidhuber, Kant, Deleuze and Guattari, Marx, Land and the CCRU, Fisher, Beer, Hamming), so the piece teaches as well as moves.

## Structure

| | Time | Score | Picture | Thinker |
|---|---|---|---|---|
| I · Noise | 0:00–0:48 | Wind made from filtered noise. A resonator bank tightens until the noise locks onto the harmonic series of D: noise compresses into tone. | Static becoming wind (line-integral convolution), grass, Hurricane Dorian from the ISS, the first cell division of a salamander egg | Hegel: being, nothing, becoming |
| II · Compression | 0:48–1:48 | A string chorale and piano in D minor grow out of that tone. | A real embryo frame rebuilt from its largest DCT coefficients (with a live count), Gray-Scott "mitosis" patterns, pond life, the sun | Schmidhuber: beauty as compressibility. Kant: purposiveness without purpose |
| III · Rhizome → Territory | 1:48–2:42 | Branching generative plucks get pulled onto a 16th-note grid and an ostinato; factory clangs arrive. | A growing network that snaps onto a Manhattan grid; Market Street in 1906, *The City* (1939), *Master Hands* (1936), Levittown | Deleuze & Guattari; Marx: "an appendage of the machine" |
| IV · Technocapital | 2:42–3:48 | Hyperpop at 160 BPM on the *same* chord progression as the chorale: supersaws, distorted 808s, a chipmunk vocal hook, and a vocoded "capitalism is a hyperstitional engine" | Cuts on the beat: *Design for Dreaming*, the NYSE floor, *Century 21 Calling*, *A is for Atom*, with an accelerating hyperstition loop diagram | Land / CCRU; Fisher; Beer: POSIWID |
| V · Metabolism | 3:48–4:42 | Post-hyperpop: the drop is stuttered, bitcrushed and granular-stretched, then the chorale comes back through a vocoder choir, then an endless Shepard-tone "foom" | Broken footage, feedback recursion, double exposures of embryos and advertising, Hamming's chalkboard, a rocket launch | Beer: recursion; Hamming; the foom debate |
| VI · Singleton | 4:42–5:39 | All four languages together in D major: wind, strings and piano, bell arps and a soft four-on-the-floor, the choir singing "what if the purpose of collective intelligence…" | A boy in a creek, a mother and child, then four viability sets V₁…V₄ filled with footage whose intersection S glows and spreads | Kant: the kingdom of ends |
| VII · Coda | 5:39–6:00 | The final chord dissolves back into wind (section I in reverse). | Grass, then flow back to static. Title. | |

The four musical languages stand for stages of emergence. Noise is being before identity. Classical is a stable, compressed identity. Hyperpop is that identity captured and accelerated by an engine. Post-hyperpop is the engine's output metabolized and recombined. In VI they coexist instead of replacing each other.

## Building it

Requires Python 3 with numpy, scipy, numba and Pillow, plus ffmpeg and espeak-ng.

```sh
# 1. download the public-domain sources (about 3.6 GB)
python3 footage/fetch.py ~/won-cache/src

# 2. compose the score: score.wav, one stem per musical language, and cues.json
python3 score/compose.py ~/won-cache/score
python3 score/analyze.py ~/won-cache/score     # loudness per section and a spectrogram

# 3. render the picture and mux the score
python3 edit/render.py ~/won-cache/src ~/won-cache/score ~/won-cache/film --jobs 4
# preview one stretch:  --range 160:200 --scale 0.5
```

`footage/contact_sheet.sh` makes the timestamped sheets used to choose shots. The whole edit (every shot, caption and footnote) is in `edit/timeline.py`, and the generative scenes are in `visuals/generative.py`. The picture reads beat and hit times from `cues.json`, so if the score changes, the cuts and flashes follow it.

## Installation notes

- 1920×1080, 30 fps, H.264, AAC 320 kb/s stereo. 6:00. It fades from and to black over about a second at each end, so it loops cleanly.
- The stems (`stem_noise.wav`, `stem_classical.wav`, `stem_hyperpop.wav`, `stem_posthyperpop.wav`, `stem_voice.wav`) are also written, if a room wants a multichannel spread.
- The score's dynamics are meant to be felt: section I sits about 11 dB below the hyperpop drop.

## Notes

- The score was checked with meters and a spectrogram (`score/analyze.py`), not by ear in this environment. Listen to it on good speakers before you show it, and adjust the `LOUDNESS` targets in `score/compose.py` and the stem gains in `main()`.
- The piece was composed, edited and coded programmatically with Claude Code. If the exhibiting venue has a disclosure policy for AI-assisted work, this is what to disclose.
- The sources and the quoted texts are in [CREDITS.md](CREDITS.md).
