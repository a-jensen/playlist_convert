from dataclasses import dataclass

from rapidfuzz import fuzz

from playlist_convert.models import Track


@dataclass
class MatchResult:
    source_track: Track
    matched_track: Track | None
    confidence: float   # 0.0–1.0
    method: str         # "isrc" | "fuzzy" | "none"


def _score(source: Track, candidate: Track) -> float:
    title_score = fuzz.token_sort_ratio(source.title, candidate.title)
    artist_score = fuzz.token_sort_ratio(source.artist, candidate.artist)
    return 0.6 * title_score + 0.4 * artist_score


def match_track(source: Track, candidates: list[Track], threshold: float = 85.0) -> MatchResult:
    """
    Pick the best matching track from candidates.

    Tries ISRC exact match first, then falls back to fuzzy title+artist matching.
    Returns a MatchResult with method="none" if no candidate meets the threshold.
    """
    if not candidates:
        return MatchResult(source_track=source, matched_track=None, confidence=0.0, method="none")

    # ISRC exact match — globally unique identifier
    if source.isrc:
        for candidate in candidates:
            if candidate.isrc and candidate.isrc.upper() == source.isrc.upper():
                return MatchResult(
                    source_track=source,
                    matched_track=candidate,
                    confidence=1.0,
                    method="isrc",
                )

    # Fuzzy text match
    best_candidate = max(candidates, key=lambda c: _score(source, c))
    best_score = _score(source, best_candidate)

    if best_score >= threshold:
        return MatchResult(
            source_track=source,
            matched_track=best_candidate,
            confidence=best_score / 100.0,
            method="fuzzy",
        )

    return MatchResult(source_track=source, matched_track=None, confidence=0.0, method="none")
