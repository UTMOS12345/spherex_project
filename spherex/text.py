"""Small helpers for the text the user sees. No imports, so any module can use them."""


def plural(n, word, many=None):
    """'1 frame', '2 frames'. Use many= for irregular plurals."""
    return f"{n} {word if n == 1 else (many or word + 's')}"
