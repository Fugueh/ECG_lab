import numpy as np  
import torch  
import torch.nn as nn  
from torch.utils.data import Dataset, DataLoader  
  
# ---------- Dataset: X -> y ----------  
class ECGWindowDataset(Dataset):  
def __init__(self, X, y):  
"""  
X: np.ndarray, shape (N, L, C) (C=1 or 2)  
y: np.ndarray, shape (N,) values in {0,1,2}  
"""  
self.X = torch.tensor(X, dtype=torch.float32).permute(0, 2, 1) # -> (N, C, L)  
self.y = torch.tensor(y, dtype=torch.long)  
  
def __len__(self): return len(self.y)  
def __getitem__(self, i): return self.X[i], self.y[i]  
  
# ---------- Model: (C,L) -> 3 logits ----------  
class Tiny1DCNN(nn.Module):  
def __init__(self, C=1, n_classes=3):  
super().__init__()  
self.net = nn.Sequential(  
nn.Conv1d(C, 16, kernel_size=7, stride=2, padding=3),  
nn.ReLU(),  
nn.Conv1d(16, 32, kernel_size=5, stride=2, padding=2),  
nn.ReLU(),  
nn.Conv1d(32, 64, kernel_size=5, stride=2, padding=2),  
nn.ReLU(),  
nn.AdaptiveAvgPool1d(1), # -> (B,64,1)  
nn.Flatten(), # -> (B,64)  
nn.Linear(64, n_classes) # -> (B,3)  
)  
  
def forward(self, x):  
return self.net(x)  
  
# ---------- Train loop ----------  
def train_one_epoch(model, loader, optim, device="cuda"):  
model.train()  
ce = nn.CrossEntropyLoss()  
total, correct, loss_sum = 0, 0, 0.0  
for Xb, yb in loader:  
Xb, yb = Xb.to(device), yb.to(device)  
optim.zero_grad()  
logits = model(Xb)  
loss = ce(logits, yb)  
loss.backward()  
optim.step()  
  
loss_sum += loss.item() * len(yb)  
pred = logits.argmax(dim=1)  
correct += (pred == yb).sum().item()  
total += len(yb)  
return loss_sum/total, correct/total  
  
# ---------- Inference: return probs ----------  
@torch.no_grad()  
def predict_proba(model, X, device="cuda"):  
"""  
X: np.ndarray (N, L, C)  
return: np.ndarray (N, 3)  
"""  
model.eval()  
Xt = torch.tensor(X, dtype=torch.float32).permute(0,2,1).to(device)  
logits = model(Xt)  
probs = torch.softmax(logits, dim=1).cpu().numpy()  
return probs
