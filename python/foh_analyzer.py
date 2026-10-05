#!/usr/bin/env python3
"""FOH Analyzer (Python desktop edition).

Real-time analyzer for live sound: RTA and FFT with peak hold, SPL meter with
A/C/Z weighting, mix advisor, mic calibration, room measurement and a crowd
mic delay finder with walkthroughs (general and DiGiCo S21).

Needs Python 3.9+, numpy and (for real audio) sounddevice. Without sounddevice
the demo, pink noise, WAV file and simulated sources still work.
"""
import json
import math
import os
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import numpy as np

try:
    import sounddevice as sd
    sd.query_devices()
    SD_ERR = None
except Exception as e:  # missing module or missing PortAudio
    sd = None
    SD_ERR = str(e) or e.__class__.__name__

APP = 'FOH Analyzer'
VERSION = '1.0'
SETTINGS = os.path.join(os.path.expanduser('~'), '.foh_analyzer.json')
TUT = json.loads('{"WALK": [{"t": "Set up the measurement mic", "x": "Use an omnidirectional measurement mic on a stand at ear height (about 1.2 m seated, 1.7 m standing), pointing up or toward the speakers. Keep it at least 1 m from walls and off tables and consoles. In your computer\'s sound settings turn off any mic enhancements, and set the interface gain so speech near the mic peaks around −30 dBFS.", "tips": []}, {"t": "Calibrate the level", "x": "Fit a 94 dB calibrator over the capsule and use the calibrator tab, or match a trusted SPL meter. RT60 and the response shape do not need calibration, but noise rating and level checks do. Skip this if you only care about the room\'s sound.", "tips": []}, {"t": "Load the mic file", "x": "If your mic came with a calibration file (UMIK, Dayton and similar), load it so the high frequencies are measured correctly. Optional for most room work.", "tips": []}, {"t": "Describe the room", "x": "Enter length, width and height in metres and choose what the room is used for. This sets the RT60 target, the Schroeder frequency and the predicted room modes.", "tips": []}, {"t": "Measure background noise", "x": "With the system muted and the room as it will be during use (air conditioning on, no music), measure 5 seconds of background noise. You get an NR rating per octave.", "tips": []}, {"t": "Set the sweep level", "x": "Turn the amplifier or mixer output down first. Run one sweep at −30 dBFS, then raise the level until the decay range reads 45 dB or more without clipping. The sweep is a rising tone from 20 Hz to 20 kHz. Warn people in the room, and protect tweeters: never start loud.", "tips": []}, {"t": "Measure several positions", "x": "Measure 3 to 6 listening positions: FOH, centre, left, right, rear, balcony. Avoid the exact centre line and spots right against walls. Name each one before you press Measure. The advisor averages all ticked positions, which is what you should EQ to.", "tips": []}, {"t": "Read the results", "x": "Frequency response: the full-room curve shows what listeners hear; peaks in the shaded modal region are room modes. Direct + early shows the speaker itself above about 250 Hz. Decay: RT60 (T30/T20) is how long sound takes to die by 60 dB; EDT is what the ear perceives. C80 and STI tell you how clear music and speech will be.", "tips": []}, {"t": "Fix, then re-measure", "x": "Work in this order: speaker placement and aiming, sub placement and delay alignment, room treatment for RT60 and reflections, and EQ last. Use the room advisor\'s EQ list as a starting point, change one thing at a time, and measure the same positions again to compare.", "tips": []}], "DWALK": [{"t": "Why crowd mics need delay", "x": "Crowd (audience) mics pick up the PA as well as the audience. That PA sound reaches them late: about 2.9 ms for every metre from the speakers. Blended with close mics in a broadcast, stream or recording mix, the late copy causes flamming and comb filtering, so the mix sounds thin and phasey. Aligning them fixes that.", "tips": ["Applause and singing are local to the mic, so they never need aligning. Only the PA bleed does.", "In-ear ambience mics on stage are usually left undelayed: low latency matters more there."]}, {"t": "Choose the time reference", "x": "The reference is \\"time zero\\": normally the console\'s band mix (a matrix or aux carrying the close mics), because that is what the crowd mics must line up with. If you can\'t send it to the interface, a mic close to the main PA works too.", "tips": ["With several crowd mics, measure each against the same reference."]}, {"t": "Place the crowd mics", "x": "Point the mics at the audience, not at the PA, and keep them out of the PA\'s main coverage where you can (high on the truss, at the side of the stage, or at FOH facing the crowd). Matched left and right pairs at the same distance keep the image steady.", "tips": ["Cardioid or shotgun mics aimed away from the PA reduce bleed, which also makes delay less critical.", "Measure the distance from the main PA hang, not from the stage."]}, {"t": "Place the reference mic", "x": "Best is no reference mic at all: feed the console band mix into input 1. It is exactly what the crowd mics must line up with, and the reading is the full delay from the PA to the crowd mic. If you have to use a mic as the reference, put it close to the PA, never near the crowd mics: about 1 m in front of the speaker the crowd mic hears most, on its axis and at the height of its high-frequency driver. The delay finder then only sees the extra path from the reference mic to the crowd mic, so set \\"Reference is\\" to \\"Mic at the PA\\" and enter that distance: the program adds the missing time back (2.9 ms per metre).", "tips": ["Same speaker, same side: measure the left crowd mic against a reference at the left hang and the right crowd mic against the right hang.", "Never put the reference next to a crowd mic: it would read about 0 ms and tell you nothing. Every crowd mic must be farther from the PA than the reference.", "Put it in front of the tops, not on a subwoofer: subs are often time-offset from the tops and smear the reading.", "Mute delay towers and front fills while measuring, or the crowd mic hears several arrivals and the spike splits.", "A mic reference misses the PA processor latency (often 1 to 3 ms) that the band mix really has, so check the result by ear or with the console bus afterwards."]}, {"t": "Estimate with the calculator", "x": "Enter the distance from the PA to each crowd mic and the air temperature. The calculator gives the delay in ms and in samples. Add each mic to the list. This is a good starting point if you cannot measure.", "tips": []}, {"t": "Wire up the delay finder", "x": "Connect a 2-channel interface: the reference (console band mix) into input 1 and the crowd mic into input 2. Set \\"Reference on\\" to match. Turn off any processing on the interface inputs. Choose a search range longer than the expected delay.", "tips": []}, {"t": "Measure the delay", "x": "Play music or pink noise through the PA at a normal level. Watch the correlation plot: one tall spike should stand out. Wait until confidence reads good and stability is within ±0.2 ms, then add the reading to the crowd mic list. A downward spike means the mic is in reverse polarity.", "tips": []}, {"t": "Apply the delay", "x": "Pick a strategy in the crowd mic list. \\"Delay the band mix\\" delays the close-mic bus by the farthest crowd mic delay and delays the nearer crowd mics to match: everything lines up. Best for broadcast and streaming, but tell the video team the audio is now later. \\"Align crowd mics\\" delays the nearer crowd mics to match the farthest: use it when you cannot delay the band, and keep crowd mics low under music.", "tips": ["Recording for later? Leave everything undelayed and slide the crowd tracks earlier in the DAW by the measured time.", "Flip polarity on any mic marked Ø."]}, {"t": "Fine-tune by ear", "x": "Solo the reference and one crowd mic at similar levels. Nudge the delay ±0.5 ms and the polarity until the low end sounds fullest and the sound stops \\"swirling\\". Then set the crowd level so it adds space without smearing the drums.", "tips": []}, {"t": "Re-check during the show", "x": "Sound slows down in cold air and speeds up in heat: at 30 m a 10 °C change moves the delay by about 1.5 ms. Re-measure after doors when the room warms up, and whenever the PA or the mics move.", "tips": []}], "S21": [{"t": "Plan the broadcast routing", "x": "The words used in this walkthrough: \\"band channels\\" are all the input channels of the band (drums, bass, guitars, keys, vocals): everything except the crowd mics. \\"L/R\\" is the main mix bus that drives the PA. \\"BAND BC\\" (band broadcast) is a stereo group you create for the broadcast only: route every band channel to it as well as to L/R (Channel Setup > Outputs > Group Assign, then tap the group and Master), so it carries the same band mix but feeds only the broadcast. Because it is separate from L/R, it can be delayed without touching the PA. \\"BCAST\\" is the stereo matrix that goes to the broadcast truck, recorder or stream. On the S21 every input channel can also send straight to a matrix and has its own delay, so send each crowd mic channel directly to BCAST and put each crowd mic\'s delay on its own channel. BAND BC also goes into BCAST, and the band delay goes on the BAND BC group output.", "tips": ["Why not delay the band channels? A channel delay sits inside the channel, before all its outputs. Every band channel feeds L/R (the PA) and the monitor auxes, so a delay on, say, the kick channel makes the kick late in the PA and in the monitors too. A delay on the BAND BC group output only affects what leaves that group: the broadcast.", "Crowd mics normally feed only the broadcast, so delaying their channels is safe. If a crowd mic also feeds the PA or the in-ears, the delay goes there too.", "No spare group? Send the band channels straight to BCAST as well and use \\"Align crowd mics\\": the crowd mics line up with each other, but the band stays early, so keep the crowd low under music.", "A delay on the BCAST matrix output moves band and crowd together, so it does not align anything. Leave it at 0 unless video needs the whole feed later.", "Already feeding L/R into BCAST? Then the crowd mic channel delays line up the crowd mics with each other, but L/R cannot be delayed because it is the PA. Either keep the crowd low under music, or give the band its own broadcast delay: a separate matrix \\"BC BAND\\" fed by L/R with output delay set to the farthest crowd mic, sent to the broadcast as its own stem next to a \\"BC CROWD\\" matrix fed by the crowd channels."]}, {"t": "Patch two measurement outputs", "x": "Reference: open the BAND BC group (tap its name to open Channel Setup), tap Outputs > Direct Outputs, choose Local I/O > Analogue and tap Out 1. Crowd mic: open Main Menu > Matrix, pick a free matrix input, tap \\"No Input\\" and choose Internal > Channel Outputs > the crowd mic channel. Send that matrix input only to one spare matrix, name it \\"MEAS\\", and patch MEAS the same way (its Channel Setup > Direct Outputs) to Out 2. Both signals then go through the console the same way, so the console\'s own latency cancels out of the measurement.", "tips": ["The MEAS send comes after the channel delay, so in the verify step it shows the delayed result.", "The crowd channel\'s direct output works too, if it is set up in your session.", "Name the outputs in the patch so the next engineer knows what they are."]}, {"t": "Where the reference comes from", "x": "On the S21 the reference should be electrical: BAND BC from local out 1, not a microphone. It is exactly the signal the broadcast mix lines up with, and the reading includes the console and PA processing latency the crowd mics really hear. Only if you cannot get a console output to the laptop, use a measurement mic as the reference: about 1 m in front of the main hang or stack on the same side as the crowd mic, on axis, at the height of the high-frequency driver, and never near the crowd mics. Set \\"Reference is\\" to \\"Mic at the PA\\" and enter its distance; the program adds that time back.", "tips": ["Same speaker, same side: measure the left crowd mic against a reference at the left hang and the right crowd mic against the right hang.", "Never put the reference next to a crowd mic: it would read about 0 ms and tell you nothing. Every crowd mic must be farther from the PA than the reference.", "Put it in front of the tops, not on a subwoofer: subs are often time-offset from the tops and smear the reading.", "Mute delay towers and front fills while measuring, or the crowd mic hears several arrivals and the spike splits.", "A mic reference misses the PA processor latency (often 1 to 3 ms) that the band mix really has, so check the result by ear or with the console bus afterwards."]}, {"t": "Connect the laptop interface", "x": "Cable local out 1 to input 1 and local out 2 to input 2 of a 2-channel USB interface. Set the interface to line level, turn off any input processing, and set the gains so both meters in the delay finder peak around −20 dBFS. Choose \\"Interface, 2 channels\\" and \\"Reference on: Input 1\\" in the delay finder below.", "tips": []}, {"t": "Zero the delays first", "x": "Before measuring, make sure nothing is already delayed. Tap each crowd mic channel\'s name to open Channel Setup: the Input Processing box shows the delay, and the right-hand side shows the Delay value with \\"Delay Off / Click to enable\\". It should read Delay Off or 0.00 ms. Do the same for the BAND BC group and the BCAST matrix (groups and matrices have the same Channel Setup), and set Input Polarity to Standard on the crowd channels.", "tips": ["Delay values on DiGiCo can be shown in ms or as a distance. Use ms so the numbers match this program."]}, {"t": "Play program through the PA", "x": "Play music or pink noise through the PA at a normal show level with the band channels feeding BAND BC. The crowd mic must hear the PA, so do this with the PA on and the room as quiet as you can get it otherwise.", "tips": []}, {"t": "Measure each crowd mic", "x": "Watch the delay finder until confidence reads good and stability is within ±0.2 ms, type the mic\'s name and press \\"Add to crowd mic list\\". Then in Main Menu > Matrix, tap the MEAS matrix input\'s source name and pick the next crowd mic channel (only one crowd mic in MEAS at a time), press Reset average, and repeat for every crowd mic.", "tips": ["A downward spike means the mic is in reverse polarity; it is marked Ø in the list.", "Can\'t measure? Add the mics from the calculator using the distance from the PA."]}, {"t": "Set the crowd channel delays", "x": "Set \\"Delay the band mix\\" in the crowd mic list. On each crowd mic channel tap its name to open Channel Setup and tap the Input Processing box. Press Delay On, drag the Input Delay slider (0 to 682 ms) near the value, then fine-tune it with the Delay encoder on the right (the mouse wheel in the offline editor) until it reads the value from the list. The nearer mics now wait for the farthest one, and because the crowd channels feed BCAST directly, the delay goes straight into the broadcast mix:", "tips": []}, {"t": "Delay the band group", "x": "Find the BAND BC group (press Space for the Console Overview; groups are red). Tap its name to open Channel Setup, tap Input Processing, press Delay On and set the arrival time of the farthest crowd mic (the largest value in the crowd mic list). Leave the BCAST matrix output undelayed.", "tips": ["Only the group gets this delay, never the band channels, so the PA and monitors stay on time.", "Using L/R into BCAST instead of a band group? Never delay L/R itself (that is the PA). Skip this step and use \\"Align crowd mics\\" in the list, or delay a separate \\"BC BAND\\" matrix fed by L/R by this amount and send it as its own stem.", "Tell the video or broadcast team the audio is now this much later, so they can keep lip sync."]}, {"t": "Verify with the delay finder", "x": "Re-measure with the delays switched on: patch BAND BC (now delayed) to input 1 and each crowd mic via the MEAS matrix to input 2 again. Every crowd mic should now read close to 0 ms (within about ±0.5 ms) with normal polarity. If one reads off, correct that channel\'s delay by the difference.", "tips": []}, {"t": "Fine-tune by ear", "x": "Solo BAND BC and one crowd mic at similar levels in your headphones. Nudge that crowd channel\'s delay in 0.1–0.5 ms steps and try the polarity button until the low end sounds fullest and the sound stops swirling. Then bring the crowd level down to where it adds space without smearing the drums.", "tips": []}, {"t": "Protect the delays in snapshots", "x": "Delays are part of each snapshot. Either open Main Menu > Session & Snapshots and press Update (✓) on every snapshot after setting them, or take delay out of the recall scope: Session & Snapshots > Global Scope, and tap the Delay block under Input Processing so snapshots stop recalling it (or use Safes in each channel\'s Channel Setup). Then save the session with File… and keep a copy on a USB stick.", "tips": ["Write the values on the console notes or a strip of tape too: quicker than digging through menus during the show."]}, {"t": "Re-check during the show", "x": "As the room fills up and warms, sound travels faster and the crowd mics arrive earlier: about 1.5 ms less at 30 m for a 10 °C rise. Re-measure after doors open, and adjust the crowd channel delays and the BAND BC delay if needed.", "tips": []}]}')

