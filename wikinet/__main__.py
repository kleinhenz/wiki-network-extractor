import argparse
import sys
import os

import wikinet

def run_xml2json(args):
    wikinet.xml2json(args.input, args.output, args.n)

def run_json2hdf(args):
    wikinet.json2hdf(args.input, args.output)

def main():
    parser = argparse.ArgumentParser(
        prog=(os.path.basename(sys.executable) + " -m wikinet"),
        description="tool for extracting network structure from wiki xml dumps"
    )

    parser.set_defaults(func=lambda _: parser.print_help())

    subparsers = parser.add_subparsers()

    xml2json_parser = subparsers.add_parser("xml2json")
    xml2json_parser.add_argument("input", help="zipped wiki xml dump to parse")
    xml2json_parser.add_argument("output", help="output ndjson file")
    xml2json_parser.add_argument("-n", type=int, help="only parse first n pages")
    xml2json_parser.set_defaults(func=run_xml2json)

    json2hdf_parser = subparsers.add_parser("json2hdf")
    json2hdf_parser.add_argument("input", help="input ndjson file to parse")
    json2hdf_parser.add_argument("output", help="output hdf5 file")
    json2hdf_parser.set_defaults(func=run_json2hdf)

    args = parser.parse_args()
    args.func(args)

main()
