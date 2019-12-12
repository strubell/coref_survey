import sys
import gap_converter


def main():
  data_home = sys.argv[1]
  print("gap")
  gap_converter.convert(data_home)


if __name__ == "__main__":
  main()