# ---------------------------------------------------------------- colours
BG, PANEL, PANEL2, LINE = '#0e1116', '#161b22', '#1d242e', '#2a3340'
TXT, DIM, TRACE, PEAK, AVG = '#d7dee8', '#8a96a8', '#4fd1c5', '#f6ad55', '#90cdf4'
WARN, BAD, GOOD = '#f6ad55', '#fc8181', '#68d391'


def db(x, floor=1e-20):
    return 10.0 * np.log10(np.maximum(x, floor))


def ftext(f):
    return f'{f / 1000:.3g} kHz' if f >= 1000 else f'{f:.0f} Hz'


# ---------------------------------------------------------------- weighting
def weight_db(f, kind):
    f = np.asarray(f, float)
    f2 = np.maximum(f, 1e-3) ** 2
    if kind == 'A':
        ra = (12194.0 ** 2 * f2 ** 2) / ((f2 + 20.6 ** 2) * np.sqrt((f2 + 107.7 ** 2) * (f2 + 737.9 ** 2)) * (f2 + 12194.0 ** 2))
        return 20 * np.log10(ra) + 2.0
    if kind == 'C':
        rc = (12194.0 ** 2 * f2) / ((f2 + 20.6 ** 2) * (f2 + 12194.0 ** 2))
        return 20 * np.log10(rc) + 0.06
    return np.zeros_like(f)


