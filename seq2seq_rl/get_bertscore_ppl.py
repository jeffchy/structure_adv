from bert_score import score
import numpy as np
import argparse

args_parser = argparse.ArgumentParser(description='Get bertscore and ppl score')
args_parser.add_argument('--prefix', type=str, required=True, help='prefix for save temp')
args = args_parser.parse_args()

LANGUAGE_CODE = 'zh'

#TODO(lwzhang) temporarily used hard code to sepcecify saved score file. Same with rl.py
# SCORE_PREFIX = '/hdd2/zhanglw/code/structure_adv/batch10_'
SCORE_PREFIX = args.prefix

# ===============bertscore===============================

with open(SCORE_PREFIX + "cands.txt", encoding='utf8') as f:  # cands.txt
    cands = [line.strip() for line in f]
with open(SCORE_PREFIX + "refs.txt") as f:
    refs = [line.strip() for line in f]

# print(cands)
# print(refs)
# P,R,F = score(cands, refs, bert="bert-base-uncased")
P, R, F = score(cands, refs, lang=LANGUAGE_CODE, verbose=False)
# TODO(lwzhang) current score only support enlish
# P,R,F = score(cands, refs, model_type='bert-base-uncased', verbose=False)
np.savetxt(SCORE_PREFIX + 'temp.txt', F.cpu().numpy())

import torch

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
if LANGUAGE_CODE is 'en':
    # =============== en ppl ===============================
    from pytorch_pretrained_bert import GPT2LMHeadModel, GPT2Tokenizer

    model_name_or_path = './pretrained_model_gpt2'
    enc = GPT2Tokenizer.from_pretrained(model_name_or_path)
    model = GPT2LMHeadModel.from_pretrained(model_name_or_path)
    model.to(device)
    model.eval()
    ppls = []
    with torch.no_grad():
        for step, s in enumerate(cands):  # actually here is a batch with batchsize=1
            # Put model in training mode.
            if not s:
                ppls.append(0)
                print('space sentence')
                continue
            s = enc.encode(s)  # + [50256]  #50256 is the token_id for <|endoftext|>
            batch = torch.tensor([s]).to(device)
            # print(batch)
            loss = model(batch, lm_labels=batch)  # everage -logp
            # print(loss.cpu().numpy())
            ppls.append(loss.cpu().numpy())  # the small, the better
            # ppls.append(math.exp(loss.cpu().numpy()))  # the small, the better
        # print(ppls)
        np.savetxt(SCORE_PREFIX + 'temp_ppl.txt', np.array(ppls))
elif LANGUAGE_CODE is 'zh':
    # =============== zh ppl ===============================
    # here is a GPT based ppl calculator for Chinese.
    # detail can see: https://github.com/qywu/Chinese-GPT
    from pytorch_pretrained_bert import BertTokenizer
    from chinese_gpt import TransformerDecoderLM as Decoder
    import torch.nn.functional as F

    tokenizer = BertTokenizer.from_pretrained("bert-base-chinese")
    batch_size = 1
    decoder = Decoder()
    decoder = decoder.to(device)
    decoder.eval()

    # load pretrained weights
    # model can be found here: https://drive.google.com/file/d/1W6n7Kv6kvHthUX18DhdGSzBYkyzDvxYh/view?usp=sharing
    old_state_dict = torch.load("./pretrained_model_gpt/model_state_epoch_62.th", map_location=lambda storage, loc: storage)
    new_state_dict = decoder.state_dict()
    for item in new_state_dict.keys():
        new_state_dict[item] = old_state_dict['module.' + item]
    decoder.load_state_dict(new_state_dict)

    get_log_ppl = torch.nn.CrossEntropyLoss()
    ppls = []
    with torch.no_grad():
        for step, s in enumerate(cands):  # actually here is a batch with batchsize=1
            # Put model in training mode.
            if not s:
                ppls.append(0)
                print('space sentence')
                continue
            s_ids = tokenizer.convert_tokens_to_ids(tokenizer.tokenize(s))
            s_tensor = torch.LongTensor([[101] + s_ids] * batch_size).to(device)
            mask = torch.ones(batch_size, s_tensor.shape[1]).to(device)
            logits, _ = decoder(s_tensor, mask, past=None, past_length=0)
            log_ppl = get_log_ppl(logits.squeeze(0), s_tensor.squeeze(0))
            ppls.append(log_ppl.cpu().numpy())
        np.savetxt(SCORE_PREFIX + 'temp_ppl.txt', np.array(ppls))
else:
    print("Error Language Code!")
