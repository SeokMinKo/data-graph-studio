"""Shared test fixtures for data-graph-studio."""

import os
import polars as pl
import pytest

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def create_large_df(n_rows: int, seed: int = 42) -> pl.DataFrame:
    """팩토리: 대용량 DataFrame 생성.

    Args:
        n_rows: 생성할 행 수.
        seed: 랜덤 시드.

    Returns:
        name, age, score, city 컬럼을 가진 DataFrame.
    """
    import random
    random.seed(seed)
    cities = ["Seoul", "Busan", "Incheon", "Daegu", "Daejeon"]
    return pl.DataFrame({
        "name": [f"user_{i}" for i in range(n_rows)],
        "age": [random.randint(18, 80) for _ in range(n_rows)],
        "score": [random.uniform(0, 100) for _ in range(n_rows)],
        "city": [random.choice(cities) for _ in range(n_rows)],
    })


@pytest.fixture
def sample_csv_path():
    return os.path.join(FIXTURES_DIR, "sample.csv")


@pytest.fixture
def sample_tsv_path():
    return os.path.join(FIXTURES_DIR, "sample.tsv")


@pytest.fixture
def sample_json_path():
    return os.path.join(FIXTURES_DIR, "sample.json")


@pytest.fixture
def sample_parquet_path():
    return os.path.join(FIXTURES_DIR, "sample.parquet")


@pytest.fixture
def sample_df():
    return pl.read_csv(os.path.join(FIXTURES_DIR, "sample.csv"))


@pytest.fixture
def small_df():
    return create_large_df(100)
