import tqdm
import json

import collections
import csv
import json
import os
import numpy as np

from bert import tokenization
VOCAB_FILE = "/home/strubell/research/coref/cased_config_vocab/vocab.txt"
TOKENIZER = tokenization.FullTokenizer(vocab_file=VOCAB_FILE, do_lower_case=False)

class DatasetName(object):
  conll12 = 'conll12' 
  gap = 'gap'
  preco = 'preco'
  wikicoref = 'wikicoref'
  ALL_DATASETS = [conll12, gap, preco, wikicoref]

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

def make_doc_id(dataset, doc_name):
  if dataset in [DatasetName.gap, DatasetName.wikicoref]:
    return dataset + '-' +  doc_name
    
  if type(doc_name) == list:
    doc_name = "_".join(doc_name)
  return "_".join([dataset, doc_name])

NO_SPEAKER = ""

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

  def dump_to_feat(self, file_handle):
    self._dump_lines("feat", file_handle)

  def dump_to_jsonl(self, max_segment_len, file_handle):
    # if not self.bert_tokenized:
    #   self._bert_tokenize()
    self._bert_tokenize()
    self._dump_lines(str(max_segment_len) + ".jsonl", file_handle)

  def dump_to_fpd(self, directory):
    create_processed_data_dir(directory)
    for doc in tqdm.tqdm(self.documents):
      with open(directory + "/" + doc.doc_id + "_" + doc.doc_part + ".txt", 'w') as f:
        f.write("\n".join(doc.dump_to_fpd()))

  def remove_singletons(self):
    for doc in self.documents:
      doc.remove_singletons()

def flatten(l):
  return sum(l, [])

class TokenizedSentences(object):
  def __init__(self, token_sentences, max_segment_len, speakers, clusters):
    self.token_sentences = token_sentences
    self.max_segment_len = max_segment_len

    self.per_sentence_speaker = []
    for sentence_speakers in speakers:
      assert len(set(sentence_speakers)) == 1
      self.per_sentence_speaker.append(sentence_speakers[0])

    (self.segments, self.sentence_map, self.subtoken_map, self.speakers) = self._segment_sentences()
    self.clusters = self.bertify_clusters(clusters, self.subtoken_map)
    # self.clusters = self.convert_clusters_bert(clusters, self.subtoken_map)

  
  def _segment_sentences(self):
    sentences, sentence_map, subtoken_map, speakers = ([], [], [], [])
    (segment_subtokens, segment_sentence_map, segment_subtoken_map,
     segment_speakers) = ([], [], [], [])
    running_token_idx = 0
    previous_token = 0
    for i, sentence in enumerate(self.token_sentences):
      subword_list = [TOKENIZER.tokenize(token) for token in sentence]
      subword_to_word = flatten([[local_token_idx + running_token_idx] * len(token_subwords)
                            for local_token_idx, token_subwords in enumerate(subword_list)])
      running_token_idx += len(subword_list)

      sentence_subtokens = flatten(subword_list)
      sentence_sentence_map = [i] * len(sentence_subtokens)
      sentence_subtoken_map = subword_to_word
      sentence_speakers = [self.per_sentence_speaker[i]] * len(sentence_subtokens)

      if len(sentence_subtokens) + len(segment_subtokens) + 2 < self.max_segment_len:
        segment_subtokens += sentence_subtokens
        segment_sentence_map += sentence_sentence_map
        segment_subtoken_map += sentence_subtoken_map
        segment_speakers += sentence_speakers
      else:
        if not segment_subtoken_map:
          # if segment_subtoken_map is empty here, that means that the sentence was longer
          # than max_segment_len, so we need to cut this segment mid-sentence
          segment_subtokens += sentence_subtokens[:self.max_segment_len]
          segment_sentence_map += sentence_sentence_map[:self.max_segment_len]
          segment_subtoken_map += sentence_subtoken_map[:self.max_segment_len]
          segment_speakers += sentence_speakers[:self.max_segment_len]
          sentence_subtokens = sentence_subtokens[self.max_segment_len:]
          sentence_sentence_map = sentence_sentence_map[self.max_segment_len:]
          sentence_subtoken_map = sentence_subtoken_map[self.max_segment_len:]
          sentence_speakers = sentence_speakers[self.max_segment_len:]

        sentences.append([CLS] + segment_subtokens + [SEP])
        sentence_map += segment_sentence_map 
        subtoken_map += [previous_token] + segment_subtoken_map + [segment_subtoken_map[-1]]
        speakers.append([SPL] + segment_speakers + [SPL])
        previous_token = segment_subtoken_map[-1]

        (segment_subtokens, segment_sentence_map, segment_subtoken_map,
         segment_speakers) = (sentence_subtokens, sentence_sentence_map,
         sentence_subtoken_map, sentence_speakers)


    sentences.append([CLS] + segment_subtokens + [SEP])
    sentence_map += segment_sentence_map 
    subtoken_map += [previous_token] + segment_subtoken_map + [segment_subtoken_map[-1]]
    speakers.append([SPL] + segment_speakers + [SPL])

    return (sentences, sentence_map, subtoken_map, speakers)

  def bertify_clusters(self, clusters, subtoken_map):
    reverse_token_map = {}
    current_start = 0
    current_end = None
    for subtoken_idx, token_idx in enumerate(subtoken_map[:-1]):
      maybe_next_token_idx = subtoken_map[subtoken_idx + 1]
      if token_idx != maybe_next_token_idx:
        reverse_token_map[token_idx] = (current_start, subtoken_idx)
        current_start = subtoken_idx + 1
    reverse_token_map[subtoken_map[-1]] = (current_start, len(subtoken_map) - 1)
    bertified_clusters = []
    for cluster in clusters:
      new_cluster = []
      for start, end in cluster:
        new_cluster.append(
          (reverse_token_map[start][0], reverse_token_map[end][1]))
      bertified_clusters.append(new_cluster)
    return bertified_clusters

  def convert_clusters_bert(self, clusters, subtoken_map):
    # update clusters to index into tokenized
    # an offset for each original token; at least 1 will be added to it
    # print("clusters", clusters)
    offsets = [-1] * sum(map(len, self.token_sentences))
    for s in subtoken_map:
      offsets[s] += 1
    offsets_cumulative = np.cumsum(offsets).tolist()

    new_clusters = []
    for c in clusters:
      new_c = []
      for m in c:
        new_m = [m[0] + offsets_cumulative[m[0]], m[1] + offsets_cumulative[m[1]]]
        if offsets[m[0]] > 0:
          new_m[0] -= offsets[m[0]]
        new_c.append(new_m)
      new_clusters.append(new_c)
    # print("new clusters", new_clusters)
    return new_clusters
        

