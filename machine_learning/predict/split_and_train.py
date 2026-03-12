import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
from sklearn.model_selection import train_test_split
from torch.utils.data import Dataset, DataLoader, WeightedRandomSampler

# -------- 数据载入：Transform, Dataset -------

def ecg_transform(sample):
    x = sample["data"].astype(np.float32)          # (2500,)
    # per-sample z-score
    m = x.mean()
    s = x.std()
    x = (x - m) / (s + 1e-8)
    # Conv1d expects (C, L)
    x = torch.from_numpy(x).unsqueeze(0)           # (1, 2500)
    y = torch.tensor(sample["labels"], dtype=torch.long)
    return {"data": x, "labels": y}


class ECGDataset(Dataset):
    def __init__(self, df, x_col="ecg_raw", y_col="label_int", transform=None):
        self.df = df.reset_index(drop=True)
        self.x_col = x_col
        self.y_col = y_col
        self.transform = transform

    def __len__(self):
        return len(self.df)

    def __getitem__(self, index):
        sample = {
            "data": np.asarray(self.df.at[index, self.x_col]).copy(),
            "labels": int(self.df.at[index, self.y_col]),
        }
        if self.transform:
            sample = self.transform(sample)
        return sample


def get_train_val_test_ds(data):
    idx = data.index.to_numpy()
    y = data["label_int"].to_numpy()

    # 1) 先切 train vs test
    # 分层：stratify=y 按 y 的类别分层
    train_idx, test_idx = train_test_split(
        idx, test_size=0.2, random_state=2026, stratify=y
    )

    # 2) 再从 train 切出 val（分层）
    train_y = data.loc[train_idx, "label_int"].to_numpy()
    train_idx, val_idx = train_test_split(
        train_idx, test_size=0.1, random_state=2026, stratify=train_y
    )
    return train_idx, val_idx, test_idx


def get_dataset(data, train_idx, val_idx, test_idx):
    # 3) Dataset
    train_ds = ECGDataset(data.loc[train_idx].reset_index(drop=True))
    val_ds   = ECGDataset(data.loc[val_idx].reset_index(drop=True))
    test_ds  = ECGDataset(data.loc[test_idx].reset_index(drop=True))
    return train_ds, val_ds, test_ds


def get_sampler(data, train_idx):
    # 4) 只给 train 做 sampler（基于 train labels）
    train_labels = data.loc[train_idx, "label_int"].to_numpy()
    class_counts = np.bincount(train_labels)          # [good, bad]
    class_weights = 1.0 / class_counts
    sample_weights = class_weights[train_labels]

    train_sampler = WeightedRandomSampler(
        weights=torch.from_numpy(sample_weights).float(),
        num_samples=len(train_labels),
        replacement=True
    )
    return train_sampler


def get_dataloader(train_ds, val_ds, test_ds, train_sampler):
    # 5) DataLoader：train 用 sampler；val/test 不用
    train_loader = DataLoader(train_ds, batch_size=64, sampler=train_sampler, num_workers=0)
    val_loader   = DataLoader(val_ds, batch_size=64, shuffle=False, num_workers=0)
    test_loader  = DataLoader(test_ds, batch_size=64, shuffle=False, num_workers=0)
    return train_loader, val_loader, test_loader


# ------ 准备喂模型：切分、采样、DataLoader实例化 ------

def get_train_val_test_ds(data):
    idx = data.index.to_numpy()
    y = data["label_int"].to_numpy()

    # 1) 先切 train vs test
    # 分层：stratify=y 按 y 的类别分层
    train_idx, test_idx = train_test_split(
        idx, test_size=0.2, random_state=2026, stratify=y
    )

    # 2) 再从 train 切出 val（分层）
    train_y = data.loc[train_idx, "label_int"].to_numpy()
    train_idx, val_idx = train_test_split(
        train_idx, test_size=0.1, random_state=2026, stratify=train_y
    )
    return train_idx, val_idx, test_idx


