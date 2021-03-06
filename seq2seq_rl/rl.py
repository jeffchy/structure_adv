from nltk.translate.bleu_score import sentence_bleu as BLEU
import numpy as np
import torch.nn as nn
import torch, os, codecs
import socket

import global_variables



def get_bleu(out, dec_out, vocab_size):
    out = out.tolist()
    dec_out = dec_out.tolist()
    stop_token = 1
    if stop_token in out:
        cnd = out[:out.index(stop_token)]
    else:
        cnd = out

    if stop_token in dec_out:
        ref = [dec_out[:dec_out.index(stop_token)]]
    else:
        ref = [dec_out]

    bleu = BLEU(ref, cnd)

    return bleu


def get_correct(out, dec_out, num_words):
    out = out.tolist()
    dec_out = dec_out.tolist()
    stop_token = 1
    if stop_token in out:
        cnd = out[:out.index(stop_token)]
    else:
        cnd = out

    if stop_token in dec_out:
        ref = [dec_out[:dec_out.index(stop_token)]]
    else:
        ref = [dec_out]
    tmp = [1 if cnd[i] == ref[i] else 0 for i in range(1, min(len(cnd), len(ref)))]
    if not tmp:
        stc_crt = 0
    else:
        stc_crt = sum(tmp)
    if not max(len(cnd), len(ref)) - 1>0:
        print(max(len(cnd), len(ref)))
    # assert max(len(cnd), len(ref)) - 1>0
    return stc_crt, max(len(cnd), len(ref))-1


class LossRL(nn.Module):
    def __init__(self):
        super(LossRL, self).__init__()

        self.bl = 0
        self.bn = 0

    def forward(self, sel, pb, dec_out, stc_length, vocab_size):
        ls = 0
        cnt = 0

        sel = sel.detach().cpu().numpy()
        dec_out = dec_out.cpu().numpy()

        batch = sel.shape[0]
        bleus = []
        for i in range(batch):
            bleu = get_bleu(sel[i], dec_out[i], vocab_size)

            bleus.append(bleu)
        bleus = np.asarray(bleus)

        wgt = np.asarray([1 for _ in range(batch)])
        for j in range(stc_length):
            ls += (- pb[:, j] *
                   torch.from_numpy(bleus - self.bl).float().cuda() *
                   torch.from_numpy(wgt.astype(float)).float().cuda()).sum()
            cnt += np.sum(wgt)
            stop_token = 1
            wgt = wgt.__and__(sel[:, j] != stop_token)  # vocab_size + 1

        ls /= cnt

        bleu = np.average(bleus)
        self.bl = (self.bl * self.bn + bleu) / (self.bn + 1)
        self.bn += 1

        return ls


