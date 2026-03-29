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
        indices = np.digitize(y, self.boundaries) - 1
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
        indices = np.digitize(Y, self.boundaries) - 1
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

        # QJL random projection vectors (d x d) — one per coordinate
        # Use seeded RNG for reproducibility
        qjl_seed = (seed or 42) + 1000
        self.qjl_rng_seed = qjl_seed
        qjl_rng = np.random.RandomState(qjl_seed)
        # Single random Gaussian vector for sign projection
        self.qjl_vector = qjl_rng.randn(d)
        self.qjl_vector /= np.linalg.norm(self.qjl_vector)

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

        # Residual
        residual = x - x_hat
        residual_norm = float(np.linalg.norm(residual))

        # QJL: project residual onto random vector, keep sign per coordinate
        # Use random sign flips for each coordinate
        rng = np.random.RandomState(self.qjl_rng_seed)
        S = rng.randn(self.d, self.d)  # random projection
        projected = S @ residual
        qjl_signs = (projected > 0).astype(np.uint8)

        return mse_indices, qjl_signs, residual_norm

    def decode(self, mse_indices: np.ndarray, qjl_signs: np.ndarray,
               residual_norm: float) -> np.ndarray:
        """Reconstruct vector (MSE part only, QJL is for IP estimation)."""
        return self.mse_quantizer.decode(mse_indices)

    def inner_product(
        self,
        code_a: tuple[np.ndarray, np.ndarray, float],
        code_b: tuple[np.ndarray, np.ndarray, float],
    ) -> float:
        """Estimate inner product between two quantized vectors.

        Uses MSE reconstruction inner product + QJL sign-based correction.

        Args:
            code_a: (mse_indices, qjl_signs, residual_norm) for vector a
            code_b: (mse_indices, qjl_signs, residual_norm) for vector b

        Returns:
            Estimated inner product <a, b>.
        """
        idx_a, signs_a, gamma_a = code_a
        idx_b, signs_b, gamma_b = code_b

        # MSE inner product
        a_hat = self.mse_quantizer.decode(idx_a)
        b_hat = self.mse_quantizer.decode(idx_b)
        ip_mse = float(np.dot(a_hat, b_hat))

        # QJL correction: sign agreement is proportional to residual inner product
        # E[sign(S r_a) * sign(S r_b)] ~ (2/pi) * <r_a, r_b> / (||r_a|| * ||r_b||)
        sign_a = 2.0 * signs_a.astype(np.float64) - 1.0
        sign_b = 2.0 * signs_b.astype(np.float64) - 1.0
        sign_agreement = float(np.mean(sign_a * sign_b))

        # Correction factor: (pi/2) * ||r_a|| * ||r_b|| * sign_agreement
        correction = (np.pi / 2.0) * gamma_a * gamma_b * sign_agreement

        return ip_mse + correction

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

        rng = np.random.RandomState(self.qjl_rng_seed)
        S = rng.randn(self.d, self.d)
        projected = residuals @ S.T  # (n, d)
        qjl_signs = (projected > 0).astype(np.uint8)

        return mse_indices, qjl_signs, residual_norms
