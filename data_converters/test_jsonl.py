import sys
import json

fname = sys.argv[1]

print(fname)

with open(fname, 'r') as f:
    for line_num, line in enumerate(f):
        d = json.loads(line)
        # orig_sentences = d['token_sentences']
        tokenized_sentences = d['sentences']
        subtoken_map = d['subtoken_map']
        clusters = d['clusters']

        flattened_tokenized_sentences = [tok for s in tokenized_sentences for tok in s]
        # flattened_orig_sentences = [tok for s in orig_sentences for tok in s]
        # for tokenized_sentence, orig_sentence in zip(tokenized_sentences, orig_sentences):
        # remapped = [[] for _ in flattened_orig_sentences]
        remapped = []
        for i, j in enumerate(subtoken_map):
            if i >= len(remapped):
                remapped.append([])
            remapped[j].append(flattened_tokenized_sentences[i])
        print(remapped)

        for ci, cluster in enumerate(clusters):
            spans = [flattened_tokenized_sentences[s:e + 1] for s, e in cluster]
            print(i, ci, spans)

        if line_num > 2:
            break

