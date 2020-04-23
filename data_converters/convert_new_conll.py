import sys
import preco_converter


def main():
  data_home = sys.argv[1]
  print("New CoNLL")
  preco_converter.convert_not_preco(data_home)


if __name__ == "__main__":
  main()
