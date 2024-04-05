def initial_cleaning(headline):
    replacements: dict[str, str] = {
        # smart quotes
        "“": '"',
        "”": '"',
        "’": "'",
        "‘": "'",
        # long dashes
        "—": "--",
        "–": "--",
        "−": "--",
    }
    for pat, repl in replacements.items():
        headline = headline.replace(pat, repl)
    return headline