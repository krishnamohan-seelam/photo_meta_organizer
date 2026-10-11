"""Domain types for AI analysis (Phase 5): embeddings, suggested tags and their rules."""

import math

import pytest

from photo_meta_organizer.domain.analysis import (
    AiTag,
    AiTagStatus,
    Embedding,
    ScoredPhoto,
    normalize,
)


class TestNormalize:
    def test_scales_to_unit_length(self):
        assert normalize([3.0, 4.0]) == pytest.approx((0.6, 0.8))

    def test_unit_vectors_are_unchanged(self):
        assert normalize([1.0, 0.0]) == (1.0, 0.0)

    @pytest.mark.parametrize("bad", [[], [0.0, 0.0], [1.0, math.nan], [math.inf, 1.0]])
    def test_rejects_vectors_that_have_no_direction(self, bad):
        with pytest.raises(ValueError):
            normalize(bad)


class TestEmbedding:
    def test_holds_an_immutable_vector(self):
        e = Embedding(file_hash="h", model_id="m", vector=[0.5, 0.5])
        assert e.vector == (0.5, 0.5)
        assert e.dimension == 2

    @pytest.mark.parametrize("field", ["file_hash", "model_id"])
    def test_identity_fields_are_required(self, field):
        values = {"file_hash": "h", "model_id": "m", "vector": [1.0]}
        values[field] = " "
        with pytest.raises(ValueError, match=field):
            Embedding(**values)

    def test_rejects_an_unusable_vector(self):
        with pytest.raises(ValueError):
            Embedding(file_hash="h", model_id="m", vector=[0.0])


class TestAiTag:
    def test_defaults_to_suggested_and_strips_the_label(self):
        tag = AiTag(label="  beach ", confidence=0.4, model_id="m")
        assert tag.label == "beach"
        assert tag.status is AiTagStatus.SUGGESTED

    @pytest.mark.parametrize("confidence", [-0.1, 1.1, math.nan])
    def test_confidence_is_a_probability(self, confidence):
        with pytest.raises(ValueError, match="confidence"):
            AiTag(label="beach", confidence=confidence, model_id="m")

    def test_label_follows_the_user_tag_rules(self):
        with pytest.raises(ValueError):
            AiTag(label="  ", confidence=0.5, model_id="m")

    def test_status_parses_from_its_stored_text(self):
        assert AiTagStatus("accepted") is AiTagStatus.ACCEPTED
        with pytest.raises(ValueError):
            AiTagStatus("maybe")


def test_scored_photo_is_a_plain_pair():
    assert ScoredPhoto(file_hash="h", score=0.9).score == 0.9
