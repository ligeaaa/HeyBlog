"""Shared constants for the offline training workflow."""

from __future__ import annotations

from pathlib import Path

DEFAULT_SOURCE_GLOB = "blog-label-training-*.csv"
DEFAULT_RANDOM_SEED = 7
DEFAULT_SPLIT_RATIOS = {
    "train": 0.70,
    "val": 0.15,
    "test": 0.15,
}
DEFAULT_THRESHOLD = 0.5
DEFAULT_MODELS = ("structured", "tfidf")
DEFAULT_DATA_ROOT = Path("data")
DEFAULT_TRAINER_ROOT = DEFAULT_DATA_ROOT / "trainer"
DEFAULT_DATASET_ROOT = DEFAULT_TRAINER_ROOT / "datasets"
DEFAULT_RUN_ROOT = DEFAULT_TRAINER_ROOT / "runs"
DEFAULT_POSITIVE_LABELS = ("blog",)
DEFAULT_NEGATIVE_LABELS = ("others",)
DEFAULT_STRUCTURED_EPOCHS = 30
DEFAULT_TFIDF_EPOCHS = 24
DEFAULT_LEARNING_RATE = 0.35
DEFAULT_L2_STRENGTH = 0.0005
DEFAULT_URL_CHAR_NGRAM_RANGE = (3, 5)
DEFAULT_TITLE_WORD_NGRAM_RANGE = (1, 2)
DEFAULT_MIN_DF = 1
URL_KEYWORDS = (
    "blog",
    "posts",
    "post",
    "article",
    "articles",
    "archive",
    "archives",
    "tag",
    "tags",
    "category",
    "categories",
    "feed",
    "about",
    "company",
    "official",
)
TITLE_KEYWORDS = (
    "blog",
    "blogs",
    "notes",
    "note",
    "journal",
    "diary",
    "company",
    "official",
    "studio",
)
