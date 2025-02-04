import argparse
import sys
import torch
import random
import numpy as np
import os


def seed_torch(seed=42):
    seed = int(seed)
    random.seed(seed)
    os.environ['PYTHONHASHSEED'] = str(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.enabled = True
    
seed_torch(123)

# def get_freer_gpu():
#     os.system('nvidia-smi -q -d Memory |grep -A4 GPU|grep Free >tmp')
#     memory_available = [int(x.split()[2]) for x in open('tmp', 'r').readlines()]
#     # memory_available = memory_available[1:6]
#     if len(memory_available) == 0:
#         return -1
#     return int(np.argmax(memory_available))

# os.environ["CUDA_VISIBLE_DEVICES"] = str(get_freer_gpu())

sys.path.append('..')
sys.path.append('../..')

parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument(
    '--dataset-dir', default='datasets/sample', help='the dataset directory'
)
parser.add_argument(
    '--gnn', default='GATConv', choices=["GCNConv", "GATConv"], help='the gnn encoder. '
)
parser.add_argument(
    '--solver', default='rk4', help='The neural ordinary equation solver.', choices=["euler", "rk4", "dopri5"]
)
parser.add_argument('--embedding-dim', type=int, default=256, help='the embedding size')
parser.add_argument('--num-layers', type=int, default=1, help='the number of layers')
parser.add_argument(
    '--feat-drop', type=float, default=0.1, help='the dropout ratio for features'
)
parser.add_argument('--lr', type=float, default=1e-3, help='the learning rate')
parser.add_argument(
    '--batch-size', type=int, default=512, help='the batch size for training'
)
parser.add_argument(
    '--epochs', type=int, default=30, help='the number of training epochs'
)
parser.add_argument(
    '--weight-decay',
    type=float,
    default=1e-4,
    help='the parameter for L2 regularization',
)
parser.add_argument(
    '--patience',
    type=int,
    default=2,
    help='the number of epochs that the performance does not improves after which the training stops',
)
parser.add_argument(
    '--num-workers',
    type=int,
    default=8,
    help='the number of processes to load the input graphs',
)
parser.add_argument(
    '--valid-split',
    type=float,
    default=None,
    help='the fraction for the validation set',
)
parser.add_argument(
    '--log-interval',
    type=int,
    default=100,
    help='print the loss after this number of iterations',
)
parser.add_argument(
    '--num-splits',
    type=int,
    default=3,
    help='print the loss after this number of iterations',
)
args = parser.parse_args()
print(args)


from pathlib import Path
import torch as th
from torch.utils.data import DataLoader, SequentialSampler
from src.utils.data.dataset import read_dataset, AugmentedDataset
from src.utils.data.collate import (
    seq_to_temporal_session_graph,
    collate_fn_factory_temporal,
)
from src.utils.train import TrainRunner
from src.models import GNG_ODE

dataset_dir = Path(args.dataset_dir)

print('reading dataset')
train_sessions, test_sessions, train_timestamps, test_timestamps, num_items = read_dataset(dataset_dir)

if args.valid_split is not None:
    num_valid        = int(len(train_sessions) * args.valid_split)
    test_sessions    = train_sessions[-num_valid:]
    train_sessions   = train_sessions[:-num_valid]
    test_timestamps  = train_timestamps[-num_valid:]
    train_timestamps = train_timestamps[:-num_valid]

dataset = args.dataset_dir.strip().split("/")[-1]

train_set = AugmentedDataset(dataset, train_sessions, train_timestamps)
test_set  = AugmentedDataset(dataset, test_sessions,  test_timestamps)

collate_fn = collate_fn_factory_temporal(seq_to_temporal_session_graph)

train_loader = DataLoader(
    train_set,
    batch_size=args.batch_size,
    shuffle=True,
    # drop_last=True,
    num_workers=args.num_workers,
    collate_fn=collate_fn,
    # pin_memory=True,
    # sampler=SequentialSampler(train_set)
)

test_loader = DataLoader(
    test_set,
    batch_size=args.batch_size,
    # shuffle=True,
    num_workers=args.num_workers,
    collate_fn=collate_fn,
)

model  = GNG_ODE(dataset, num_items, args.gnn, args.embedding_dim, args.num_layers, feat_drop=args.feat_drop, solver=args.solver, num_splits=args.num_splits)
device = th.device('cuda:0' if th.cuda.is_available() else 'cpu')
model  = model.to(device)
print(model)

runner = TrainRunner(
    args.dataset_dir,
    model,
    train_loader,
    test_loader,
    device=device,
    lr=args.lr,
    weight_decay=args.weight_decay,
    patience=args.patience,
)

print('start training')
mrr10, mrr20, hit10, hit20 = runner.train(args.epochs, args.log_interval)
print('MRR@20\tHR@20')
print(f'{mrr10 * 100:.3f}%\t{mrr20 * 100:.3f}%\t{hit10 * 100:.3f}%\t{hit20 * 100:.3f}%')
