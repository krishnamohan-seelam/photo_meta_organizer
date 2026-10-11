"""ZeroShotTagger: suggest labels for a photo from its image vector (ADR-002 decision 7)."""

from collections.abc import Sequence
from typing import BinaryIO

import pytest

from photo_meta_organizer.application.tag_vocabulary import VOCABULARY
from photo_meta_organizer.application.zero_shot_tagger import ZeroShotTagger
from photo_meta_organizer.domain.analysis import AiTagStatus
from photo_meta_organizer.domain.curation import validate_tag

LABELS = ["beach", "sea", "city", "dog", "forest"]


class AxisEmbedder:
    """Text vectors are one-hot per label, so which label an image vector 'means' is exact."""

    def __init__(self, labels=LABELS, model_id="axis-v1"):
        self.labels = list(labels)
        self._model_id = model_id
        self.text_calls: list[str] = []

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimension(self) -> int:
        return len(self.labels)

    def embed_text(self, text: str) -> Sequence[float]:
        self.text_calls.append(text)
        words = text.split()
        return [1.0 if name in words else 0.0 for name in self.labels]

    def embed_image(self, stream: BinaryIO, filename: str) -> Sequence[float]:
        raise NotImplementedError

    def image(self, **weights: float) -> list[float]:
        return [weights.get(name, 0.0) for name in self.labels]


@pytest.fixture
def embedder():
    return AxisEmbedder()


@pytest.fixture
def tagger(embedder):
    return ZeroShotTagger(embedder, LABELS)


class TestSuggest:
    def test_ranks_labels_by_similarity_most_confident_first(self, embedder, tagger):
        tags = tagger.suggest(embedder.image(beach=1.0, sea=0.6, city=0.1), limit=3, threshold=0.0)
        assert [t.label for t in tags] == ["beach", "sea", "city"]
        assert tags[0].confidence > tags[1].confidence > tags[2].confidence

    def test_tags_are_suggestions_stamped_with_the_model(self, embedder, tagger):
        tag, *_ = tagger.suggest(embedder.image(dog=1.0), limit=1, threshold=0.0)
        assert tag.status is AiTagStatus.SUGGESTED
        assert tag.model_id == "axis-v1"
        assert 0.0 < tag.confidence <= 1.0

    def test_confidences_are_a_probability_distribution(self, embedder, tagger):
        tags = tagger.suggest(embedder.image(beach=1.0, sea=0.5), limit=10, threshold=0.0)
        assert sum(t.confidence for t in tags) == pytest.approx(1.0, abs=1e-5)

    def test_limit_caps_the_number_of_tags(self, embedder, tagger):
        tags = tagger.suggest(embedder.image(beach=1.0, sea=0.9, city=0.8), limit=2, threshold=0.0)
        assert len(tags) == 2

    def test_threshold_drops_unlikely_labels(self, embedder, tagger):
        image = embedder.image(beach=1.0)
        assert [t.label for t in tagger.suggest(image, limit=5, threshold=0.5)] == ["beach"]

    def test_nothing_clears_a_threshold_when_the_image_matches_nothing_in_particular(
        self, embedder, tagger
    ):
        flat = embedder.image(beach=1, sea=1, city=1, dog=1, forest=1)
        assert tagger.suggest(flat, limit=5, threshold=0.5) == []

    def test_the_length_of_the_image_vector_does_not_matter(self, embedder, tagger):
        small = tagger.suggest(embedder.image(beach=0.01, sea=0.006), limit=2, threshold=0.0)
        large = tagger.suggest(embedder.image(beach=100, sea=60), limit=2, threshold=0.0)
        assert [t.label for t in small] == [t.label for t in large]
        assert small[0].confidence == pytest.approx(large[0].confidence)

    def test_a_vector_of_the_wrong_size_is_an_error(self, tagger):
        with pytest.raises(ValueError, match="dimension"):
            tagger.suggest([1.0, 0.0], limit=3, threshold=0.0)

    def test_a_vector_with_no_direction_is_an_error(self, tagger):
        with pytest.raises(ValueError):
            tagger.suggest([0.0] * len(LABELS), limit=3, threshold=0.0)


class TestLabelVectors:
    def test_each_label_is_embedded_once_as_a_photo_of_a_label(self, embedder, tagger):
        tagger.suggest(embedder.image(beach=1.0), limit=1, threshold=0.0)
        tagger.suggest(embedder.image(sea=1.0), limit=1, threshold=0.0)
        assert embedder.text_calls == [f"a photo of a {label}" for label in LABELS]

    def test_the_prompt_template_is_configurable(self, embedder):
        ZeroShotTagger(embedder, LABELS, template="{} picture").suggest(
            embedder.image(beach=1.0), limit=1, threshold=0.0
        )
        assert embedder.text_calls[0] == "beach picture"

    def test_vectors_are_cached_on_disk_for_the_next_process(self, tmp_path):
        first = AxisEmbedder()
        ZeroShotTagger(first, LABELS, cache_dir=tmp_path).suggest(
            first.image(beach=1.0), limit=1, threshold=0.0
        )
        second = AxisEmbedder()
        tags = ZeroShotTagger(second, LABELS, cache_dir=tmp_path).suggest(
            second.image(beach=1.0), limit=1, threshold=0.0
        )
        assert second.text_calls == []
        assert tags[0].label == "beach"

    @pytest.mark.parametrize(
        "change",
        [
            {"model_id": "axis-v2"},  # another model: its vectors are not comparable
            {"template": "{}"},  # another prompt
            {"labels": LABELS[:-1]},  # another vocabulary
        ],
    )
    def test_the_cache_is_not_reused_when_model_prompt_or_vocabulary_change(self, tmp_path, change):
        first = AxisEmbedder()
        ZeroShotTagger(first, LABELS, cache_dir=tmp_path).suggest(
            first.image(beach=1.0), limit=1, threshold=0.0
        )
        labels = change.get("labels", LABELS)
        second = AxisEmbedder(labels, model_id=change.get("model_id", "axis-v1"))
        ZeroShotTagger(
            second, labels, template=change.get("template", "a photo of {}"), cache_dir=tmp_path
        ).suggest(second.image(beach=1.0), limit=1, threshold=0.0)
        assert len(second.text_calls) == len(labels)

    def test_a_corrupt_cache_file_is_recomputed(self, tmp_path):
        first = AxisEmbedder()
        ZeroShotTagger(first, LABELS, cache_dir=tmp_path).suggest(
            first.image(beach=1.0), limit=1, threshold=0.0
        )
        for f in tmp_path.glob("*.npy"):
            f.write_bytes(b"garbage")
        second = AxisEmbedder()
        tags = ZeroShotTagger(second, LABELS, cache_dir=tmp_path).suggest(
            second.image(beach=1.0), limit=1, threshold=0.0
        )
        assert len(second.text_calls) == len(LABELS)
        assert tags[0].label == "beach"


class TestTheShippedVocabulary:
    def test_is_a_few_hundred_distinct_valid_tags(self):
        assert 450 <= len(VOCABULARY) <= 650
        assert len(set(VOCABULARY)) == len(VOCABULARY)
        for label in VOCABULARY:
            assert validate_tag(label) == label

    def test_labels_are_short_lowercase_phrases(self):
        for label in VOCABULARY:
            assert label == label.lower(), label
            assert len(label.split()) <= 3, label

    def test_covers_the_everyday_subjects_of_a_photo_library(self):
        for expected in (
            "beach",
            "sunset",
            "mountain",
            "dog",
            "birthday party",
            "food",
            "portrait",
        ):
            assert expected in VOCABULARY
