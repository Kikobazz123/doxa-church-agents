"""Build the English word list the announcer uses to tell English words from Nigerian ones.

    pip install wordfreq
    python tools/build_wordlist.py 100000 > english_words_ranked.txt

Prints the top N English words (lower case, letters only) in frequency order.
Run by the "Build word list" workflow; the cut-off used by the bot is chosen
from this ranking and committed as announcer/data/english_words.txt.
"""

import sys

from wordfreq import top_n_list

n = int(sys.argv[1]) if len(sys.argv) > 1 else 100_000
seen = set()
for word in top_n_list("en", n * 2):
    if word.isalpha() and word.isascii() and len(word) > 1 and word not in seen:
        seen.add(word)
        print(word)
        if len(seen) >= n:
            break
