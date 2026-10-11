"""The ImageEmbedder port and its deterministic test double."""

from io import BytesIO

import pytest
from tests.fakes import FakeImageEmbedder

from photo_meta_organizer.application.interfaces import ImageEmbedder
from photo_meta_organizer.domain.analysis import normalize


def test_fake_satisfies_the_port():
    assert isinstance(FakeImageEmbedder(), ImageEmbedder)


def test_same_input_same_vector_different_input_different_vector():
    fake = FakeImageEmbedder()
    a1 = fake.embed_image(BytesIO(b"photo-a"), "a.jpg")
    a2 = fake.embed_image(BytesIO(b"photo-a"), "a.jpg")
    b = fake.embed_image(BytesIO(b"photo-b"), "b.jpg")
    assert a1 == a2
    assert a1 != b
    assert len(a1) == fake.dimension == 16


def test_vectors_have_a_direction_and_text_shares_the_space():
    fake = FakeImageEmbedder(dimension=40)  # longer than one hash block
    assert len(fake.embed_text("beach")) == 40
    normalize(fake.embed_text("beach"))  # does not raise


def test_an_undecodable_image_raises_like_the_real_thing():
    with pytest.raises(ValueError):
        FakeImageEmbedder().embed_image(BytesIO(b""), "x.jpg")


def test_counts_image_calls():
    fake = FakeImageEmbedder()
    fake.embed_image(BytesIO(b"x"), "x.jpg")
    fake.embed_image(BytesIO(b"y"), "y.jpg")
    assert fake.image_calls == 2
