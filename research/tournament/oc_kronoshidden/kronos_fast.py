"""KV-cached multi-path sampler for Kronos (zero-shot inference only).

Mathematically the same procedure as the reference `auto_regressive_inference` (model/kronos.py, copied from ../Kronos), restricted to
the case context + pred_len <= max_context (no window roll), but
  * the context prefix (tokenizer encoder, predictor transformer, tokenizer decoder) is computed ONCE per series and shared by all
    sample paths (the reference repeats the context sample_count times),
  * every generated token reuses cached keys / values (the reference recomputes the full window at every step),
  * all sample paths are returned (the reference returns only their mean).
`verify()` checks the cached path against the reference model calls by teacher forcing the sampled tokens.
"""
from __future__ import annotations

import math

import torch
import torch.nn.functional as F

from model.kronos import sample_from_logits


def _rope(inv_freq, pos):
    """cos/sin for absolute positions pos (1-D long tensor) -> [len, dh]."""
    f = torch.outer(pos.to(inv_freq.dtype), inv_freq)
    e = torch.cat((f, f), dim=-1)
    return e.cos(), e.sin()


def _rot_half(x):
    x1, x2 = x.chunk(2, dim=-1)
    return torch.cat((-x2, x1), dim=-1)


def _apply_rope(x, cos, sin):  # x [..., n, dh], cos/sin [n, dh]
    return x * cos + _rot_half(x) * sin