# ---------------------------------------------------------------- settings
def load_settings():
    try:
        with open(SETTINGS, 'r', encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return {}


def save_settings(s):
    try:
        with open(SETTINGS, 'w', encoding='utf-8') as fh:
            json.dump(s, fh, indent=1)
    except Exception:
        pass


# ---------------------------------------------------------------- wav reader
def read_wav(path):
    """Minimal RIFF/WAVE reader: PCM 8/16/24/32 bit, float 32/64, extensible."""
    with open(path, 'rb') as fh:
        data = fh.read()
    if data[:4] != b'RIFF' or data[8:12] != b'WAVE':
        raise ValueError('Not a WAV file')
    pos, fmt, raw = 12, None, None
    while pos + 8 <= len(data):
        cid, size = data[pos:pos + 4], int.from_bytes(data[pos + 4:pos + 8], 'little')
        body = data[pos + 8:pos + 8 + size]
        if cid == b'fmt ':
            tag = int.from_bytes(body[0:2], 'little')
            ch = int.from_bytes(body[2:4], 'little')
            fs = int.from_bytes(body[4:8], 'little')
            bits = int.from_bytes(body[14:16], 'little')
            if tag == 0xFFFE and len(body) >= 26:
                tag = int.from_bytes(body[24:26], 'little')
            fmt = (tag, ch, fs, bits)
        elif cid == b'data':
            raw = body
        pos += 8 + size + (size & 1)
    if fmt is None or raw is None:
        raise ValueError('WAV file has no fmt or data chunk')
    tag, ch, fs, bits = fmt
    if tag == 3:
        x = np.frombuffer(raw[:len(raw) // (bits // 8) * (bits // 8)], '<f4' if bits == 32 else '<f8').astype(np.float32)
    elif tag == 1:
        if bits == 8:
            x = (np.frombuffer(raw, np.uint8).astype(np.float32) - 128) / 128
        elif bits == 16:
            x = np.frombuffer(raw[:len(raw) // 2 * 2], '<i2').astype(np.float32) / 32768
        elif bits == 24:
            b = np.frombuffer(raw[:len(raw) // 3 * 3], np.uint8).reshape(-1, 3).astype(np.int32)
            v = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
            v = np.where(v & 0x800000, v - 0x1000000, v)
            x = v.astype(np.float32) / 8388608
        elif bits == 32:
            x = np.frombuffer(raw[:len(raw) // 4 * 4], '<i4').astype(np.float32) / 2147483648
        else:
            raise ValueError(f'{bits}-bit PCM is not supported')
    else:
        raise ValueError(f'WAV format {tag} is not supported (use PCM or float)')
    x = x[:len(x) // ch * ch].reshape(-1, ch)
    return x, fs


def resample(x, fs_in, fs_out):
    if fs_in == fs_out:
        return x
    n = int(round(len(x) * fs_out / fs_in))
    t_in = np.arange(len(x)) / fs_in
    t_out = np.arange(n) / fs_out
    return np.stack([np.interp(t_out, t_in, x[:, c]) for c in range(x.shape[1])], 1).astype(np.float32)


# ---------------------------------------------------------------- test signals
def pink(n, fs, rng):
    X = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / fs)
    X[1:] /= np.sqrt(f[1:])
    X[0] = 0
    X[f < 15] = 0
    x = np.fft.irfft(X, n)
    return (x / np.sqrt(np.mean(x ** 2))).astype(np.float32)


def frac_delay(x, d_samples):
    """Circular fractional delay of a periodic loop (exact via FFT phase)."""
    n = len(x)
    X = np.fft.rfft(x)
    k = np.arange(len(X))
    return np.fft.irfft(X * np.exp(-2j * np.pi * k * d_samples / n), n).astype(np.float32)


def make_demo(fs, seconds=8.0):
    """A rough 'band' loop: pink bed, kick pulses, a 250 Hz mud bump and a feedback tone that grows."""
    rng = np.random.default_rng(7)
    n = int(fs * seconds)
    t = np.arange(n) / fs
    bed = pink(n, fs, rng)
    X = np.fft.rfft(bed)
    f = np.fft.rfftfreq(n, 1 / fs)
    # mud bump at 250 Hz (+7 dB, about an octave wide) and gentle top roll-off
    g = 1 + (10 ** (7 / 20) - 1) * np.exp(-0.5 * (np.log2(np.maximum(f, 1) / 250) / 0.45) ** 2)
    g /= np.sqrt(1 + (f / 9000) ** 2)
    bed = np.fft.irfft(X * g, n)
    env = 0.6 + 0.4 * np.abs(np.sin(np.pi * t * 2.0))  # pumping, music-like envelope
    kick = np.zeros(n)
    for k0 in np.arange(0, seconds, 0.5):
        i = int(k0 * fs)
        m = min(n - i, int(0.25 * fs))
        tt = np.arange(m) / fs
        kick[i:i + m] += np.sin(2 * np.pi * (55 + 90 * np.exp(-tt * 30)) * tt) * np.exp(-tt * 12)
    fb = np.sin(2 * np.pi * 2520 * t) * np.clip((t - 3) / 4, 0, 1) * 0.5
    x = 0.12 * bed * env + 0.25 * kick + 0.12 * fb
    return (x / np.max(np.abs(x)) * 0.5).astype(np.float32)


def make_pink_loop(fs, seconds=6.0):
    x = pink(int(fs * seconds), fs, np.random.default_rng(3))
    return (x * 0.125).astype(np.float32)  # about -18 dBFS RMS


# ---------------------------------------------------------------- audio engine
class Engine:
    """Ring buffer fed either by a sounddevice input stream or by a looping generated signal."""

    def __init__(self, fs=48000):
        self.fs = fs
        self.size = 1 << 19
        self.buf = np.zeros((2, self.size), np.float32)
        self.w = 0
        self.total = 0
        self.lock = threading.Lock()
        self.stream = None
        self.loop = None  # (n, 2) float32
        self.loop_pos = 0
        self.last = None
        self.running = False
        self.clip = 0.0
        self.tone = None  # (freq, amp) internal calibrator tone mixed into channel 1
        self.tone_phase = 0.0

    # --- writing
    def push(self, block):
        block = np.asarray(block, np.float32)
        if block.ndim == 1:
            block = np.stack([block, block], 1)
        if block.shape[1] == 1:
            block = np.repeat(block, 2, 1)
        n = len(block)
        if n == 0:
            return
        if self.tone is not None:
            f, a = self.tone
            ph = self.tone_phase + 2 * np.pi * f * np.arange(n) / self.fs
            block = block.copy()
            block[:, 0] += (a * np.sin(ph)).astype(np.float32)
            self.tone_phase = float((ph[-1] + 2 * np.pi * f / self.fs) % (2 * np.pi))
        if np.max(np.abs(block[:, 0])) >= 0.999:
            self.clip = time.time()
        with self.lock:
            if n >= self.size:
                block = block[-self.size:]
                n = self.size
            i = self.w
            j = min(n, self.size - i)
            self.buf[:, i:i + j] = block[:j].T
            if j < n:
                self.buf[:, :n - j] = block[j:].T
            self.w = (i + n) % self.size
            self.total += n

    def latest(self, n):
        with self.lock:
            idx = (self.w - n + np.arange(n)) % self.size
            return self.buf[:, idx].copy()

    # --- sources
    def stop(self):
        self.running = False
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
        self.stream = None
        self.loop = None

    def start_loop(self, loop):
        self.stop()
        self.loop = loop.astype(np.float32)
        self.loop_pos = 0
        self.last = time.perf_counter()
        self.running = True

    def start_input(self, device, channels=2):
        self.stop()
        if sd is None:
            raise RuntimeError('Audio input is unavailable: ' + str(SD_ERR))
        info = sd.query_devices(device, 'input')
        ch = max(1, min(channels, int(info['max_input_channels'])))
        fs = self.fs

        def cb(indata, frames, t, status):
            self.push(indata[:, :2])

        try:
            self.stream = sd.InputStream(device=device, channels=ch, samplerate=fs, blocksize=1024, dtype='float32', callback=cb)
        except Exception:
            fs = int(info['default_samplerate'])
            self.stream = sd.InputStream(device=device, channels=ch, samplerate=fs, blocksize=1024, dtype='float32', callback=cb)
        self.fs = fs
        self.stream.start()
        self.running = True
        return ch

    def pump(self):
        """Advance a generated source by real elapsed time (called from the GUI loop)."""
        if self.loop is None or not self.running:
            return
        now = time.perf_counter()
        n = int((now - self.last) * self.fs)
        if n <= 0:
            return
        n = min(n, self.fs)  # never jump more than a second
        self.last += n / self.fs
        if now - self.last > 1:
            self.last = now
        L = len(self.loop)
        idx = (self.loop_pos + np.arange(n)) % L
        self.loop_pos = int((self.loop_pos + n) % L)
        self.push(self.loop[idx])


# ---------------------------------------------------------------- plot widget
class Plot(tk.Canvas):
    """Log-frequency (or linear) plot on a Tk canvas with cheap line updates."""

    def __init__(self, master, ymin=20, ymax=130, xmin=20, xmax=20000, logx=True, ylabel='dB', height=300, xlabel=None, **kw):
        super().__init__(master, bg=BG, highlightthickness=0, height=height, **kw)
        self.ymin, self.ymax, self.xmin, self.xmax, self.logx = ymin, ymax, xmin, xmax, logx
        self.ylabel, self.xlabel = ylabel, xlabel
        self.items = {}
        self.ml, self.mr, self.mt, self.mb = 44, 10, 8, 22
        self.bind('<Configure>', lambda e: self.redraw())
        self.data = {}

    def X(self, f):
        w = max(10, self.winfo_width() - self.ml - self.mr)
        if self.logx:
            r = (np.log10(np.maximum(f, 1e-9)) - math.log10(self.xmin)) / (math.log10(self.xmax) - math.log10(self.xmin))
        else:
            r = (np.asarray(f, float) - self.xmin) / (self.xmax - self.xmin)
        return self.ml + r * w

    def Y(self, v):
        h = max(10, self.winfo_height() - self.mt - self.mb)
        r = (np.asarray(v, float) - self.ymin) / (self.ymax - self.ymin)
        return self.mt + (1 - np.clip(r, -0.02, 1.02)) * h

    def set_range(self, ymin, ymax):
        self.ymin, self.ymax = ymin, ymax
        self.redraw()

    def redraw(self):
        self.delete('all')
        self.items = {}
        W, H = self.winfo_width(), self.winfo_height()
        if self.logx:
            ticks = [20, 50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000]
            ticks = [t for t in ticks if self.xmin <= t <= self.xmax]
            lab = lambda t: f'{t // 1000}k' if t >= 1000 else str(t)
        else:
            span = self.xmax - self.xmin
            step = 10 ** math.floor(math.log10(span / 4))
            for m in (1, 2, 5, 10):
                if span / (step * m) <= 8:
                    step *= m
                    break
            ticks = list(np.arange(math.ceil(self.xmin / step) * step, self.xmax + 1e-9, step))
            lab = lambda t: f'{t:g}'
        for t in ticks:
            x = float(self.X(t))
            self.create_line(x, self.mt, x, H - self.mb, fill=LINE)
            self.create_text(x, H - self.mb + 10, text=lab(t), fill=DIM, font=('Segoe UI', 8))
        span = self.ymax - self.ymin
        step = 10 if span > 60 else 6 if span > 30 else 3 if span > 12 else 1
        v = math.ceil(self.ymin / step) * step
        while v <= self.ymax:
            y = float(self.Y(v))
            self.create_line(self.ml, y, W - self.mr, y, fill=LINE)
            self.create_text(self.ml - 4, y, text=f'{v:g}', anchor='e', fill=DIM, font=('Segoe UI', 8))
            v += step
        self.create_text(4, self.mt, text=self.ylabel, anchor='nw', fill=DIM, font=('Segoe UI', 8))
        if self.xlabel:
            self.create_text(W - self.mr, H - self.mb - 4, text=self.xlabel, anchor='se', fill=DIM, font=('Segoe UI', 8))
        for k, d in list(self.data.items()):
            self._draw(k, *d)

    def _draw(self, key, kind, x, y, opts):
        if kind == 'line':
            if len(x) < 2:
                return
            xs, ys = self.X(np.asarray(x)), self.Y(np.asarray(y))
            pts = np.empty(2 * len(xs))
            pts[0::2], pts[1::2] = xs, ys
            it = self.items.get(key)
            if it and len(it) == 1:
                self.coords(it[0], *pts.tolist())
            else:
                self.delete(key)
                self.items[key] = [self.create_line(*pts.tolist(), tags=(key,), **opts)]
        elif kind == 'bars':
            lo, hi = x
            base = float(self.Y(self.ymin))
            it = self.items.get(key)
            x0, x1, yy = self.X(lo), self.X(hi), self.Y(y)
            if it and len(it) == len(lo):
                for i, r in enumerate(it):
                    self.coords(r, x0[i] + 0.5, yy[i], x1[i] - 0.5, base)
            else:
                self.delete(key)
                self.items[key] = [self.create_rectangle(x0[i] + 0.5, yy[i], x1[i] - 0.5, base, tags=(key,), **opts) for i in range(len(lo))]
        elif kind == 'marks':
            self.delete(key)
            self.items[key] = []
            for xi, yi, txt in zip(x, y, opts.pop('labels', []) if False else opts.get('labels', [])):
                px, py = float(self.X(xi)), float(self.Y(yi))
                self.items[key].append(self.create_oval(px - 4, py - 4, px + 4, py + 4, outline=opts.get('fill', BAD), width=2, tags=(key,)))
                self.items[key].append(self.create_text(px, py - 12, text=txt, fill=opts.get('fill', BAD), font=('Segoe UI', 8, 'bold'), tags=(key,)))
        elif kind == 'zones':
            self.delete(key)
            self.items[key] = []
            H = self.winfo_height()
            for (lo, hi, col, lab) in x:
                r = self.create_rectangle(float(self.X(lo)), self.mt, float(self.X(hi)), H - self.mb, fill=col, stipple='gray12', outline='', tags=(key,))
                t = self.create_text(float(self.X(math.sqrt(lo * hi))), self.mt + 8, text=lab, fill=col, font=('Segoe UI', 8), tags=(key,))
                self.items[key] += [r, t]
                self.tag_lower(r)

    def line(self, key, x, y, **opts):
        opts.setdefault('fill', TRACE)
        opts.setdefault('width', 1.5)
        self.data[key] = ('line', x, y, opts)
        self._draw(key, 'line', x, y, opts)

    def bars(self, key, lo, hi, y, **opts):
        opts.setdefault('fill', '#2c7a7b')
        opts.setdefault('outline', '')
        self.data[key] = ('bars', (lo, hi), y, opts)
        self._draw(key, 'bars', (lo, hi), y, opts)

    def marks(self, key, x, y, labels, fill=BAD):
        opts = {'labels': labels, 'fill': fill}
        self.data[key] = ('marks', x, y, opts)
        self._draw(key, 'marks', x, y, opts)

    def zones(self, key, zl):
        self.data[key] = ('zones', zl, None, {})
        self._draw(key, 'zones', zl, None, {})

    def clear(self, key):
        self.data.pop(key, None)
        self.delete(key)
        self.items.pop(key, None)


# ---------------------------------------------------------------- band helpers
def make_bands(frac, fmin=20, fmax=20000):
    """Base-10 fractional-octave bands (IEC 61260 centres)."""
    G = 10 ** 0.3
    bands = []
    k_lo = math.ceil(frac * math.log(fmin / 1000, G))
    k_hi = math.floor(frac * math.log(fmax / 1000, G))
    for k in range(k_lo, k_hi + 1):
        fc = 1000 * G ** (k / frac)
        bands.append((fc, fc * G ** (-0.5 / frac), fc * G ** (0.5 / frac)))
    return bands


def nominal(fc):
    iso = [20, 25, 31.5, 40, 50, 63, 80, 100, 125, 160, 200, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600, 2000,
           2500, 3150, 4000, 5000, 6300, 8000, 10000, 12500, 16000, 20000]
    return min(iso, key=lambda v: abs(math.log(v / fc)))


REGIONS = [
    dict(id='sub', lo=25, hi=50, label='Sub', over=12),
    dict(id='boom', lo=50, hi=125, label='Boom', over=10),
    dict(id='mud', lo=160, hi=400, label='Mud', over=4, under=-5),
    dict(id='box', lo=400, hi=800, label='Boxy', over=4),
    dict(id='honk', lo=800, hi=1600, label='Honk', over=4),
    dict(id='harsh', lo=2000, hi=5000, label='Harsh', over=3.5, under=-5),
    dict(id='sib', lo=5000, hi=10000, label='Sibilance', over=4),
    dict(id='air', lo=10000, hi=16000, label='Air', under=-12),
]
TIPS = {
    'sub+': ['Check the sub level and the sub-to-main crossover before EQ.', 'High-pass every channel that does not need sub: vocals, guitars, keys left hand, overheads.', 'If the stage rumbles, look at wedges and drum fills.'],
    'boom+': ['Look for a steady, narrow bump: that is a room mode. Cut it narrow on the system EQ.', 'Kick and bass fighting? Cut one where the other has its fundamental.', 'Too many channels without HPF add up here.'],
    'mud+': ['Cut on the sources first: kick 300–400 Hz, toms 300–500 Hz, acoustic guitar 200–300 Hz, keys.', 'Gate or duck idle mics; stage wash from open vocal mics piles up here.', 'If it persists, 2–3 dB wide cut on the mix bus.'],
    'mud-': ['The mix sounds thin. Check that HPFs are not set too high on vocals and guitars.', 'Bring up the body of guitars and keys around 200–300 Hz.'],
    'box+': ['Usually one source: sweep snare, kick and toms for a hollow ring.', 'Use narrow cuts on channels rather than a wide master cut.'],
    'honk+': ['Often horns, distorted guitars or a nasal vocal.', 'A small 1.2–1.6 kHz cut on guitars makes room for the vocal.'],
    'harsh+': ['Ears are most sensitive at 2–5 kHz; this tires the audience first.', 'Find the source: cymbals, guitar fizz, a pushed vocal. Dynamic EQ around 2.5–4 kHz on the vocal bus.', 'If every source sounds harsh, check the PA HF level and horn alignment.'],
    'harsh-': ['Vocals may be buried. Raise the vocal or cut competing guitars and keys at 2–4 kHz.'],
    'sib+': ['De-ess vocals around 5–8 kHz.', 'Hats and ride may be too loud at the front.'],
    'air-': ['Top end is falling off. Normal at a distance, but check the HF shelf on the system and whether the mic is off-axis.'],
}
TITLES_OVER = dict(sub='Sub-heavy low end', boom='Boomy low end', mud='Mud building in the low mids', box='Boxy midrange',
                   honk='Honky, nasal mids', harsh='Harsh upper mids', sib='Sibilant, brittle top')
TITLES_UNDER = dict(mud='Thin low mids', harsh='Lacking presence', air='Dull top end')


# ================================================================= the app
class App(tk.Tk):
    N = 32768

    def __init__(self):
        super().__init__()
        self.title(f'{APP} {VERSION}')
        self.geometry('1280x860')
        self.minsize(980, 640)
        self.configure(bg=BG)
        self.settings = load_settings()
        self.eng = Engine(48000)
        self.devices = []
        self.dev_name = 'Demo'
        self.cal = 120.0           # dB SPL at 0 dBFS RMS (assumed until calibrated)
        self.calibrated = False
        self.mic_corr = None       # (freqs, dB) from a mic calibration file
        self._style()
        self._build_top()
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill='both', expand=True, padx=8, pady=(0, 8))
        self.live = LiveTab(self.nb, self)
        self.room = RoomTab(self.nb, self)
        self.crowd = CrowdTab(self.nb, self)
        self.nb.add(self.live, text='  Live (RTA / SPL / advisor)  ')
        self.nb.add(self.room, text='  Room  ')
        self.nb.add(self.crowd, text='  Crowd mic delay  ')
        self.protocol('WM_DELETE_WINDOW', self.quit_app)
        self.set_source('Demo mix (band with mud + feedback)')
        self.after(100, self.tick)

    # ------------------------------------------------------------ style
    def _style(self):
        s = ttk.Style(self)
        s.theme_use('clam')
        f = ('Segoe UI', 10)
        s.configure('.', background=BG, foreground=TXT, fieldbackground=PANEL2, bordercolor=LINE, font=f,
                    lightcolor=PANEL, darkcolor=PANEL, troughcolor=PANEL2, selectbackground='#2c7a7b')
        s.configure('TFrame', background=BG)
        s.configure('Panel.TFrame', background=PANEL)
        s.configure('TLabel', background=BG, foreground=TXT)
        s.configure('Panel.TLabel', background=PANEL)
        s.configure('Dim.TLabel', background=PANEL, foreground=DIM, font=('Segoe UI', 9))
        s.configure('Big.TLabel', background=PANEL, foreground=TRACE, font=('Consolas', 30, 'bold'))
        s.configure('Mid.TLabel', background=PANEL, foreground=TXT, font=('Consolas', 13))
        s.configure('H.TLabel', background=PANEL, foreground=TXT, font=('Segoe UI', 11, 'bold'))
        s.configure('TButton', background=PANEL2, foreground=TXT, padding=(10, 4))
        s.map('TButton', background=[('active', '#2a3646')])
        s.configure('Accent.TButton', background='#2c7a7b', foreground='white')
        s.map('Accent.TButton', background=[('active', '#319795')])
        s.configure('TNotebook', background=BG, borderwidth=0)
        s.configure('TNotebook.Tab', background=PANEL, foreground=DIM, padding=(10, 5))
        s.map('TNotebook.Tab', background=[('selected', PANEL2)], foreground=[('selected', TXT)])
        s.configure('TCombobox', fieldbackground=PANEL2, background=PANEL2, foreground=TXT, arrowcolor=TXT)
        s.map('TCombobox', fieldbackground=[('readonly', PANEL2)], foreground=[('readonly', TXT)],
              selectbackground=[('readonly', PANEL2)], selectforeground=[('readonly', TXT)], background=[('active', '#2a3646')])
        self.option_add('*TCombobox*Listbox.background', PANEL2)
        self.option_add('*TCombobox*Listbox.foreground', TXT)
        s.configure('TRadiobutton', background=PANEL, foreground=TXT)
        s.configure('TCheckbutton', background=PANEL, foreground=TXT)
        s.map('TRadiobutton', background=[('active', PANEL)])
        s.map('TCheckbutton', background=[('active', PANEL)])
        s.configure('TLabelframe', background=PANEL, bordercolor=LINE)
        s.configure('TLabelframe.Label', background=PANEL, foreground=DIM)
        s.configure('Treeview', background=PANEL2, fieldbackground=PANEL2, foreground=TXT, rowheight=22)
        s.configure('Treeview.Heading', background=PANEL, foreground=DIM)
        s.configure('TEntry', fieldbackground=PANEL2, foreground=TXT, insertcolor=TXT)
        s.configure('TSpinbox', fieldbackground=PANEL2, foreground=TXT, arrowcolor=TXT)

    # ------------------------------------------------------------ top bar
    SOURCES = ['Demo mix (band with mud + feedback)', 'Pink noise', 'WAV file…', 'Simulated crowd mic (2 ch)', 'Microphone / interface']

    def _build_top(self):
        top = ttk.Frame(self, style='Panel.TFrame', padding=(10, 6))
        top.pack(fill='x', padx=8, pady=8)
        ttk.Label(top, text='FOH Analyzer', style='H.TLabel').pack(side='left', padx=(0, 14))
        ttk.Label(top, text='Source', style='Dim.TLabel').pack(side='left')
        self.src_var = tk.StringVar()
        cb = ttk.Combobox(top, textvariable=self.src_var, values=self.SOURCES, state='readonly', width=24)
        cb.pack(side='left', padx=6)
        cb.bind('<<ComboboxSelected>>', lambda e: self.set_source(self.src_var.get()))
        ttk.Label(top, text='Input device', style='Dim.TLabel').pack(side='left', padx=(10, 0))
        self.dev_var = tk.StringVar()
        self.dev_cb = ttk.Combobox(top, textvariable=self.dev_var, state='readonly', width=22)
        self.dev_cb.pack(side='left', padx=6)
        self.dev_cb.bind('<<ComboboxSelected>>', lambda e: self.set_source('Microphone / interface'))
        ttk.Button(top, text='↻', width=3, command=self.refresh_devices).pack(side='left')
        self.run_btn = ttk.Button(top, text='Pause', command=self.toggle_run)
        self.run_btn.pack(side='left', padx=6)
        ttk.Button(top, text='Calibrate mic…', style='Accent.TButton', command=lambda: CalDialog(self)).pack(side='left', padx=6)
        self.status = ttk.Label(top, text='', style='Dim.TLabel')
        self.status.pack(side='left', padx=10)
        self.meter = tk.Canvas(top, width=150, height=22, bg=PANEL2, highlightthickness=0)
        self.meter.pack(side='right')
        ttk.Label(top, text='In', style='Dim.TLabel').pack(side='right', padx=4)
        self.refresh_devices()

    def refresh_devices(self):
        self.devices = []
        if sd is not None:
            try:
                for i, d in enumerate(sd.query_devices()):
                    if d['max_input_channels'] > 0:
                        api = sd.query_hostapis(d['hostapi'])['name']
                        self.devices.append((i, f"{d['name']} ({api}, {d['max_input_channels']} in)"))
            except Exception:
                pass
        vals = [n for _, n in self.devices] or ['(no audio input: ' + (SD_ERR or 'none found')[:40] + ')']
        self.dev_cb['values'] = vals
        if not self.dev_var.get() or self.dev_var.get() not in vals:
            self.dev_var.set(vals[0])

    def set_source(self, name):
        self.src_var.set(name)
        try:
            if name.startswith('Demo'):
                self.eng.fs = 48000
                self.eng.start_loop(np.stack([make_demo(48000)] * 2, 1))
                self.dev_name = 'Demo'
            elif name.startswith('Pink'):
                self.eng.fs = 48000
                self.eng.start_loop(np.stack([make_pink_loop(48000)] * 2, 1))
                self.dev_name = 'Demo'
            elif name.startswith('WAV'):
                p = filedialog.askopenfilename(title='Open a WAV file', filetypes=[('WAV audio', '*.wav'), ('All files', '*.*')])
                if not p:
                    return
                x, wfs = read_wav(p)
                if x.shape[1] == 1:
                    x = np.repeat(x, 2, 1)
                self.eng.fs = 48000
                self.eng.start_loop(resample(x[:, :2], wfs, 48000))
                self.dev_name = 'Demo'
                self.src_var.set('WAV file…')
                self.status.config(text=os.path.basename(p))
            elif name.startswith('Simulated'):
                self.eng.fs = 48000
                band = make_demo(48000)
                rng = np.random.default_rng(11)
                crowd = -0.7 * frac_delay(band, 0.0382 * 48000) + 0.05 * pink(len(band), 48000, rng)
                self.eng.start_loop(np.stack([band, crowd.astype(np.float32)], 1))
                self.dev_name = 'Demo'
            else:
                if not self.devices:
                    messagebox.showwarning(APP, 'No audio input found.\n\n' + (SD_ERR or '') +
                                           '\n\nInstall the sounddevice package (the launcher does this) and check that Windows lets apps use the microphone.')
                    return
                vals = [n for _, n in self.devices]
                i = vals.index(self.dev_var.get()) if self.dev_var.get() in vals else 0
                dev = self.devices[i][0]
                ch = self.eng.start_input(dev, 2)
                self.dev_name = self.devices[i][1].split(' (')[0]
                self.status.config(text=f'{ch} ch @ {self.eng.fs} Hz')
        except Exception as e:
            messagebox.showerror(APP, f'Could not start the source:\n{e}')
            return
        if not name.startswith(('WAV', 'Micro')):
            self.status.config(text='test signal')
        self.load_cal()
        self.run_btn.config(text='Pause')
        for t in (self.live, self.crowd):
            t.reset()

    def toggle_run(self):
        if self.eng.stream is not None:
            if self.eng.running:
                self.eng.stream.stop()
            else:
                self.eng.stream.start()
        self.eng.running = not self.eng.running
        if self.eng.loop is not None and self.eng.running:
            self.eng.last = time.perf_counter()
        self.run_btn.config(text='Pause' if self.eng.running else 'Run')

    # ------------------------------------------------------------ calibration
    def load_cal(self):
        c = self.settings.get('cal', {}).get(self.dev_name)
        if c:
            self.cal = c.get('offset', 120.0)
            self.calibrated = c.get('calibrated', False)
            self.mic_corr = (np.array(c['corr_f']), np.array(c['corr_db'])) if c.get('corr_f') else None
        else:
            self.cal, self.calibrated, self.mic_corr = 120.0, False, None
        self.live.cal_changed()

    def store_cal(self):
        c = self.settings.setdefault('cal', {})
        d = {'offset': self.cal, 'calibrated': self.calibrated}
        if self.mic_corr is not None:
            d['corr_f'] = self.mic_corr[0].tolist()
            d['corr_db'] = self.mic_corr[1].tolist()
        c[self.dev_name] = d
        save_settings(self.settings)
        self.live.cal_changed()

    def corr_at(self, f):
        """Mic correction in dB to ADD to measured levels (cal files list the mic's deviation, so we subtract it)."""
        if self.mic_corr is None:
            return np.zeros_like(np.asarray(f, float))
        cf, cd = self.mic_corr
        return -np.interp(np.log10(np.maximum(f, 1)), np.log10(cf), cd)

    # ------------------------------------------------------------ main loop
    def tick(self):
        try:
            self.eng.pump()
            x = self.eng.latest(4096)[0]
            pk = float(np.max(np.abs(x))) if len(x) else 0
            rms = float(np.sqrt(np.mean(x ** 2)))
            self.meter.delete('all')
            for v, col in ((rms, TRACE), (pk, '#2c7a7b')):
                d = 20 * math.log10(max(v, 1e-6))
                w = max(0, min(150, (d + 60) / 60 * 150))
                self.meter.create_rectangle(0, 4 if col == TRACE else 15, w, 11 if col == TRACE else 19, fill=col, outline='')
            if time.time() - self.eng.clip < 2:
                self.meter.create_text(146, 11, text='CLIP', fill=BAD, anchor='e', font=('Segoe UI', 8, 'bold'))
            if self.eng.running:
                cur = self.nb.index('current')
                self.live.update_audio(cur == 0)
                if cur == 2:
                    self.crowd.update_audio()
        except Exception as e:  # keep the UI alive
            print('tick error:', repr(e), file=sys.stderr)
        self.after(80, self.tick)

    def quit_app(self):
        self.eng.stop()
        self.destroy()


# ================================================================= live tab
class LiveTab(ttk.Frame):
    def __init__(self, nb, app):
        super().__init__(nb)
        self.app = app
        N = App.N
        self.win = np.blackman(N).astype(np.float32)
        self.norm = 2.0 / (N * np.sum(self.win ** 2))
        self.f = np.fft.rfftfreq(N, 1 / 48000)
        self.frac = tk.StringVar(value='1/3')
        self.avg = tk.StringVar(value='Medium')
        self.show_fft = tk.BooleanVar(value=True)
        self.show_peak = tk.BooleanVar(value=True)
        self.weight = tk.StringVar(value='A')
        self.tw = tk.StringVar(value='Fast')
        self.hold = tk.StringVar(value='15 s')
        self.adv_on = tk.BooleanVar(value=True)
        self._layout()
        self.reset()

    def _layout(self):
        left = ttk.Frame(self)
        left.pack(side='left', fill='both', expand=True)
        ctl = ttk.Frame(left, style='Panel.TFrame', padding=6)
        ctl.pack(fill='x')

        def combo(lbl, var, vals, w=8, cmd=None):
            ttk.Label(ctl, text=lbl, style='Dim.TLabel').pack(side='left', padx=(8, 2))
            c = ttk.Combobox(ctl, textvariable=var, values=vals, state='readonly', width=w)
            c.pack(side='left')
            if cmd:
                c.bind('<<ComboboxSelected>>', lambda e: cmd())
        combo('Bands', self.frac, ['1/1', '1/3', '1/6', '1/12', '1/24'], 5, self.make_bands)
        combo('Average', self.avg, ['None', 'Fast', 'Medium', 'Slow', 'Very slow'], 9)
        ttk.Checkbutton(ctl, text='FFT line', variable=self.show_fft, command=lambda: self.plot.clear('fft')).pack(side='left', padx=8)
        ttk.Checkbutton(ctl, text='Peak hold', variable=self.show_peak, command=lambda: self.plot.clear('peak')).pack(side='left')
        ttk.Button(ctl, text='Reset peak', command=self.reset_peak).pack(side='left', padx=6)
        self.freeze = tk.BooleanVar(value=False)
        ttk.Checkbutton(ctl, text='Freeze', variable=self.freeze).pack(side='left', padx=6)
        self.readout = ttk.Label(ctl, text='', style='Dim.TLabel')
        self.readout.pack(side='right', padx=6)
        self.plot = Plot(left, 20, 120, ylabel='dB SPL', height=380)
        self.plot.pack(fill='both', expand=True, pady=(6, 0))
        self.plot.bind('<Motion>', self.on_motion)
        # advisor
        self.adv = ttk.Frame(left, style='Panel.TFrame', padding=8)
        self.adv.pack(fill='x', pady=(6, 0))
        head = ttk.Frame(self.adv, style='Panel.TFrame')
        head.pack(fill='x')
        ttk.Label(head, text='Mix advisor', style='H.TLabel').pack(side='left')
        self.adv_sum = ttk.Label(head, text='', style='Dim.TLabel')
        self.adv_sum.pack(side='left', padx=10)
        self.adv_btn = ttk.Button(head, text='Hide', command=self.toggle_adv)
        self.adv_btn.pack(side='right')
        ttk.Combobox(head, textvariable=self.hold, values=['5 s', '15 s', '30 s', '60 s'], state='readonly', width=5).pack(side='right', padx=4)
        ttk.Label(head, text='Keep tips for', style='Dim.TLabel').pack(side='right')
        self.adv_txt = tk.Text(self.adv, height=10, bg=PANEL, fg=TXT, relief='flat', wrap='word', font=('Segoe UI', 10), highlightthickness=0)
        self.adv_txt.pack(fill='x', pady=(6, 0))
        for tag, col in (('warn', WARN), ('bad', BAD), ('info', AVG), ('good', GOOD)):
            self.adv_txt.tag_configure(tag, foreground=col, font=('Segoe UI', 10, 'bold'))
        self.adv_txt.tag_configure('dim', foreground=DIM)
        # SPL panel
        right = ttk.Frame(self, style='Panel.TFrame', padding=12, width=260)
        right.pack(side='right', fill='y', padx=(8, 0))
        ttk.Label(right, text='SPL meter', style='H.TLabel').pack(anchor='w')
        r = ttk.Frame(right, style='Panel.TFrame')
        r.pack(fill='x', pady=4)
        for w in 'AC Z'.split() if False else ['A', 'C', 'Z']:
            ttk.Radiobutton(r, text=w, value=w, variable=self.weight).pack(side='left', padx=4)
        r2 = ttk.Frame(right, style='Panel.TFrame')
        r2.pack(fill='x')
        for w in ['Fast', 'Slow', 'Impulse']:
            ttk.Radiobutton(r2, text=w, value=w, variable=self.tw).pack(side='left', padx=4)
        self.spl_lbl = ttk.Label(right, text='--.-', style='Big.TLabel')
        self.spl_lbl.pack(anchor='w', pady=(10, 0))
        self.spl_unit = ttk.Label(right, text='dB(A) Fast', style='Dim.TLabel')
        self.spl_unit.pack(anchor='w')
        self.spl_more = ttk.Label(right, text='', style='Mid.TLabel', justify='left')
        self.spl_more.pack(anchor='w', pady=10)
        ttk.Button(right, text='Reset Leq / Max', command=self.reset_spl).pack(anchor='w')
        self.cal_lbl = ttk.Label(right, text='', style='Dim.TLabel', wraplength=230, justify='left')
        self.cal_lbl.pack(anchor='w', pady=(14, 0))
        self.hist = Plot(right, 40, 120, xmin=-60, xmax=0, logx=False, ylabel='dB', height=150, xlabel='s', width=240)
        self.hist.pack(fill='x', pady=(10, 0))
        self.make_bands()

    def make_bands(self):
        frac = int(self.frac.get().split('/')[1])
        self.bands = make_bands(frac)
        self.bfc = np.array([b[0] for b in self.bands])
        self.blo = np.array([b[1] for b in self.bands])
        self.bhi = np.array([b[2] for b in self.bands])
        self.plot.clear('bars')
        self.plot.clear('peak')
        self.band_avg = None
        self.band_peak = None
        self.edges_for = None

    def reset(self):
        self.band_avg = None
        self.band_peak = None
        self.lt = None
        self.lt_t = 0.0
        self.last_total = self.app.eng.total
        self.reset_spl()
        self.adv_seen = {}
        self.rings = {}
        self.edges_for = None

    def reset_peak(self):
        self.band_peak = None
        self.plot.clear('peak')

    def reset_spl(self):
        self.ms = {'A': 0.0, 'C': 0.0, 'Z': 0.0}
        self.imp = {'A': 0.0, 'C': 0.0, 'Z': 0.0}
        self.slow = {'A': 0.0, 'C': 0.0, 'Z': 0.0}
        self.leq_e = {'A': 0.0, 'C': 0.0, 'Z': 0.0}
        self.leq_t = 0.0
        self.lmax = -999.0
        self.lpk = -999.0
        self.spl_hist = []

    def cal_changed(self):
        a = self.app
        txt = f'Calibration ({a.dev_name}): offset {a.cal:.1f} dB'
        txt += '' if a.calibrated else '\nNot calibrated: SPL uses an assumed offset. Use Calibrate mic… for real numbers.'
        if a.mic_corr is not None:
            txt += '\nMic correction file loaded.'
        self.cal_lbl.config(text=txt, foreground=DIM if a.calibrated else WARN)

    def toggle_adv(self):
        on = not self.adv_on.get()
        self.adv_on.set(on)
        self.adv_btn.config(text='Hide' if on else 'Show')
        if on:
            self.adv_txt.pack(fill='x', pady=(6, 0))
        else:
            self.adv_txt.pack_forget()

    def on_motion(self, e):
        p = self.plot
        w = max(10, p.winfo_width() - p.ml - p.mr)
        r = (e.x - p.ml) / w
        if not 0 <= r <= 1:
            return
        f = 10 ** (math.log10(20) + r * 3)
        h = max(10, p.winfo_height() - p.mt - p.mb)
        v = p.ymax - (e.y - p.mt) / h * (p.ymax - p.ymin)
        lv = ''
        if self.band_avg is not None:
            i = int(np.argmin(np.abs(np.log(self.bfc / f))))
            lv = f'  band {ftext(self.bfc[i])}: {self.band_db[i]:.1f} dB'
        self.readout.config(text=f'{ftext(f)}  {v:.1f} dB{lv}')

    # ------------------------------------------------------------ analysis
    def bin_edges(self, fs):
        if self.edges_for != (fs, len(self.bands)):
            df = fs / App.N
            self.lo_i = np.clip(np.ceil(self.blo / df).astype(int), 1, len(self.f) - 1)
            self.hi_i = np.clip(np.floor(self.bhi / df).astype(int), 1, len(self.f) - 1)
            self.hi_i = np.maximum(self.hi_i, self.lo_i)
            self.edges_for = (fs, len(self.bands))

    def update_audio(self, visible):
        app, eng = self.app, self.app.eng
        fs = eng.fs
        if len(self.f) != App.N // 2 + 1 or self.f[1] != fs / App.N:
            self.f = np.fft.rfftfreq(App.N, 1 / fs)
            self.edges_for = None
        new = eng.total - self.last_total
        self.last_total = eng.total
        new = int(min(new, fs * 2))
        if new > 0:
            self.update_spl(eng.latest(new)[0], fs)
        if self.freeze.get():
            return
        x = eng.latest(App.N)[0]
        X = np.fft.rfft(x * self.win)
        P = (np.abs(X) ** 2) * self.norm
        P[0] = 0
        corr = app.corr_at(self.f)
        Pc = P * 10 ** (corr / 10) if app.mic_corr is not None else P
        self.bin_edges(fs)
        cs = np.concatenate([[0], np.cumsum(Pc)])
        bp = cs[self.hi_i + 1] - cs[self.lo_i]
        # narrow low bands may fall between bins: interpolate the bin density instead
        narrow = self.hi_i <= self.lo_i
        if narrow.any():
            dens = np.interp(self.bfc[narrow], self.f, Pc)
            bp[narrow] = dens * (self.bhi[narrow] - self.blo[narrow]) / (fs / App.N)
        dt = 0.08
        tau = {'None': 0, 'Fast': 0.25, 'Medium': 1.0, 'Slow': 3.0, 'Very slow': 8.0}[self.avg.get()]
        a = math.exp(-dt / tau) if tau else 0
        self.band_avg = bp if self.band_avg is None or len(self.band_avg) != len(bp) else a * self.band_avg + (1 - a) * bp
        self.band_peak = self.band_avg.copy() if self.band_peak is None or len(self.band_peak) != len(bp) else np.maximum(self.band_peak, self.band_avg)
        cal = app.cal
        self.band_db = db(self.band_avg) + cal
        # long-term 1/3-octave average for the advisor (3 s)
        if self.lt is None or len(self.lt) != len(self.adv_bands_lo()):
            self.lt = None
        tb = self.third_bands(Pc, fs)
        b = math.exp(-dt / 3.0)
        self.lt = tb if self.lt is None else b * self.lt + (1 - b) * tb
        self.lt_t += dt
        if not visible:
            return
        p = self.plot
        p.bars('bars', self.blo, self.bhi, self.band_db)
        if self.show_peak.get():
            xs = np.repeat(np.stack([self.blo, self.bhi], 1).ravel(), 1)
            ys = np.repeat(db(self.band_peak) + cal, 2)
            p.line('peak', xs, ys, fill=PEAK, width=1.5)
        if self.show_fft.get():
            fl = np.geomspace(20, min(20000, fs / 2 - 1), 900)
            # log-spaced resampling of the per-bin level, with gentle 1/48-octave smoothing
            sm = np.convolve(Pc, np.ones(3) / 3, 'same')
            yd = db(np.interp(fl, self.f, sm)) + cal + 10 * math.log10(1)  # density per bin
            p.line('fft', fl, yd, fill=AVG, width=1)
        self.advise(P, fs)

    # third-octave helpers for the advisor
    def adv_bands_lo(self):
        if not hasattr(self, '_tb'):
            self._tb = make_bands(3, 25, 16000)
        return self._tb

    def third_bands(self, Pc, fs):
        tb = self.adv_bands_lo()
        df = fs / App.N
        cs = np.concatenate([[0], np.cumsum(Pc)])
        lo = np.clip(np.ceil(np.array([b[1] for b in tb]) / df).astype(int), 1, len(Pc) - 1)
        hi = np.clip(np.floor(np.array([b[2] for b in tb]) / df).astype(int), 1, len(Pc) - 1)
        return cs[np.maximum(hi, lo) + 1] - cs[lo]

    def update_spl(self, x, fs):
        n = len(x)
        if n < 16:
            return
        cal = self.app.cal
        X = np.fft.rfft(x)
        f = np.fft.rfftfreq(n, 1 / fs)
        P = np.abs(X) ** 2
        P[1:-1] *= 2
        P /= n * n
        if self.app.mic_corr is not None:
            P *= 10 ** (self.app.corr_at(f) / 10)
        dt = n / fs
        for w in ('A', 'C', 'Z'):
            ms = float(np.sum(P * 10 ** (weight_db(f, w) / 10))) if w != 'Z' else float(np.sum(P))
            for d, tau in ((self.ms, 0.125), (self.slow, 1.0)):
                k = math.exp(-dt / tau)
                d[w] = d[w] * k + ms * (1 - k)
            k = math.exp(-dt / (0.035 if ms > self.imp[w] else 1.5))
            self.imp[w] = self.imp[w] * k + ms * (1 - k)
            self.leq_e[w] += ms * dt
        self.leq_t += dt
        self.lpk = max(self.lpk, 20 * math.log10(max(float(np.max(np.abs(x))), 1e-9)) + cal)
        w, tw = self.weight.get(), self.tw.get()
        src = {'Fast': self.ms, 'Slow': self.slow, 'Impulse': self.imp}[tw]
        L = 10 * math.log10(max(src[w], 1e-20)) + cal
        if self.leq_t > 0.5:
            self.lmax = max(self.lmax, L)
        leq = 10 * math.log10(max(self.leq_e[w] / max(self.leq_t, 1e-9), 1e-20)) + cal
        self.spl_now = L
        self.la = 10 * math.log10(max(self.ms['A'], 1e-20)) + cal
        self.lc = 10 * math.log10(max(self.ms['C'], 1e-20)) + cal
        self.spl_lbl.config(text=f'{L:5.1f}')
        self.spl_unit.config(text=f'dB({w}) {tw}' + ('' if self.app.calibrated else '  (uncalibrated)'))
        mins = self.leq_t / 60
        self.spl_more.config(text=f'Leq {leq:5.1f}  ({mins:.1f} min)\nMax {self.lmax:5.1f}\nPeak {self.lpk:5.1f} dB(Z)\n'
                                  f'LA {self.la:5.1f}  LC {self.lc:5.1f}')
        now = time.time()
        self.spl_hist.append((now, L))
        self.spl_hist = [(t, v) for t, v in self.spl_hist if now - t <= 60]
        if len(self.spl_hist) > 2:
            self.hist.line('h', [t - now for t, _ in self.spl_hist], [v for _, v in self.spl_hist], fill=TRACE, width=1.5)

    # ------------------------------------------------------------ advisor
    def advise(self, P, fs):
        now = time.time()
        found = []  # (key, sev, title, tag, text, tips)
        cal = self.app.cal
        f = self.f
        # --- feedback / ringing detection on the fine FFT
        Pd = db(P)
        band = (f > 100) & (f < 12000)
        idx = np.where(band)[0]
        if len(idx):
            from_ = idx[0]
            seg = Pd[idx]
            # local median over about 1/3 octave, computed on a coarse grid for speed
            grid = np.geomspace(100, 12000, 120)
            medg = []
            for g in grid:
                m = (f >= g / 1.12) & (f <= g * 1.12)
                medg.append(np.median(Pd[m]) if m.any() else -200)
            med = np.interp(f[idx], grid, medg)
            excess = seg - med
            cand = np.where((excess > 18) & (seg > np.max(seg) - 30))[0]
            peaks = []
            for c in cand:
                i = c + from_
                if Pd[i] >= Pd[i - 1] and Pd[i] >= Pd[i + 1]:
                    peaks.append((float(excess[c]), i))
            peaks.sort(reverse=True)
            seen_now = set()
            for ex, i in peaks[:4]:
                a, b, c = Pd[i - 1], Pd[i], Pd[i + 1]
                d = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0
                fr = (i + d) * fs / App.N
                key = round(math.log2(fr) * 24)
                seen_now.add(key)
                r = self.rings.get(key, {'n': 0, 'f': fr, 'ex': ex})
                r['n'] += 1
                r['f'] = fr
                r['ex'] = ex
                r['t'] = now
                self.rings[key] = r
            for k in list(self.rings):
                if k not in seen_now:
                    self.rings[k]['n'] = max(0, self.rings[k]['n'] - 2)
                    if self.rings[k]['n'] == 0:
                        del self.rings[k]
            for k, r in self.rings.items():
                if r['n'] >= 8:
                    sev = 'bad' if r['n'] >= 20 else 'warn'
                    found.append((f'fb{k}', sev, 'Possible feedback or ringing', f'{ftext(r["f"])} · +{r["ex"]:.0f} dB',
                                  f'A narrow, steady peak at {ftext(r["f"])} sits {r["ex"]:.0f} dB above its neighbours. '
                                  f'On a 31-band GEQ that is the {ftext(nominal(r["f"]))} slider.',
                                  ['Find which mic: pull wedge or channel faders one by one.',
                                   f'Notch it narrow (Q 8–15, −3 to −6 dB) at {r["f"]:.0f} Hz on that wedge or channel.',
                                   'Reduce gain before EQ: closer mic placement beats notches.']))
            rf = [(r['f'], float(Pd[int(round(r['f'] * App.N / fs))]) + cal) for r in self.rings.values() if r['n'] >= 8]
            if rf:
                self.plot.marks('rings', [a for a, _ in rf], [b + 3 for _, b in rf], [ftext(a) for a, _ in rf])
            else:
                self.plot.clear('rings')
        # --- level checks
        if now - self.app.eng.clip < 2:
            found.append(('clip', 'bad', 'Input clipping', '0 dBFS', 'The analyzer input is clipping, so readings are wrong.',
                          ['Turn the interface input gain down until the CLIP marker stays off.']))
        la = getattr(self, 'la', 0)
        if self.app.calibrated and la > 100:
            found.append(('loud', 'warn', 'Very loud', f'{la:.0f} dB(A)', 'Short-term A level is above 100 dB(A).',
                          ['Check your venue limit and the Leq.', 'Hearing damage risk rises fast above 100 dB(A).']))
        x3 = self.app.eng.latest(int(3 * self.app.eng.fs))[0]
        r3 = float(np.sqrt(np.mean(x3 ** 2)))
        self.crest = 20 * math.log10(max(float(np.max(np.abs(x3))), 1e-9) / max(r3, 1e-9))
        if self.crest < 6 and r3 > 0.01 and self.lt_t > 3:
            found.append(('crest', 'info', 'Very little dynamics', f'crest {self.crest:.1f} dB',
                          'Peak-to-RMS is low: the mix may be over-compressed or limited.',
                          ['Check bus compression and the system limiter gain reduction.']))
        lc_la = getattr(self, 'lc', 0) - la
        if lc_la > 22 and la > 0:
            found.append(('ca', 'warn', 'Low end dominating the level', f'LC − LA {lc_la:.1f} dB',
                          'C-weighted level is far above A-weighted, so most energy sits below 100 Hz.', TIPS['sub+']))
        # --- tonal balance from the 3 s average
        zones = []
        lt = self.lt
        tb = self.adv_bands_lo()
        if lt is not None and self.lt_t >= 3 and 10 * math.log10(max(np.sum(lt), 1e-20)) > -62:
            fc = np.array([b[0] for b in tb])
            ringed = np.zeros(len(tb), bool)
            for r in self.rings.values():
                ringed |= (np.array([b[1] for b in tb]) <= r['f']) & (np.array([b[2] for b in tb]) >= r['f'])
            lv = np.where((lt > 0) & ~ringed, db(lt), -np.inf)
            xs = np.log2(fc / 1000)
            ok = np.where((fc >= 100) & (fc <= 10000) & np.isfinite(lv))[0]
            sl = [(lv[ok[j]] - lv[ok[i]]) / (xs[ok[j]] - xs[ok[i]]) for i in range(len(ok)) for j in range(i + 3, len(ok))]
            m = float(np.clip(np.median(sl) if sl else -1, -3.5, 0.5))
            c = float(np.median(lv[ok] - m * xs[ok])) if len(ok) else 0
            dev = lv - (m * xs + c)
            for R in REGIONS:
                ii = [i for i in range(len(tb)) if R['lo'] <= fc[i] <= R['hi'] and np.isfinite(dev[i])]
                if not ii:
                    continue
                mean = float(np.mean(dev[ii]))
                d_over = max([mean] + [(dev[ii[k]] + dev[ii[k + 1]]) / 2 for k in range(len(ii) - 1)])
                fpk = fc[max(ii, key=lambda i: dev[i])]
                hi = f"{R['hi'] // 1000}k" if R['hi'] >= 1000 else str(R['hi'])
                if 'over' in R and d_over > R['over']:
                    sev = 'warn' if d_over > R['over'] + 4 else 'info'
                    cut = int(np.clip(round(d_over - 1), 2, 6))
                    found.append((R['id'] + '+', sev, TITLES_OVER[R['id']], f'+{d_over:.1f} dB · {ftext(fpk)}',
                                  f"{R['lo']}–{hi} Hz peaks {d_over:.1f} dB above the mix's own trend line, highest near {ftext(fpk)}. "
                                  f"On a 31-band GEQ that is the {ftext(nominal(fpk))} slider; try −{cut} dB there only after fixing sources.",
                                  TIPS[R['id'] + '+']))
                    zones.append((R['lo'], R['hi'], WARN if sev == 'warn' else AVG, R['label']))
                elif 'under' in R and mean < R['under']:
                    found.append((R['id'] + '-', 'info', TITLES_UNDER[R['id']], f'{mean:.1f} dB',
                                  f"{R['lo']}–{hi} Hz is {-mean:.1f} dB below the trend line.", TIPS[R['id'] + '-']))
                    zones.append((R['lo'], R['hi'], AVG, R['label']))
        elif self.lt_t < 3:
            found.append(('settle', 'info', 'Listening…', '', 'Building a 3-second average before judging the balance.', []))
        self.plot.zones('zones', zones)
        # --- tips linger for the chosen hold time
        hold = int(self.hold.get().split()[0])
        for item in found:
            self.adv_seen[item[0]] = (now, item)
        show = [(t, it) for k, (t, it) in self.adv_seen.items() if now - t <= hold]
        self.adv_seen = {k: v for k, v in self.adv_seen.items() if now - v[0] <= hold}
        order = {'bad': 0, 'warn': 1, 'info': 2}
        show.sort(key=lambda v: (order.get(v[1][1], 3), v[1][0]))
        nwarn = sum(1 for _, it in show if it[1] in ('bad', 'warn'))
        self.adv_sum.config(text=('No problems spotted' if not show else
                                  f'{nwarn} warning(s), {len(show) - nwarn} note(s)' if show[0][1][0] != 'settle' or len(show) > 1 else 'Listening…'),
                            foreground=BAD if nwarn else DIM)
        if not self.adv_on.get():
            return
        sig = [(it[0], it[3], round(now - t)) for t, it in show]
        if sig == getattr(self, '_last_sig', None):
            return
        self._last_sig = sig
        tx = self.adv_txt
        y = tx.yview()[0]
        tx.config(state='normal')
        tx.delete('1.0', 'end')
        if not show:
            tx.insert('end', 'No problems spotted. ', 'good')
            tx.insert('end', 'Tips appear here when the mix shows build-ups, ringing, clipping or a dull top end.', 'dim')
        for t, (k, sev, title, tag, text, tips) in show:
            tx.insert('end', '● ' + title, sev)
            if tag:
                tx.insert('end', f'   {tag}', 'dim')
            if now - t > 1.5:
                tx.insert('end', f'   (cleared {now - t:.0f} s ago)', 'dim')
            tx.insert('end', '\n' + text + '\n')
            for tip in tips:
                tx.insert('end', '   – ' + tip + '\n', 'dim')
        tx.config(state='disabled')
        tx.yview_moveto(y)


# ================================================================= calibration dialog
class CalDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title('Calibrate mic')
        self.configure(bg=PANEL)
        self.geometry('560x500')
        self.transient(app)
        nb = ttk.Notebook(self)
        nb.pack(fill='both', expand=True, padx=8, pady=8)
        ttk.Label(self, text=f'Device: {app.dev_name}. Calibrations are saved per device in {SETTINGS}.',
                  style='Dim.TLabel', wraplength=520).pack(padx=8, pady=(0, 8), anchor='w')

        # --- acoustic calibrator
        f1 = ttk.Frame(nb, style='Panel.TFrame', padding=12)
        nb.add(f1, text='Calibrator')
        ttk.Label(f1, text='Put the acoustic calibrator on the measurement mic, switch it on, then press Measure. '
                           'Keep it steady for 3 seconds.', style='Panel.TLabel', wraplength=500, justify='left').pack(anchor='w')
        r = ttk.Frame(f1, style='Panel.TFrame')
        r.pack(anchor='w', pady=10)
        self.lvl = tk.StringVar(value='94')
        self.cfreq = tk.StringVar(value='1000')
        for v in ('94', '104', '114'):
            ttk.Radiobutton(r, text=f'{v} dB', value=v, variable=self.lvl).pack(side='left', padx=4)
        ttk.Label(r, text='   at', style='Panel.TLabel').pack(side='left')
        for v in ('1000', '250'):
            ttk.Radiobutton(r, text=f'{v} Hz', value=v, variable=self.cfreq).pack(side='left', padx=4)
        ttk.Button(f1, text='Measure (3 s)', style='Accent.TButton', command=self.measure_cal).pack(anchor='w')
        self.vt = tk.BooleanVar(value=False)
        ttk.Checkbutton(f1, text='No calibrator? Play a virtual calibrator tone inside the program (tests the procedure only)',
                        variable=self.vt, command=self.virtual_tone).pack(anchor='w', pady=10)
        self.msg1 = ttk.Label(f1, text='', style='Panel.TLabel', wraplength=500, justify='left')
        self.msg1.pack(anchor='w', pady=6)

        # --- match a meter
        f2 = ttk.Frame(nb, style='Panel.TFrame', padding=12)
        nb.add(f2, text='Match a meter')
        ttk.Label(f2, text='Place a trusted SPL meter right next to the mic, play steady pink noise, and type the meter reading. '
                           'Use the same weighting on both.', style='Panel.TLabel', wraplength=500, justify='left').pack(anchor='w')
        r = ttk.Frame(f2, style='Panel.TFrame')
        r.pack(anchor='w', pady=10)
        self.meter_val = tk.StringVar(value='')
        self.meter_w = tk.StringVar(value='A')
        ttk.Entry(r, textvariable=self.meter_val, width=8).pack(side='left')
        ttk.Label(r, text=' dB ', style='Panel.TLabel').pack(side='left')
        for w in ('A', 'C', 'Z'):
            ttk.Radiobutton(r, text=w, value=w, variable=self.meter_w).pack(side='left', padx=3)
        ttk.Button(f2, text='Match (averages 3 s)', style='Accent.TButton', command=self.match_meter).pack(anchor='w')
        self.msg2 = ttk.Label(f2, text='', style='Panel.TLabel', wraplength=500)
        self.msg2.pack(anchor='w', pady=6)

        # --- manual
        f3 = ttk.Frame(nb, style='Panel.TFrame', padding=12)
        nb.add(f3, text='Manual offset')
        ttk.Label(f3, text='Offset = dB SPL that a full-scale (0 dBFS RMS) signal would read. Default 120.',
                  style='Panel.TLabel', wraplength=500).pack(anchor='w')
        self.man = tk.StringVar(value=f'{app.cal:.1f}')
        ttk.Entry(f3, textvariable=self.man, width=10).pack(anchor='w', pady=10)
        ttk.Button(f3, text='Apply', command=self.manual).pack(anchor='w')
        ttk.Button(f3, text='Reset to uncalibrated', command=self.reset).pack(anchor='w', pady=10)

        # --- mic file
        f4 = ttk.Frame(nb, style='Panel.TFrame', padding=12)
        nb.add(f4, text='Mic file')
        ttk.Label(f4, text='Load the frequency response file that came with your measurement mic (UMIK-1, Dayton, '
                           'Sonarworks and similar text files: one "frequency dB" pair per line). '
                           'The RTA, FFT and SPL are corrected with it.', style='Panel.TLabel', wraplength=500, justify='left').pack(anchor='w')
        ttk.Button(f4, text='Load mic file…', command=self.load_file).pack(anchor='w', pady=10)
        ttk.Button(f4, text='Remove mic file', command=self.remove_file).pack(anchor='w')
        self.msg4 = ttk.Label(f4, text='', style='Panel.TLabel', wraplength=500, justify='left')
        self.msg4.pack(anchor='w', pady=6)
        if app.mic_corr is not None:
            self.msg4.config(text=f'Loaded: {len(app.mic_corr[0])} points, {app.mic_corr[0][0]:.0f} Hz to {app.mic_corr[0][-1]:.0f} Hz.')
        self.protocol('WM_DELETE_WINDOW', self.close)

    def close(self):
        self.app.eng.tone = None
        self.destroy()

    def virtual_tone(self):
        if self.vt.get():
            # amplitude chosen so the tone reads the selected level with the default 120 dB offset (a stand-in mic)
            target = float(self.lvl.get())
            amp = math.sqrt(2) * 10 ** ((target - 120) / 20)
            self.app.eng.tone = (float(self.cfreq.get()), amp)
            self.msg1.config(text='Virtual calibrator on: a tone is mixed into the analyzer input. Press Measure to rehearse the steps.')
        else:
            self.app.eng.tone = None

    def avg_level(self, seconds, cb):
        """Collect the band level near the calibrator frequency (or broadband) for a few seconds."""
        app = self.app
        start = app.eng.total
        need = int(seconds * app.eng.fs)

        def poll():
            app.eng.pump()
            got = app.eng.total - start
            if got < need:
                self.after(100, poll)
                return
            x = app.eng.latest(min(need, app.eng.size - 1))[0]
            cb(x)
        poll()

    def measure_cal(self):
        f0 = float(self.cfreq.get())
        self.msg1.config(text='Measuring… keep the calibrator steady.')

        def done(x):
            fs = self.app.eng.fs
            X = np.fft.rfft(x * np.hanning(len(x)))
            f = np.fft.rfftfreq(len(x), 1 / fs)
            P = np.abs(X) ** 2 * 2 / (len(x) * np.sum(np.hanning(len(x)) ** 2))
            m = (f > f0 / 2 ** (1 / 6)) & (f < f0 * 2 ** (1 / 6))
            ms_band = float(np.sum(P[m]))
            ms_all = float(np.mean(x ** 2))
            if ms_band < 1e-12:
                self.msg1.config(text='No signal. Check the mic, interface gain and the input device.', foreground=BAD)
                return
            if ms_band < 0.5 * ms_all:
                self.msg1.config(text=f'Warning: less than half the energy is at {f0:.0f} Hz. Too much background noise or the wrong frequency?', foreground=WARN)
            corr = float(self.app.corr_at(np.array([f0]))[0])
            lvl_dbfs = 10 * math.log10(ms_band) + corr
            target = float(self.lvl.get())
            self.app.cal = target - lvl_dbfs
            self.app.calibrated = True
            self.app.store_cal()
            self.msg1.config(text=f'Done. The calibrator read {lvl_dbfs:.1f} dBFS, so the offset is now {self.app.cal:.1f} dB. Saved.', foreground=GOOD)
        self.avg_level(3, done)

    def match_meter(self):
        try:
            ref = float(self.meter_val.get().replace(',', '.'))
        except ValueError:
            self.msg2.config(text='Type the meter reading first, e.g. 85.0', foreground=WARN)
            return
        w = self.meter_w.get()
        self.msg2.config(text='Averaging…', foreground=TXT)

        def done(x):
            fs = self.app.eng.fs
            X = np.fft.rfft(x)
            f = np.fft.rfftfreq(len(x), 1 / fs)
            P = np.abs(X) ** 2 / len(x) ** 2
            P[1:-1] *= 2
            P *= 10 ** ((weight_db(f, w) + self.app.corr_at(f)) / 10)
            lv = 10 * math.log10(max(float(np.sum(P)), 1e-20))
            self.app.cal = ref - lv
            self.app.calibrated = True
            self.app.store_cal()
            self.msg2.config(text=f'Matched: offset {self.app.cal:.1f} dB. Saved.', foreground=GOOD)
        self.avg_level(3, done)

    def manual(self):
        try:
            self.app.cal = float(self.man.get().replace(',', '.'))
        except ValueError:
            return
        self.app.calibrated = True
        self.app.store_cal()

    def reset(self):
        self.app.cal, self.app.calibrated = 120.0, False
        self.man.set('120.0')
        self.app.store_cal()

    def load_file(self):
        p = filedialog.askopenfilename(parent=self, title='Mic calibration file', filetypes=[('Text', '*.txt *.cal *.frd'), ('All files', '*.*')])
        if not p:
            return
        try:
            fr, d = parse_mic_file(p)
        except Exception as e:
            messagebox.showerror(APP, str(e), parent=self)
            return
        self.app.mic_corr = (fr, d)
        self.app.store_cal()
        self.msg4.config(text=f'Loaded {os.path.basename(p)}: {len(fr)} points, {fr[0]:.0f} Hz to {fr[-1]:.0f} Hz.', foreground=GOOD)

    def remove_file(self):
        self.app.mic_corr = None
        self.app.store_cal()
        self.msg4.config(text='Mic file removed.', foreground=DIM)


def parse_mic_file(path):
    fr, d = [], []
    with open(path, 'r', encoding='utf-8', errors='ignore') as fh:
        for line in fh:
            s = line.strip().replace(',', ' ').replace(';', ' ').replace('\t', ' ')
            if not s or s[0] in '*#"\'' or s[0].isalpha():
                continue
            parts = s.split()
            try:
                a, b = float(parts[0]), float(parts[1])
            except (ValueError, IndexError):
                continue
            if a > 0:
                fr.append(a)
                d.append(b)
    if len(fr) < 5:
        raise ValueError('Could not read frequency/dB pairs from that file.')
    o = np.argsort(fr)
    return np.array(fr)[o], np.array(d)[o]


# ================================================================= walkthrough widget
class Walk(ttk.Frame):
    """Step-by-step tutorial panel with a step list, text and tips."""

    def __init__(self, master, steps, extra=None, **kw):
        super().__init__(master, style='Panel.TFrame', padding=8, **kw)
        self.steps, self.extra, self.i = steps, extra, 0
        top = ttk.Frame(self, style='Panel.TFrame')
        top.pack(fill='x')
        self.head = ttk.Label(top, text='', style='H.TLabel', wraplength=290, justify='left')
        self.head.pack(side='left', fill='x', expand=True)
        ttk.Button(top, text='▶', width=3, command=lambda: self.go(self.i + 1)).pack(side='right')
        ttk.Button(top, text='◀', width=3, command=lambda: self.go(self.i - 1)).pack(side='right', padx=4)
        self.lb = tk.Listbox(self, height=6, bg=PANEL2, fg=TXT, selectbackground='#2c7a7b', relief='flat',
                             highlightthickness=0, activestyle='none', font=('Segoe UI', 9))
        self.lb.pack(fill='x', pady=6)
        self.lb.bind('<<ListboxSelect>>', lambda e: self.lb.curselection() and self.go(self.lb.curselection()[0]))
        self.txt = tk.Text(self, bg=PANEL, fg=TXT, relief='flat', wrap='word', font=('Segoe UI', 10), highlightthickness=0, height=14)
        sb = ttk.Scrollbar(self, command=self.txt.yview)
        self.txt.config(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        self.txt.pack(fill='both', expand=True)
        self.txt.tag_configure('tip', foreground=AVG)
        self.txt.tag_configure('val', foreground=PEAK, font=('Segoe UI', 10, 'bold'))
        self.set_steps(steps)

    def set_steps(self, steps):
        self.steps = steps
        self.lb.delete(0, 'end')
        for k, s in enumerate(steps):
            self.lb.insert('end', f'{k + 1}. {s["t"]}')
        self.go(0)

    def go(self, i):
        if not self.steps:
            return
        self.i = max(0, min(len(self.steps) - 1, i))
        s = self.steps[self.i]
        self.head.config(text=f'Step {self.i + 1} of {len(self.steps)}: {s["t"]}')
        self.lb.selection_clear(0, 'end')
        self.lb.selection_set(self.i)
        self.lb.see(self.i)
        self.refresh()

    def refresh(self):
        s = self.steps[self.i]
        t = self.txt
        t.config(state='normal')
        t.delete('1.0', 'end')
        t.insert('end', s['x'] + '\n')
        if self.extra:
            v = self.extra(self.i, s)
            if v:
                t.insert('end', '\n' + v + '\n', 'val')
        for tip in s.get('tips', []):
            t.insert('end', '\nTip: ' + tip + '\n', 'tip')
        t.config(state='disabled')


# ================================================================= room tab
OCT = [63, 125, 250, 500, 1000, 2000, 4000, 8000]


def sim_room_ir(fs, seed=5):
    rng = np.random.default_rng(seed)
    n = int(fs * 2.5)
    t = np.arange(n) / fs
    ir = np.zeros(n)
    d0 = int(0.004 * fs)
    ir[d0] = 1.0
    ir[int(0.011 * fs)] += 0.45   # floor bounce
    ir[int(0.023 * fs)] += -0.3   # side wall
    tail = rng.standard_normal(n) * (t > 0.015)
    # frequency-dependent decay: RT 1.6 s at low end, 0.9 s at high end
    T = np.fft.rfft(tail)
    f = np.fft.rfftfreq(n, 1 / fs)
    out = np.zeros(n)
    edges = [20, 90, 180, 355, 710, 1400, 2800, 5600, 11200, 24000]
    rts = [1.7, 1.6, 1.45, 1.25, 1.1, 1.0, 0.92, 0.85, 0.8]
    for k in range(len(rts)):
        m = (f >= edges[k]) & (f < edges[k + 1])
        part = np.fft.irfft(T * m, n)
        out += part * np.exp(-6.91 * t / rts[k])
    ir += 0.06 * out
    # two room modes ringing
    for fm, rt, a in ((48, 2.4, 0.015), (112, 1.9, 0.008)):
        ir += a * np.sin(2 * np.pi * fm * t) * np.exp(-6.91 * t / rt) * (t > 0.004)
    return ir


def exp_sweep(fs, T=5.0, f1=20.0, f2=20000.0):
    n = int(T * fs)
    t = np.arange(n) / fs
    L = T / math.log(f2 / f1)
    x = np.sin(2 * math.pi * f1 * L * (np.exp(t / L) - 1))
    fade = int(0.02 * fs)
    x[:fade] *= np.hanning(2 * fade)[:fade]
    x[-fade:] *= np.hanning(2 * fade)[fade:]
    return (0.5 * x).astype(np.float32)


def deconvolve(rec, sweep, fs, ir_len):
    n = 1 << int(math.ceil(math.log2(len(rec) + len(sweep))))
    R = np.fft.rfft(rec, n)
    S = np.fft.rfft(sweep, n)
    f = np.fft.rfftfreq(n, 1 / fs)
    eps = 1e-4 * np.max(np.abs(S)) ** 2
    H = R * np.conj(S) / (np.abs(S) ** 2 + eps)
    H[(f < 15) | (f > 21000)] *= 0.0
    h = np.fft.irfft(H, n)
    return h[:ir_len]


def octave_filter(ir, fs, fc):
    # zero-phase filter: pad both ends so pre-ringing cannot wrap round into the tail
    pad = int(0.5 * fs)
    n0 = len(ir)
    ir = np.concatenate([np.zeros(pad), ir, np.zeros(pad)])
    n = len(ir)
    X = np.fft.rfft(ir)
    f = np.fft.rfftfreq(n, 1 / fs)
    # smooth (raised-cosine in log f) octave mask
    lf = np.log2(np.maximum(f, 1e-3) / fc)
    m = np.clip(1.5 - np.abs(lf) * 2, 0, 1)  # flat within +-1/4 oct, zero beyond +-3/4 oct
    m = 0.5 - 0.5 * np.cos(np.pi * m)
    return np.fft.irfft(X * m, n)[pad:pad + n0]


def decay_params(h, fs):
    """Schroeder backward integration with noise compensation; returns dict and the decay curve."""
    e = h.astype(float) ** 2
    n = len(e)
    tail = e[int(n * 0.9):]
    noise = float(np.mean(tail)) if len(tail) else 0
    # truncate where the 10 ms smoothed envelope meets noise + 5 dB
    k = max(1, int(0.01 * fs))
    env = np.convolve(e, np.ones(k) / k, 'same')
    start = int(np.argmax(env))
    above = np.where(env[start:] < noise * 10 ** 0.5)[0]
    cut = start + (above[0] if len(above) else n - start - 1)
    cut = max(cut, start + int(0.05 * fs))
    e2 = np.maximum(e[:cut] - noise, 0)
    sch = np.cumsum(e2[::-1])[::-1]
    sch = sch / max(sch[0], 1e-30)
    L = 10 * np.log10(np.maximum(sch, 1e-12))
    t = np.arange(len(L)) / fs

    def fit(a, b):
        i = np.where((L <= a) & (L >= b))[0]
        if len(i) < 10:
            return None
        p = np.polyfit(t[i], L[i], 1)
        return -60 / p[0] if p[0] < 0 else None
    out = {'EDT': fit(0, -10), 'T20': fit(-5, -25), 'T30': fit(-5, -35)}
    s = int(np.argmax(np.abs(h)))
    tot = float(np.sum(e2[s:])) or 1e-30
    e50 = float(np.sum(e2[s:s + int(0.05 * fs)]))
    e80 = float(np.sum(e2[s:s + int(0.08 * fs)]))
    out['C50'] = 10 * math.log10(max(e50, 1e-30) / max(tot - e50, 1e-30))
    out['C80'] = 10 * math.log10(max(e80, 1e-30) / max(tot - e80, 1e-30))
    out['D50'] = 100 * e50 / tot
    out['noise_db'] = 10 * math.log10(max(noise, 1e-30) / max(float(np.max(env)), 1e-30))
    return out, t, L


class RoomTab(ttk.Frame):
    def __init__(self, nb, app):
        super().__init__(nb)
        self.app = app
        self.q = queue.Queue()
        self.result = None
        left = ttk.Frame(self)
        ctl = ttk.Frame(left, style='Panel.TFrame', padding=6)
        ctl.pack(fill='x')
        ttk.Label(ctl, text='Measure with', style='Dim.TLabel').pack(side='left', padx=(4, 2))
        self.mode = tk.StringVar(value='Simulated room (no mic needed)')
        ttk.Combobox(ctl, textvariable=self.mode, values=['Simulated room (no mic needed)', 'Speaker + mic (sweep)'],
                     state='readonly', width=24).pack(side='left', padx=4)
        ttk.Label(ctl, text='Output', style='Dim.TLabel').pack(side='left', padx=(8, 2))
        self.out_var = tk.StringVar()
        self.out_cb = ttk.Combobox(ctl, textvariable=self.out_var, state='readonly', width=18)
        self.out_cb.pack(side='left')
        self.lvl = tk.StringVar(value='-12')
        ttk.Label(ctl, text='Level dBFS', style='Dim.TLabel').pack(side='left', padx=(8, 2))
        ttk.Combobox(ctl, textvariable=self.lvl, values=['-30', '-24', '-18', '-12', '-6'], state='readonly', width=5).pack(side='left')
        self.go_btn = ttk.Button(ctl, text='Measure', style='Accent.TButton', command=self.measure)
        self.go_btn.pack(side='left', padx=8)
        self.msg = ttk.Label(ctl, text='', style='Dim.TLabel')
        self.msg.pack(side='left')
        plots = ttk.Frame(left)
        plots.pack(fill='both', expand=True, pady=(6, 0))
        self.fr = Plot(plots, -30, 12, ylabel='dB (1/6 oct)', height=230)
        self.fr.pack(fill='both', expand=True)
        self.dec = Plot(plots, -70, 0, xmin=0, xmax=2.0, logx=False, ylabel='dB decay', height=200, xlabel='s')
        self.dec.pack(fill='both', expand=True, pady=(6, 0))
        self.table = tk.Text(left, height=11, bg=PANEL, fg=TXT, relief='flat', font=('Consolas', 10), highlightthickness=0, wrap='none')
        self.table.pack(fill='x', pady=(6, 0))
        right = ttk.Frame(self, width=380)
        right.pack(side='right', fill='both', padx=(8, 0))
        right.pack_propagate(False)
        left.pack(side='left', fill='both', expand=True)
        self.advice = tk.Text(right, height=14, bg=PANEL, fg=TXT, relief='flat', wrap='word', font=('Segoe UI', 10), highlightthickness=0)
        self.advice.pack(fill='x')
        self.advice.tag_configure('h', foreground=TRACE, font=('Segoe UI', 11, 'bold'))
        self.advice.insert('end', 'Room advisor\n', 'h')
        self.advice.insert('end', 'Press Measure. The simulated room works without hardware; for a real room pick "Speaker + mic", '
                                  'choose the output that feeds a speaker and use your measurement mic as the input device (top bar).')
        self.walk = Walk(right, TUT['WALK'])
        self.walk.pack(fill='both', expand=True, pady=(8, 0))
        self.refresh_outputs()
        self.after(200, self.poll)

    def refresh_outputs(self):
        vals = []
        self.outs = []
        if sd is not None:
            try:
                for i, d in enumerate(sd.query_devices()):
                    if d['max_output_channels'] > 0:
                        self.outs.append(i)
                        vals.append(f"{d['name']} ({sd.query_hostapis(d['hostapi'])['name']})")
            except Exception:
                pass
        self.out_cb['values'] = vals or ['(no audio output available)']
        self.out_var.set((vals or ['(no audio output available)'])[0])

    def measure(self):
        fs = 48000
        sim = self.mode.get().startswith('Sim')
        self.go_btn.state(['disabled'])
        self.msg.config(text='Measuring…')
        lvl = 10 ** (float(self.lvl.get()) / 20) / 0.5
        app = self.app
        in_dev = None
        if not sim:
            if sd is None or not app.devices:
                messagebox.showwarning(APP, 'Real measurement needs sounddevice and an audio input.\n\n' + (SD_ERR or ''))
                self.go_btn.state(['!disabled'])
                self.msg.config(text='')
                return
            vals = [n for _, n in app.devices]
            in_dev = app.devices[vals.index(app.dev_var.get()) if app.dev_var.get() in vals else 0][0]
            out_dev = self.outs[self.out_cb.current()] if self.outs and self.out_cb.current() >= 0 else None
            app.eng.stop()  # release the input for the sweep

        def work():
            try:
                sw = exp_sweep(fs) * lvl
                pad = np.zeros(int(2.5 * fs), np.float32)
                play = np.concatenate([pad[:int(0.3 * fs)], sw, pad])
                if sim:
                    ir = sim_room_ir(fs)
                    n = 1 << int(math.ceil(math.log2(len(play) + len(ir))))
                    rec = np.fft.irfft(np.fft.rfft(play, n) * np.fft.rfft(ir, n), n)[:len(play)]
                    rec = rec / np.max(np.abs(rec)) * 0.5 * lvl + np.random.default_rng(1).standard_normal(len(rec)) * 2e-5
                    noise_rec = np.random.default_rng(2).standard_normal(fs) * 2e-5
                else:
                    noise_rec = sd.rec(fs, samplerate=fs, channels=1, device=in_dev, dtype='float32')
                    sd.wait()
                    noise_rec = noise_rec[:, 0]
                    rec = sd.playrec(play.reshape(-1, 1), samplerate=fs, channels=1, device=(in_dev, out_dev), dtype='float32')
                    sd.wait()
                    rec = rec[:, 0]
                h = deconvolve(rec, play, fs, int(fs * 2.4))
                self.q.put(('ok', h, rec, noise_rec, fs))
            except Exception as e:
                self.q.put(('err', str(e)))
        threading.Thread(target=work, daemon=True).start()

    def poll(self):
        try:
            item = self.q.get_nowait()
        except queue.Empty:
            self.after(200, self.poll)
            return
        self.go_btn.state(['!disabled'])
        if not self.mode.get().startswith('Sim'):
            self.app.set_source(self.app.src_var.get())
        if item[0] == 'err':
            self.msg.config(text='Failed')
            messagebox.showerror(APP, 'Measurement failed:\n' + item[1])
        else:
            self.msg.config(text='Done')
            self.analyse(*item[1:])
        self.after(200, self.poll)

    def analyse(self, h, rec, noise_rec, fs):
        pk = int(np.argmax(np.abs(h)))
        s = max(0, pk - int(0.002 * fs))
        h = h[s:]
        cal = self.app.cal
        if np.max(np.abs(rec)) > 0.98:
            self.msg.config(text='Done, but the recording clipped: lower the level or the input gain.')
        elif np.max(np.abs(rec)) < 0.003:
            self.msg.config(text='Done, but the recording was very quiet: raise the level.')
        # frequency response (500 ms window, 1/6-octave smoothing)
        w = h[:int(0.5 * fs)] * np.hanning(int(fs))[int(0.5 * fs):]
        F = np.fft.rfft(w, 1 << 16)
        f = np.fft.rfftfreq(1 << 16, 1 / fs)
        Pm = np.abs(F) ** 2
        fl = np.geomspace(20, 20000, 400)
        cs = np.concatenate([[0], np.cumsum(Pm)])
        lo = np.searchsorted(f, fl / 2 ** (1 / 12))
        hi = np.maximum(np.searchsorted(f, fl * 2 ** (1 / 12)), lo + 1)
        sm = (cs[hi] - cs[lo]) / (hi - lo)
        resp = db(sm) - self.app.corr_at(fl) * -1 if False else db(sm) + self.app.corr_at(fl)
        ref = np.median(resp[(fl > 200) & (fl < 5000)])
        resp -= ref
        top = max(12, math.ceil((np.max(resp[(fl > 25) & (fl < 18000)]) + 3) / 6) * 6)
        if top != self.fr.ymax:
            self.fr.set_range(-30, top)
        self.fr.line('resp', fl, resp, fill=TRACE, width=2)
        self.fr.line('zero', [20, 20000], [0, 0], fill=DIM, width=1, dash=(3, 3))
        # octave decays
        rows = []
        cols = ['#4fd1c5', '#90cdf4', '#b794f4', '#f6ad55', '#68d391', '#fc8181', '#faf089', '#a0aec0']
        for k, fc in enumerate(OCT):
            hb = octave_filter(h, fs, fc)
            p, t, L = decay_params(hb, fs)
            rows.append((fc, p))
            step = max(1, len(t) // 600)
            self.dec.line(f'd{fc}', t[::step], L[::step], fill=cols[k], width=1.3)
        pb, tb, Lb = decay_params(h, fs)
        step = max(1, len(tb) // 600)
        self.dec.line('dbb', tb[::step], Lb[::step], fill='white', width=2)
        fmt = lambda v, d=2: '  -  ' if v is None else f'{v:5.{d}f}'
        tx = self.table
        tx.config(state='normal')
        tx.delete('1.0', 'end')
        tx.insert('end', 'Octave   ' + ''.join(f'{(str(fc) if fc < 1000 else str(fc // 1000) + "k"):>7}' for fc, _ in rows) + '   Broad\n')
        for key, d in (('T20', 2), ('T30', 2), ('EDT', 2), ('C50', 1), ('C80', 1), ('D50', 0)):
            tx.insert('end', f'{key + (" s" if key[0] in "TE" else " dB" if key[0] == "C" else " %"):<9}' +
                      ''.join(f'{fmt(p[key], d):>7}' for _, p in rows) + f'{fmt(pb[key], d):>8}\n')
        nf = np.fft.rfft(noise_rec * np.hanning(len(noise_rec)))
        nff = np.fft.rfftfreq(len(noise_rec), 1 / fs)
        nP = np.abs(nf) ** 2 * 2 / (len(noise_rec) * np.sum(np.hanning(len(noise_rec)) ** 2))
        oct_noise = []
        for fc in OCT:
            m = (nff >= fc / math.sqrt(2)) & (nff < fc * math.sqrt(2))
            oct_noise.append(10 * math.log10(max(float(np.sum(nP[m])), 1e-20)) + cal)
        tx.insert('end', 'Noise dB ' + ''.join(f'{v:7.0f}' for v in oct_noise) + '\n')
        tx.insert('end', '\nT20/T30: reverberation time; EDT: early decay (what you hear).\nC80 > 0 dB means clear music, '
                         'C50 > 0 dB clear speech; D50 = early energy share.' + ('' if self.app.calibrated else '  Noise is uncalibrated.'))
        tx.config(state='disabled')
        self.write_advice(rows, pb, fl, resp)

    def write_advice(self, rows, pb, fl, resp):
        a = self.advice
        a.config(state='normal')
        a.delete('1.0', 'end')
        a.insert('end', 'Room advisor\n', 'h')
        rt = {fc: (p['T30'] or p['T20']) for fc, p in rows}
        mid = [v for v in (rt.get(500), rt.get(1000)) if v]
        rtm = sum(mid) / len(mid) if mid else None
        out = []
        if rtm:
            if rtm > 1.8:
                out.append(f'Mid-band RT60 is {rtm:.2f} s: a very live room. Expect a blurry mix; keep stage volume down, '
                           'aim the PA at the audience (not walls and ceiling) and add absorption (heavy drapes, panels) if you can.')
            elif rtm > 1.1:
                out.append(f'Mid-band RT60 is {rtm:.2f} s: on the live side for amplified music (about 0.8–1.2 s is comfortable). '
                           'Tight low end and fewer open mics help.')
            elif rtm < 0.5:
                out.append(f'Mid-band RT60 is {rtm:.2f} s: very dry. The room adds little; you may want some reverb on the mix.')
            else:
                out.append(f'Mid-band RT60 is {rtm:.2f} s: a good range for amplified music.')
        lo = [v for v in (rt.get(63), rt.get(125)) if v]
        if rtm and lo:
            br = sum(lo) / len(lo) / rtm
            if br > 1.3:
                out.append(f'Bass rings {br:.1f}× longer than the mids. Bass traps in corners help; at the desk, keep the sub level '
                           'modest and avoid boosting below 125 Hz.')
        if pb['C80'] is not None and pb['C80'] < -2:
            out.append(f'Clarity C80 is {pb["C80"]:.1f} dB: late sound dominates. Reduce reflections, use more directional '
                       'speakers or bring the audience closer to the PA.')
        # modes: narrow peaks in 20-300 Hz above a 1-octave smoothed curve
        m = (fl >= 25) & (fl <= 300)
        k = 30
        smooth = np.convolve(resp, np.ones(k) / k, 'same')
        dev = resp - smooth
        idx = [i for i in np.where(m)[0] if dev[i] > 5 and dev[i] == max(dev[max(0, i - 5):i + 6])]
        for i in idx[:3]:
            out.append(f'Room mode near {fl[i]:.0f} Hz (+{dev[i]:.1f} dB). Try a narrow cut (Q 4–8, −{min(6, round(dev[i])):.0f} dB) '
                       'on the system EQ, or move the subs or the mix position.')
        hf = np.mean(resp[(fl > 8000) & (fl < 14000)])
        if hf < -8:
            out.append(f'High frequencies are {-hf:.0f} dB down at this mic position. Check HF coverage and the mic aiming.')
        if not out:
            out.append('No big problems found.')
        for o in out:
            a.insert('end', '• ' + o + '\n\n')
        a.config(state='disabled')


# ================================================================= crowd tab
class CrowdTab(ttk.Frame):
    NG = 32768

    def __init__(self, nb, app):
        super().__init__(nb)
        self.app = app
        self.list = []
        self.ref = tk.StringVar(value='Console band mix (best)')
        self.ref_dist = tk.StringVar(value='1.0')
        self.temp = tk.StringVar(value='20')
        self.dist = tk.StringVar(value='25')
        self.align = tk.StringVar(value='Delay the band mix')
        self.guide = tk.StringVar(value='DiGiCo S21')
        left = ttk.Frame(self)
        # finder
        fb = ttk.Frame(left, style='Panel.TFrame', padding=10)
        fb.pack(fill='x')
        ttk.Label(fb, text='Delay finder', style='H.TLabel').grid(row=0, column=0, sticky='w')
        ttk.Label(fb, text='Input 1 = reference (band mix), input 2 = crowd mic. Choose "Microphone / interface" in the top bar, '
                           'or "Simulated crowd mic" to try it.', style='Dim.TLabel', wraplength=640).grid(row=1, column=0, columnspan=6, sticky='w')
        ttk.Label(fb, text='Reference', style='Dim.TLabel').grid(row=2, column=0, sticky='w', pady=6)
        ttk.Combobox(fb, textvariable=self.ref, values=['Console band mix (best)', 'Mic at the PA'], state='readonly', width=24).grid(row=2, column=1, sticky='w')
        ttk.Label(fb, text='PA-to-ref-mic distance m', style='Dim.TLabel').grid(row=2, column=2, padx=(10, 2))
        ttk.Entry(fb, textvariable=self.ref_dist, width=6).grid(row=2, column=3, sticky='w')
        self.big = ttk.Label(fb, text='--.- ms', style='Big.TLabel')
        self.big.grid(row=3, column=0, columnspan=2, sticky='w')
        self.info = ttk.Label(fb, text='', style='Mid.TLabel', justify='left')
        self.info.grid(row=3, column=2, columnspan=4, sticky='w')
        bb = ttk.Frame(fb, style='Panel.TFrame')
        bb.grid(row=4, column=0, columnspan=6, sticky='w', pady=(6, 0))
        ttk.Button(bb, text='Reset', command=self.reset).pack(side='left')
        self.name = tk.StringVar(value='Crowd L')
        ttk.Entry(bb, textvariable=self.name, width=14).pack(side='left', padx=(12, 4))
        ttk.Button(bb, text='Add to list', style='Accent.TButton', command=self.add_measured).pack(side='left')
        self.corr = Plot(left, -1, 1, xmin=-100, xmax=400, logx=False, ylabel='corr', height=170, xlabel='ms')
        self.corr.pack(fill='x', pady=6)
        # calculator + list
        row = ttk.Frame(left)
        row.pack(fill='both', expand=True)
        calc = ttk.Frame(row, style='Panel.TFrame', padding=10)
        calc.pack(side='left', fill='y')
        ttk.Label(calc, text='Distance calculator', style='H.TLabel').pack(anchor='w')
        r = ttk.Frame(calc, style='Panel.TFrame')
        r.pack(anchor='w', pady=6)
        ttk.Label(r, text='Distance m', style='Dim.TLabel').pack(side='left')
        ttk.Entry(r, textvariable=self.dist, width=6).pack(side='left', padx=4)
        ttk.Label(r, text='Temp °C', style='Dim.TLabel').pack(side='left')
        ttk.Entry(r, textvariable=self.temp, width=5).pack(side='left', padx=4)
        self.calc_out = ttk.Label(calc, text='', style='Mid.TLabel')
        self.calc_out.pack(anchor='w')
        ttk.Button(calc, text='Add calculated to list', command=self.add_calc).pack(anchor='w', pady=6)
        for v in (self.dist, self.temp):
            v.trace_add('write', lambda *a: self.calc())
        self.calc()
        lst = ttk.Frame(row, style='Panel.TFrame', padding=10)
        lst.pack(side='left', fill='both', expand=True, padx=(8, 0))
        top = ttk.Frame(lst, style='Panel.TFrame')
        top.pack(fill='x')
        ttk.Label(top, text='Crowd mics', style='H.TLabel').pack(side='left')
        ttk.Combobox(top, textvariable=self.align, values=['Delay the band mix', 'Align crowd mics'], state='readonly', width=18).pack(side='right')
        self.align.trace_add('write', lambda *a: self.refresh_list())
        self.tree = ttk.Treeview(lst, columns=('name', 'meas', 'pol', 'set'), show='headings', height=5)
        for c, t, w in (('name', 'Mic', 110), ('meas', 'Measured ms', 90), ('pol', 'Polarity', 80), ('set', 'Set delay ms', 100)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor='w')
        self.tree.pack(fill='both', expand=True, pady=6)
        lb = ttk.Frame(lst, style='Panel.TFrame')
        lb.pack(fill='x')
        ttk.Button(lb, text='Remove selected', command=self.remove).pack(side='left')
        self.band_lbl = ttk.Label(lb, text='', style='Dim.TLabel', wraplength=330, justify='left')
        self.band_lbl.pack(side='left', padx=10)
        # tutorial
        right = ttk.Frame(self, width=460)
        right.pack(side='right', fill='both', padx=(8, 0))
        right.pack_propagate(False)
        left.pack(side='left', fill='both', expand=True)
        g = ttk.Frame(right, style='Panel.TFrame', padding=(8, 6))
        g.pack(fill='x')
        ttk.Label(g, text='Walkthrough', style='H.TLabel').pack(side='left')
        for v in ('General', 'DiGiCo S21'):
            ttk.Radiobutton(g, text=v, value=v, variable=self.guide, command=self.set_guide).pack(side='right', padx=4)
        self.walk = Walk(right, TUT['S21'], extra=self.walk_values)
        self.walk.pack(fill='both', expand=True)
        self.reset()

    def set_guide(self):
        self.walk.set_steps(TUT['S21'] if self.guide.get() == 'DiGiCo S21' else TUT['DWALK'])

    def walk_values(self, i, s):
        if not self.list:
            return ''
        sets = self.settings()
        band = max(m['ms'] for m in self.list) if self.align.get() == 'Delay the band mix' else 0
        t = s['t'].lower()
        if any(w in t for w in ('delay', 'set', 'enter', 'align', 'apply', 'store', 'save', 'check', 'verify', 'listen')):
            lines = [f"{m['name']}: {d:.1f} ms{' + polarity invert' if m['inv'] else ''}" for m, d in zip(self.list, sets)]
            if band:
                lines.insert(0, f'Band broadcast delay: {band:.1f} ms')
            return 'Your values: ' + '; '.join(lines)
        return ''

    # --------------------------------------------------- finder
    def reset(self):
        self.S = None
        self.hist = []
        self.last = None

    def c_sound(self):
        try:
            return 331.3 + 0.606 * float(self.temp.get().replace(',', '.'))
        except ValueError:
            return 343.0

    def ref_off(self):
        if self.ref.get().startswith('Mic'):
            try:
                return float(self.ref_dist.get().replace(',', '.')) / self.c_sound() * 1000
            except ValueError:
                return 0.0
        return 0.0

    def update_audio(self):
        eng = self.app.eng
        fs = eng.fs
        x = eng.latest(self.NG)
        a, b = x[0].astype(float), x[1].astype(float)
        if np.sqrt(np.mean(a ** 2)) < 1e-5 or np.sqrt(np.mean(b ** 2)) < 1e-5:
            self.info.config(text='Need signal on both inputs.\nInput 1 band mix, input 2 crowd mic.')
            return
        w = np.hanning(self.NG)
        A = np.fft.rfft(a * w, 2 * self.NG)
        B = np.fft.rfft(b * w, 2 * self.NG)
        G = B * np.conj(A)
        self.S = G if self.S is None else 0.85 * self.S + 0.15 * G
        f = np.fft.rfftfreq(2 * self.NG, 1 / fs)
        W = self.S / np.maximum(np.abs(self.S), 1e-20)
        W[(f < 200) | (f > 8000)] = 0
        r = np.fft.irfft(W, 2 * self.NG)
        maxlag = int(0.5 * fs)
        lags = np.concatenate([np.arange(-maxlag, 0), np.arange(0, maxlag)])
        rr = np.concatenate([r[-maxlag:], r[:maxlag]])
        ar = np.abs(rr)
        i = int(np.argmax(ar))
        d = 0.0
        if 0 < i < len(ar) - 1:
            y0, y1, y2 = ar[i - 1], ar[i], ar[i + 1]
            den = y0 - 2 * y1 + y2
            d = 0.5 * (y0 - y2) / den if den != 0 else 0.0
        lag = lags[i] + d
        ms = lag / fs * 1000 + self.ref_off()
        inv = rr[i] < 0
        conf = float(ar[i] / (np.std(rr) + 1e-20))
        self.hist.append(ms)
        self.hist = self.hist[-8:]
        stab = float(np.std(self.hist)) if len(self.hist) > 2 else 99
        self.last = (ms, inv, conf, stab)
        q = 'good' if conf >= 15 else 'fair' if conf >= 8 else 'poor'
        col = GOOD if q == 'good' else WARN if q == 'fair' else BAD
        self.big.config(text=f'{ms:6.1f} ms', foreground=col)
        dist = ms / 1000 * self.c_sound()
        self.info.config(text=f'≈ {dist:.1f} m of sound travel\nPolarity: {"INVERTED, flip the crowd mic" if inv else "normal"}\n'
                              f'Confidence {conf:.0f} ({q}), stable ±{stab:.2f} ms' + (f'\n(+{self.ref_off():.2f} ms for the reference mic)' if self.ref_off() else ''))
        step = 4
        lm = lags[::step] / fs * 1000 + self.ref_off()
        self.corr.line('c', lm, rr[::step] / max(ar[i], 1e-20), fill=TRACE, width=1)
        self.corr.line('m', [ms, ms], [-1, 1], fill=PEAK, width=1, dash=(3, 3))

    def add_measured(self):
        if not self.last:
            messagebox.showinfo(APP, 'No measurement yet. Open this tab with a 2-channel source running.')
            return
        ms, inv, conf, stab = self.last
        if conf < 8 and not messagebox.askyesno(APP, f'Confidence is low ({conf:.0f}). Add anyway?'):
            return
        self.list.append({'name': self.name.get() or f'Crowd {len(self.list) + 1}', 'ms': ms, 'inv': inv})
        self.refresh_list()

    def calc(self):
        try:
            d = float(self.dist.get().replace(',', '.'))
        except ValueError:
            self.calc_out.config(text='')
            return
        c = self.c_sound()
        self.calc_ms = d / c * 1000
        self.calc_out.config(text=f'{self.calc_ms:.1f} ms  (c = {c:.1f} m/s)')

    def add_calc(self):
        if hasattr(self, 'calc_ms'):
            self.list.append({'name': (self.name.get() or 'Crowd') + ' (calc)', 'ms': self.calc_ms, 'inv': False})
            self.refresh_list()

    def remove(self):
        sel = [self.tree.index(s) for s in self.tree.selection()]
        self.list = [m for k, m in enumerate(self.list) if k not in sel]
        self.refresh_list()

    def settings(self):
        if not self.list:
            return []
        mx = max(m['ms'] for m in self.list)
        return [mx - m['ms'] for m in self.list]

    def refresh_list(self):
        self.tree.delete(*self.tree.get_children())
        for m, s in zip(self.list, self.settings()):
            self.tree.insert('', 'end', values=(m['name'], f"{m['ms']:.1f}", 'invert' if m['inv'] else 'normal', f'{s:.1f}'))
        if self.list:
            mx = max(m['ms'] for m in self.list)
            if self.align.get() == 'Delay the band mix':
                self.band_lbl.config(text=f'Delay the band broadcast feed (BAND BC group or band matrix) by {mx:.1f} ms. '
                                          'Never delay L/R itself: that would delay the PA.')
            else:
                self.band_lbl.config(text='Band stays undelayed; crowd mics are aligned to the latest one. '
                                          'Use this when L/R feeds the broadcast directly.')
        else:
            self.band_lbl.config(text='')
        self.walk.refresh()


def main():
    app = App()
    if SD_ERR:
        app.after(600, lambda: app.status.config(text='No audio I/O (' + SD_ERR[:50] + '): demo sources only'))
    app.mainloop()


if __name__ == '__main__':
    main()
