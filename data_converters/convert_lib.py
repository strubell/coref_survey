import tqdm
import json

import collections
import csv
import json
import os

from bert import tokenization
VOCAB_FILE = "/home/nnayak/spanbert-coref-fork/cased_config_vocab/vocab.txt"
MAX_SEGMENT_LEN = 384
TOKENIZER = tokenization.FullTokenizer(vocab_file=VOCAB_FILE, do_lower_case=False)

class DatasetName(object):
  conll12 = 'conll12' # TODO delete one of these later
  gap = 'gap'
  knowref = 'knowref'
  preco = 'preco'
  red = 'red'
  wikicoref = 'wikicoref'
  ALL_DATASETS = [conll12, gap, knowref, preco, red, wikicoref]

class DatasetSplit(object):
  train = 'train'
  test = 'test'
  dev = 'dev'
  valid = 'valid'

class FormatName(object):
  jsonl = 'jsonl'
  file_per_doc = 'file_per_doc'
  txt = 'txt'
  ALL_FORMATS = [jsonl, file_per_doc, txt]

def get_filename(data_home, dataset_name, dataset_split, format_name):
  return os.path.join(data_home, 'processed', dataset_name,
      dataset_split + "." + format_name)

def create_processed_data_dir(path):
  try:
      os.makedirs(path)
  except OSError:
      print ("Creation of the directory %s failed" % path)
  else:
      print ("Successfully created the directory %s " % path)

NO_SPEAKER = "-"

def make_doc_id(dataset, doc_name):
  if type(doc_name) == list:
    doc_name = "_".join(doc_name)
  return "_".join([dataset, doc_name])


def make_empty_speakers(sentences):
  return [[NO_SPEAKER for token in sent] for sent in sentences]

CLS = "[CLS]"
SPL = "[SPL]"
SEP = "[SEP]"


class Dataset(object):
  def __init__(self, dataset_name):
    self.name = dataset_name
    self.documents = []
    self.bert_tokenized = False

  def _bert_tokenize(self):
    for doc in tqdm.tqdm(self.documents):
      doc._bert_tokenize()
    self.bert_tokenized = True

  def _dump_lines(self, function, file_handle):
    lines = []
    for doc in self.documents:
      lines += doc.apply_dump_fn(function)
    file_handle.write("\n".join(lines))

  def dump_to_mconll(self, file_handle):
    self._dump_lines("mconll", file_handle)

  def dump_to_jsonl(self, max_segment_len, file_handle):
    if not self.bert_tokenized:
      self._bert_tokenize()
    self._dump_lines(str(max_segment_len) + ".jsonl", file_handle)

  def dump_to_stanford(self, directory):
    create_processed_data_dir(directory)
    for doc in tqdm.tqdm(self.documents):
      with open(directory + "/" + doc.doc_id + "_" + doc.doc_part + ".txt", 'w') as f:
        f.write("\n".join(doc.dump_to_stanford()))

  def remove_singletons(self):
    for doc in self.documents:
      doc.remove_singletons()

def new_segment():
  return [], [], [], []

def flatten(l):
  return sum(l, [])

class TokenizedSentences(object):
  def __init__(self, token_sentences, max_segment_len):
    self.token_sentences = token_sentences
    self.max_segment_len = max_segment_len
    (self.segments, self.sentence_map, self.subtoken_map, self.speakers) = self._segment_sentences()

  def _segment_sentences(self):
    sentences, sentence_map, subtoken_map, speakers = ([], [], [], [])
    (segment_subtokens, segment_sentence_map, segment_subtoken_map,
     segment_speakers) = new_segment()
    running_token_idx = 0
    for i, sentence in enumerate(self.token_sentences):
      subword_list = [TOKENIZER.tokenize(token) for token in sentence]
      subword_to_word = flatten([[local_token_idx + running_token_idx]* len(token_subwords)
                            for local_token_idx, token_subwords in enumerate(subword_list)])

      sentence_subtokens = flatten(subword_list)
      sentence_sentence_map = [i] * len(sentence_subtokens)
      sentence_subtoken_map = subword_to_word
      sentence_speakers = [""] * len(sentence_subtokens)

      if len(flatten(subword_list)) + len(segment_subtokens) + 2 < self.max_segment_len:
        # Add to current segment
        segment_subtokens += flatten(subword_list)
        segment_sentence_map += sentence_sentence_map
        segment_subtoken_map += sentence_subtoken_map
        segment_speakers += sentence_speakers
      else:
        sentences.append([CLS] + segment_subtokens + [SEP])
        sentence_map += segment_sentence_map 
        subtoken_map += [0] + segment_subtoken_map + [segment_subtoken_map[-1]]
        speakers += [SPL] + segment_speakers + [SPL]
        (segment_subtokens, segment_sentence_map, segment_subtoken_map,
         segment_speakers) = (sentence_subtokens, sentence_sentence_map,
         sentence_subtoken_map, sentence_speakers)

      running_token_idx += len(subword_list)

    return sentences, sentence_map, subtoken_map, speakers



