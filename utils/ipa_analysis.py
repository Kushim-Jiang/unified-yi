"""
IPA character analysis for Unified Yi book TSV files.
Scans all pronunciation fields and reports:
  1. Every non-ASCII character with frequency
  2. Common digraph patterns (tie-bar affricates, prenasalization)
  3. Tone distribution
  4. Generates an ASCII → IPA mapping table for data entry
"""

import re
from pathlib import Path
from collections import Counter

BOOK_DIR = Path(__file__).parent.parent / "book"
IPA_CHAR_CACHE = Counter()
TONE_COUNTER = Counter()
PRON_LENGTHS = Counter()

# Collect all pronunciation fields
all_prons = []
for tsv_file in sorted(BOOK_DIR.glob("*.tsv")):
    with open(tsv_file, encoding="utf-8") as f:
        lines = f.readlines()
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            pron = parts[2].strip()
            if pron:
                all_prons.append(pron)
                for char in pron:
                    if ord(char) > 127:
                        IPA_CHAR_CACHE[char] += 1
                # Count tones (superscript numbers)
                tones = re.findall(r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+", pron)
                for t in tones:
                    TONE_COUNTER[t] += 1
                PRON_LENGTHS[len(pron)] += 1

print("=" * 70)
print("  📊 UNIFIED YI — IPA CHARACTER ANALYSIS")
print("=" * 70)

print(f"\n📁 Files scanned: {len(list(BOOK_DIR.glob('*.tsv')))}")
print(f"🔤 Total pronunciation entries: {len(all_prons)}")
print(f"🔣 Unique non-ASCII chars: {len(IPA_CHAR_CACHE)}")

# ── 1. All non-ASCII characters sorted by frequency ──
print(f"\n{'─'*70}")
print("  🏆 IPA CHARACTER FREQUENCY TABLE")
print(f"{'─'*70}")
print(f"{'Char':<10} {'Unicode':<12} {'Name':<42} {'Count':<8} {'Pct':<8}")
print(f"{'─'*70}")
total = sum(IPA_CHAR_CACHE.values())
prev_cat = None
for char, count in IPA_CHAR_CACHE.most_common():
    try:
        import unicodedata

        name = unicodedata.name(char, "UNKNOWN")
    except:
        name = "UNKNOWN"
    cp = ord(char)
    pct = count / total * 100

    # Categorize
    if 0x0300 <= cp <= 0x036F:
        cat = "◌ Combining diacritic"
    elif 0x02B0 <= cp <= 0x02FF:
        cat = "˔ Spacing modifier"
    elif 0x2070 <= cp <= 0x209F:
        cat = "⁰ Superscript"
    elif 0x1D00 <= cp <= 0x1D7F:
        cat = "ᴀ Phonetic extension"
    elif 0x0250 <= cp <= 0x02AF:
        cat = "ɑ IPA extension"
    else:
        cat = "Other"

    if cat != prev_cat:
        print(f"  --- {cat} ---")
        prev_cat = cat
    print(f"  {char:<8} U+{cp:04X}   {name:<42} {count:<8} {pct:.1f}%")

# ── 2. Tone distribution ──
print(f"\n{'─'*70}")
print("  🎵 TONE MARK DISTRIBUTION")
print(f"{'─'*70}")
for tone, cnt in TONE_COUNTER.most_common():
    print(f"  {tone:<12} → {cnt} occurrences")

# ── 3. Common affricate + prenasalization patterns ──
print(f"\n{'─'*70}")
print("  🔗 COMMON AFFRICATE & PRENASALIZATION PATTERNS")
print(f"{'─'*70}")
patterns = Counter()
for p in all_prons:
    # Find tie-bar sequences
    for m in re.finditer(
        r"[ⁿᵐᶰᶮᶯ][tdkgbdjzcsrl]?[ʰʱ]?"
        r"(?:[tcdjszrl][͜͡][ʰʱ]?[ɕʑʂʐszrltdc])?"
        r"[aeiouɑɛɔɤɯɚəɨʉɿʅ]+"
        r"[̰̤̹̜]?"
        r"[⁰¹²³⁴⁵⁶⁷⁸⁹]+",
        p,
    ):
        patterns[m.group()] += 1
for pat, cnt in patterns.most_common(30):
    print(f"  {pat:<20} × {cnt}")

# ── 4. Generate ASCII→IPA mapping ──
print(f"\n{'='*70}")
print("  ⌨️  ASCII → IPA INPUT METHOD MAPPING")
print(f"{'='*70}")
print("""
Use these ASCII sequences in the pronunciation field.
The mapping is applied during auto-formatting.

  ┌───────────────┬──────────┬──────────────────────────────┐
  │ ASCII Input   │ IPA Out  │ Description                  │
  ├───────────────┼──────────┼──────────────────────────────┤""")

# Generate the mapping table
mapping = [
    # Glottal
    ("?", "ʔ", "Glottal stop"),
    # Velar / uvular
    ("ng", "ŋ", "Velar nasal"),
    ("G", "ŋ", "Velar nasal (alt)"),
    ("gh", "ɣ", "Voiced velar fricative"),
    # Palatal
    ("ny", "ɲ", "Palatal nasal"),
    ("J", "ɲ", "Palatal nasal (Sinological)"),
    ("sh", "ɕ", "Voiceless palatal fricative"),
    ("zh", "ʑ", "Voiced palatal fricative"),
    # Retroflex
    ("sr", "ʂ", "Voiceless retroflex fricative"),
    ("zr", "ʐ", "Voiced retroflex fricative"),
    ("tr", "ʈ", "Voiceless retroflex stop"),
    ("dr", "ɖ", "Voiced retroflex stop"),
    # Lateral
    ("lh", "ɬ", "Voiceless lateral fricative"),
    # Special vowels
    ("eu", "ɯ", "Close back unrounded vowel"),
    ("ox", "ɤ", "Close-mid back unrounded vowel"),
    ("eh", "ɛ", "Open-mid front unrounded vowel"),
    ("oh", "ɔ", "Open-mid back rounded vowel"),
    ("ah", "ɑ", "Open back unrounded vowel"),
    ("@", "ɚ", "Rhotacized schwa"),
    ("ix", "ɿ", "Apical vowel (dzi)"),
    ("yx", "ʅ", "Apical vowel (dzhʅ)"),
    # Tie bar for affricates
    ("_", "͡", "Tie bar (between consonants)"),
    # Tone (digits after syllable → superscript)
    ("1", "¹", "Tone 1 (superscript)"),
    ("2", "²", "Tone 2 (superscript)"),
    ("3", "³", "Tone 3 (superscript)"),
    ("4", "⁴", "Tone 4 (superscript)"),
    ("5", "⁵", "Tone 5 (superscript)"),
]

for ascii_in, ipa_out, desc in mapping:
    print(f"  │ {ascii_in:<13} │ {ipa_out:<8} │ {desc:<28} │")

print("""  └───────────────┴──────────┴──────────────────────────────┘""")

print(f"\n{'='*70}")
print("  💡 TYPING EXAMPLES")
print(f"{'='*70}")
examples = [
    ("t_h_e55", "t͡ɕʰe⁵⁵", "t + tiebar + c + h + e + 55"),
    ("k_h_oh33", "kʰɔ³³", "k + h + oh(ɔ) + 33"),
    ("Ndz_h_eu21", "ⁿd͡zʰɯ²¹", "N(prenasal) + dz + h + eu(ɯ) + 21"),
    ("Ndr_h_eh21", "ⁿd͡ʐʰɛ²¹", "N + dr + h + eh(ɛ) + 21"),
    ("Jih55", "ɲi⁵⁵", "J(ɲ) + i + h(ʰ) + 55"),
    ("ghoh21", "ɣɔ²¹", "gh(ɣ) + oh(ɔ) + 21"),
    ("?eh55", "ʔɛ⁵⁵", "glottal + eh(ɛ) + 55"),
    ("lhoh55", "ɬɔ⁵⁵", "lh(ɬ) + oh(ɔ) + 55"),
    ("sr~21", "ʂ̰²¹", "sr(ʂ) + ~(creaky) + 21"),
]

print(f"\n{'ASCII Input':<30} {'IPA Output':<20} {'Notes'}")
print(f"{'─'*70}")
for ascii_in, ipa_out, notes in examples:
    print(f"  {ascii_in:<28} {ipa_out:<20} {notes}")

print(f"\n{'─'*70}")
print("✅ Analysis complete. Copy the mapping into entry.js as needed.")