class LossBiafRL1(nn.Module):
    def __init__(self, device, word_alphabet, vocab_size):
        super(LossBiafRL1, self).__init__()

        self.bl = 0
        self.bn = 0
        self.device = device
        self.word_alphabet = word_alphabet
        self.vocab_size = vocab_size

    def get_reward(self, out, dec_out, length_out, ori_words, ori_words_length):

        stc_dda = sum([0 if out[i] == dec_out[i] else 1 for i in range(1, length_out)])

        reward = stc_dda

        return reward

    def write_text(self, ori_words, ori_words_length, sel, stc_length_out):
        condsf = 'cands.txt'
        refs = 'refs.txt'
        oris = [[self.word_alphabet.get_instance(ori_words[si, wi]).encode('utf-8') for wi in range(1, ori_words_length[si])] for si in range(len(ori_words))]
        preds = [[self.word_alphabet.get_instance(sel[si, wi]).encode('utf-8') for wi in range(1, stc_length_out[si])] for si in range(len(sel))]

        wf = codecs.open(condsf, 'w', encoding='utf8')
        preds_tmp = [' '.join(i) for i in preds]
        preds_s = '\n'.join(preds_tmp)
        wf.write(preds_s)
        wf.close()

        wf = codecs.open(refs, 'w', encoding='utf8')
        oris_tmp = [' '.join(i) for i in oris]
        oris_s = '\n'.join(oris_tmp)
        wf.write(oris_s)
        wf.close()


    def forward(self, sel, pb, predicted_out, golden_out, mask_id, stc_length_out, sudo_golden_out, sudo_golden_out_1, ori_words, ori_words_length):


        ####1####
        ls1 = 0
        cnt1 = 0
        stc_length_seq = sel.shape[1]
        batch = sel.shape[0]
        rewards = []
        for i in range(batch):  #batch
            reward = self.get_reward(predicted_out[i], sudo_golden_out[i], stc_length_out[i], ori_words[i], ori_words_length[i])  
            rewards.append(reward)
        rewards = np.asarray(rewards)
        for j in range(stc_length_seq):
            wgt1 = np.asarray([1 if j < stc_length_out[i] else 0 for i in range(batch)])
            # ls1 += (- pb[:, j] *
            #         torch.from_numpy(rewards).float().cuda() *
            #         torch.from_numpy(wgt1.astype(float)).float().cuda()).sum()
            ls1 += (- pb[:, j] *
                    torch.from_numpy(rewards).float().to(self.device) *
                    torch.from_numpy(wgt1.astype(float)).float().to(self.device)).sum()
            cnt1 += np.sum(wgt1)

        ls1 /= cnt1
        rewards_ave1 = np.average(rewards)

        # ####2####
        ls2 = 0
        cnt2 = 0
        stc_length_seq = sel.shape[1]
        batch = sel.shape[0]
        rewards = []
        for i in range(batch):  #batch
            reward = self.get_reward(predicted_out[i], sudo_golden_out_1[i], stc_length_out[i], ori_words[i], ori_words_length[i])  
            rewards.append(reward)
        rewards = np.asarray(rewards)

        for j in range(stc_length_seq):
            wgt2 = np.asarray([1 if j < stc_length_out[i] else 0 for i in range(batch)])
            # ls2 += (- pb[:, j] *
            #         torch.from_numpy(rewards).float().cuda() *
            #         torch.from_numpy(wgt2.astype(float)).float().cuda()).sum()
            ls2 += (- pb[:, j] *
                    torch.from_numpy(rewards).float().to(self.device) *
                    torch.from_numpy(wgt2.astype(float)).float().to(self.device)).sum()
            cnt2 += np.sum(wgt2)

        ls2 /= cnt2

        ####3#####add meaning_preservation as reward
        ls3 = 0
        cnt3 = 0
        stc_length_seq = sel.shape[1]
        batch = sel.shape[0]
        self.write_text(ori_words, ori_words_length, sel, stc_length_out)
        # os.system('/hdd2/zhanglw/anaconda3/envs/bertscore/bin/python seq2seq_rl/get_bert_score.py --prefix ' + global_variables.PREFIX)
        meaning_preservation = np.loadtxt('temp.txt')
        rewards = meaning_preservation  # affect more

        bleus_w = []
        for i in range(batch):
            bleu = get_bleu(ori_words[i], sel[i], self.vocab_size)

            bleus_w.append(bleu)
        bleus_w = np.asarray(bleus_w)
        # rewards = rewards + bleus_w
        rewards = bleus_w * 100  # 8.26

        for j in range(stc_length_seq):
            wgt3 = np.asarray([1 if j < min(stc_length_out[i]+1, stc_length_seq) else 0 for i in range(batch)])  # consider in STOP token
            ls3 += (- pb[:, j] *
                    torch.from_numpy(rewards).float().to(self.device) *
                    torch.from_numpy(wgt3.astype(float)).float().to(self.device)).sum()
            cnt3 += np.sum(wgt3)

        ls3 /= cnt3
        rewards_ave3 = np.average(rewards)


        loss = ls3

        return loss, ls1, ls3, rewards_ave1, rewards_ave3 #loss, ls, ls1, bleu, bleu1