class Document(object):
  def __init__(self, doc_id, doc_part):
    self.doc_id = doc_id
    self.doc_part = doc_part
    self.doc_key = "UNK"
    self.sentences = []
    self.speakers = []
    self.clusters = []

    self.bert_tokenized = False
    self.tokenized_sentences = {}

    self.FN_MAP = {
      "mconll": self.dump_to_mconll,
      "512.jsonl": lambda: self.dump_to_jsonl(512),
      "384.jsonl": lambda: self.dump_to_jsonl(384),
      "file_per_doc": self.dump_to_stanford}

  def _bert_tokenize(self):
    self.token_sentences = self.sentences
    for max_segment_len in [384, 512]:
      self.tokenized_sentences[max_segment_len] = TokenizedSentences(
        self.token_sentences, max_segment_len)
    self.bert_tokenized = True

  def apply_dump_fn(self, function):
    return self.FN_MAP[function]()

  def _get_conll_coref_labels(self):
    coref_labels = collections.defaultdict(list)
    for cluster, tok_idxs in enumerate(self.clusters):
      for tok_start, tok_end in tok_idxs:
        if tok_start == tok_end:
          coref_labels[tok_start].append("({})".format(cluster))
        else:
          coref_labels[tok_start].append("({}".format(cluster))
          coref_labels[tok_end].append("{})".format(cluster))

    return coref_labels

  def remove_singletons(self):
    new_clusters = []
    for cluster in self.clusters:
      if len(cluster) > 1:
        new_clusters.append(cluster)
    self.clusters = new_clusters

  def dump_to_jsonl(self, max_segment_len):
    assert self.bert_tokenized
    return [json.dumps({
          "doc_key": self.doc_id + "_" + self.doc_part,
          "document_id": self.doc_id + "_" + self.doc_part,
          "token_sentences": self.token_sentences,
          "sentences": self.tokenized_sentences[max_segment_len].segments,
          "sentence_map": self.tokenized_sentences[max_segment_len].sentence_map,
          "subtoken_map": self.tokenized_sentences[max_segment_len].subtoken_map,
          "speakers": self.tokenized_sentences[max_segment_len].speakers,
          "clusters": self.clusters
        })]

  def dump_to_stanford(self):
    return [" ".join(sentence) for sentence in self.sentences]

     
  def dump_to_mconll(self):
    document_name = self.doc_id
    coref_labels = self._get_conll_coref_labels()
    sent_start_tok_count = 0

    mconll_lines = ["#begin document " + document_name + "\n"] 

    for i_sent, sentence in enumerate(self.sentences):
      for i_tok, token in enumerate(sentence):
        coref_label_vals = coref_labels.get(sent_start_tok_count + i_tok)
        if not coref_label_vals:
          label = '-'  
        else:
          label = "|".join(coref_label_vals)
        mconll_lines.append("\t".join([
          self.doc_id, self.doc_part, str(i_tok), token, self.speakers[i_sent][i_tok], label]))
      sent_start_tok_count += len(sentence)
      mconll_lines.append("")

    mconll_lines.append("\n#end document " + document_name + "\n")

    return mconll_lines


def write_converted(dataset, prefix):
    print(prefix)
    with open(prefix + ".mconll", 'w') as f:
      dataset.dump_to_mconll(f)
    for max_segment_len in [384, 512]:
      with open(prefix + "." + str(max_segment_len) + ".jsonl", 'w') as f:
        dataset.dump_to_jsonl(max_segment_len, f)
    dataset.dump_to_stanford(prefix + "-fpd/")
 