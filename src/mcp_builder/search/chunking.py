"""Markdown sections; code fences remain balanced in indexed fragments."""

import re

CHUNK_BYTES = 1800


def utf8_size(value: str) -> int:
    """Return the deterministic UTF-8 byte budget used without a local tokenizer."""
    return len(value.encode("utf-8"))


def sections(markdown: str) -> list[tuple[str, str]]:
    """Return ordered (heading, original text) pairs from Markdown.

    Headings inside fenced code are ignored. Text before the first heading
    is labelled Introduction; heading lines remain in the returned content.
    """
    result, lines = [], []
    heading = "Introduction"
    fence = None
    for line in markdown.splitlines(keepends=True):
        marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
        if marker:
            run = marker.group(1)
            if fence is None:
                fence = run
            elif run[0] == fence[0] and len(run) >= len(fence):
                fence = None
        match = re.match(r"^(#{1,6})\s+(.+?)\s*#*\s*$", line) if not fence else None
        if match:
            if lines and "".join(lines).strip():
                result.append((heading, "".join(lines)))
            heading, lines = match.group(2), []
        lines.append(line)
    if lines and "".join(lines).strip():
        result.append((heading, "".join(lines)))
    return result


def chunks(markdown: str, limit: int = CHUNK_BYTES):
    """Yield (section, content); raw page is retained separately without modifications.

    Oversize code blocks are split at lines and reopened with their original fence.
    Pathological long lines are bisected rather than silently truncated.
    """
    for heading, section in sections(markdown):
        current = ""
        fence = None
        opening = ""
        lines = section.splitlines(keepends=True)
        for position, line in enumerate(lines):
            marker = re.match(r"^\s{0,3}(`{3,}|~{3,})", line)
            if marker and fence is None:
                run = marker.group(1)
                block_lines = [line]
                for following in lines[position + 1:]:
                    block_lines.append(following)
                    closing = re.match(r"^\s{0,3}(`{3,}|~{3,})\s*$", following)
                    if closing and closing.group(1)[0] == run[0] and len(closing.group(1)) >= len(run):
                        break
                block = "".join(block_lines)
                # Move a normal-sized block as a unit rather than splitting it just
                # because the preceding prose consumed the current passage budget.
                if (current.strip() and utf8_size(block) <= limit
                        and utf8_size(current + block) > limit):
                    yield heading, current
                    current = ""
            next_fence, next_opening = fence, opening
            if marker:
                run = marker.group(1)
                if fence is None:
                    next_fence, next_opening = run, line
                elif run[0] == fence[0] and len(run) >= len(fence):
                    next_fence, next_opening = None, ""
            suffix = "\n" + next_fence + "\n" if next_fence else ""
            if utf8_size(current + line + suffix) <= limit:
                current += line
            else:
                if current.strip():
                    yield heading, current + ("\n" + fence + "\n" if fence else "")
                current = opening if fence else ""
                remaining = line
                while utf8_size(current + remaining + suffix) > limit:
                    lo, hi = 0, len(remaining)
                    while lo < hi:
                        mid = (lo + hi + 1) // 2
                        if utf8_size(current + remaining[:mid] + suffix) <= limit:
                            lo = mid
                        else:
                            hi = mid - 1
                    if lo == 0:
                        raise ValueError("Markdown fence too long for the model")
                    yield heading, current + remaining[:lo] + suffix
                    remaining = remaining[lo:]
                    current = next_opening if next_fence else ""
                current += remaining
            fence, opening = next_fence, next_opening
        if current.strip():
            yield heading, current + ("\n" + fence + "\n" if fence else "")
