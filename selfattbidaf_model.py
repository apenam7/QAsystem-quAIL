import layers
import torch
import torch.nn as nn


class SelfAttBiDAF(nn.Module):
    """
    Follows a high-level structure commonly found in SQuAD models:
        - Embedding layer: Embed word indices to get word vectors.
        - Encoder layer: Encode the embedded sequence.
        - Attention layer: Apply an attention mechanism to the encoded sequence.
        - self-attention layer: apply the self attention to the output of attention layer.
        - Model encoder layer: Encode the sequence again.
        - Output layer: Simple layer to get final outputs.
    Args:
        weights_matrix (np.array): Pre-trained word vectors. In our case, GloVe is adopted.
        hidden_size (int): Number of features in the hidden state at each layer.
        drop_prob (float): Dropout probability.
    """
    def __init__(self, weights_matrix, hidden_size, drop_prob=0.):
        super(SelfAttBiDAF, self).__init__()
        self.emb = layers.Embedding(weights_matrix=weights_matrix,
                                    hidden_size=hidden_size)

        self.enc = layers.RNNEncoder(input_size=hidden_size,
                                     hidden_size=hidden_size,
                                     num_layers=1,
                                     drop_prob=drop_prob)

        self.att = layers.BiDAFAttention(hidden_size=2 * hidden_size,
                                         drop_prob=drop_prob)

        self.self_att = layers.SelfAtt(hidden_size=2 * hidden_size,
                                       drop_prob=drop_prob)

        self.mod = layers.RNNEncoder(input_size=8 * hidden_size,
                                     hidden_size=hidden_size,
                                     num_layers=2,
                                     drop_prob=drop_prob)

        self.out = layers.BiDAFOutput(hidden_size=hidden_size)

    def forward(self, cw_idxs, qw_idxs):
        c_mask = torch.zeros_like(cw_idxs) != cw_idxs
        q_mask = torch.zeros_like(qw_idxs) != qw_idxs
        c_len, q_len = c_mask.sum(-1), q_mask.sum(-1)

        c_emb = self.emb(cw_idxs)         # (batch_size, c_len, hidden_size)
        q_emb = self.emb(qw_idxs)         # (batch_size, q_len, hidden_size)

        c_enc,_ = self.enc(c_emb, c_len)    # (batch_size, c_len, 2 * hidden_size)
        q_enc,_ = self.enc(q_emb, q_len)    # (batch_size, q_len, 2 * hidden_size)

        att = self.att(c_enc, q_enc,
                       c_mask, q_mask)    # (batch_size, c_len, 8 * hidden_size)

        att = self.self_att(att, c_mask)    # (batch_size, c_len, 8 * hidden_size)

        _, h_n = self.mod(att, c_len)        # (batch_size, c_len, 2 * hidden_size)

        out = self.out(h_n)  # 2 tensors, each (batch_size, c_len)

        return out
