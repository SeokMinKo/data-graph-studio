"""
Statistical Analysis — Clustering Module

Provides ClusterAnalyzer with K-Means, hierarchical (Ward linkage), and
DBSCAN implementations built on NumPy and SciPy.  All algorithms operate
on normalized column data extracted from Polars DataFrames.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import numpy as np
import polars as pl
from scipy.cluster import hierarchy

logger = logging.getLogger(__name__)


class ClusterMethod(Enum):
    """Supported clustering algorithms."""

    KMEANS = "kmeans"
    HIERARCHICAL = "hierarchical"
    DBSCAN = "dbscan"


@dataclass
class ClusterResult:
    """Result payload returned by any clustering algorithm.

    labels — integer cluster assignment per sample (-1 means noise for DBSCAN).
    centers — cluster centroid coordinates (K-Means only).
    inertia — total within-cluster sum-of-squares (K-Means only).
    silhouette — mean silhouette coefficient if computed, else None.
    dendrogram_data — {"linkage": linkage_matrix} for hierarchical results.
    """

    labels: np.ndarray
    n_clusters: int
    method: ClusterMethod
    centers: Optional[np.ndarray] = None
    inertia: Optional[float] = None
    silhouette: Optional[float] = None
    dendrogram_data: Optional[Dict] = None


class ClusterAnalyzer:
    """Clustering analysis engine supporting K-Means, hierarchical, and DBSCAN.

    All public methods accept Polars DataFrames and column name lists.
    Data is normalized (zero-mean, unit-variance) internally before any
    algorithm runs; NaN values are replaced with 0.0.
    """

    def cluster(
        self,
        data: pl.DataFrame,
        columns: List[str],
        method: ClusterMethod = ClusterMethod.KMEANS,
        n_clusters: int = 3,
        **kwargs
    ) -> ClusterResult:
        """Run the selected clustering algorithm on the specified columns.

        Input: data — pl.DataFrame, source dataset
               columns — List[str], columns to use (missing columns silently skipped)
               method — ClusterMethod, algorithm to apply (default KMEANS)
               n_clusters — int, number of clusters for K-Means / hierarchical
               **kwargs — extra params: eps (float, DBSCAN), min_samples (int, DBSCAN)
        Output: ClusterResult — labels, n_clusters, method, and algorithm-specific fields
        Invariants: NaN values replaced with 0.0; data normalized before clustering
        """
        # 데이터 추출 및 정규화
        logger.debug("statistics.cluster", extra={"method": method.value, "n_clusters": n_clusters})
        valid_columns = [c for c in columns if c in data.columns]
        X = data.select(valid_columns).to_numpy()

        # NaN 처리
        X = np.nan_to_num(X, nan=0.0)

        # 정규화
        X_mean = np.mean(X, axis=0)
        X_std = np.std(X, axis=0)
        X_std[X_std == 0] = 1  # 0으로 나누기 방지
        X_normalized = (X - X_mean) / X_std

        if method == ClusterMethod.KMEANS:
            return self._kmeans_cluster(X_normalized, n_clusters)
        elif method == ClusterMethod.HIERARCHICAL:
            return self._hierarchical_cluster(X_normalized, n_clusters)
        elif method == ClusterMethod.DBSCAN:
            eps = kwargs.get("eps", 0.5)
            min_samples = kwargs.get("min_samples", 5)
            return self._dbscan_cluster(X_normalized, eps, min_samples)

        return ClusterResult(
            labels=np.zeros(len(X)),
            n_clusters=1,
            method=method
        )

    def _kmeans_cluster(
        self,
        X: np.ndarray,
        n_clusters: int,
        max_iter: int = 100
    ) -> ClusterResult:
        """Run a simplified K-Means++ clustering on pre-normalized data.

        Input: X — np.ndarray shape (n_samples, n_features), normalized
               n_clusters — int, number of clusters
               max_iter — int, iteration cap (default 100)
        Output: ClusterResult with labels, centers, and inertia set
        Invariants: converges when centers change by less than machine epsilon
        """
        n_samples = len(X)

        # 초기 중심 (K-Means++ 단순화 버전)
        centers = X[np.random.choice(n_samples, n_clusters, replace=False)]

        for _ in range(max_iter):
            # 각 포인트를 가장 가까운 중심에 할당
            distances = np.sqrt(((X[:, np.newaxis] - centers) ** 2).sum(axis=2))
            labels = np.argmin(distances, axis=1)

            # 중심 업데이트
            new_centers = np.array([
                X[labels == k].mean(axis=0) if np.sum(labels == k) > 0 else centers[k]
                for k in range(n_clusters)
            ])

            # 수렴 확인
            if np.allclose(centers, new_centers):
                break

            centers = new_centers

        # Inertia 계산
        inertia = sum(
            ((X[labels == k] - centers[k]) ** 2).sum()
            for k in range(n_clusters)
        )

        return ClusterResult(
            labels=labels,
            n_clusters=n_clusters,
            method=ClusterMethod.KMEANS,
            centers=centers,
            inertia=inertia
        )

    def _hierarchical_cluster(
        self,
        X: np.ndarray,
        n_clusters: int
    ) -> ClusterResult:
        """Run Ward linkage hierarchical clustering on pre-normalized data.

        Input: X — np.ndarray shape (n_samples, n_features), normalized
               n_clusters — int, number of flat clusters to cut from the dendrogram
        Output: ClusterResult with labels (0-based) and dendrogram_data["linkage"]
        """
        # 연결 행렬 계산
        linkage_matrix = hierarchy.linkage(X, method='ward')

        # 클러스터 할당
        labels = hierarchy.fcluster(linkage_matrix, n_clusters, criterion='maxclust') - 1

        return ClusterResult(
            labels=labels,
            n_clusters=n_clusters,
            method=ClusterMethod.HIERARCHICAL,
            dendrogram_data={"linkage": linkage_matrix}
        )

    def _dbscan_cluster(
        self,
        X: np.ndarray,
        eps: float,
        min_samples: int
    ) -> ClusterResult:
        """Run a pure-NumPy DBSCAN on pre-normalized data.

        Input: X — np.ndarray shape (n_samples, n_features), normalized
               eps — float, neighborhood radius
               min_samples — int, minimum points to form a core point
        Output: ClusterResult with labels (-1 = noise) and n_clusters (noise excluded)
        Invariants: visited array ensures O(n^2) worst case, no sample processed twice
        """
        n_samples = len(X)
        labels = np.full(n_samples, -1)
        cluster_id = 0

        visited = np.zeros(n_samples, dtype=bool)

        for i in range(n_samples):
            if visited[i]:
                continue

            visited[i] = True

            # 이웃 찾기
            distances = np.sqrt(((X - X[i]) ** 2).sum(axis=1))
            neighbors = np.where(distances < eps)[0]

            if len(neighbors) < min_samples:
                continue

            # 새 클러스터 시작
            labels[i] = cluster_id
            seed_set = list(neighbors)

            j = 0
            while j < len(seed_set):
                q = seed_set[j]

                if not visited[q]:
                    visited[q] = True
                    distances_q = np.sqrt(((X - X[q]) ** 2).sum(axis=1))
                    neighbors_q = np.where(distances_q < eps)[0]

                    if len(neighbors_q) >= min_samples:
                        seed_set.extend(neighbors_q)

                if labels[q] == -1:
                    labels[q] = cluster_id

                j += 1

            cluster_id += 1

        n_clusters = len(set(labels)) - (1 if -1 in labels else 0)

        return ClusterResult(
            labels=labels,
            n_clusters=n_clusters,
            method=ClusterMethod.DBSCAN
        )

    def get_cluster_statistics(
        self,
        result: ClusterResult,
        data: pl.DataFrame,
        columns: List[str]
    ) -> List[Dict[str, Any]]:
        """Compute per-cluster descriptive statistics (center and std deviation).

        Input: result — ClusterResult from a previous cluster() call
               data — pl.DataFrame, the original (unnormalized) source data
               columns — List[str], columns to summarize
        Output: List[Dict[str, Any]] — one dict per cluster with keys:
                cluster_id (int), size (int), center (List[float]), std (List[float])
        Invariants: len(output) == result.n_clusters; empty clusters yield empty lists
        """
        X = data.select(columns).to_numpy()
        statistics = []

        for k in range(result.n_clusters):
            mask = result.labels == k
            cluster_data = X[mask]

            stat = {
                "cluster_id": k,
                "size": int(np.sum(mask)),
                "center": cluster_data.mean(axis=0).tolist() if len(cluster_data) > 0 else [],
                "std": cluster_data.std(axis=0).tolist() if len(cluster_data) > 0 else []
            }
            statistics.append(stat)

        return statistics

    def silhouette_score(
        self,
        result: ClusterResult,
        data: pl.DataFrame,
        columns: List[str]
    ) -> float:
        """Compute the mean silhouette coefficient for the clustering result.

        Input: result — ClusterResult, must have at least 2 distinct labels
               data — pl.DataFrame, original source data (unnormalized)
               columns — List[str], columns used for distance calculation
        Output: float — mean silhouette score in [-1, 1]; 0.0 if fewer than 2 clusters
        Invariants: noise points (label == -1) are excluded from neighbor clusters
        """
        X = data.select(columns).to_numpy()
        labels = result.labels

        n_samples = len(X)
        if len(set(labels)) < 2:
            return 0.0

        scores = []

        for i in range(n_samples):
            # a(i): 같은 클러스터 내 평균 거리
            same_cluster = X[labels == labels[i]]
            if len(same_cluster) > 1:
                a = np.mean(np.sqrt(((same_cluster - X[i]) ** 2).sum(axis=1)))
            else:
                a = 0

            # b(i): 다른 클러스터와의 최소 평균 거리
            b = np.inf
            for k in set(labels):
                if k == labels[i] or k == -1:
                    continue
                other_cluster = X[labels == k]
                if len(other_cluster) > 0:
                    avg_dist = np.mean(np.sqrt(((other_cluster - X[i]) ** 2).sum(axis=1)))
                    b = min(b, avg_dist)

            if b == np.inf:
                b = 0

            # 실루엣 점수
            s = (b - a) / max(a, b) if max(a, b) > 0 else 0
            scores.append(s)

        return np.mean(scores)

    def find_optimal_k(
        self,
        data: pl.DataFrame,
        columns: List[str],
        k_range: Tuple[int, int] = (2, 10)
    ) -> Tuple[List[int], List[float]]:
        """Find the optimal K for K-Means via the elbow method.

        Runs K-Means for each k in [k_range[0], k_range[1]) and collects inertia.
        Input: data — pl.DataFrame, source dataset
               columns — List[str], columns to cluster on
               k_range — Tuple[int, int], inclusive start, exclusive end (default (2, 10))
        Output: Tuple[List[int], List[float]] — (k_values, inertia_values) of equal length
        Invariants: len(k_values) == len(inertia_values); same order as k_range
        """
        k_values = list(range(k_range[0], k_range[1]))
        inertias = []

        for k in k_values:
            result = self.cluster(data, columns, ClusterMethod.KMEANS, k)
            inertias.append(result.inertia)

        return k_values, inertias
