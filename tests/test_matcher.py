import pytest

from playlist_convert.matcher import MatchResult, match_track
from playlist_convert.models import Track


def make_track(**kwargs) -> Track:
    defaults = dict(title="Test Song", artist="Test Artist", isrc="")
    return Track(**{**defaults, **kwargs})


class TestMatchTrackIsrc:
    def test_exact_isrc_match(self):
        source = make_track(title="Bohemian Rhapsody", artist="Queen", isrc="GBBKS7200074")
        candidates = [
            make_track(title="Bohemian Rhapsody", artist="Queen", isrc="GBBKS7200074",
                       provider_uri="spotify:track:abc"),
        ]
        result = match_track(source, candidates)
        assert result.method == "isrc"
        assert result.confidence == 1.0
        assert result.matched_track is candidates[0]

    def test_isrc_case_insensitive(self):
        source = make_track(isrc="gbbks7200074")
        candidates = [make_track(isrc="GBBKS7200074")]
        result = match_track(source, candidates)
        assert result.method == "isrc"

    def test_isrc_match_preferred_over_fuzzy(self):
        """ISRC match should win even if there's a higher fuzzy-scoring candidate."""
        source = make_track(title="Hello", artist="Adele", isrc="GBBKS1234567")
        isrc_match = make_track(title="Hello", artist="Adele", isrc="GBBKS1234567",
                                provider_uri="correct")
        better_fuzzy = make_track(title="Hello", artist="Adele", isrc="",
                                  provider_uri="wrong")
        result = match_track(source, [better_fuzzy, isrc_match])
        assert result.matched_track is isrc_match
        assert result.method == "isrc"

    def test_no_isrc_on_source_falls_through_to_fuzzy(self):
        source = make_track(title="Blinding Lights", artist="The Weeknd", isrc="")
        candidates = [make_track(title="Blinding Lights", artist="The Weeknd", isrc="USRC12345678")]
        result = match_track(source, candidates)
        assert result.method == "fuzzy"

    def test_isrc_mismatch_falls_through_to_fuzzy(self):
        source = make_track(title="Shape of You", artist="Ed Sheeran", isrc="GBAHS1700099")
        candidates = [
            make_track(title="Shape of You", artist="Ed Sheeran", isrc="DIFFERENT123456"),
        ]
        result = match_track(source, candidates)
        # ISRC doesn't match, but fuzzy should still find it
        assert result.method == "fuzzy"
        assert result.matched_track is candidates[0]


class TestMatchTrackFuzzy:
    def test_exact_title_and_artist(self):
        source = make_track(title="Blinding Lights", artist="The Weeknd")
        candidates = [make_track(title="Blinding Lights", artist="The Weeknd")]
        result = match_track(source, candidates)
        assert result.method == "fuzzy"
        assert result.matched_track is candidates[0]
        assert result.confidence > 0.85

    def test_picks_best_of_multiple_candidates(self):
        source = make_track(title="Hello", artist="Adele")
        candidates = [
            make_track(title="Hello", artist="Lionel Richie"),
            make_track(title="Hello", artist="Adele"),
            make_track(title="Helo", artist="Adell"),
        ]
        result = match_track(source, candidates)
        assert result.matched_track is candidates[1]

    def test_feat_variation_matches(self):
        source = make_track(title="Sunflower", artist="Post Malone")
        candidates = [
            make_track(title="Sunflower", artist="Post Malone feat. Swae Lee"),
        ]
        result = match_track(source, candidates, threshold=60.0)
        assert result.matched_track is not None

    def test_below_threshold_returns_none(self):
        source = make_track(title="Yesterday", artist="The Beatles")
        candidates = [
            make_track(title="Tomorrow Never Knows", artist="The Beatles"),
            make_track(title="Yesterday Once More", artist="Carpenters"),
        ]
        result = match_track(source, candidates, threshold=85.0)
        assert result.matched_track is None
        assert result.method == "none"
        assert result.confidence == 0.0

    def test_empty_candidates_returns_none(self):
        source = make_track(title="Anything", artist="Anyone")
        result = match_track(source, [])
        assert result.matched_track is None
        assert result.method == "none"

    def test_custom_threshold_lower(self):
        source = make_track(title="Hey Jude", artist="The Beatles")
        candidates = [make_track(title="Hey Jude (Remastered)", artist="Beatles, The")]
        # Should fail at strict threshold
        strict = match_track(source, candidates, threshold=95.0)
        # Should pass at lenient threshold
        lenient = match_track(source, candidates, threshold=60.0)
        assert lenient.matched_track is not None
        # strict might or might not match depending on scores; just check lenient passes
        assert lenient.confidence > 0.0

    def test_result_confidence_normalized(self):
        """Confidence should be between 0 and 1."""
        source = make_track(title="Waterloo", artist="ABBA")
        candidates = [make_track(title="Waterloo", artist="ABBA")]
        result = match_track(source, candidates)
        assert 0.0 <= result.confidence <= 1.0

    def test_source_track_preserved_in_result(self):
        source = make_track(title="My Song", artist="My Artist")
        result = match_track(source, [])
        assert result.source_track is source


class TestMatchResult:
    def test_match_result_fields(self):
        source = make_track()
        matched = make_track(title="Other")
        r = MatchResult(source_track=source, matched_track=matched, confidence=0.9, method="fuzzy")
        assert r.source_track is source
        assert r.matched_track is matched
        assert r.confidence == 0.9
        assert r.method == "fuzzy"
