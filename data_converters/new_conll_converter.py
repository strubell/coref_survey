import os
import json
import convert_lib
import random
import tqdm

PRECO = convert_lib.DatasetName.preco
DUMMY_DOC_PART = '0'

def get_lines_from_file(filename):
  with open(filename, 'r') as f:
    return f.readlines()

      
def make_empty_speakers(sentences):
  return [["" for token in sent] for sent in sentences]


def create_dataset(filename):
  dataset = convert_lib.Dataset("conll12")

  lines = get_lines_from_file(filename)
  for line in tqdm.tqdm(lines):
    orig_document = json.loads(line)
    id = orig_document["document_id"]
    curr_doc_id = id[:-4]
    part = str(int(id[-3:]))
    new_document = convert_lib.Document(curr_doc_id, part)
    new_document.sentences = orig_document["sentences"]
    new_document.speakers = orig_document["speakers"]
    new_document.clusters = orig_document["clusters"]
    dataset.documents.append(new_document)

  return dataset


def convert(data_home):
  output_directory = os.path.join(data_home, "processed")

  convert_lib.create_processed_data_dir(output_directory)
  preco_datasets = {}
  for split in [convert_lib.DatasetSplit.train, convert_lib.DatasetSplit.dev, convert_lib.DatasetSplit.test]:
    input_filename = os.path.join(data_home, split + "." +
                                  convert_lib.FormatName.jsonl)
    converted_dataset = create_dataset(input_filename)
    convert_lib.write_converted(converted_dataset, output_directory + "/" + split, dump_fpd=False)
    preco_datasets[split] = converted_dataset
