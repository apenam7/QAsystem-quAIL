"""Train a model on SQuAD.
Author:
    Chris Chute (chute@stanford.edu)
"""
import os
import numpy as np
import random
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import torch.optim.lr_scheduler as sched
import torch.utils.data as data
from torch.utils.data import DataLoader
import utils.util as util
from sklearn.metrics import accuracy_score


from collections import OrderedDict
from json import dumps
from selfattbidaf_model import SelfAttBiDAF
from baseline_model import BiDAF
from utils.util import get_dataset_quail,get_dataset_race,get_dataset_race_and_quail

from tqdm import tqdm
from ujson import load as json_load
import warnings
warnings.filterwarnings("ignore")


def main():
    # for experiment, we are going to try 4 setups, which are use_baseline_mode (True or False) and use_data_augmentation (True or False)
    save_model_subdirectory = "preemd_proposal_augmentation/"
    load_path = None
    use_baseline_model = True
    use_data_augmentation = True

    root_dir = "./save/"
    models_dir = root_dir + save_model_subdirectory
    if save_model_subdirectory not in os.listdir(root_dir):
        os.mkdir(models_dir)
    # load_path = root_dir + "baseline/baseline_epoch5.pt"


    device = torch.device("cuda:0")
    #device = torch.device("cpu")
    # Set random seed
    ramdom_seed = 123
    random.seed(ramdom_seed)
    np.random.seed(ramdom_seed)
    torch.manual_seed(ramdom_seed)
    torch.cuda.manual_seed_all(ramdom_seed)

    # get processed batch dataloader
    # build standard Pytorch DataLoader object of our data
    if not use_data_augmentation:
        train_dataset, dev_dataset = get_dataset_quail()
    else:
        train_dataset, dev_dataset = get_dataset_race_and_quail()

    weights_matrix = train_dataset.vocab.weights_matrix
    weights_matrix = util.transform_weight_mat(weights_matrix)

    dataloader_train = DataLoader(train_dataset, shuffle=True, batch_size=64)
    dataloader_dev = DataLoader(dev_dataset, shuffle=True, batch_size=64)

    # define model parameters
    drop_prob = 0.0
    vocab_size = len(train_dataset.vocab)
    hidden_size = 80
    lr = 0.5
    l2_wd = 0
    max_grad_norm = 5.0

    # Get model
    if use_baseline_model:
        model = BiDAF(weights_matrix=weights_matrix,
                      hidden_size=hidden_size,
                      drop_prob=drop_prob)
    else:
        model = SelfAttBiDAF(weights_matrix=weights_matrix,
                          hidden_size=hidden_size,
                          drop_prob=drop_prob)

    if load_path:
        model.load_state_dict(torch.load(load_path))

    model = model.to(device)
    model.train()

    # training parameters
    step = 0
    ema = util.EMA(model, 0.999)
    criterion = nn.CrossEntropyLoss()
    criterion = criterion.to(device)
    num_epochs = 100

    # Get optimizer and scheduler
    optimizer = optim.Adadelta(model.parameters(), lr,
                               weight_decay=l2_wd)
    scheduler = sched.LambdaLR(optimizer, lambda s: 1.)  # Constant LR

    epoch = step // len(train_dataset)
    while epoch != num_epochs:
        epoch += 1
        epoch_losses = []
        print("epoch {}:".format(epoch))
        for cw_idxs, qw_idxs, y in dataloader_train:
            # Setup for forward
            cw_idxs = cw_idxs.to(device)
            qw_idxs = qw_idxs.to(device)
            batch_size = cw_idxs.size(0)
            optimizer.zero_grad()

            # Forward
            logits = model(cw_idxs, qw_idxs)
            y = y.to(device)
            loss = criterion(logits,y)
            loss_val = loss.item()
            # print("batch loss: {}".format(loss_val))
            epoch_losses.append(loss_val)
            # Backward
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
            optimizer.step()
            scheduler.step(step // batch_size)
            ema(model, step // batch_size)

            step += batch_size

        epoch_loss = np.mean(epoch_losses)
        print("training loss: {}".format(epoch_loss))
        ema.assign(model)
        # #y_true_train, y_pred_train = predict(model, dataloader_train, device)
        y_true_dev, y_pred_dev = predict(model, dataloader_dev, device)
        ema.resume(model)
        # #acc_train = accuracy_score(y_true_train, y_pred_train)
        acc_dev = accuracy_score(y_true_dev, y_pred_dev)
        print("dev accuracy: {0}\n".format(acc_dev))

        if epoch%10==0:
            save_dir = models_dir + "baseline_epoch{}.pt".format(epoch)
            torch.save(model.state_dict(), save_dir)


def predict(model, data_loader, device):
    y_pred = []
    y_true = []

    for i, batch in enumerate(data_loader):
        cw_idxs, qw_idxs, y = batch
        cw_idxs = cw_idxs.to(device)
        qw_idxs = qw_idxs.to(device)
        # Forward
        logits = model(cw_idxs, qw_idxs)

        y_pred_batch = torch.argmax(logits, 1)
        y_pred_batch = y_pred_batch.cpu()
        y_true_batch = y
        y_pred.append(y_pred_batch)
        y_true.append(y_true_batch)

    y_pred = np.concatenate(y_pred, axis=0)
    y_true = np.concatenate(y_true, axis=0)

    return y_true, y_pred

if __name__ == '__main__':
    main()