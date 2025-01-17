# Copyright (c) Facebook, Inc. and its affiliates.
#
# This source code is licensed under the MIT license found in the
# LICENSE file in the root directory of this source tree.

import math
import torch
from fairseq import utils
from fairseq.criterions import FairseqCriterion, register_criterion


def label_smoothed_nll_loss(lprobs, target, epsilon, ignore_index=None, reduce=True):
    if target.dim() == lprobs.dim() - 1:
        target = target.unsqueeze(-1)
    nll_loss = -lprobs.gather(dim=-1, index=target)
    smooth_loss = -lprobs.sum(dim=-1, keepdim=True)
    if ignore_index is not None:
        non_pad_mask = target.ne(ignore_index)
        nll_loss = nll_loss[non_pad_mask]
        smooth_loss = smooth_loss[non_pad_mask]
    else:
        nll_loss = nll_loss.squeeze(-1)
        smooth_loss = smooth_loss.squeeze(-1)
    if reduce:
        nll_loss = nll_loss.sum()
        smooth_loss = smooth_loss.sum()
    eps_i = epsilon / lprobs.size(-1)
    loss = (1. - epsilon) * nll_loss + eps_i * smooth_loss
    return loss, nll_loss


@register_criterion('crf_loss')
class CRFCriterion(FairseqCriterion):

    def __init__(self, args, task):
        super().__init__(args, task)
        self.eps = args.label_smoothing
        self.task = task

    @staticmethod
    def add_args(parser):
        """Add criterion-specific arguments to the parser."""
        # fmt: off
        parser.add_argument('--label-smoothing', default=0., type=float, metavar='D',
                            help='epsilon for label smoothing, 0 means no label smoothing')
        # fmt: on

    def forward(self, model, sample, reduce=True):
        """Compute the loss for the given sample.

        Returns a tuple with three elements:
        1) the loss
        2) the sample size, which is used as the denominator for the gradient
        3) logging outputs to display while training
        """
        net_output = model(**sample['net_input'])
        # loss, nll_loss = self.compute_loss(model, net_output, sample, reduce=reduce)
        loss = self.compute_loss(model, net_output, sample, reduce=reduce)
        sample_size = sample['target'].size(0) if self.args.sentence_avg else sample['ntokens']
        logging_output = {
            'loss': utils.item(loss.data) if reduce else loss.data,
            # 'nll_loss': utils.item(nll_loss.data) if reduce else nll_loss.data,
            'ntokens': sample['ntokens'],
            'nsentences': sample['target'].size(0),
            'sample_size': sample_size,
        }
        return loss, sample_size, logging_output
#    def compute_loss(self, model, net_output, sample, reduce=True):
#        lprobs = model.get_normalized_probs(net_output, log_probs=True)
#        lprobs = lprobs.view(-1, lprobs.size(-1))
#        target = model.get_targets(sample, net_output).view(-1)
#        loss = F.nll_loss(
#            lprobs,
#            target,
#            ignore_index=self.padding_idx,
#            reduction='sum' if reduce else 'none',
#        )
#        return loss, loss
    def compute_loss(self, model, net_output, sample, reduce=True):
        mask_tensor = torch.arange(net_output.size(1))[None, :].to(sample['net_input']['src_lengths'].device) < \
                      sample['net_input']['src_lengths'][:, None]
        #print(net_output.size())
        #print("--------------------")
        #print(sample['target'].size())
        #for src in self.task.source_dictionary.string(sample['net_input']['src_tokens']):
        #    print(src)
        #print(self.task.source_dictionary.string(sample['net_input']['src_tokens']).split())
        #print(len(self.task.source_dictionary.string(sample['net_input']['src_tokens']).split()))
        #for tgt in sample['target']:
        #    print(''.join(self.task.target_dictionary.string(tgt).replace('▁', '')))
        #for src in sample['net_input']['src_tokens']:
        #    print(''.join(self.task.source_dictionary.string(src)).replace('▁', ''))
        #for i in sample['id'].tolist():
        #    print(i)
        #print('--------------------')

        return -model.crf(net_output, sample['target'], mask=mask_tensor)

    @staticmethod
    def aggregate_logging_outputs(logging_outputs):
        """Aggregate logging outputs from data parallel training."""
        ntokens = sum(log.get('ntokens', 0) for log in logging_outputs)
        nsentences = sum(log.get('nsentences', 0) for log in logging_outputs)
        sample_size = sum(log.get('sample_size', 0) for log in logging_outputs)
        return {
            'loss': sum(log.get('loss', 0) for log in logging_outputs) / sample_size / math.log(
                2) if sample_size > 0 else 0.,
            'nll_loss': sum(log.get('nll_loss', 0) for log in logging_outputs) / ntokens / math.log(
                2) if ntokens > 0 else 0.,
            'ntokens': ntokens,
            'nsentences': nsentences,
            'sample_size': sample_size,
       }
