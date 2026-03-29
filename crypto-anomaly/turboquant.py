"""
TurboQuant: Online Vector Quantization with Near-optimal Distortion Rate

Implementation of Algorithm 1 (MSE-Optimal Quantizer) and Algorithm 2
(Inner Product Preserving Quantizer) from arXiv:2504.19874.

Key idea: Random rotation makes unit-norm vector coordinates approximately
N(0, 1/d), enabling optimal scalar quantization via Lloyd-Max codebooks.
"""

import numpy as np

# Lloyd-Max optimal codebook values for standard normal N(0, 1).
# Scaled by 1/sqrt(d) at runtime for N(0, 1/d).
# Format: {bit_width: {"boundaries": [...], "centroids": [...]}}
LLOYD_MAX_STANDARD = {
    1: {
        "boundaries": np.array([0.0]),
        "centroids": np.array([-0.7979, 0.7979]),
    },
    2: {
        "boundaries": np.array([-0.9816, 0.0, 0.9816]),
        "centroids": np.array([-1.510, -0.4528, 0.4528, 1.510]),
    },
    3: {
        "boundaries": np.array([-1.748, -1.050, -0.5006, 0.0, 0.5006, 1.050, 1.748]),
        "centroids": np.array([-2.152, -1.344, -0.7560, -0.2451, 0.2451, 0.7560, 1.344, 2.152]),
    },
    4: {
        "boundaries": np.array([
            -2.401, -1.844, -1.437, -1.099, -0.7995, -0.5224, -0.2582, 0.0,
            0.2582, 0.5224, 0.7995, 1.099, 1.437, 1.844, 2.401,
        ]),
        "centroids": np.array([
            -2.733, -2.069, -1.618, -1.256, -0.9424, -0.6568, -0.3881, -0.1284,
            0.1284, 0.3881, 0.6568, 0.9424, 1.256, 1.618, 2.069, 2.733,
        ]),
    },
}

# Theoretical MSE values from Theorem 1
THEORETICAL_MSE = {1: 0.3634, 2: 0.1175, 3: 0.0345, 4: 0.0094}


def _generate_haar_rotation(d: int, seed: int | None = None) -> np.ndarray:
    """Generate a uniformly random (Haar-distributed) orthogonal matrix.

    Uses QR decomposition of a random Gaussian matrix with sign correction.
    """
    rng = np.random.RandomState(seed)
    G = rng.randn(d, d)
    Q, R = np.linalg.qr(G)
    # Fix sign ambiguity for uniform Haar distribution
    Q = Q @ np.diag(np.sign(np.diag(R)))
    return Q


class TurboQuantMSE:
    """MSE-Optimal Quantizer (Algorithm 1).

    Applies random rotation to unit-norm vectors, then quantizes each
    coordinate independently using a Lloyd-Max optimal scalar quantizer.
    """

    def __init__(self, d: int, b: int, seed: int | None = None):
        """
        Args:
            d: Vector dimension (e.g. 128).
            b: Bit-width per coordinate (1, 2, 3, or 4).
            seed: Random seed for reproducible rotation matrix.
        """
        if b not in LLOYD_MAX_STANDARD:
            raise ValueError(f"Unsupported bit-width b={b}. Choose from {list(LLOYD_MAX_STANDARD.keys())}")

        self.d = d
        self.b = b
        self.n_levels = 2 ** b

        # Random rotation matrix (d x d orthogonal)
        self.rotation = _generate_haar_rotation(d, seed)

        # Scale Lloyd-Max codebook from N(0,1) to N(0, 1/d)
        sigma = 1.0 / np.sqrt(d)
        std_codebook = LLOYD_MAX_STANDARD[b]
        self.boundaries = std_codebook["boundaries"] * sigma
        self.centroids = std_codebook["centroids"] * sigma

    def encode(self, x: np.ndarray) -> np.ndarray:
        """Quantize a single unit-norm vector.

        Args:
            x: Shape (d,) unit-norm vector.

        Returns:
            Shape (d,) uint8 array of quantization indices.
        """
        y = self.rotation @ x
        # np.digitize with sorted boundaries returns bin index directly:
        # for b=2, boundaries [-σ, 0, σ] → returns 0,1,2,3 → maps to 4 centroids
        indices = np.digitize(y, self.boundaries)
        np.clip(indices, 0, self.n_levels - 1, out=indices)
        return indices.astype(np.uint8)

    def decode(self, indices: np.ndarray) -> np.ndarray:
        """Reconstruct vector from quantization indices.

        Args:
            indices: Shape (d,) uint8 array of indices.

        Returns:
            Shape (d,) reconstructed vector.
        """
        y_hat = self.centroids[indices]
        return self.rotation.T @ y_hat

    def encode_batch(self, X: np.ndarray) -> np.ndarray:
        """Quantize a batch of vectors.

        Args:
            X: Shape (n, d) array of unit-norm vectors.

        Returns:
            Shape (n, d) uint8 array of indices.
        """
        Y = X @ self.rotation.T  # (n, d)
        indices = np.digitize(Y, self.boundaries)
        np.clip(indices, 0, self.n_levels - 1, out=indices)
        return indices.astype(np.uint8)

    def decode_batch(self, indices: np.ndarray) -> np.ndarray:
        """Reconstruct a batch of vectors.

        Args:
            indices: Shape (n, d) uint8 array.

        Returns:
            Shape (n, d) reconstructed vectors.
        """
        Y_hat = self.centroids[indices]  # (n, d)
        return Y_hat @ self.rotation  # (n, d)