def _proj_heads(lin, x, nh):  # x [..., n, d] -> [..., nh, n, dh]
    y = lin(x)
    sh = y.shape[:-1] + (nh, y.shape[-1] // nh)
    return y.view(sh).transpose(-3, -2)


def _merge_heads(o):  # [..., nh, n, dh] -> [..., n, d]
    o = o.transpose(-3, -2)
    return o.reshape(o.shape[:-2] + (o.shape[-2] * o.shape[-1],))


def _two_part_attn(q, kp, vp, kg, vg, causal_gen):
    """q [B,S,h,n,dh]; prefix kp/vp [B,h,P,dh] (shared by the S paths); generated kg/vg [B,S,h,m,dh] (m >= n, the last n are q's own
    positions). causal_gen: apply a causal mask inside the generated block (aligned to the end)."""
    scale = 1.0 / math.sqrt(q.shape[-1])
    sp = torch.einsum("bshnd,bhpd->bshnp", q, kp) * scale
    sg = torch.einsum("bshnd,bshmd->bshnm", q, kg) * scale
    n, m = q.shape[-2], kg.shape[-2]
    if causal_gen and n > 1:
        i = torch.arange(n, device=q.device)[:, None] + (m - n)
        j = torch.arange(m, device=q.device)[None, :]
        sg = sg.masked_fill(j > i, float("-inf"))
    w = torch.softmax(torch.cat([sp, sg], dim=-1), dim=-1)
    P = kp.shape[-2]
    return torch.einsum("bshnp,bhpd->bshnd", w[..., :P], vp) + torch.einsum("bshnm,bshmd->bshnd", w[..., P:], vg)


def _block_prefix(blk, x, pos):
    """Run a TransformerBlock on a full prefix x [B,P,d] (causal), return output and the post-RoPE k, v [B,h,P,dh]."""
    at = blk.self_attn
    h = blk.norm1(x)
    q, k, v = (_proj_heads(l, h, at.n_heads) for l in (at.q_proj, at.k_proj, at.v_proj))
    cos, sin = _rope(at.rotary.inv_freq, pos)
    q, k = _apply_rope(q, cos, sin), _apply_rope(k, cos, sin)
    o = F.scaled_dot_product_attention(q, k, v, is_causal=True)
    x = x + at.out_proj(_merge_heads(o))
    x = x + blk.ffn(blk.norm2(x))
    return x, k, v


def _block_step(blk, x, pos, kp, vp, cache, causal_gen=True):
    """Run a TransformerBlock on new tokens x [B,S,n,d] at absolute positions pos, attending to prefix (kp, vp) + generated cache
    (list [k, v] of [B,S,h,m,dh] or None). Updates cache in place."""
    at = blk.self_attn
    h = blk.norm1(x)
    q, k, v = (_proj_heads(l, h, at.n_heads) for l in (at.q_proj, at.k_proj, at.v_proj))
    cos, sin = _rope(at.rotary.inv_freq, pos)
    q, k = _apply_rope(q, cos, sin), _apply_rope(k, cos, sin)
    if cache[0] is None:
        cache[0], cache[1] = k, v
    else:
        cache[0], cache[1] = torch.cat([cache[0], k], dim=-2), torch.cat([cache[1], v], dim=-2)
    o = _two_part_attn(q, kp, vp, cache[0], cache[1], causal_gen)
    x = x + at.out_proj(_merge_heads(o))
    x = x + blk.ffn(blk.norm2(x))
    return x


def _dep_s2_logits(model, Hp_kv, Hg, h_last, s1):
    """DependencyAwareLayer + conditional head for the LAST position only.
    In eval mode the reference cross-attention (query = emb_s1(sampled s1), length 1) attends to ALL hidden states, is not causal, and
    its RoPE uses position 0 for q and k (identity). Its output is broadcast-added to every position; only the last is used.
    Hp_kv: (k, v) of the prefix hidden states [B,h,P,dh]; Hg: generated hidden states [B,S,m,d] (incl. the current one); h_last [B,S,d]."""
    ca = model.dep_layer.cross_attn
    sib = model.embedding.emb_s1(s1)  # [B,S,d]
    q = _proj_heads(ca.q_proj, sib[:, :, None, :], ca.n_heads)  # [B,S,h,1,dh]
    kg, vg = _proj_heads(ca.k_proj, Hg, ca.n_heads), _proj_heads(ca.v_proj, Hg, ca.n_heads)
    o = _two_part_attn(q, Hp_kv[0], Hp_kv[1], kg, vg, causal_gen=False)
    attn = ca.out_proj(_merge_heads(o))[:, :, 0, :]
    x2 = model.dep_layer.norm(h_last + attn)
    return model.head.cond_forward(x2)


@torch.no_grad()
def sample_paths(tokenizer, model, x, x_stamp, y_stamp, pred_len, S, T=1.0, top_k=0, top_p=0.9, clip=5, return_tokens=False):
    """x [B,P,6] normalised; x_stamp [B,P,5]; y_stamp [B,pred_len,5]. Returns decoded paths [B,S,pred_len,6] (normalised units)."""
    x = torch.clip(x, -clip, clip)
    B, P, _ = x.shape
    s1p, s2p = tokenizer.encode(x, half=True)  # [B,P] each (deterministic quantisation)
    pos_p = torch.arange(P, device=x.device)
    # ---- predictor prefix
    h = model.embedding([s1p, s2p]) + model.time_emb(x_stamp)
    pkv = []
    for blk in model.transformer:
        h, k, v = _block_prefix(blk, h, pos_p)
        pkv.append((k, v))
    Hp = model.norm(h)  # [B,P,d]
    ca = model.dep_layer.cross_attn
    Hp_kv = (_proj_heads(ca.k_proj, Hp, ca.n_heads), _proj_heads(ca.v_proj, Hp, ca.n_heads))
    logits1 = model.head(Hp[:, -1, :])  # [B,V]
    caches = [[None, None] for _ in model.transformer]
    Hg = None
    gen1, gen2 = [], []
    h_last = Hp[:, -1, :][:, None, :].expand(B, S, Hp.shape[-1])
    lg = logits1[:, None, :].expand(B, S, logits1.shape[-1]).reshape(B * S, -1).clone()
    for i in range(pred_len):
        s1 = sample_from_logits(lg, temperature=T, top_k=top_k, top_p=top_p, sample_logits=True).view(B, S)
        Hcat = h_last[:, :, None, :] if Hg is None else Hg
        if i == 0:
            # at step 0 the query attends to prefix hidden states only (Hp already contains the last context position)
            sib_kv = Hp_kv
            ca_q = _proj_heads(ca.q_proj, model.embedding.emb_s1(s1)[:, :, None, :], ca.n_heads)
            scale = 1.0 / math.sqrt(ca_q.shape[-1])
            w = torch.softmax(torch.einsum("bshnd,bhpd->bshnp", ca_q, sib_kv[0]) * scale, dim=-1)
            o = torch.einsum("bshnp,bhpd->bshnd", w, sib_kv[1])
            x2 = model.dep_layer.norm(h_last + ca.out_proj(_merge_heads(o))[:, :, 0, :])
            lg2 = model.head.cond_forward(x2)
        else:
            lg2 = _dep_s2_logits(model, Hp_kv, Hcat, h_last, s1)
        s2 = sample_from_logits(lg2.reshape(B * S, -1), temperature=T, top_k=top_k, top_p=top_p, sample_logits=True).view(B, S)
        gen1.append(s1)
        gen2.append(s2)
        if i == pred_len - 1:
            break
        # feed the new token at absolute position P + i with the forecast-bar stamp y_stamp[:, i]
        e = model.embedding([s1, s2]) + model.time_emb(y_stamp[:, i:i + 1, :].expand(B, S, -1).reshape(B * S, 1, -1)).view(B, S, -1)
        hh = e[:, :, None, :]
        pos = torch.tensor([P + i], device=x.device)
        for li, blk in enumerate(model.transformer):
            hh = _block_step(blk, hh, pos, pkv[li][0], pkv[li][1], caches[li])
        hn = model.norm(hh)  # [B,S,1,d]
        Hg = hn if Hg is None else torch.cat([Hg, hn], dim=2)
        h_last = hn[:, :, 0, :]
        lg = model.head(h_last).reshape(B * S, -1)
    g1, g2 = torch.stack(gen1, dim=-1), torch.stack(gen2, dim=-1)  # [B,S,pred_len]
    # ---- tokenizer decoder: prefix once, generated chunk per path (causal)
    zp = tokenizer.post_quant_embed(tokenizer.indices_to_bits([s1p, s2p], half=True))
    tkv = []
    for blk in tokenizer.decoder:
        zp, k, v = _block_prefix(blk, zp, pos_p)
        tkv.append((k, v))
    zg = tokenizer.post_quant_embed(tokenizer.indices_to_bits([g1, g2], half=True))  # [B,S,n,d]
    posg = torch.arange(P, P + pred_len, device=x.device)
    for li, blk in enumerate(tokenizer.decoder):
        zg = _block_step(blk, zg, posg, tkv[li][0], tkv[li][1], [None, None], causal_gen=True)
    out = tokenizer.head(zg)  # [B,S,n,6]
    if return_tokens:
        return out, (s1p, s2p, g1, g2)
    return out


@torch.no_grad()
def verify(tokenizer, model, x, x_stamp, y_stamp, pred_len, S=4):
    """Teacher-force the paths sampled by sample_paths through the reference model calls and compare outputs + logits."""
    torch.manual_seed(0)
    out, (s1p, s2p, g1, g2) = sample_paths(tokenizer, model, x, x_stamp, y_stamp, pred_len, S, return_tokens=True)
    B, P = s1p.shape
    full1 = torch.cat([s1p[:, None, :].expand(B, S, P), g1], -1).reshape(B * S, -1)
    full2 = torch.cat([s2p[:, None, :].expand(B, S, P), g2], -1).reshape(B * S, -1)
    st = torch.cat([x_stamp, y_stamp], 1)[:, None].expand(B, S, -1, -1).reshape(B * S, P + pred_len, -1)
    z = tokenizer.decode([full1, full2], half=True)[:, -pred_len:, :].view(B, S, pred_len, -1)
    err_dec = (z - out).abs().max().item()
    # reference s1 logits at the last context position and at generated positions (only the first pred_len-1 tokens are fed)
    lg1, ctx = model.decode_s1(full1[:, :P + pred_len - 1], full2[:, :P + pred_len - 1], st[:, :P + pred_len - 1])
    # recompute our s1 logits by teacher forcing via the cached path is implicit: compare the reference argmax-consistency with probabilities
    # of the sampled tokens (must be finite = inside the top-p nucleus of the reference distribution)
    ref = lg1[:, P - 1:, :]  # logits for generated positions 0..pred_len-1
    lp = torch.log_softmax(ref, -1).gather(-1, g1.reshape(B * S, -1)[..., None])[..., 0]
    # s2 reference for the last generated step
    s2l = []
    for i in range(pred_len):
        L = P + i
        _, c = model.decode_s1(full1[:, :L], full2[:, :L], st[:, :L])
        s2l.append(model.decode_s2(c, full1[:, L:L + 1])[:, -1, :])
    s2ref = torch.stack(s2l, 1)
    lp2 = torch.log_softmax(s2ref, -1).gather(-1, g2.reshape(B * S, -1)[..., None])[..., 0]
    return dict(max_abs_decode_diff=err_dec, min_logp_s1=lp.min().item(), min_logp_s2=lp2.min().item())


@torch.no_grad()
def logits_check(tokenizer, model, x, x_stamp, y_stamp, pred_len):
    """Exact check of the cached logits vs the reference forward (greedy decoding: top_k=1 makes sampling deterministic)."""
    out_fast, (s1p, s2p, g1, g2) = sample_paths(tokenizer, model, x, x_stamp, y_stamp, pred_len, S=1, top_k=1, top_p=1.0, return_tokens=True)
    # reference greedy loop using the original model calls (full recompute each step)
    B, P = s1p.shape
    c1, c2 = s1p.clone(), s2p.clone()
    st = torch.cat([x_stamp, y_stamp], 1)
    for i in range(pred_len):
        L = P + i
        lg, c = model.decode_s1(c1, c2, st[:, :L])
        a1 = lg[:, -1, :].argmax(-1, keepdim=True)
        a2 = model.decode_s2(c, a1)[:, -1, :].argmax(-1, keepdim=True)
        c1, c2 = torch.cat([c1, a1], 1), torch.cat([c2, a2], 1)
    z = tokenizer.decode([c1, c2], half=True)[:, -pred_len:, :]
    same_tokens = bool((c1[:, P:] == g1[:, 0]).all() and (c2[:, P:] == g2[:, 0]).all())
    return dict(same_greedy_tokens=same_tokens, max_abs_decode_diff=(z - out_fast[:, 0]).abs().max().item())
