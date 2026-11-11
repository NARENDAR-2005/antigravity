import os
import io
import re
import time
import json
import wave
import uuid
import math
import base64
import struct
import subprocess
import urllib.parse
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageOps
from dotenv import load_dotenv

try:
    import imageio_ffmpeg
    HAS_FFMPEG = True
except ImportError:
    HAS_FFMPEG = False


MUSIC_KEYWORDS = (
    'music', 'song', 'beat', 'melody', 'soundtrack', 'instrumental',
    'lofi', 'lo-fi', 'synth', 'piano', 'guitar', 'drum', 'ambient',
    'tune', 'ringtone', 'jingle', 'bgm', 'background sound', 'chime'
)


def _clean_media_prompt(prompt, prefixes):
    text = re.sub(r'\s+', ' ', (prompt or '').strip())
    lower = text.lower()
    for p in prefixes:
        if lower.startswith(p):
            text = text[len(p):].strip()
            break
    cleaned = re.sub(r'\s+', ' ', text.strip(' ":\''))
    return cleaned or re.sub(r'\s+', ' ', (prompt or '').strip())


def _is_placeholder(key):
    if not key:
        return True
    k = key.lower().strip()
    return any(p in k for p in ('paste-', 'your-', 'xxxx', 'key-here', 'api_key')) or len(k) < 15


def _write_wav_bytes(path, pcm_int16, sample_rate=24000, channels=1):
    """Write numpy int16 PCM samples to a standard WAV file."""
    pcm_clipped = np.clip(pcm_int16, -32768, 32767).astype('<i2')
    with wave.open(path, 'wb') as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm_clipped.tobytes())


def _read_wav_as_float(path, target_rate=24000):
    """Read a WAV file into mono float32 array in [-1, 1] resampled to target_rate."""
    with wave.open(path, 'rb') as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        src_rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())

    if sampwidth == 2:
        samples = np.frombuffer(raw, dtype='<i2').astype(np.float32) / 32768.0
    elif sampwidth == 1:
        samples = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        samples = np.frombuffer(raw, dtype='<i4').astype(np.float32) / 2147483648.0

    if n_channels > 1:
        samples = samples.reshape(-1, n_channels).mean(axis=1)

    if src_rate != target_rate and len(samples) > 1:
        new_len = int(len(samples) * target_rate / src_rate)
        x_old = np.linspace(0, 1, len(samples))
        x_new = np.linspace(0, 1, new_len)
        samples = np.interp(x_new, x_old, samples).astype(np.float32)

    return samples