class LossBiafRL(nn.Module):
    def __init__(self, device, word_alphabet, vocab_size, port):
        super(LossBiafRL, self).__init__()

        self.bl = 0
        self.bn = 0
        self.device = device
        self.word_alphabet = word_alphabet
        self.vocab_size = vocab_size
        self.port = port

    def get_reward_diff(self, out, dec_out, length_out, ori_words, ori_words_length):
        stc_dda = sum([0 if out[i] == dec_out[i] else 1 for i in range(1, length_out)])

        reward = stc_dda

        return reward

    def get_unk_rate(self, sent, length):
        return sent[:length].count(0) / float(length)

    def get_reward_same(self, out, dec_out, length_out, ori_words, ori_words_length):
        stc_dda = sum([1 if out[i] == dec_out[i] else 0 for i in range(1, length_out)])

        reward = stc_dda

        return reward

    def get_same_bc(self, out, dec_out, dec_out_1, length_out, ori_words, ori_words_length):
        stc_dda = sum([1 if out[i] == dec_out[i] == dec_out_1[i] else 0 for i in range(1, length_out)])

        reward = stc_dda

        return reward

    def get_diff_bc(self, dec_out, dec_out_1, out, length_out, ori_words, ori_words_length):
        stc_dda = sum([0 if out[i] == dec_out[i] == dec_out_1[i] else 1 for i in range(1, length_out)])

        reward = stc_dda

        return reward

    def get_bertscore_ppl(self, ori_words, ori_words_length, sel, stc_length_out):

        self.write_text(ori_words, ori_words_length, sel, stc_length_out)

        message = 'calculate'
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(('localhost', self.port))
        sock.sendall(message)

        rec_data = sock.recv(1024)

        sock.close()
        if rec_data == 'done':
            meaning_preservation = np.loadtxt(global_variables.PREFIX + 'temp.txt')
            logppl = np.loadtxt(global_variables.PREFIX + 'temp_ppl.txt')
            os.remove(global_variables.PREFIX + 'temp_ppl.txt')
            os.remove(global_variables.PREFIX + 'temp.txt')
            os.remove(global_variables.PREFIX + 'cands.txt')
            os.remove(global_variables.PREFIX + 'refs.txt')
            return meaning_preservation, logppl
        else:
            raise ValueError('server error!')


    def write_text(self, ori_words, ori_words_length, sel, stc_length_out):
        condsf = global_variables.PREFIX + 'cands.txt'
        refs = global_variables.PREFIX + 'refs.txt'
        oris = [[self.word_alphabet.get_instance(ori_words[si, wi]).encode('utf-8') for wi in range(1, ori_words_length[si])] for si in range(len(ori_words))]
        preds = [[self.word_alphabet.get_instance(sel[si, wi]).encode('utf-8') for wi in range(1, stc_length_out[si])] for si in range(len(sel))]

        wf = codecs.open(condsf, 'w', encoding='utf8')
        preds_tmp = [' '.join(i) for i in preds]
        for i in range(len(preds_tmp)):
            if len(preds_tmp[i]) == 0:
                preds_tmp[i] = 'Blank line .'
        preds_s = '\n'.join(preds_tmp)
        wf.write(preds_s)
        wf.close()

        wf = codecs.open(refs, 'w', encoding='utf8')
        oris_tmp = [' '.join(i) for i in oris]
        for i in range(len(oris_tmp)):
            if len(oris_tmp[i]) == 0:
                oris_tmp[i] = 'Blank line .'
        oris_s = '\n'.join(oris_tmp)
        wf.write(oris_s)
        wf.close()


    def forward(self, sel, pb, predicted_out, golden_out, mask_id, stc_length_out, sudo_golden_out, sudo_golden_out_1, ori_words, ori_words_length):

        list_stc_length_out = stc_length_out.cpu().numpy().tolist()

        ####1####
        batch = sel.shape[0]
        rewards_z1 = []
        for i in range(batch):  #batch
            reward = self.get_reward_diff(predicted_out[i], sudo_golden_out[i], list_stc_length_out[i], ori_words[i], ori_words_length[i])  
            rewards_z1.append(reward)
        rewards_z1 = np.asarray(rewards_z1)

        #####2####
        batch = sel.shape[0]
        rewards_z2 = []
        for i in range(batch):  #batch
            reward = self.get_reward_diff(predicted_out[i], sudo_golden_out_1[i], list_stc_length_out[i], ori_words[i], ori_words_length[i])  
            rewards_z2.append(reward)
        rewards_z2 = np.asarray(rewards_z2)

        #####3####
        batch = sel.shape[0]
        rewards_z3 = []
        for i in range(batch):  #batch
            reward = self.get_reward_same(sudo_golden_out[i], sudo_golden_out_1[i], list_stc_length_out[i], ori_words[i], ori_words_length[i])  
            rewards_z3.append(reward)
        rewards_z3 = np.asarray(rewards_z3)

        ####3#####add meaning_preservation as reward
        batch = sel.shape[0]

        meaning_preservation, logppl = self.get_bertscore_ppl(ori_words, ori_words_length, sel, stc_length_out)
        meaning_preservation = np.array(meaning_preservation)
        ppl = -np.exp(np.array(logppl))



        ###6### unk rate
        unk_rewards = []
        list_sel = sel.cpu().float().numpy().tolist()
        for i in range(batch):
            reward = self.get_unk_rate(list_sel[i], list_stc_length_out[i])
            unk_rewards.append(-1 * reward)
        unk_rewards = np.asarray(unk_rewards)

        rewards = (meaning_preservation * global_variables.MP_REWARD_WEIGHT +
                   ppl * global_variables.PPL_REWARD_WEIGHT +
                   rewards_z1 * global_variables.Z1_REWARD_WEIGHT +
                   rewards_z2 * global_variables.Z2_REWARD_WEIGHT +
                   rewards_z3 * global_variables.Z3_REWARD_WEIGHT +
                   unk_rewards * global_variables.UNK_REWARD_WEIGHT) * 0.001
        # rewards = bleus_w * 10  # 8.26

        ls3 = 0
        cnt3 = 0
        stc_length_seq = sel.shape[1]
        for j in range(stc_length_seq):
            wgt3 = np.asarray([1 if j < min(stc_length_out[i]+1, stc_length_seq) else 0 for i in range(batch)])  # consider in STOP token
            ls3 += (- pb[:, j] *
                    torch.from_numpy(rewards-self.bl).float().to(self.device) *  # rewards-self.bl
                    torch.from_numpy(wgt3.astype(float)).float().to(self.device)).sum()
            cnt3 += np.sum(wgt3)

        ls3 /= cnt3
        rewards_ave3 = np.average(rewards)
        self.bl = (self.bl * self.bn + rewards_ave3) / (self.bn + 1)
        self.bn += 1

        loss = ls3


        return loss, \
               np.average(rewards_z1) * global_variables.Z1_REWARD_WEIGHT, \
               np.average(rewards_z2) * global_variables.Z2_REWARD_WEIGHT, \
               np.average(rewards_z3) * global_variables.Z3_REWARD_WEIGHT, \
               np.average(meaning_preservation) * global_variables.MP_REWARD_WEIGHT, \
               np.average(ppl) * global_variables.PPL_REWARD_WEIGHT, \
               np.average(unk_rewards) * global_variables.UNK_REWARD_WEIGHT #loss, ls, ls1, bleu, bleu1


    def forward_verbose(self, sel, pb, predicted_out, golden_out, mask_id, stc_length_out, sudo_golden_out, sudo_golden_out_1, ori_words, ori_words_length):

        list_stc_length_out = stc_length_out.cpu().numpy().tolist()

        ####1####
        batch = sel.shape[0]
        rewards_z1 = []
        metrics1 = []
        metricsall1 = []
        for i in range(batch):  #batch
            reward = self.get_reward_diff(predicted_out[i], sudo_golden_out[i], list_stc_length_out[i], ori_words[i], ori_words_length[i])  
            rewards_z1.append(reward)
            metrics1.append(1.0-(reward*1.0/(list_stc_length_out[i]-1)))
            allsame = 1 if reward == 0 else 0
            metricsall1.append(allsame)
        rewards_z1 = np.asarray(rewards_z1)
        metrics1 = np.asarray(metrics1)
        metricsall1 = np.asarray(metricsall1)

        #####2####
        batch = sel.shape[0]
        rewards_z2 = []
        metrics2 = []
        metricsall2 = []
        for i in range(batch):  #batch
            reward = self.get_reward_diff(predicted_out[i], sudo_golden_out_1[i], list_stc_length_out[i], ori_words[i], ori_words_length[i])  
            rewards_z2.append(reward)
            metrics2.append(1.0-(reward*1.0/(list_stc_length_out[i]-1)))
            allsame = 1 if reward==0 else 0
            metricsall2.append(allsame)
        rewards_z2 = np.asarray(rewards_z2)
        metrics2 = np.asarray(metrics2)
        metricsall2 = np.asarray(metricsall2)

        #####3####
        batch = sel.shape[0]
        rewards_z3 = []
        metrics3 = []
        cnt_misc3 = []
        metricsall3 = []
        for i in range(batch):  #batch
            reward = self.get_reward_same(sudo_golden_out[i], sudo_golden_out_1[i], list_stc_length_out[i], ori_words[i], ori_words_length[i])  
            metric3 = self.get_same_bc(sudo_golden_out[i], sudo_golden_out_1[i], predicted_out[i], stc_length_out[i], ori_words[i],ori_words_length[i])  # we now only consider a simple case. the result of a third-party parser should be added here.

            stc_diff = self.get_diff_bc(sudo_golden_out[i], sudo_golden_out_1[i], predicted_out[i], list_stc_length_out[i], ori_words[i], ori_words_length[i])  # we now only consider a simple case. the result of a third-party parser should be added here.
            rewards_z3.append(reward)
            metrics3.append(metric3*1.0/(list_stc_length_out[i]-1))
            cnt_misc3.append(metric3*1.0)
            allsame = 1 if stc_diff==0 else 0
            metricsall3.append(allsame)
        rewards_z3 = np.asarray(rewards_z3)
        metrics3 = np.array(metrics3)
        cnt_misc3 = np.array(cnt_misc3)
        metricsall3 = np.asarray(metricsall3)

        ####3#####add meaning_preservation as reward
        batch = sel.shape[0]

        meaning_preservation, logppl = self.get_bertscore_ppl(ori_words, ori_words_length, sel, stc_length_out)
        meaning_preservation = np.array(meaning_preservation)
        ppl = -np.exp(np.array(logppl))
        metrics4 = meaning_preservation
        metrics5 = logppl



        unk_rewards = []
        list_sel = sel.cpu().float().numpy().tolist()
        for i in range(batch):
            reward = self.get_unk_rate(list_sel[i], list_stc_length_out[i])
            unk_rewards.append(-1 * reward)
        unk_rewards = np.asarray(unk_rewards)

        #-----------------------------------------------

        rewards = (meaning_preservation * global_variables.MP_REWARD_WEIGHT +
                   ppl * global_variables.PPL_REWARD_WEIGHT +
                   rewards_z1 * global_variables.Z1_REWARD_WEIGHT +
                   rewards_z2 * global_variables.Z2_REWARD_WEIGHT +
                   rewards_z3 * global_variables.Z3_REWARD_WEIGHT +
                   unk_rewards * global_variables.UNK_REWARD_WEIGHT) * 0.001
        # rewards = bleus_w * 10  # 8.26

        ls3 = 0
        cnt3 = 0
        stc_length_seq = sel.shape[1]
        for j in range(stc_length_seq):
            wgt3 = np.asarray([1 if j < min(stc_length_out[i]+1, stc_length_seq) else 0 for i in range(batch)])  # consider in STOP token
            ls3 += (- pb[:, j] *
                    torch.from_numpy(rewards-self.bl).float().to(self.device) *  # rewards-self.bl
                    torch.from_numpy(wgt3.astype(float)).float().to(self.device)).sum()
            cnt3 += np.sum(wgt3)

        ls3 /= cnt3
        rewards_ave3 = np.average(rewards)
        self.bl = (self.bl * self.bn + rewards_ave3) / (self.bn + 1)
        self.bn += 1


        loss = ls3


        res = {}
        res['loss'] = loss
        res['avg_z1'] = np.average(rewards_z1)
        res['avg_z2'] = np.average(rewards_z2)
        res['avg_z3'] = np.average(rewards_z3)
        res['avg_mp'] = np.average(meaning_preservation)
        res['avg_ppl'] = np.average(ppl)
        res['abg_unk'] = np.average(unk_rewards)
        res['sum_me1'] = np.sum(metrics1)
        res['sum_me2'] = np.sum(metrics2)
        res['sum_me3'] = np.sum(metrics3)
        res['sum_me4'] = np.sum(metrics4)
        res['sum_me5'] = np.sum(metrics5)
        res['cnt_me1'] = np.sum(rewards_z1)
        res['cnt_me2'] = np.sum(rewards_z2)
        res['cnt_me3'] = np.sum(cnt_misc3)

        res['sum_me1all'] = np.sum(metricsall1)
        res['sum_me2all'] = np.sum(metricsall2)
        res['sum_me3all'] = np.sum(metricsall3)


        return res


