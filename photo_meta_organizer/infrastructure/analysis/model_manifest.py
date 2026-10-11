"""What the AI features download, exactly: files, sizes and checksums, pinned to a revision.

Nothing here is fetched at import. The download itself happens only when the user agrees
(`ModelStore.download`), and every file is verified against the checksum below, so a changed
or tampered file on the server is rejected rather than loaded.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelFile:
    name: str  # path inside the model directory
    url: str
    size: int
    sha256: str


@dataclass(frozen=True)
class ModelManifest:
    model_id: str
    files: tuple[ModelFile, ...]
    licence: str
    source: str  # where the files come from, for the consent prompt

    @property
    def total_bytes(self) -> int:
        return sum(f.size for f in self.files)


_REVISION = "d15189d7028b43f1d3e65039190477f6af591c2a"
_BASE = f"https://huggingface.co/Xenova/clip-vit-base-patch32/resolve/{_REVISION}"

# OpenAI's CLIP ViT-B/32 (MIT licence, github.com/openai/CLIP) as exported to ONNX by the
# Xenova/transformers.js project, with fp16 weights. Chosen over the int8 files (89 + 65 MB) after
# measuring on 65 real photos: int8 changed 44% of a search's top-5 results against fp32 (mean
# image-vector cosine 0.91); fp16 matched fp32 to cosine 1.00000 and 99.7% of top-5 results, at the
# same CPU speed and half the size of the fp32 files (352 + 254 MB). See ADR-002.
# The two ONNX hashes equal the LFS object ids Hugging Face lists for that revision.
CLIP_VIT_B32_FP16 = ModelManifest(
    model_id="clip-vit-b32-openai-fp16-d15189d",
    files=(
        ModelFile(
            name="vision_model_fp16.onnx",
            url=f"{_BASE}/onnx/vision_model_fp16.onnx",
            size=176_080_659,
            sha256="35c4e0fb0aeee527dcde1693520b214a34424a786babd530f35366bad5844efd",
        ),
        ModelFile(
            name="text_model_fp16.onnx",
            url=f"{_BASE}/onnx/text_model_fp16.onnx",
            size=127_339_794,
            sha256="df587ffbf248bf20d44fa6e16adc5ebc27ead691860e5333dbdaab5fd6bf3f6e",
        ),
        ModelFile(
            name="tokenizer.json",
            url=f"{_BASE}/tokenizer.json",
            size=2_224_119,
            sha256="f7f3b7af117d467b58374797691a6438d3e6b9e9cef800dfd5dced7f697a90cd",
        ),
    ),
    licence="MIT",
    source="huggingface.co/Xenova/clip-vit-base-patch32 (OpenAI CLIP ViT-B/32, ONNX export)",
)
