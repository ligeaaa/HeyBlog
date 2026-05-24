"""Small PyTorch GCN model for graph node classification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import torch
from scipy import sparse
from sklearn.metrics import accuracy_score
from sklearn.metrics import average_precision_score
from sklearn.metrics import confusion_matrix
from sklearn.metrics import f1_score
from sklearn.metrics import precision_score
from sklearn.metrics import recall_score
from sklearn.metrics import roc_auc_score
from torch import nn
from torch.nn import functional as F

from trainer.graph.dataset import GraphDataset


class ResidualGCN(nn.Module):
    """Residual multi-hop graph convolutional network.

    Args:
        input_dim: Number of node input features.
        hidden_dim: Hidden representation size.
        output_dim: Number of output classes.
        dropout: Dropout probability applied before each layer.
        layers: Number of graph message-passing blocks.

    Returns:
        Logits for each node and class when called.
    """

    def __init__(
        self,
        input_dim: int,
        hidden_dim: int,
        output_dim: int = 2,
        dropout: float = 0.35,
        layers: int = 3,
    ) -> None:
        super().__init__()
        self.input_projection = nn.Linear(input_dim, hidden_dim)
        self.graph_layers = nn.ModuleList(nn.Linear(hidden_dim, hidden_dim) for _ in range(max(1, layers)))
        self.layer_norms = nn.ModuleList(nn.LayerNorm(hidden_dim) for _ in self.graph_layers)
        self.output_projection = nn.Linear(hidden_dim, output_dim)
        self.dropout = dropout

    def forward(self, features: torch.Tensor, adjacency: torch.Tensor) -> torch.Tensor:
        hidden = F.relu(self.input_projection(features))
        for layer, layer_norm in zip(self.graph_layers, self.layer_norms, strict=True):
            residual = hidden
            hidden = torch.sparse.mm(adjacency, hidden)
            hidden = F.relu(layer(hidden))
            hidden = F.dropout(hidden, p=self.dropout, training=self.training)
            hidden = layer_norm(hidden + residual)
        return self.output_projection(hidden)


GCN = ResidualGCN


@dataclass(slots=True)
class GCNTrainingConfig:
    """Training configuration for a GCN run."""

    seed: int = 7
    hidden_dim: int = 64
    layers: int = 3
    epochs: int = 200
    learning_rate: float = 0.01
    weight_decay: float = 5e-4
    dropout: float = 0.35
    patience: int = 25


def _sparse_matrix_to_torch(matrix: sparse.spmatrix) -> torch.Tensor:
    coo = matrix.tocoo().astype(np.float32)
    indices = torch.tensor(np.vstack([coo.row, coo.col]), dtype=torch.long)
    values = torch.tensor(coo.data, dtype=torch.float32)
    return torch.sparse_coo_tensor(indices, values, size=coo.shape).coalesce()


def _labels_to_tensor(labels: np.ndarray) -> torch.Tensor:
    return torch.tensor(labels, dtype=torch.long)


def _mask_to_tensor(mask: np.ndarray) -> torch.Tensor:
    return torch.tensor(mask, dtype=torch.bool)


def _safe_auc(y_true: np.ndarray, scores: np.ndarray, *, kind: str) -> float:
    if len(np.unique(y_true)) < 2:
        return 0.0
    if kind == "roc":
        return float(roc_auc_score(y_true, scores))
    return float(average_precision_score(y_true, scores))


def compute_binary_metrics(y_true: np.ndarray, probabilities: np.ndarray, *, threshold: float = 0.5) -> dict[str, Any]:
    """Compute binary blog/non-blog classification metrics.

    Args:
        y_true: Gold labels where ``1`` means blog.
        probabilities: Blog class probabilities.
        threshold: Probability threshold used for the binary prediction.

    Returns:
        Serializable metrics and confusion counts.
    """
    predicted = (probabilities >= threshold).astype(np.int64)
    labels = [0, 1]
    matrix = confusion_matrix(y_true, predicted, labels=labels)
    tn, fp, fn, tp = [int(value) for value in matrix.ravel()]
    return {
        "accuracy": round(float(accuracy_score(y_true, predicted)), 6),
        "precision": round(float(precision_score(y_true, predicted, zero_division=0)), 6),
        "recall": round(float(recall_score(y_true, predicted, zero_division=0)), 6),
        "f1": round(float(f1_score(y_true, predicted, zero_division=0)), 6),
        "pr_auc": round(_safe_auc(y_true, probabilities, kind="pr"), 6),
        "roc_auc": round(_safe_auc(y_true, probabilities, kind="roc"), 6),
        "threshold": round(float(threshold), 6),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
    }


def _evaluate_logits(
    logits: torch.Tensor,
    labels: torch.Tensor,
    mask: torch.Tensor,
    *,
    threshold: float = 0.5,
) -> dict[str, Any]:
    with torch.no_grad():
        probs = torch.softmax(logits[mask], dim=1)[:, 1].detach().cpu().numpy()
        gold = labels[mask].detach().cpu().numpy()
    return compute_binary_metrics(gold, probs, threshold=threshold)


def select_threshold(y_true: np.ndarray, probabilities: np.ndarray) -> tuple[float, float]:
    """Select the validation F1-optimal threshold for graph probabilities."""

    candidates = sorted({0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9} | {round(float(value), 6) for value in probabilities})
    best_threshold = 0.5
    best_f1 = -1.0
    for threshold in candidates:
        score = float(compute_binary_metrics(y_true, probabilities, threshold=threshold)["f1"])
        if score > best_f1 or (score == best_f1 and abs(threshold - 0.5) < abs(best_threshold - 0.5)):
            best_threshold = threshold
            best_f1 = score
    return best_threshold, best_f1


def train_gcn(dataset: GraphDataset, config: GCNTrainingConfig) -> tuple[ResidualGCN, dict[str, Any], np.ndarray]:
    """Train a residual GCN on graph-in labeled nodes.

    Args:
        dataset: Loaded graph dataset.
        config: Training hyperparameters.

    Returns:
        The trained model, training summary, and final blog probabilities for every node.
    """
    torch.manual_seed(config.seed)
    np.random.seed(config.seed)
    features = torch.tensor(dataset.features.toarray(), dtype=torch.float32)
    adjacency = _sparse_matrix_to_torch(dataset.adjacency)
    labels = _labels_to_tensor(dataset.labels)
    train_mask = _mask_to_tensor(dataset.split_masks["train"])
    val_mask = _mask_to_tensor(dataset.split_masks["val"])
    model = ResidualGCN(
        input_dim=features.shape[1],
        hidden_dim=config.hidden_dim,
        output_dim=2,
        dropout=config.dropout,
        layers=config.layers,
    )
    optimizer = torch.optim.Adam(
        model.parameters(),
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
    best_state = None
    best_val_f1 = -1.0
    best_epoch = 0
    stale_epochs = 0
    history: list[dict[str, Any]] = []
    for epoch in range(1, config.epochs + 1):
        model.train()
        optimizer.zero_grad()
        logits = model(features, adjacency)
        loss = F.cross_entropy(logits[train_mask], labels[train_mask])
        loss.backward()
        optimizer.step()

        model.eval()
        logits = model(features, adjacency)
        val_metrics = _evaluate_logits(logits, labels, val_mask)
        history.append({"epoch": epoch, "loss": round(float(loss.item()), 6), "val_f1": val_metrics["f1"]})
        if val_metrics["f1"] > best_val_f1:
            best_val_f1 = float(val_metrics["f1"])
            best_epoch = epoch
            stale_epochs = 0
            best_state = {key: value.detach().clone() for key, value in model.state_dict().items()}
        else:
            stale_epochs += 1
            if stale_epochs >= config.patience:
                break
    if best_state is not None:
        model.load_state_dict(best_state)
    model.eval()
    with torch.no_grad():
        final_logits = model(features, adjacency)
        probabilities = torch.softmax(final_logits, dim=1)[:, 1].detach().cpu().numpy()
    val_probabilities = probabilities[dataset.split_masks["val"]]
    val_labels = dataset.labels[dataset.split_masks["val"]]
    selected_threshold, selected_val_f1 = select_threshold(val_labels, val_probabilities)
    summary = {
        "best_epoch": best_epoch,
        "best_val_f1": best_val_f1,
        "selected_threshold": selected_threshold,
        "selected_threshold_val_f1": round(float(selected_val_f1), 6),
        "epochs_ran": len(history),
        "history": history,
        "config": {
            "seed": config.seed,
            "hidden_dim": config.hidden_dim,
            "layers": config.layers,
            "epochs": config.epochs,
            "learning_rate": config.learning_rate,
            "weight_decay": config.weight_decay,
            "dropout": config.dropout,
            "patience": config.patience,
        },
    }
    return model, summary, probabilities
