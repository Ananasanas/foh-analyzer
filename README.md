# FOH Analyzer

A single-file browser app for live sound engineers: real-time analyzer (RTA/FFT with peak hold), SPL meter with A/C/Z weighting, mix advisor, mic calibration, room measurement, and crowd mic delay tools with a DiGiCo S21 walkthrough.

## Use it

- **Windows, easiest:** download [FOH-Analyzer-Windows.zip](FOH-Analyzer-Windows.zip?raw=1), right-click > Extract All, then double-click `Start FOH Analyzer.bat`.
- **Python desktop app (Windows, macOS, Linux):** download [FOH-Analyzer-Python.zip](FOH-Analyzer-Python.zip?raw=1), extract it, install Python 3 and double-click `Start FOH Analyzer.bat` (or run `start.sh`). Source is in [python/](python/).
- **Live with a microphone:** download `FOH-Analyzer.html` and open it in Chrome, Edge or Firefox. Allow microphone access when asked.
- **In the browser:** if GitHub Pages is turned on for this repository (Settings > Pages > Deploy from branch `main`, folder `/`), the app opens at `https://<your-user>.github.io/<repo>/`. Pages are served over HTTPS, so the microphone works there too.

## Features

- RTA and FFT spectrum analyzer with peak hold
- SPL meter: A, C and Z weighting, Fast/Slow/Impulse, Leq, peak and dose
- Mix advisor: feedback, mud, harshness, level and clipping tips (can be hidden)
- Mic calibration: acoustic calibrator, SPL meter match, manual offset, mic calibration files, virtual calibrator
- Room tab: sweep impulse response, RT60, EDT, C50/C80, STI, room modes, advisor and a 9-step walkthrough
- Crowd mic delay tab: calculator, two-channel delay finder, crowd mic list, a general tutorial and a DiGiCo S21 walkthrough with offline editor screenshots

## Limitations

SPL readings need calibration before they are accurate. The mic and room measurement paths have not been tested on real hardware yet. DiGiCo screenshots are from the S-Series Offline Editor, S21 software V3.1.1.

## Building

`src/core.html` is the source. `src/build.sh` wraps it into the standalone `FOH-Analyzer.html`.
