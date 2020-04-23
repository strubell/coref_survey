import sys
import new_conll_converter


def main():
  data_home = sys.argv[1]
  print("New CoNLL")
  new_conll_converter.convert(data_home)


if __name__ == "__main__":
  main()
