"""Rebuild plain-text abstracts from OpenAlex inverted indexes."""


def reconstruct_abstract(inverted_index: dict | None) -> str | None:
    """Turn an OpenAlex ``abstract_inverted_index`` into a readable string.

    OpenAlex does not return the abstract as a paragraph. It returns a map
    from each word to the positions where that word appears::

        {"Graph": [0], "neural": [1], "networks": [2]}

    Positions are zero-based word indexes. The same word can appear more
    than once. This function places every word at its index and joins them
    in order. It returns None when there is nothing to rebuild.
    """
    if not isinstance(inverted_index, dict) or not inverted_index:
        return None

    placed: list[tuple[int, str]] = []
    for token, positions in inverted_index.items():
        word = "" if token is None else str(token).strip()
        if not word:
            continue
        for position in _positions(positions):
            placed.append((position, word))

    if not placed:
        return None

    placed.sort(key=lambda item: item[0])
    abstract = " ".join(word for _, word in placed).strip()
    return abstract or None


def _positions(value: object) -> list[int]:
    """Normalize one inverted-index entry into a list of integer positions."""
    if isinstance(value, bool):
        return []
    if isinstance(value, int):
        return [value]
    if not isinstance(value, (list, tuple)):
        return []

    positions: list[int] = []
    for item in value:
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            positions.append(item)
            continue
        if isinstance(item, str) and item.strip().lstrip("-").isdigit():
            positions.append(int(item.strip()))
    return positions
