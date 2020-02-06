import sys
import json

fname = sys.argv[1]
mconll_fname = sys.argv[2]

threshold = 8000

output_fname = "{}.filtered".format(fname)
mconll_output_fname = "{}.filtered".format(mconll_fname)

# load jsonlines
with open(fname, 'r') as f:
    docs = [json.loads(line) for line in f]

print("Loaded {} json docs".format(len(docs)))

doc_lens = [len([item for sublist in x['token_sentences'] for item in sublist]) for x in docs]
print("Document lengths: {}".format(doc_lens))

filtered_docs = [d for d, l in zip(docs, doc_lens) if l < threshold]
# filtered_mconll = [d for d, l in zip(mconll_docs, doc_lens) if l < threshold]
print("Filtered {} docs with length > {}".format(len(docs) - len(filtered_docs), threshold))

filtered_indices = [i for i, l in enumerate(doc_lens) if l < threshold]

# load mconll
with open(mconll_fname, 'r') as f:
    mconll_lines = []
    doc_idx = -1
    for line in f:
        if line.startswith("#begin"):
            doc_idx += 1
        if doc_idx in filtered_indices:
            mconll_lines.append(line[:-1])

with open(output_fname, 'w') as output_file:
    for doc in filtered_docs:
        json.dump(doc, output_file)
        print("", file=output_file)

with open(mconll_output_fname, 'w') as output_file:
    for line in mconll_lines:
        print(line, file=output_file)

print("Wrote {} docs to {}".format(len(filtered_docs), output_fname))