class TurboQuantProd:
    """Inner Product Preserving Quantizer (Algorithm 2).

    Uses (b-1)-bit MSE quantizer + 1-bit QJL residual correction
    for unbiased inner product estimation.
    """

    def __init__(self, d: int, b: int, seed: int | None = None):
        """
        Args:
            d: Vector dimension.
            b: Total bit-width (b-1 bits for MSE, 1 bit for QJL).
            seed: Random seed for reproducibility.
        """
        if b < 2:
            raise ValueError("TurboQuantProd requires b >= 2 (1 bit for MSE + 1 for QJL)")

        self.d = d
        self.b = b

        # MSE quantizer with (b-1) bits
        self.mse_quantizer = TurboQuantMSE(d, b - 1, seed=seed)

        # QJL: random projection matrix S ∈ R^{d×d}, S_{i,j} ~ N(0,1)
        # (Algorithm 2, line 3)
        qjl_seed = (seed or 42) + 1000
        self.qjl_rng_seed = qjl_seed
        rng = np.random.RandomState(qjl_seed)
        self.S = rng.randn(d, d)  # fixed random matrix for QJL

    def encode(self, x: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
        """Quantize vector with inner-product preservation.

        Args:
            x: Shape (d,) unit-norm vector.

        Returns:
            (mse_indices, qjl_signs, residual_norm):
                mse_indices: uint8 (d,) — MSE quantization indices
                qjl_signs: uint8 (d,) — QJL sign bits (0 or 1)
                residual_norm: float — L2 norm of quantization residual
        """
        # MSE quantize
        mse_indices = self.mse_quantizer.encode(x)
        x_hat = self.mse_quantizer.decode(mse_indices)

        # Residual: r ← x - DeQuantmse(idx)  (Algorithm 2, line 6)
        residual = x - x_hat
        residual_norm = float(np.linalg.norm(residual))

        # QJL on residual: qjl ← sign(S · r)  (Algorithm 2, line 7)
        projected = self.S @ residual
        qjl_signs = np.sign(projected)  # ∈ {-1, 0, +1}
        # Convert to {-1, +1} (treat 0 as +1)
        qjl_signs[qjl_signs == 0] = 1.0

        return mse_indices, qjl_signs, residual_norm

    def decode(self, mse_indices: np.ndarray, qjl_signs: np.ndarray,
               residual_norm: float) -> np.ndarray:
        """Full dequantization per Algorithm 2, lines 10-12.

        x̃ = x̃_mse + x̃_qjl
        where x̃_qjl = √(π/2) / d · γ · S^T · qjl
        """
        x_mse = self.mse_quantizer.decode(mse_indices)
        # Algorithm 2, line 11: x̃_qjl = √(π/2) / d · γ · S^T · qjl
        x_qjl = (np.sqrt(np.pi / 2.0) / self.d) * residual_norm * (self.S.T @ qjl_signs)
        return x_mse + x_qjl

    def inner_product_asymmetric(
        self,
        y: np.ndarray,
        code_x: tuple[np.ndarray, np.ndarray, float],
    ) -> float:
        """Estimate ⟨y, x⟩ where y is a fresh vector and x is quantized.

        This is the primary use case per the paper (Theorem 2):
        ⟨y, x̃⟩ = ⟨y, x̃_mse⟩ + √(π/2)/d · γ · ⟨y, S^T · qjl⟩

        Args:
            y: Fresh (unquantized) vector, shape (d,).
            code_x: (mse_indices, qjl_signs, residual_norm) for quantized x.

        Returns:
            Unbiased estimate of ⟨y, x⟩.
        """
        idx_x, qjl_x, gamma_x = code_x

        # MSE inner product: ⟨y, x̃_mse⟩
        x_mse = self.mse_quantizer.decode(idx_x)
        ip_mse = float(np.dot(y, x_mse))

        # QJL correction: ⟨y, x̃_qjl⟩ = √(π/2)/d · γ · (S·y)^T · qjl
        Sy = self.S @ y
        qjl_correction = float(np.sqrt(np.pi / 2.0) / self.d * gamma_x * np.dot(Sy, qjl_x))

        return ip_mse + qjl_correction

    def inner_product_symmetric(
        self,
        code_a: tuple[np.ndarray, np.ndarray, float],
        code_b: tuple[np.ndarray, np.ndarray, float],
    ) -> float:
        """Estimate ⟨a, b⟩ where both vectors are quantized.

        Uses full dequantization: ⟨decode(a), decode(b)⟩.
        Note: the paper primarily defines the asymmetric case.

        Args:
            code_a: (mse_indices, qjl_signs, residual_norm) for vector a.
            code_b: (mse_indices, qjl_signs, residual_norm) for vector b.

        Returns:
            Estimated inner product.
        """
        a_hat = self.decode(*code_a)
        b_hat = self.decode(*code_b)
        return float(np.dot(a_hat, b_hat))

    def encode_batch(self, X: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Batch encode for inner product preservation.

        Args:
            X: Shape (n, d) unit-norm vectors.

        Returns:
            (mse_indices, qjl_signs, residual_norms)
        """
        mse_indices = self.mse_quantizer.encode_batch(X)
        X_hat = self.mse_quantizer.decode_batch(mse_indices)

        residuals = X - X_hat
        residual_norms = np.linalg.norm(residuals, axis=1)

        # QJL: sign(S · r) for each residual vector
        projected = residuals @ self.S.T  # (n, d)
        qjl_signs = np.sign(projected)
        qjl_signs[qjl_signs == 0] = 1.0

        return mse_indices, qjl_signs, residual_norms
