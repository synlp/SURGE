"""Generic training and evaluation loop for the SURGE benchmark."""

import copy
import logging

import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import DataLoader

from benchmark.evaluate import evaluate_predictions

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _set_seed(seed: int) -> None:
    """Set random seeds for reproducibility."""
    torch.manual_seed(seed)
    np.random.seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train_model(
    model: nn.Module,
    train_loader: DataLoader,
    val_loader: DataLoader,
    config: dict,
) -> dict:
    """Train a model with early stopping based on validation loss.

    Args:
        model: PyTorch model.
        train_loader: Training data loader.
        val_loader: Validation data loader.
        config: Dict with keys "lr", "epochs", "patience", "device".

    Returns:
        Dict with "best_val_loss", "epochs_trained", "train_losses",
        "val_losses".
    """
    lr = config.get("lr", 0.001)
    epochs = config.get("epochs", 100)
    patience = config.get("patience", 10)
    device = config.get("device", "cpu")

    model = model.to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.MSELoss()

    best_val_loss = float("inf")
    best_state_dict = None
    epochs_without_improvement = 0

    train_losses = []
    val_losses = []

    for epoch in range(1, epochs + 1):
        # --- Training ---
        model.train()
        total_train_loss = 0.0
        n_train_batches = 0
        for x_batch, y_batch in train_loader:
            x_batch = x_batch.to(device)
            y_batch = y_batch.to(device)

            pred = model(x_batch)
            loss = criterion(pred, y_batch)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            total_train_loss += loss.item()
            n_train_batches += 1

        avg_train_loss = total_train_loss / max(n_train_batches, 1)
        train_losses.append(avg_train_loss)

        # --- Validation ---
        model.eval()
        total_val_loss = 0.0
        n_val_batches = 0
        with torch.no_grad():
            for x_batch, y_batch in val_loader:
                x_batch = x_batch.to(device)
                y_batch = y_batch.to(device)

                pred = model(x_batch)
                loss = criterion(pred, y_batch)

                total_val_loss += loss.item()
                n_val_batches += 1

        avg_val_loss = total_val_loss / max(n_val_batches, 1)
        val_losses.append(avg_val_loss)

        # --- Logging (every 10 epochs) ---
        if epoch % 10 == 0 or epoch == 1:
            logger.info(
                "Epoch %d/%d  train_loss=%.6f  val_loss=%.6f",
                epoch, epochs, avg_train_loss, avg_val_loss,
            )

        # --- Early stopping ---
        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            best_state_dict = copy.deepcopy(model.state_dict())
            epochs_without_improvement = 0
        else:
            epochs_without_improvement += 1
            if epochs_without_improvement >= patience:
                logger.info(
                    "Early stopping at epoch %d (patience=%d)",
                    epoch, patience,
                )
                break

    if best_state_dict is not None:
        model.load_state_dict(best_state_dict)

    return {
        "best_val_loss": best_val_loss,
        "epochs_trained": len(train_losses),
        "train_losses": train_losses,
        "val_losses": val_losses,
    }


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def evaluate_model(
    model: nn.Module,
    test_loader: DataLoader,
    device: str = "cpu",
) -> tuple:
    """Run a neural model on test data and collect predictions.

    Args:
        model: ``nn.Module`` whose ``forward`` returns shape
            ``(B, pred_len, C)``.
        test_loader: Test data loader.
        device: Device string.

    Returns:
        ``(y_true, y_pred)`` where each is an ``np.ndarray`` of shape
        ``(N, pred_len, C)``.
    """
    all_true = []
    all_pred = []

    model = model.to(device)
    model.eval()
    with torch.no_grad():
        for x_batch, y_batch in test_loader:
            x_batch = x_batch.to(device)
            pred = model(x_batch)
            all_true.append(y_batch.numpy())
            all_pred.append(pred.cpu().numpy())

    y_true = np.concatenate(all_true, axis=0)
    y_pred = np.concatenate(all_pred, axis=0)
    return y_true, y_pred


# ---------------------------------------------------------------------------
# Single experiment
# ---------------------------------------------------------------------------

def run_single_experiment(
    model_name: str,
    model: nn.Module,
    train_loader: DataLoader,
    val_loader: DataLoader,
    test_loader: DataLoader,
    config: dict,
    seed: int,
) -> dict:
    """Set seed, train, evaluate, and report MAE / MSE / RMSE for one run.

    Args:
        model_name: Name of the model (for logging and the result dict).
        model: ``nn.Module`` instance.
        train_loader: Training data loader.
        val_loader: Validation data loader.
        test_loader: Test data loader.
        config: Training config dict (``lr``, ``epochs``, ``patience``,
            ``device``).
        seed: Random seed.

    Returns:
        Result dict with keys ``model``, ``seed``, ``config``,
        ``metrics``, ``train_info``.
    """
    _set_seed(seed)
    device = config.get("device", "cpu")

    logger.info("Training %s (seed=%d) ...", model_name, seed)
    train_info = train_model(model, train_loader, val_loader, config)
    logger.info(
        "Training complete. best_val_loss=%.6f  epochs_trained=%d",
        train_info["best_val_loss"],
        train_info["epochs_trained"],
    )

    logger.info("Evaluating %s on test set ...", model_name)
    y_true, y_pred = evaluate_model(model, test_loader, device=device)

    metrics = evaluate_predictions(y_true, y_pred)
    logger.info("Metrics for %s: %s", model_name, metrics)

    return {
        "model": model_name,
        "seed": seed,
        "config": config,
        "metrics": metrics,
        "train_info": {
            "best_val_loss": train_info.get("best_val_loss"),
            "epochs_trained": train_info.get("epochs_trained"),
        },
    }