def get_dataset(data, train_idx, val_idx, test_idx):
    # 3) Dataset
    train_ds = ECGDataset(data.loc[train_idx].reset_index(drop=True))
    val_ds   = ECGDataset(data.loc[val_idx].reset_index(drop=True))
    test_ds  = ECGDataset(data.loc[test_idx].reset_index(drop=True))
    return train_ds, val_ds, test_ds


def get_sampler(data, train_idx):
    # 4) 只给 train 做 sampler（基于 train labels）
    train_labels = data.loc[train_idx, "label_int"].to_numpy()
    class_counts = np.bincount(train_labels)          # [good, bad]
    class_weights = 1.0 / class_counts
    sample_weights = class_weights[train_labels]

    train_sampler = WeightedRandomSampler(
        weights=torch.from_numpy(sample_weights).float(),
        num_samples=len(train_labels),
        replacement=True
    )
    return train_sampler


def get_dataloader(train_ds, val_ds, test_ds, train_sampler):
    # 5) DataLoader：train 用 sampler；val/test 不用
    train_loader = DataLoader(train_ds, batch_size=64, sampler=train_sampler, num_workers=0)
    val_loader   = DataLoader(val_ds, batch_size=64, shuffle=False, num_workers=0)
    test_loader  = DataLoader(test_ds, batch_size=64, shuffle=False, num_workers=0)
    return train_loader, val_loader, test_loader


# ------ 模型与训练 ------

class ConvNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.conv1 = nn.Conv1d(1, 32, 7, padding=3)
        self.mp = nn.MaxPool1d(5)
        self.conv2 = nn.Conv1d(32, 32, 7, padding=3)
        self.gap = nn.AdaptiveAvgPool1d(1)   # (B, 32, 1)
        self.linear1 = nn.Linear(32, 128)
        self.linear2 = nn.Linear(128, 1)     # binary logit

    def forward(self, x):
        # x: (B, 1, L)
        x = self.mp(torch.relu(self.conv1(x)))
        x = torch.relu(self.conv2(x))
        x = self.gap(x).squeeze(-1)          # (B, 32)
        x = torch.relu(self.linear1(x))
        x = self.linear2(x).squeeze(-1)      # (B,)
        return x


def accuracy_from_logits(logits, y):
    probs = torch.sigmoid(logits)
    preds = (probs > 0.5).long()
    return (preds == y.long()).float().mean().item()


def train_one_epoch(dataloader, model, criterion, optimizer, device):
    model.train()
    total_loss = 0.0
    total_acc = 0.0
    n = 0

    for batch in dataloader:
        x = batch["data"].to(device).float()  # (B, 2500)
        if x.ndim == 2:
            x = x.unsqueeze(1)   # (B, 1, 2500)
        y = batch["labels"].to(device).float() # (B,) float for BCE

        optimizer.zero_grad()
        logits = model(x)
        loss = criterion(logits, y)
        loss.backward()
        optimizer.step()

        bs = x.size(0)
        total_loss += loss.item() * bs
        total_acc += accuracy_from_logits(logits.detach(), y.detach()) * bs
        n += bs
    return total_loss / n, total_acc / n


@torch.no_grad()
def evaluate(dataloader, model, criterion, device):
    model.eval()
    total_loss = 0.0
    total_acc = 0.0
    n = 0

    for batch in dataloader:
        x = batch["data"].to(device).float()  # (B, 2500)
        if x.ndim == 2:
            x = x.unsqueeze(1)   # (B, 1, 2500)
        y = batch["labels"].to(device).float() # (B,) float for BCE

        logits = model(x)
        loss = criterion(logits, y)

        bs = x.size(0)
        total_loss += loss.item() * bs
        total_acc += accuracy_from_logits(logits, y) * bs
        n += bs

    return total_loss / n, total_acc / n