class LabelSequences(object):
  WORD = "WORD"
  POS = "POS"
  NER = "NER"
  PARSE = "PARSE"
  COREF = "COREF"
  SPEAKER = "SPEAKER"


class Document(object):
  def __init__(self, doc_id, doc_part):
    self.doc_id = doc_id
    self.doc_part = doc_part
    self.doc_key = "UNK"
    self.sentences = []
    self.speakers = []
    self.clusters = []
    self.parse_spans = []
    self.pos = []

    self.bert_tokenized = False
    self.tokenized_sentences = {}

    self.label_sequences = {}
    self.label_sequences_verified = False

    self.FN_MAP = {
      "mconll": self.dump_to_mconll,
      "512.jsonl": lambda: self.dump_to_jsonl(512),
      "384.jsonl": lambda: self.dump_to_jsonl(384),
      "128.jsonl": lambda: self.dump_to_jsonl(128),
      "feat": self.dump_to_feat,
      "file_per_doc": self.dump_to_fpd}

  def dump_to_fpd(self):
    return [" ".join(sentence) for sentence in self.sentences]

  def dump_to_feat(self):
    features = []
    for cluster in self.clusters:
      for mention in cluster:
        features.append(self.featurize(mention))

  def _get_sentence_idx(self, start, end):
    token_count = 0
    for sent_i, sentence in enumerate(self.sentences):
      end_sentence_token_count = token_count + len(sentence)
      if end_sentence_token_count <= start:
        token_count = end_sentence_token_count
      elif end_sentence_token_count > start:
        assert end_sentence_token_count > end
        return sent_i, start - token_count
      else:
        assert False
       
  def featurize(self, mention):
    sent_i, start_token = self._get_sentence_idx(*mention)

  def dump_to_mconll(self):
    document_name = self.doc_id
    coref_labels = self._get_conll_coref_labels()
    sent_start_tok_count = 0

    orig_tokenized_sents = self.sentences
    if self.bert_tokenized:
      orig_tokenized_sents = self.token_sentences

    mconll_lines = ["#begin document ({}); part {}\n".format(self.doc_id, self.doc_part)]

    for i_sent, sentence in enumerate(orig_tokenized_sents):
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

    # mconll_lines.append("\n#end document " + document_name + "\n")
    mconll_lines.append("\n#end document\n")

    return mconll_lines

  def _verify_label_sequences(self):
    pass

  def _bert_tokenize(self):
    self.token_sentences = self.sentences
    self.token_clusters = self.clusters
    for max_segment_len in [128, 384, 512]:
      self.tokenized_sentences[max_segment_len] = TokenizedSentences(
        self.token_sentences, max_segment_len, self.speakers, self.token_clusters)
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

  # def convert_clusters_bert(self, max_segment_len):
  #   # update clusters to index into tokenized
  #   # todo not totally clear to me why this is max-seg-length-dependent?
  #   offsets = [-1] * sum(map(len, self.token_sentences))
  #   for s in self.tokenized_sentences[max_segment_len].subtoken_map:
  #     offsets[s] += 1
  #   offsets_cumulative = np.cumsum(offsets).tolist()
  #
  #   new_clusters = []
  #   for c in self.clusters:
  #     new_c = []
  #     for m in c:
  #       new_m = [m[0] + offsets_cumulative[m[0]], m[1] + offsets_cumulative[m[1]]]
  #       if offsets[m[0]] > 0:
  #         new_m[0] -= offsets[m[0]]
  #       new_c.append(new_m)
  #     new_clusters.append(new_c)
  #   self.tokenized_clusters[max_segment_len] = new_clusters

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
          "clusters": self.tokenized_sentences[max_segment_len].clusters,
          "parse_spans": self.parse_spans,
          "pos": self.pos
        })]


def write_converted(dataset, prefix):
    with open(prefix + ".mconll", 'w') as f:
      dataset.dump_to_mconll(f)
    for max_segment_len in [128, 384, 512]:
      with open(prefix + "." + str(max_segment_len) + ".jsonl", 'w') as f:
        dataset.dump_to_jsonl(max_segment_len, f)
    dataset.dump_to_fpd(prefix + "-fpd/")
 
