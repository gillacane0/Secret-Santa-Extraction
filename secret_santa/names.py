def normalize(name: str) -> str:
    """Make names comparable ignoring case and extra spaces: ' anna  MARIA ' -> 'anna maria'."""
    return " ".join(name.split()).casefold()
