"""HTTP client for the HeyBlog model classification service."""

from __future__ import annotations

from typing import Any

import httpx

from shared.http_clients.context import context_header_kwargs


class ModelApiClient:
    """Classify one public URL through HeyBlog_Model_API."""

    def __init__(self, base_url: str, *, timeout_seconds: float = 30.0) -> None:
        self.client = httpx.Client(base_url=base_url.rstrip("/"), timeout=timeout_seconds)

    def classify_url(self, url: str, *, title: str = "") -> dict[str, Any]:
        """Return the model API prediction for one URL.

        Args:
            url: Absolute public URL to classify.
            title: Optional anchor/context title forwarded to feature extraction.

        Returns:
            The single prediction object returned by the model API.
        """
        response = self.client.post(
            "/v1/classify",
            json={"url": {"url": url, "title": title}, "fetch_connections": False},
            **context_header_kwargs(),
        )
        response.raise_for_status()
        payload = response.json()
        predictions = payload.get("predictions")
        if not isinstance(predictions, list) or len(predictions) != 1:
            raise ValueError("model_api_invalid_prediction_response")
        prediction = predictions[0]
        if not isinstance(prediction, dict):
            raise ValueError("model_api_invalid_prediction")
        return prediction