class TagLossBiafRL(nn.Module): # parsers
    def __init__(self, device, word_alphabet, vocab_size, port):
        super(TagLossBiafRL, self).__init__()

        self.bl = 0
        self.bn = 0
        self.device = device
        self.word_alphabet = word_alphabet
        self.vocab_size = vocab_size
        self.port = port

    def get_reward_diff(self, out, dec_out, length_out, ori_words, ori_words_length):
        stc_dda = sum([0 if out[i] == dec_out[i] else 1 for i in range(0, length_out)])

        reward = stc_dda

        return reward

    def get_reward_same(self, out, dec_out, length_out, ori_words, ori_words_length):
        stc_dda = sum([1 if out[i] == dec_out[i] else 0 for i in range(0, length_out)])

        reward = stc_dda

        return reward

    def get_same_bc(self, out, dec_out, dec_out_1, length_out, ori_words, ori_words_length):
        stc_dda = sum([1 if out[i] == dec_out[i] == dec_out_1[i] else 0 for i in range(0, length_out)])

        reward = stc_dda

        return reward

    def get_diff_bc(self, dec_out, dec_out_1, out, length_out, ori_words, ori_words_length):
        stc_dda = sum([0 if out[i] == dec_out[i] == dec_out_1[i] else 1 for i in range(0, length_out)])

        reward = stc_dda

        return reward

    def get_unk_rate(self, sent, length):
        return float(sent[:length].count(0) / float(length))

    def get_bertscore_ppl(self, ori_words, ori_words_length, sel, stc_length_out):

        self.write_text(ori_words, ori_words_length, sel, stc_length_out)

        message = 'calculate'
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(('localhost', self.port))
        sock.sendall(message)

        rec_data = sock.recv(1024)

        sock.close()
        if rec_data == 'done':
            meaning_preservation = np.loadtxt(global_variables.PREFIX + 'temp.txt')
            logppl = np.loadtxt(global_variables.PREFIX + 'temp_ppl.txt')
            os.remove(global_variables.PREFIX + 'temp_ppl.txt')
            os.remove(global_variables.PREFIX + 'temp.txt')
            os.remove(global_variables.PREFIX + 'cands.txt')
            os.remove(global_variables.PREFIX + 'refs.txt')
            return meaning_preservation, logppl
        else:
            raise ValueError('server error!')

    def write_text(self, ori_words, ori_words_length, sel, stc_length_out):
        condsf = global_variables.PREFIX + 'cands.txt'
        refs = global_variables.PREFIX + 'refs.txt'
        oris = [[self.word_alphabet.get_instance(ori_words[si, wi]).encode('utf-8') for wi in range(1, ori_words_length[si])] for si in range(len(ori_words))]
        preds = [[self.word_alphabet.get_instance(sel[si, wi]).encode('utf-8') for wi in range(1, stc_length_out[si])] for si in range(len(sel))]

        wf = codecs.open(condsf, 'w', encoding='utf8')
        preds_tmp = [' '.join(i) for i in preds]
        for i in range(len(preds_tmp)):
            if len(preds_tmp[i]) == 0:
                preds_tmp[i] = 'Blank line .'
        preds_s = '\n'.join(preds_tmp)
        wf.write(preds_s)
        wf.close()

        wf = codecs.open(refs, 'w', encoding='utf8')
        oris_tmp = [' '.join(i) for i in oris]
        for i in range(len(oris_tmp)):
            if len(oris_tmp[i]) == 0:
                oris_tmp[i] = 'Blank line .'
        oris_s = '\n'.join(oris_tmp)
        wf.write(oris_s)
        wf.close()


    def forward(self, sel, pb, predicted_out, golden_out, mask_id, stc_length_out, sudo_golden_out, sudo_golden_out_1, ori_words, ori_words_length):

        list_stc_length_out = stc_length_out.cpu().numpy().tolist()

        ####1####
        batch = sel.shape[0]
        rewards_z1 = []
        for i in range(batch):  #batch
            reward = self.get_reward_diff(predicted_out[i], sudo_golden_out[i], list_stc_length_out[i], ori_words[i], ori_words_length[i])
            rewards_z1.append(reward)
        rewards_z1 = np.asarray(rewards_z1)

        #####2####
        batch = sel.shape[0]
        rewards_z2 = []
        for i in range(batch):  #batch
            reward = self.get_reward_diff(predicted_out[i], sudo_golden_out_1[i], list_stc_length_out[i], ori_words[i], ori_words_length[i])
            rewards_z2.append(reward)
        rewards_z2 = np.asarray(rewards_z2)

        #####3####
        batch = sel.shape[0]
        rewards_z3 = []
        for i in range(batch):  #batch
            reward = self.get_reward_same(sudo_golden_out[i], sudo_golden_out_1[i], list_stc_length_out[i], ori_words[i], ori_words_length[i])  
            rewards_z3.append(reward)
        rewards_z3 = np.asarray(rewards_z3) *0.01

        ####3#####add meaning_preservation as reward
        batch = sel.shape[0]


        meaning_preservation, logppl = self.get_bertscore_ppl(ori_words, ori_words_length, sel, stc_length_out)
        meaning_preservation = np.array(meaning_preservation)
        ppl = -np.exp(np.array(logppl))


        ###6### unk rate
        unk_rewards = []
        list_sel = sel.cpu().float().numpy().tolist()
        for i in range(batch):
            reward = self.get_unk_rate(list_sel[i], list_stc_length_out[i])
            unk_rewards.append(-1 * reward)
        unk_rewards = np.asarray(unk_rewards)

        #-----------------------------------------------

        rewards = (meaning_preservation * global_variables.MP_REWARD_WEIGHT +
                   ppl * global_variables.PPL_REWARD_WEIGHT +
                   rewards_z1 * global_variables.Z1_REWARD_WEIGHT +
                   rewards_z2 * global_variables.Z2_REWARD_WEIGHT +
                   rewards_z3 * global_variables.Z3_REWARD_WEIGHT +
                   unk_rewards * global_variables.UNK_REWARD_WEIGHT) * 0.001
        # rewards = bleus_w * 10  # 8.26

        ls3 = 0
        cnt3 = 0
        stc_length_seq = sel.shape[1]
        for j in range(stc_length_seq):
            wgt3 = np.asarray([1 if j < min(stc_length_out[i]+1, stc_length_seq) else 0 for i in range(batch)])  # consider in STOP token
            ls3 += (- pb[:, j] *
                    torch.from_numpy(rewards-self.bl).float().to(self.device) *  # rewards-self.bl
                    torch.from_numpy(wgt3.astype(float)).float().to(self.device)).sum()
            cnt3 += np.sum(wgt3)

        ls3 /= cnt3
        rewards_ave3 = np.average(rewards)
        self.bl = (self.bl * self.bn + rewards_ave3) / (self.bn + 1)
        self.bn += 1


        loss = ls3

        return loss, \
               np.average(rewards_z1) * global_variables.Z1_REWARD_WEIGHT, \
               np.average(rewards_z2) * global_variables.Z2_REWARD_WEIGHT, \
               np.average(rewards_z3) * global_variables.Z3_REWARD_WEIGHT, \
               np.average(meaning_preservation) * global_variables.MP_REWARD_WEIGHT, \
               np.average(ppl) * global_variables.PPL_REWARD_WEIGHT, \
               np.average(unk_rewards) * global_variables.UNK_REWARD_WEIGHT #loss, ls, ls1, bleu, bleu1

    def forward_verbose(self, sel, pb, predicted_out, golden_out, mask_id, stc_length_out, sudo_golden_out, sudo_golden_out_1, ori_words, ori_words_length):

        list_stc_length_out = stc_length_out.cpu().numpy().tolist()

        ####1####tagging
        batch = sel.shape[0]
        rewards_z1 = []
        metrics1 = []
        metricsall1 = []
        for i in range(batch):  # batch
            reward = self.get_reward_diff(predicted_out[i], sudo_golden_out[i], list_stc_length_out[i], ori_words[i], ori_words_length[i])  # we now only consider a simple case. the result of a third-party parser should be added here.
            rewards_z1.append(reward)
            metrics1.append(1.0-(reward*1.0/(stc_length_out[i].cpu().numpy())))
            allsame = 1 if reward==0 else 0
            metricsall1.append(allsame)
        rewards_z1 = np.asarray(rewards_z1)
        metrics1 = np.asarray(metrics1)
        metricsall1 = np.asarray(metricsall1)


        #####2####
        batch = sel.shape[0]
        rewards_z2 = []
        metrics2 = []
        metricsall2 = []
        for i in range(batch):  # batch
            reward = self.get_reward_diff(predicted_out[i], sudo_golden_out_1[i], list_stc_length_out[i], ori_words[i], ori_words_length[i])  # we now only consider a simple case. the result of a third-party parser should be added here.
            rewards_z2.append(reward)
            metrics2.append(1.0-(reward*1.0/(list_stc_length_out[i] * 1.0)))
            allsame = 1 if reward==0 else 0
            metricsall2.append(allsame)
        rewards_z2 = np.asarray(rewards_z2)
        metrics2 = np.asarray(metrics2)
        metricsall2 = np.asarray(metricsall2)

        #####3####
        batch = sel.shape[0]
        rewards_z3 = []
        metrics3 = []
        cnt_misc3 = []
        metricsall3 = []
        for i in range(batch):  # batch
            reward = self.get_reward_same(sudo_golden_out[i], sudo_golden_out_1[i], list_stc_length_out[i], ori_words[i], ori_words_length[i])  # we now only consider a simple case. the result of a third-party parser should be added here.
            metric3 = self.get_same_bc(sudo_golden_out[i], sudo_golden_out_1[i], predicted_out[i], list_stc_length_out[i], ori_words[i], ori_words_length[i])  # we now only consider a simple case. the result of a third-party parser should be added here.
            stc_diff = self.get_diff_bc(sudo_golden_out[i], sudo_golden_out_1[i], predicted_out[i], list_stc_length_out[i], ori_words[i],ori_words_length[i])  # we now only consider a simple case. the result of a third-party parser should be added here.


            rewards_z3.append(reward)
            metrics3.append(metric3*1.0/(list_stc_length_out[i] * 1.0))
            cnt_misc3.append(metric3*1.0)
            allsame = 1 if stc_diff==0 else 0
            metricsall3.append(allsame)
        rewards_z3 = np.asarray(rewards_z3)
        metrics3 = np.array(metrics3)
        cnt_misc3 = np.array(cnt_misc3)
        metricsall3 = np.asarray(metricsall3)

        ####3#####add meaning_preservation as reward
        batch = sel.shape[0]


        meaning_preservation, logppl = self.get_bertscore_ppl(ori_words, ori_words_length, sel, stc_length_out)
        meaning_preservation = np.array(meaning_preservation)
        ppl = -np.exp(np.array(logppl))
        metrics4 = meaning_preservation
        metrics5 = logppl


        ###6### unk rate ######
        unk_rewards = []
        list_sel = sel.cpu().float().numpy().tolist()
        for i in range(batch):
            reward = self.get_unk_rate(list_sel[i], list_stc_length_out[i])
            unk_rewards.append(-1 * reward)
        unk_rewards = np.asarray(unk_rewards)

        # -----------------------------------------------

        rewards = (meaning_preservation * global_variables.MP_REWARD_WEIGHT +
                   ppl * global_variables.PPL_REWARD_WEIGHT +
                   rewards_z1 * global_variables.Z1_REWARD_WEIGHT +
                   rewards_z2 * global_variables.Z2_REWARD_WEIGHT +
                   rewards_z3 * global_variables.Z3_REWARD_WEIGHT +
                   unk_rewards * global_variables.UNK_REWARD_WEIGHT) * 0.001
        # rewards = bleus_w * 10  # 8.26

        ls3 = 0
        cnt3 = 0
        stc_length_seq = sel.shape[1]
        for j in range(stc_length_seq):
            wgt3 = np.asarray([1 if j < min(stc_length_out[i] + 1, stc_length_seq) else 0 for i in
                               range(batch)])  # consider in STOP token
            ls3 += (- pb[:, j] *
                    torch.from_numpy(rewards - self.bl).float().to(self.device) *  # rewards-self.bl
                    torch.from_numpy(wgt3.astype(float)).float().to(self.device)).sum()
            cnt3 += np.sum(wgt3)

        ls3 /= cnt3
        rewards_ave3 = np.average(rewards)
        self.bl = (self.bl * self.bn + rewards_ave3) / (self.bn + 1)
        self.bn += 1

        loss = ls3

        res = {}
        res['loss'] = loss
        res['avg_z1'] = np.average(rewards_z1)
        res['avg_z2'] = np.average(rewards_z2)
        res['avg_z3'] = np.average(rewards_z3)
        res['avg_mp'] = np.average(meaning_preservation)
        res['avg_ppl'] = np.average(ppl)
        res['abg_unk'] = np.average(unk_rewards)
        res['sum_me1'] = np.sum(metrics1)
        res['sum_me2'] = np.sum(metrics2)
        res['sum_me3'] = np.sum(metrics3)
        res['sum_me4'] = np.sum(metrics4)
        res['sum_me5'] = np.sum(metrics5)
        res['cnt_me1'] = np.sum(rewards_z1)
        res['cnt_me2'] = np.sum(rewards_z2)
        res['cnt_me3'] = np.sum(cnt_misc3)

        res['sum_me1all'] = np.sum(metricsall1)
        res['sum_me2all'] = np.sum(metricsall2)
        res['sum_me3all'] = np.sum(metricsall3)

        return res