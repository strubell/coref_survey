import collections
import csv
import json
import nltk
from nltk.tokenize import sent_tokenize, word_tokenize
import os

class DatasetName(object):
  conll = 'conll'
  gap = 'gap'
  knowref = 'knowref'
  preco = 'preco'
  red = 'red'
  wikicoref = 'wikicoref'
  ALL_DATASETS = [conll, gap, knowref, preco, red, wikicoref]

class DatasetSplit(object):
  train = 'train'
  test = 'test'
  dev = 'dev'
  valid = 'valid'

class FormatName(object):
  jsonl = 'jsonl'
  jsonlb = 'jsonlb'
  stanford = 'stanford'
  ALL_FORMATS = [jsonl, jsonlb, stanford]

def get_filename(data_home, dataset_name, dataset_split, format_name):
  return os.path.join(data_home, 'processed', dataset_name,
      dataset_split + "." + format_name)

NO_SPEAKER = "NO_SPEAKER"

def make_doc_id(dataset, doc_name):
  if type(doc_name) == list:
    doc_name = "_".join(doc_name)
  return "_".join([dataset, doc_name])


def get_lines_from_file(filename):
  with open(filename, 'r') as f:
    return f.readlines()

def add_sentence(curr_doc, curr_sent):
  # This is definitely passed by reference right
  words, speakers = zip(*curr_sent)
  curr_doc.sentences.append(words)
  curr_doc.speakers.append(speakers)

def make_empty_speakers(sentences):
  return [[NO_SPEAKER for token in sent] for sent in sentences]


def dataset_from_conll():
  pass

def char_to_tok_idx(text, char_indices):
  text = text.replace(
      "''", "``").replace("'", "`").replace("Kasthuri/Lalitha",
  "Kasthuri Lalitha").replace("N.J.Parvathy", "N.J Parvathy").replace(
      "Burch/Joe", "Burch Joe").replace("Punjab.He", "Punjab He"
          ).replace("Hanks/Sally", "Hanks Sally").replace("Down-on-his-luck",
              "Down-on his luck").replace("edal.She", "edal She"
                  ).replace("Medeim/Raisa", "Medeim Raisa"
                      ).replace("Glen/Glenda", "Glen Glenda"
                          ).replace("Ask-Elizabeth", "Ask Elizabeth")

  print("*" * 80)
  print(text)
  print(len(text))
  print(char_indices)
  tokens = sum([word_tokenize(sent) for sent in sent_tokenize(text)], [])
  print(tokens)
  orig_text_counter = 0
  index_map = collections.OrderedDict()
  for i, token in enumerate(tokens):
    print(i, token, orig_text_counter)
    assert text[orig_text_counter:orig_text_counter + len(token)] == token
    index_map[orig_text_counter] = i
    orig_text_counter += len(token)
    if i == len(tokens) - 1:
      break
    while True:
      next_token = tokens[i+1]
      next_token_len = len(next_token)
      if next_token == text[orig_text_counter:orig_text_counter+next_token_len]:
        break
      else:
        assert text[orig_text_counter].isspace()
        orig_text_counter += 1

  token_indices = []
  for mention_text, char_idx in char_indices.items():
    start_index = int(char_idx)
    end_char_index = start_index + len(mention_text)
    prev_index = start_index
    end_index = start_index
    for maybe_end_index in index_map:
      if maybe_end_index > end_char_index:
        end_index = prev_index
        break
      prev_index = maybe_end_index
    token_indices.append((index_map[start_index], index_map[end_index]))

  return token_indices


def dataset_from_gap(filename):
  dataset = Dataset(DatasetName.gap)
  print(filename)
  with open(filename, 'r') as tsvfile:
    for row in csv.DictReader(tsvfile, delimiter='\t'):
      curr_document = Document(make_doc_id(DatasetName.gap, row["ID"]))
      (pronoun_indices, a_indices, b_indices) = char_to_tok_idx(row["Text"],
        {row["Pronoun"]: row["Pronoun-offset"],
         row["A"]: row["A-offset"],
         row["B"]: row["B-offset"]})
      true_cluster = [pronoun_indices]
      if bool(row["A-coref"]):
        true_cluster.append(a_indices)
      if bool(row["B-coref"]):
        true_cluster.append(b_indices)
      curr_document.sentences = [
          word_tokenize(sent) for sent in sent_tokenize(row["Text"])]
      curr_document.speakers = make_empty_speakers(curr_document.sentences)
      curr_document.clusters = [true_cluster]
      dataset.documents.append(curr_document)

  return dataset

def dataset_from_knowref():
  pass

def dataset_from_preco(filename):

  dataset = Dataset(DatasetName.preco)
  
  for line in get_lines_from_file(filename):
    orig_document = json.loads(line)
    new_document = Document(
        make_doc_id(DatasetName.preco, orig_document["id"]))
    new_document.sentences = orig_document["sentences"]
    new_document.speakers = make_empty_speakers(new_document.sentences)
    new_document.clusters = orig_document["mention_clusters"]
    dataset.documents.append(new_document)

  return dataset



def dataset_from_red():
  pass

def dataset_from_wikicoref(filename):
 
  dataset_name = DatasetName.wikicoref
  dataset = Dataset(dataset_name)

  document_counter = 0

  curr_doc = None
  curr_sent = []

  for line in get_lines_from_file(filename):

    if line.startswith("#end") or line.startswith("null"):
      continue
    elif line.startswith("#begin"):
      if curr_doc is not None:
        dataset.documents.append(curr_doc)
      curr_doc_id = make_doc_id(dataset_name, line.split()[3:])
      curr_doc = Document(curr_doc_id)
    else:
      fields = line.split()
      if not fields:
        if curr_sent:
          add_sentence(curr_doc, curr_sent)
          curr_sent = []
      else:
          word = fields[3]
          curr_sent.append((word, NO_SPEAKER))
  return dataset


class Dataset(object):
  def __init__(self, dataset_name):
    self.name = dataset_name
    self.documents = []

    self.DUMP_FUNCTIONS = {
      FormatName.jsonl: self.dump_to_jsonl,
      FormatName.jsonlb: self.dump_to_jsonlb,
      FormatName.stanford: self.write_to_stanford_files
      }

  def dump_to_jsonl(self):
    return "\n".join(doc.dump_to_jsonl() for doc in self.documents)

  def write_to_stanford_files(self, path):
    for document in self.documents:
      filename = os.path.join(path, document.doc_id + ".txt")
      with open(filename, 'w') as f:
        for sentence in document.sentences:
          f.write(" ".join(sentence) + "\n")


class Document(object):
  def __init__(self, doc_id):
    self.doc_id = doc_id
    self.sentences = []
    self.speakers = []
    self.clusters = []


  def dump_to_jsonl(self):
    return json.dumps({
          "doc_key": "nw",
          "document_id": self.doc_id,
          "sentences": self.sentences,
          "speakers": self.speakers,
          "clusters": self.clusters
        })

  def dump_to_bert_jsonl(self, ):
    pass