def _synthesize_music_array(prompt, duration=10.0, sample_rate=24000):
    """Synthesize a clean multi-harmonic musical track tailored to prompt mood."""
    lower = (prompt or '').lower()
    n_samples = int(duration * sample_rate)
    t = np.linspace(0, duration, n_samples, endpoint=False, dtype=np.float32)

    # Choose scale & tempo by mood
    if any(w in lower for w in ('sad', 'calm', 'sleep', 'lofi', 'lo-fi', 'chill', 'relax', 'ambient', 'space', 'ocean')):
        chords = [(220.0, 261.63, 329.63), (174.61, 220.0, 261.63), (196.0, 246.94, 293.66), (164.81, 196.0, 246.94)]
        bpm = 80
        wave_type = 'warm'
    elif any(w in lower for w in ('dark', 'epic', 'cyber', 'action', 'cinematic', 'dramatic', 'battle', 'robot')):
        chords = [(146.83, 174.61, 220.0), (130.81, 164.81, 196.0), (116.54, 146.83, 174.61), (130.81, 164.81, 220.0)]
        bpm = 118
        wave_type = 'synth'
    else:
        chords = [(261.63, 329.63, 392.0), (220.0, 261.63, 329.63), (174.61, 220.0, 261.63), (196.0, 246.94, 293.66)]
        bpm = 110
        wave_type = 'bright'

    beat_sec = 60.0 / bpm
    audio = np.zeros(n_samples, dtype=np.float32)

    # Build sample-by-sample chord & arpeggio signal
    step_sec = beat_sec / 2.0
    n_steps = int(math.ceil(duration / step_sec))
    for step in range(n_steps):
        s_start = int(step * step_sec * sample_rate)
        s_end = min(n_samples, int((step + 1) * step_sec * sample_rate))
        if s_start >= s_end:
            break
        local_t = np.arange(s_end - s_start, dtype=np.float32) / sample_rate
        chord = chords[(step // 4) % len(chords)]

        # Warm pad from chord triad + sub bass
        pad = np.zeros_like(local_t)
        for f in chord:
            pad += 0.14 * np.sin(2.0 * np.pi * f * local_t)
            if wave_type == 'synth':
                pad += 0.04 * np.sin(2.0 * np.pi * f * 2.0 * local_t)
        pad += 0.18 * np.sin(2.0 * np.pi * (chord[0] * 0.5) * local_t)

        # Gentle plucked arpeggio note
        arp_freq = chord[step % len(chord)] * (2.0 if wave_type != 'synth' else 1.5)
        env = np.exp(-local_t * (5.5 if wave_type == 'bright' else 3.5))
        arp = 0.20 * env * (
            np.sin(2.0 * np.pi * arp_freq * local_t) +
            0.35 * np.sin(2.0 * np.pi * arp_freq * 2.0 * local_t)
        )

        # Soft kick/pulse on quarter beats for upbeat/synth styles
        pulse = np.zeros_like(local_t)
        if wave_type in ('synth', 'bright') and step % 2 == 0:
            kick_env = np.exp(-local_t * 24.0)
            kick_f = 55.0 + 75.0 * np.exp(-local_t * 35.0)
            pulse = 0.22 * kick_env * np.sin(2.0 * np.pi * kick_f * local_t)

        audio[s_start:s_end] = pad + arp + pulse

    # Smooth fade in & fade out
    fade_len = min(int(0.4 * sample_rate), n_samples // 4)
    if fade_len > 0:
        audio[:fade_len] *= np.linspace(0.0, 1.0, fade_len, dtype=np.float32)
        audio[-fade_len:] *= np.linspace(1.0, 0.0, fade_len, dtype=np.float32)

    peak = np.max(np.abs(audio)) or 1.0
    return (audio / peak * 0.85).astype(np.float32)


def _call_gemini_tts(script_text, out_wav_path):
    """Generate speech WAV using Google Gemini TTS models. Returns True on success."""
    load_dotenv(override=True)
    api_key = (os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY') or '').strip()
    if _is_placeholder(api_key):
        return False

    tts_models = ['gemini-3.8-flash-lite-tts', 'gemini-2.5-flash-preview-tts', 'gemini-3.8-flash-tts']
    payload = json.dumps({
        'contents': [{'role': 'user', 'parts': [{'text': script_text}]}],
        'generationConfig': {
            'responseModalities': ['AUDIO'],
            'speechConfig': {
                'voiceConfig': {
                    'prebuiltVoiceConfig': {'voiceName': 'Kore'}
                }
            }
        }
    }).encode('utf-8')

    for model_name in tts_models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        req = urllib.request.Request(
            url,
            data=payload,
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode('utf-8'))

            parts = body.get('candidates', [{}])[0].get('content', {}).get('parts', [])
            for p in parts:
                inline = p.get('inlineData')
                if inline and inline.get('data'):
                    raw_bytes = base64.b64decode(inline['data'])
                    mime = (inline.get('mimeType') or '').lower()
                    if raw_bytes[:4] == b'RIFF' and 'wav' in mime:
                        with open(out_wav_path, 'wb') as f:
                            f.write(raw_bytes)
                    else:
                        # Raw 16-bit PCM fallback wrapping
                        pcm = np.frombuffer(raw_bytes, dtype='<i2')
                        _write_wav_bytes(out_wav_path, pcm, sample_rate=24000)
                    return True
        except urllib.error.HTTPError as e:
            err_body = e.read().decode('utf-8', errors='replace')
            print(f"Gemini TTS HTTP {e.code} on {model_name}: {err_body[:200]}")
            if e.code in (400, 401, 403):
                break
        except Exception as e:
            print(f"Gemini TTS error on {model_name}: {e}")

    return False


def _windows_sapi_tts(script_text, out_wav_path):
    """Offline fallback using built-in Windows SpeechSynthesizer if Gemini TTS fails."""
    if os.name != 'nt':
        return False
    try:
        clean = script_text.replace("'", " ").replace('"', ' ').replace('\n', ' ')
        ps_cmd = (
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.SetOutputToWaveFile('{out_wav_path}'); "
            f"$s.Speak('{clean[:500]}'); "
            "$s.Dispose()"
        )
        subprocess.run(['powershell', '-NoProfile', '-Command', ps_cmd], check=True, timeout=20)
        return os.path.exists(out_wav_path) and os.path.getsize(out_wav_path) > 100
    except Exception as e:
        print(f"Windows SAPI fallback error: {e}")
        return False


def generate_audio(prompt, output_dir, text_generator=None):
    """Generate an audio file (.wav) for either voice narration or synthesized music.

    Returns (audio_url, summary_markdown).
    """
    os.makedirs(output_dir, exist_ok=True)
    clean_prompt = _clean_media_prompt(prompt, (
        'create an audio of', 'create audio of', 'create audio:', 'create audio',
        'generate audio of', 'generate an audio of', 'generate audio',
        'create music of', 'generate music of', 'make audio of', 'make music of',
        'text to speech:', 'speak:'
    ))

    filename = f"audio_{uuid.uuid4().hex[:10]}.wav"
    out_path = os.path.join(output_dir, filename)
    audio_url = f"/static/generated/{filename}"
    lower = clean_prompt.lower()

    # Branch 1: Instrumental / Music / Sound prompt
    if any(k in lower for k in MUSIC_KEYWORDS):
        samples = _synthesize_music_array(clean_prompt, duration=10.0, sample_rate=24000)
        _write_wav_bytes(out_path, (samples * 32767.0).astype(np.int16), sample_rate=24000)
        summary = (
            f"Here is your generated AI audio track for: **{clean_prompt}**\n\n"
            f"- **Type:** Synthesized Stereo/Mono Instrumental (`WAV`, 10s)"
        )
        return audio_url, summary

    # Branch 2: Voice / Narration / Speech prompt
    script_text = clean_prompt
    # If the user gave a topic rather than exact words to read aloud, ask Gemini to write a concise spoken script
    word_count = len(clean_prompt.split())
    if text_generator and word_count <= 12 and not any(lower.startswith(w) for w in ('say ', 'read ', 'speak ')):
        try:
            script_prompt = (
                f"Write a natural, engaging 2-3 sentence spoken voiceover script (30 to 45 words total, "
                f"plain spoken text only, no markdown or asterisks or stage directions) about: {clean_prompt}"
            )
            generated = text_generator(script_prompt)
            if generated and not generated.startswith('## ') and 'offline mode' not in generated.lower():
                script_text = re.sub(r'[*#`_]+', '', generated).strip()
        except Exception as e:
            print(f"Script generation error: {e}")

    ok = _call_gemini_tts(script_text, out_path)
    engine_label = "Gemini Neural Voice (`Kore`)"
    if not ok:
        ok = _windows_sapi_tts(script_text, out_path)
        engine_label = "Offline Speech Synthesizer"
    if not ok:
        samples = _synthesize_music_array(clean_prompt, duration=6.0, sample_rate=24000)
        _write_wav_bytes(out_path, (samples * 32767.0).astype(np.int16), sample_rate=24000)
        engine_label = "Procedural Audio Fallback"

    summary = (
        f"Here is your generated AI voice audio for: **{clean_prompt}**\n\n"
        f"- **Voice Engine:** {engine_label}\n"
        f"- **Spoken Script:** *\"{script_text}\"*"
    )
    return audio_url, summary


VIDEO_PREFIXES = (
    'create a video with audio of', 'create video with audio of',
    'create a animation video of', 'create an animation video of', 'create animation video of',
    'create a video on', 'create video on', 'create a video about', 'create video about',
    'create a video of', 'create video of', 'create video:', 'create video',
    'generate a video on', 'generate a video about', 'generate a video of', 'generate video of', 'generate video',
    'make a video on', 'make a video about', 'make a video of', 'make video of', 'make video',
    'video of', 'video on', 'video about'
)

ASPECT_DIMENSIONS = {
    '16:9': (1280, 720),
    '9:16': (720, 1280),
    '1:1': (720, 720),
    '4:3': (960, 720),
}

STYLE_KEYWORDS = (
    'anime', 'cartoon', '3d animation', '3d render', 'pixar', 'watercolor',
    'oil painting', 'cyberpunk', 'retro', 'vintage', 'documentary',
    'photorealistic', 'realistic', 'minimalist', 'noir', 'sketch', 'cinematic'
)

_UNSAFE_PATTERNS = (
    'deepfake', 'impersonate', 'clone voice of', 'fake news', 'misleading political',
    'without permission', 'celebrity likeness', 'non-consensual', 'explicit violence', 'gore'
)


def parse_video_specs(prompt):
    """Extract topic, purpose, duration, aspect_ratio, style, and audio preference with sensible defaults."""
    clean = _clean_media_prompt(prompt, VIDEO_PREFIXES)
    lower = clean.lower()

    # Duration (default 8s)
    duration = 8.0
    explicit_duration = False
    m_dur = re.search(r'\b(\d{1,2})\s*(?:s|sec|secs|second|seconds)\b', lower)
    if m_dur:
        duration = float(max(5, min(28, int(m_dur.group(1)))))
        explicit_duration = True

    # Aspect ratio (default 16:9)
    aspect_ratio = '16:9'
    if '9:16' in lower or any(w in lower for w in ('vertical', 'portrait', 'reel', 'reels', 'shorts', 'tiktok')):
        aspect_ratio = '9:16'
    elif '1:1' in lower or 'square' in lower:
        aspect_ratio = '1:1'
    elif '4:3' in lower:
        aspect_ratio = '4:3'

    # Style (default cinematic)
    style = 'cinematic'
    for st in STYLE_KEYWORDS:
        if st in lower:
            style = st
            break

    # Audio preference (default voiceover + ambient soundtrack)
    audio_mode = 'voiceover'
    if any(w in lower for w in ('no audio', 'silent', 'without audio', 'mute audio', 'muted')):
        audio_mode = 'silent'
    elif any(w in lower for w in ('music only', 'no voice', 'instrumental only', 'soundtrack only')):
        audio_mode = 'music'

    # Purpose
    purpose = 'visual showcase'
    for kw, label in (
        ('ad', 'product commercial / ad'), ('commercial', 'commercial'), ('promo', 'promotional showcase'),
        ('tutorial', 'step-by-step tutorial'), ('how to', 'educational guide'), ('explain', 'explainer'),
        ('story', 'short narrative story'), ('documentary', 'mini documentary')
    ):
        if re.search(rf'\b{re.escape(kw)}\b', lower):
            purpose = label
            break

    return {
        'clean_prompt': clean,
        'duration': duration,
        'explicit_duration': explicit_duration,
        'aspect_ratio': aspect_ratio,
        'dimensions': ASPECT_DIMENSIONS[aspect_ratio],
        'style': style,
        'audio_mode': audio_mode,
        'purpose': purpose,
    }


def check_video_safety(prompt):
    """Rule 6: Refuse harmful, misleading, or unauthorized real-person likeness requests."""
    lower = (prompt or '').lower()
    if any(pat in lower for pat in _UNSAFE_PATTERNS) or re.search(r'\bmake a video of\s+(elon musk|taylor swift|donald trump|narendra modi|joe biden|virat kohli)\b', lower):
        return False, (
            "I can't create videos using real people's likenesses without permission, "
            "or generate harmful or misleading content. Share a fictional subject or general topic instead!"
        )
    return True, ''


def check_video_clarification(prompt):
    """Rule 1: Ask ONE short question only if core topic/subject is missing; otherwise default cleanly."""
    clean = _clean_media_prompt(prompt, VIDEO_PREFIXES).lower()
    stripped = re.sub(r'\b(\d{1,2}\s*(?:s|sec|secs|second|seconds)|16:9|9:16|1:1|4:3|with audio|no audio|silent|cinematic|anime|cartoon|realistic|video|create|make|generate|for|me|a|an|the|about|on|of|please)\b', ' ', clean)
    meaningful_words = [w for w in re.findall(r'[a-z0-9]+', stripped) if len(w) > 1]
    if len(meaningful_words) < 1:
        return True, "What topic should the video cover, and what is its main purpose (e.g., showcase, tutorial, or story)?"
    return False, ''


def apply_video_refinement(previous_prompt, tweak_text, text_generator=None):
    """Rule 5: Adjust only the requested attribute (camera, style, action, duration, ratio, lighting) on the existing prompt."""
    clean_prev = _clean_media_prompt(previous_prompt, VIDEO_PREFIXES)
    clean_tweak = (tweak_text or '').strip()
    lower = clean_tweak.lower()

    # Identify which single element is being changed for user explanation
    changed_label = 'visual detail'
    for keywords, label in (
        (('camera', 'zoom', 'pan', 'close up', 'close-up', 'wide', 'angle'), 'camera movement'),
        (('style', 'anime', 'cartoon', '3d', 'realistic', 'cinematic', 'watercolor', 'noir'), 'visual style'),
        (('action', 'scene', 'show', 'cutting', 'running', 'moving', 'add', 'instead'), 'action sequence'),
        (('light', 'bright', 'dark', 'golden', 'sunset', 'warm', 'cool', 'color'), 'lighting & color'),
        (('second', 'sec', 'longer', 'shorter', 'duration', '16:9', '9:16', '1:1', 'vertical', 'square'), 'duration / framing'),
        (('audio', 'voice', 'music', 'silent', 'mute'), 'audio track'),
    ):
        if any(k in lower for k in keywords):
            changed_label = label
            break

    if text_generator:
        try:
            merge_prompt = (
                f"Original video request: \"{clean_prev}\"\n"
                f"User single adjustment: \"{clean_tweak}\"\n"
                "Rewrite into ONE updated single-line video request keeping the original subject, character, outfit, setting, "
                "and unchanged parameters intact while applying ONLY the requested change. Keep any explicit duration/aspect/style tags. Output ONLY the single line."
            )
            merged = re.sub(r'\s+', ' ', (text_generator(merge_prompt) or '').strip().strip('"\''))
            if merged and 'offline mode' not in merged.lower() and len(merged) > 5:
                return merged, changed_label
        except Exception as e:
            print(f"Refinement merge fallback: {e}")

    return f"{clean_prev}, {clean_tweak}", changed_label


def _build_storyboard(prompt, text_generator=None, specs=None):
    """Create a structured production prompt and consistent scene storyboard per Rules 2 & 3."""
    specs = specs or parse_video_specs(prompt)
    clean = specs['clean_prompt']
    duration = specs['duration']
    style = specs['style']
    aspect_ratio = specs['aspect_ratio']
    audio_mode = specs['audio_mode']
    purpose = specs['purpose']

    # Rule 3: For videos > 10s split into scenes of 5-8s each
    if duration > 10.0:
        n_scenes = max(2, min(5, round(duration / 6.5)))
    else:
        n_scenes = 3
    scene_dur = round(duration / n_scenes, 1)
    is_non_photo = any(k in style.lower() for k in ('anime', 'cartoon', '3d', 'pixar', 'watercolor', 'oil painting', 'sketch'))
    target_words = max(12, min(48, int(duration * 2.0)))

    default_storyboard = {
        'title': clean[:60],
        'subject': clean,
        'consistency_anchor': f"{clean}, consistent appearance and environment in {style} style",
        'action_sequence': f"1. Establish scene; 2. Core action of {clean}; 3. Clean closing beat",
        'setting': f"Natural environment matching {clean}",
        'style': style,
        'camera_movement': "Smooth slow push-in alternating with gentle horizontal pan",
        'lighting': "Balanced natural golden daylight",
        'color_palette': "Rich organic greens, warm sunlit highlights, crisp shadows",
        'audio': "Calm voiceover + warm ambient music" if audio_mode == 'voiceover' else audio_mode,
        'avoid': ["blurry faces", "deformed hands", "watermarks", "vintage B&W", "text overlays"],
        'narration': f"Watch as {clean} unfolds smoothly in crisp detail." if audio_mode == 'voiceover' else "",
        'search_queries': [] if is_non_photo else [clean[:45]] * n_scenes,
        'scenes': [
            {
                'duration_sec': scene_dur,
                'image_prompt': f"{clean}, consistent character outfit and setting, {style}, scene {i+1}, sharp focus, crisp detail, {aspect_ratio}",
                'caption': clean[:44]
            }
            for i in range(n_scenes)
        ]
    }

    if not text_generator:
        return default_storyboard

    try:
        sb_prompt = (
            f"Create a structured video production prompt & {n_scenes}-scene storyboard strictly matching: \"{clean}\".\n"
            f"Specs: Purpose={purpose}, Duration={duration:.0f}s ({n_scenes} scenes of ~{scene_dur}s each), Aspect={aspect_ratio}, Style={style}, Audio={audio_mode}.\n"
            "STRICT RULES:\n"
            "1. Fix typos (e.g. 'tarctor' -> 'tractor'). Fill ALL fields cleanly: subject, consistency_anchor (character, outfit, and setting description to repeat verbatim across EVERY scene), action_sequence, setting, style, camera_movement, lighting, color_palette, audio, avoid list.\n"
            "2. EVERY scene in 'scenes' MUST start with the exact character, outfit, and setting from consistency_anchor, plus that beat's specific action, camera_movement, lighting, and requested style. Keep image_prompts concrete & uncluttered (never distorted faces/portraits unless requested).\n"
            f"3. Include 'search_queries': {n_scenes} concise 2-to-4-word real photography keywords aligned 1-to-1 with Scenes 1..{n_scenes} ONLY if photographic/cinematic real-world imagery fits; return [] if anime/cartoon/3D/fictional.\n"
            f"4. Keep 'narration' plain spoken text sized cleanly (~{target_words} words max) matching the prompt (or empty string if silent/music only).\n"
            "Return ONLY valid JSON (no markdown fences) matching this exact schema:\n"
            "{\n"
            '  "title": "Short title",\n'
            '  "subject": "Core subject and wardrobe if any",\n'
            '  "consistency_anchor": "Exact character, outfit, and setting locked across all scenes",\n'
            '  "action_sequence": "Step 1 -> Step 2 -> Step 3",\n'
            '  "setting": "Location, props, atmosphere",\n'
            f'  "style": "{style}",\n'
            '  "camera_movement": "Camera motion description",\n'
            '  "lighting": "Lighting description",\n'
            '  "color_palette": "3-5 main colors/tones",\n'
            '  "audio": "Voiceover tone + background audio",\n'
            '  "avoid": ["blurry faces", "watermarks", "off-topic objects", "deformed hands"],\n'
            '  "narration": "Concise spoken voiceover script",\n'
            '  "search_queries": ["q1", "q2", "q3"],\n'
            '  "scenes": [\n'
            '    {"duration_sec": 5.0, "image_prompt": "Detailed visual prompt starting with consistency_anchor", "caption": "3-6 word caption"}\n'
            "  ]\n"
            "}"
        )
        raw = text_generator(sb_prompt)
        match = re.search(r'\{[\s\S]*\}', raw or '')
        if match:
            parsed = json.loads(match.group(0))
            scenes = parsed.get('scenes') or []
            narration = re.sub(r'[*#`_]+', '', (parsed.get('narration') or '')).strip()
            queries = [str(q).strip() for q in (parsed.get('search_queries') or []) if str(q).strip()]
            anchor = (parsed.get('consistency_anchor') or '').strip()
            if len(scenes) >= n_scenes:
                scenes = scenes[:n_scenes]
                # Ensure every scene preserves the locked character/outfit/setting anchor
                if anchor:
                    for sc in scenes:
                        sc.setdefault('duration_sec', scene_dur)
                        ip = sc.get('image_prompt', '')
                        if anchor.lower()[:25] not in ip.lower():
                            sc['image_prompt'] = f"{anchor}. {ip}"
                avoid_list = parsed.get('avoid') or default_storyboard['avoid']
                if isinstance(avoid_list, str):
                    avoid_list = [x.strip() for x in avoid_list.split(',') if x.strip()]
                return {
                    'title': (parsed.get('title') or clean)[:60],
                    'subject': parsed.get('subject') or clean,
                    'consistency_anchor': anchor or default_storyboard['consistency_anchor'],
                    'action_sequence': parsed.get('action_sequence') or default_storyboard['action_sequence'],
                    'setting': parsed.get('setting') or default_storyboard['setting'],
                    'style': parsed.get('style') or style,
                    'camera_movement': parsed.get('camera_movement') or default_storyboard['camera_movement'],
                    'lighting': parsed.get('lighting') or default_storyboard['lighting'],
                    'color_palette': parsed.get('color_palette') or default_storyboard['color_palette'],
                    'audio': parsed.get('audio') or default_storyboard['audio'],
                    'avoid': avoid_list[:6],
                    'narration': narration or default_storyboard['narration'],
                    'search_queries': [] if is_non_photo else queries[:n_scenes],
                    'scenes': scenes,
                }
    except Exception as e:
        print(f"Storyboard generation error: {e}")

    return default_storyboard


def _fit_cover(img, width=1280, height=720):
    """Center-crop and resize image cleanly to target aspect ratio without stretching."""
    return ImageOps.fit(img.convert('RGB'), (width, height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def _encode_jpeg_bytes(img, quality=85):
    buf = io.BytesIO()
    img.convert('RGB').save(buf, format='JPEG', quality=quality)
    return buf.getvalue()


def _verify_image_matches_prompt(img_bytes, prompt_desc, scene_desc='', require_color_photo=True):
    """Use Gemini Vision to verify an image sharply matches the prompt and lacks distortion/vintage defects."""
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env'), override=True)
    api_key = os.getenv('GEMINI_API_KEY')
    if _is_placeholder(api_key):
        return True, 7, ''

    style_rule = (
        "Reject black-and-white/sepia/vintage photos, book scans, bare flower blossoms or leafless winter branches without leaves/fruit, rotten fruit, blurry haze, deformed faces/hands, or off-topic scenes."
        if require_color_photo else
        "Reject blurry haze, unreadable noise, bare blossoms without main fruit/subject, deformed faces or limbs, or completely off-topic objects."
    )
    target_txt = scene_desc.strip() if scene_desc and scene_desc.strip() else prompt_desc
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={api_key}"
    payload = json.dumps({
        'contents': [{'parts': [
            {'text': f"Evaluate if this image sharply and clearly depicts '{target_txt}' (part of a video about '{prompt_desc}'; for picking/cutting fruit actions, accept crisp harvesting/picking by hand OR shears/knife without penalizing if shears are absent). {style_rule} Reply ONLY strict JSON: {{\"match\": true/false, \"score\": 1-10, \"issue\": \"short\"}}"},
            {'inlineData': {'mimeType': 'image/jpeg', 'data': base64.b64encode(img_bytes).decode('ascii')}}
        ]}],
        'generationConfig': {'temperature': 0.1, 'maxOutputTokens': 140}
    }).encode('utf-8')
    try:
        req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(req, timeout=12) as resp:
            body = json.loads(resp.read().decode('utf-8'))
        txt = body.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
        m = re.search(r'\{[\s\S]*\}', txt)
        if m:
            parsed = json.loads(m.group(0))
            score = int(parsed.get('score', 5))
            is_match = bool(parsed.get('match', score >= 6))
            return is_match, score, str(parsed.get('issue', ''))
    except Exception as e:
        print(f"Vision verification skipped ({e})")
    return True, 5, ''


def _search_wikimedia_images(search_queries, prompt_desc, width=1280, height=720, max_candidates=10, max_results=3):
    """Fetch and Vision-verify modern, crisp Wikimedia Commons photos matching the storyboard."""
    if not search_queries:
        return []

    lower_p = prompt_desc.lower()
    skip_words = [w for w in ('blossom', 'flower', 'winter', 'rotten', '191', '192', '193', '194', '195', '196') if w not in lower_p]
    candidates = []
    seen_titles = set()
    for q_idx, q in enumerate(search_queries[:max(3, max_results)]):
        u = (
            "https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrnamespace=6"
            "&gsrsearch=" + urllib.parse.quote(f"{q} filetype:bitmap -1910 -1920 -1912 -1917 -1937 -1951 -archive -survey")
            + "&gsrlimit=6&prop=imageinfo&iiprop=url|mime|size&iiurlwidth=1280&format=json"
        )
        try:
            req = urllib.request.Request(u, headers={'User-Agent': 'LoboRoboMediaBot/1.0 (https://localhost; dev)'})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            for page in (data.get('query') or {}).get('pages', {}).values():
                title = page.get('title', '')
                if not title or title in seen_titles:
                    continue
                if any(sw in title.lower() for sw in skip_words):
                    continue
                seen_titles.add(title)
                ii = (page.get('imageinfo') or [{}])[0]
                mime = ii.get('mime', '')
                iw, ih = ii.get('width', 0), ii.get('height', 0)
                turl = ii.get('thumburl') or ii.get('url')
                if mime in ('image/jpeg', 'image/png') and iw >= 640 and ih >= 480 and turl:
                    candidates.append((q_idx, q, title, turl))
        except Exception as e:
            print(f"Wikimedia search error ({q}): {e}")

    if not candidates:
        return []

    def _fetch_and_score(item):
        q_idx, q, title, turl = item
        try:
            req = urllib.request.Request(turl, headers={'User-Agent': 'LoboRoboMediaBot/1.0 (https://localhost; dev)'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw = resp.read()
            pil_img = _fit_cover(Image.open(io.BytesIO(raw)), width, height)
            chk_w, chk_h = (640, 360) if width >= height else (360, 640)
            check_bytes = _encode_jpeg_bytes(pil_img.resize((chk_w, chk_h), Image.Resampling.LANCZOS), quality=80)
            ok, score, issue = _verify_image_matches_prompt(
                check_bytes, prompt_desc, scene_desc=q, require_color_photo=True
            )
            if ok and score >= 7:
                return (q_idx, score, pil_img, title)
            print(f"Wikimedia candidate rejected ({title}, score={score}): {issue}", flush=True)
        except Exception as e:
            print(f"Wikimedia image fetch error ({title}): {e}")
        return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        scored = [r for r in pool.map(_fetch_and_score, candidates[:max_candidates]) if r is not None]

    scored.sort(key=lambda x: x[1], reverse=True)
    picked = []
    seen_q = set()
    used_imgs = set()
    for item in scored:
        if item[0] not in seen_q:
            seen_q.add(item[0])
            picked.append((item[0], item[2]))
            used_imgs.add(id(item[2]))
    for item in scored:
        if id(item[2]) not in used_imgs:
            picked.append((item[0], item[2]))
            used_imgs.add(id(item[2]))
    return picked[:max_results]


def _make_fallback_scene_image(caption, idx, width=1280, height=720):
    """Create a clean procedural gradient artwork frame if all remote image fetches fail."""
    palettes = [
        ((24, 34, 68), (217, 119, 6)),
        ((20, 52, 65), (16, 185, 129)),
        ((48, 25, 68), (236, 72, 153)),
    ]
    c1, c2 = palettes[idx % len(palettes)]
    y_grad = np.linspace(0.0, 1.0, height, dtype=np.float32)[:, None, None]
    x_grad = np.linspace(0.0, 1.0, width, dtype=np.float32)[None, :, None]
    mix = 0.65 * y_grad + 0.35 * x_grad
    arr = (np.array(c1, dtype=np.float32) * (1.0 - mix) + np.array(c2, dtype=np.float32) * mix).astype(np.uint8)
    img = Image.fromarray(arr, mode='RGB')
    draw = ImageDraw.Draw(img)
    cx, cy = width // 2 + (idx - 1) * 140, height // 2 - 40
    for r, alpha_tone in ((220, 40), (140, 70), (70, 100)):
        col = tuple(min(255, c + alpha_tone) for c in c2)
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=col, width=3)
    return img


def _fetch_pollinations_image(scene_prompt, idx, width=1280, height=720, seed_offset=0):
    """Download a single AI scene image from Pollinations, matching orientation & cropping bottom watermark."""
    if width > height:
        req_w, req_h = 1024, 624
    elif height > width:
        req_w, req_h = 576, 1072
    else:
        req_w, req_h = 768, 816
    encoded = urllib.parse.quote(scene_prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width={req_w}&height={req_h}&nologo=true&seed={211 + idx * 53 + seed_offset}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=28) as resp:
        raw = resp.read()
    img = Image.open(io.BytesIO(raw)).convert('RGB')
    iw, ih = img.size
    if ih > 200:
        img = img.crop((0, 0, iw, ih - 48))
    return _fit_cover(img, width, height)


def _derive_scene_variant(base_img, idx, width=1280, height=720):
    """Create a distinct cinematic framing & lighting variation from a verified scene image."""
    w, h = base_img.size
    if idx == 1:
        crop = base_img.crop((int(w * 0.14), int(h * 0.08), int(w * 0.88), int(h * 0.82)))
        varied = _fit_cover(crop, width, height)
        varied = ImageEnhance.Contrast(varied).enhance(1.06)
        varied = ImageEnhance.Color(varied).enhance(1.08)
        return varied
    crop = base_img.crop((int(w * 0.05), int(h * 0.06), int(w * 0.90), int(h * 0.91)))
    varied = _fit_cover(crop, width, height)
    varied = ImageEnhance.Brightness(varied).enhance(1.03)
    varied = ImageEnhance.Color(varied).enhance(1.05)
    return varied


def _draw_caption_bar(frame_img, caption_text):
    """Overlay a clean translucent subtitle bar onto a 1280x720 PIL Image."""
    if not caption_text:
        return frame_img
    overlay = Image.new('RGBA', frame_img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    w, h = frame_img.size
    bar_h = 64
    draw.rectangle([(0, h - bar_h - 18), (w, h - 18)], fill=(15, 15, 18, 155))

    try:
        font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 28)
    except Exception:
        font = ImageFont.load_default()

    bbox = draw.textbbox((0, 0), caption_text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    tx = max(24, (w - tw) // 2)
    ty = h - bar_h - 18 + (bar_h - th) // 2 - 4
    draw.text((tx, ty), caption_text, fill=(250, 249, 245, 245), font=font)

    composited = Image.alpha_composite(frame_img.convert('RGBA'), overlay)
    return composited.convert('RGB')


def generate_video_with_audio(prompt, output_dir, text_generator=None):
    """Generate an MP4 video following structured prompt, duration/aspect defaults, and multi-scene consistency.

    Returns (video_url, audio_url, summary_markdown).
    """
    if not HAS_FFMPEG:
        raise RuntimeError("imageio-ffmpeg is not installed. Run: pip install imageio-ffmpeg")

    os.makedirs(output_dir, exist_ok=True)
    specs = parse_video_specs(prompt)
    clean_prompt = specs['clean_prompt']
    target_duration = specs['duration']
    aspect_ratio = specs['aspect_ratio']
    width, height = specs['dimensions']
    audio_mode = specs['audio_mode']
    fps = 24

    storyboard = _build_storyboard(clean_prompt, text_generator, specs=specs)
    scenes = storyboard['scenes']
    n_scenes = len(scenes)
    narration = storyboard['narration'] if audio_mode == 'voiceover' else ''
    search_queries = storyboard.get('search_queries') or []

    uid = uuid.uuid4().hex[:10]
    voice_wav = os.path.join(output_dir, f"temp_voice_{uid}.wav")
    mixed_wav_name = f"audio_{uid}.wav"
    mixed_wav = os.path.join(output_dir, mixed_wav_name)
    video_name = f"video_{uid}.mp4"
    video_path = os.path.join(output_dir, video_name)

    def _fetch_verified_hero(seed_offset=0):
        mid_idx = min(1, n_scenes - 1)
        action_prompt = scenes[mid_idx].get('image_prompt') or clean_prompt
        img = _fetch_pollinations_image(action_prompt, mid_idx, width, height, seed_offset=seed_offset)
        chk_w, chk_h = (640, 360) if width >= height else (360, 640)
        chk = _encode_jpeg_bytes(img.resize((chk_w, chk_h), Image.Resampling.LANCZOS), quality=80)
        ok, score, issue = _verify_image_matches_prompt(
            chk, clean_prompt, scenes[mid_idx].get('caption', ''),
            require_color_photo=bool(search_queries)
        )
        print(f"Hero AI vision check: match={ok}, score={score}, issue={issue}", flush=True)
        return img, ok, score

    with ThreadPoolExecutor(max_workers=3) as pool:
        tts_future = pool.submit(_call_gemini_tts, narration, voice_wav) if narration else None
        hero_future = pool.submit(_fetch_verified_hero, 0)
        wiki_future = pool.submit(_search_wikimedia_images, search_queries, clean_prompt, width, height, 10, n_scenes)

        tts_ok = tts_future.result() if tts_future else False
        wiki_imgs = wiki_future.result() or []
        hero_img, hero_ok, hero_score = None, False, 0
        try:
            hero_img, hero_ok, hero_score = hero_future.result()
        except Exception as e:
            print(f"Hero scene fetch error: {e}", flush=True)

    best_hero = (hero_score, hero_img) if hero_img is not None else (0, None)
    if not wiki_imgs and best_hero[0] < 5:
        for wait_s, s_off in ((15, 97), (20, 211)):
            time.sleep(wait_s)
            try:
                retry_img, r_ok, r_score = _fetch_verified_hero(s_off)
                if retry_img is not None and r_score > best_hero[0]:
                    best_hero = (r_score, retry_img)
                if r_ok or r_score >= 7:
                    break
            except Exception as e:
                print(f"Hero retry after {wait_s}s error: {e}", flush=True)

    good_hero = best_hero[1] if best_hero[0] >= 5 else (best_hero[1] if not wiki_imgs else None)
    scene_imgs = [None] * n_scenes
    if good_hero is not None:
        mid_slot = min(1, n_scenes - 1) if wiki_imgs else 0
        scene_imgs[mid_slot] = good_hero

    leftover_wiki = []
    for q_idx, w_img in wiki_imgs:
        if 0 <= q_idx < n_scenes and scene_imgs[q_idx] is None:
            scene_imgs[q_idx] = w_img
        else:
            leftover_wiki.append(w_img)

    w_left_idx = 0
    for idx in range(n_scenes):
        if scene_imgs[idx] is None and w_left_idx < len(leftover_wiki):
            scene_imgs[idx] = leftover_wiki[w_left_idx]
            w_left_idx += 1

    available = [im for im in scene_imgs if im is not None]
    for i in range(n_scenes):
        if scene_imgs[i] is None:
            if available:
                scene_imgs[i] = _derive_scene_variant(available[i % len(available)], i, width, height)
            else:
                scene_imgs[i] = _make_fallback_scene_image(scenes[i].get('caption', ''), i, width, height)

    if narration and not tts_ok:
        tts_ok = _windows_sapi_tts(narration, voice_wav)

    sample_rate = 24000
    if audio_mode == 'silent':
        duration = target_duration
        mixed = np.zeros(int(duration * sample_rate), dtype=np.float32)
        audio_mode_label = "Silent (No Audio)"
    elif tts_ok and os.path.exists(voice_wav):
        voice_samples = _read_wav_as_float(voice_wav, target_rate=sample_rate)
        try:
            os.remove(voice_wav)
        except OSError:
            pass
        pad_pre = np.zeros(int(0.5 * sample_rate), dtype=np.float32)
        pad_post = np.zeros(int(0.6 * sample_rate), dtype=np.float32)
        voice_padded = np.concatenate([pad_pre, voice_samples, pad_post])
        spoken_dur = len(voice_padded) / sample_rate
        duration = max(target_duration, min(28.0, spoken_dur)) if not specs['explicit_duration'] else target_duration
        target_len = int(duration * sample_rate)
        if len(voice_padded) < target_len:
            voice_padded = np.pad(voice_padded, (0, target_len - len(voice_padded)))
        else:
            voice_padded = voice_padded[:target_len]

        bg_music = _synthesize_music_array(clean_prompt, duration=duration, sample_rate=sample_rate)
        mixed = np.clip(voice_padded * 0.90 + bg_music * 0.16, -0.98, 0.98)
        audio_mode_label = "AI Voiceover + Ambient Soundtrack"
    else:
        duration = target_duration
        mixed = _synthesize_music_array(clean_prompt, duration=duration, sample_rate=sample_rate)
        audio_mode_label = "Synthesized Ambient Soundtrack"

    _write_wav_bytes(mixed_wav, (mixed * 32767.0).astype(np.int16), sample_rate=sample_rate)

    # Upscale source scenes slightly (1.12x) so Ken Burns zoom/pan stays sharp
    overscan_w, overscan_h = int(width * 1.12), int(height * 1.12)
    overscan_imgs = [
        img.resize((overscan_w, overscan_h), Image.Resampling.LANCZOS)
        for img in scene_imgs
    ]

    total_frames = int(duration * fps)
    n_scenes = len(overscan_imgs)
    frames_per_scene = total_frames / n_scenes
    fade_frames = int(0.5 * fps)

    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    cmd = [
        ffmpeg_exe, '-y',
        '-f', 'rawvideo',
        '-vcodec', 'rawvideo',
        '-s', f'{width}x{height}',
        '-pix_fmt', 'rgb24',
        '-r', str(fps),
        '-i', '-',
        '-i', mixed_wav,
        '-c:v', 'libx264',
        '-preset', 'fast',
        '-crf', '22',
        '-pix_fmt', 'yuv420p',
        '-c:a', 'aac',
        '-b:a', '128k',
        '-shortest',
        '-movflags', '+faststart',
        video_path
    ]

    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    def render_scene_frame(sc_idx, progress):
        base = overscan_imgs[sc_idx]
        # Subpixel-accurate alternate zoom-in / zoom-out + gentle horizontal pan
        if sc_idx % 2 == 0:
            scale = 1.0 + 0.10 * progress
            pan_x = progress
        else:
            scale = 1.10 - 0.10 * progress
            pan_x = 1.0 - progress

        view_w = overscan_w / scale
        view_h = overscan_h / scale
        step_x = view_w / width
        step_y = view_h / height
        x0 = max(0.0, (overscan_w - view_w) * pan_x)
        y0 = max(0.0, (overscan_h - view_h) * 0.5)
        frame = base.transform(
            (width, height),
            Image.Transform.AFFINE,
            (step_x, 0.0, x0, 0.0, step_y, y0),
            resample=Image.Resampling.BICUBIC
        )
        return _draw_caption_bar(frame, scenes[sc_idx].get('caption', ''))

    for f_idx in range(total_frames):
        sc_pos = f_idx / frames_per_scene
        sc_idx = min(n_scenes - 1, int(sc_pos))
        local_f = f_idx - sc_idx * frames_per_scene
        progress = min(1.0, max(0.0, local_f / frames_per_scene))

        frame_img = render_scene_frame(sc_idx, progress)

        # Crossfade smoothly into next scene near boundary
        if sc_idx < n_scenes - 1 and local_f > (frames_per_scene - fade_frames):
            alpha = (local_f - (frames_per_scene - fade_frames)) / fade_frames
            next_img = render_scene_frame(sc_idx + 1, 0.0)
            frame_img = Image.blend(frame_img, next_img, min(1.0, max(0.0, alpha)))

        proc.stdin.write(frame_img.tobytes())

    proc.stdin.close()
    stderr_out = proc.stderr.read().decode('utf-8', errors='replace')
    ret = proc.wait()
    if ret != 0:
        raise RuntimeError(f"FFmpeg video encoding failed (exit {ret}): {stderr_out[-400:]}")

    video_url = f"/static/generated/{video_name}"
    audio_url = None if audio_mode == 'silent' else f"/static/generated/{mixed_wav_name}"
    if audio_mode == 'silent' and os.path.exists(mixed_wav):
        try:
            os.remove(mixed_wav)
        except OSError:
            pass

    avoid_raw = storyboard.get('avoid') or []
    avoid_str = ', '.join(str(x) for x in avoid_raw) if isinstance(avoid_raw, list) else str(avoid_raw)
    palette_raw = storyboard.get('color_palette') or ''
    palette_str = ', '.join(str(x) for x in palette_raw) if isinstance(palette_raw, list) else str(palette_raw)
    per_scene_sec = duration / n_scenes
    scene_lines = "\n".join(
        f"  - Scene {i + 1} ({per_scene_sec:.1f}s): {sc.get('caption', '')} — *{sc.get('image_prompt', '')[:120]}*"
        for i, sc in enumerate(scenes)
    )
    summary = (
        f"Here is your generated video for: **{clean_prompt}**\n\n"
        f"- **Specs:** `{aspect_ratio}` ({width}x{height}), `{duration:.1f}s` ({n_scenes} scenes @ `{per_scene_sec:.1f}s` each), **{storyboard.get('style', specs['style'])}**\n"
        f"- **Audio:** {audio_mode_label}"
        + (f' — *"{narration}"*' if narration else '') + "\n\n"
        f"**Final Video Prompt**\n"
        f"- **Subject:** {storyboard.get('subject', clean_prompt)}\n"
        f"- **Action Sequence:** {storyboard.get('action_sequence', clean_prompt)}\n"
        f"- **Setting:** {storyboard.get('setting', '')}\n"
        f"- **Camera & Style:** {storyboard.get('camera_movement', '')} ({storyboard.get('style', specs['style'])})\n"
        f"- **Lighting & Colors:** {storyboard.get('lighting', '')} | {palette_str}\n"
        f"- **Audio Plan:** {storyboard.get('audio', audio_mode_label)}\n"
        f"- **Avoid:** {avoid_str}\n"
        f"- **Scenes (Consistent Character/Setting):**\n{scene_lines}"
    )
    return video_url, audio_url, summary
