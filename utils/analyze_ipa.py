"""Analyze IPA characters used in all book TSV files and generate ASCII replacement mappings."""

import re
from collections import Counter
from pathlib import Path

BOOK_DIR = Path(__file__).parent.parent / "book"
IPA_PATTERN = re.compile(
    r"[ⁿᵐᶰᵑᶮᶯᶬᵑᵐʰʱʷʲˠˤ]"  # modifiers
    r"|[æɑɒɐʌɔɜəɛɝɞɵœɶøɤɨɪʉʊɯɘɯɤ]"  # vowels
    r"|[βðʒʝɣʁʕʖħɦʢʡʔʘ]"  # consonants
    r"|[çʍχʃɕʑʐʂʈɖɟɠɢɴɲɳŋɱɯ]"  # more consonants
    r"|[ɓɗɠʄɢ]"  # implosives
    r"|[ǀǁǃǂ]"  # clicks
    r"|[ɬɮ]"  # laterals
    r"|[ʰʱʷʲˠˤ]"  # diacritics as separate
    r"|[̴̵̶̷̸̰̥̩̯̤̪̺̻̼̹̍̾˞]"  # combining diacritics
    r"|[ˈˌːˑ]"  # prosody
    r"|[˥˦˧˨˩]"  # tone letters
    r"|[⁵⁴³²¹⁰]"  # superscript tone numbers
    r"|[t͡sɖʐd͡ʐd͡zʈʂt͡ɕd͡ʑɕʑt͡ʃd͡ʒ]"  # affricates (base chars)
    r"|[͜͡]"  # tie bars
    r"|[ɹɻɾʁʀɾ]"  # rhotics
    r"|[ʎʟ]"  # laterals
)

# All IPA characters we've seen
all_ipa_chars = Counter()

for tsv_file in sorted(BOOK_DIR.glob("*.tsv")):
    with open(tsv_file, encoding="utf-8") as f:
        lines = f.readlines()
    for line in lines[1:]:  # skip header
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            pron = parts[2]  # pronunciation column
            # Split multi-pronunciation by /
            for p in pron.split("/"):
                p = p.strip()
                for char in p:
                    if ord(char) > 127:
                        all_ipa_chars[char] += 1

print("=== IPA Characters Used (non-ASCII) ===")
print(f"{'Char':<8} {'Unicode':<10} {'Name':<40} {'Count':<8}")
print("-" * 66)
# Sort by frequency
for char, count in all_ipa_chars.most_common():
    try:
        import unicodedata

        name = unicodedata.name(char, "UNKNOWN")
    except:
        name = "UNKNOWN"
    print(f"{char:<8} U+{ord(char):04X}  {name:<40} {count:<8}")

print(f"\nTotal unique IPA characters: {len(all_ipa_chars)}")

# Now also collect ALL distinct pronunciation strings to find patterns
print("\n\n=== All unique pronunciation strings (sample) ===")
all_prons = set()
for tsv_file in sorted(BOOK_DIR.glob("*.tsv")):
    with open(tsv_file, encoding="utf-8") as f:
        lines = f.readlines()
    for line in lines[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            pron = parts[2]
            if pron:
                all_prons.add(pron)

print(f"Total unique pronunciation strings: {len(all_prons)}")
for p in sorted(all_prons)[:50]:
    print(f"  {p}")
