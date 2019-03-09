#!/usr/bin/env python3

import argparse
import json
import re
import time

from collections import namedtuple

import numpy as np
import h5py

filter_title_re = re.compile("(?:Wikipedia:|:?Category:|:?File:|Media:|:?Image:|:?Template:|Draft:|Portal:|Module:|TimedText:|MediaWiki:|Help:)")

Page = namedtuple("Page", ["title", "length"])

def parse_titles(infile):
    print("reading titles...")
    begin_time = time.perf_counter()
    last_output_time = begin_time

    redirects = {}
    pages = []

    with open(infile, "r") as f:
        for n, line in enumerate(f):
            data = json.loads(line)
            if data["type"] == "redirect":
                src, dest = data["src"], data["dest"]
                redirects[src] = dest
            elif data["type"] == "page":
                title, length = data["title"], data["length"]
                if not filter_title_re.match(title):
                    pages.append(Page(title, length))
            else: assert False

            if (time.perf_counter() - last_output_time) > 1.0:
                rate = n / (time.perf_counter() - begin_time)
                last_output_time = time.perf_counter()
                print("\rprocessed {:d} pages ({:0.1f} pages per second)".format(n, rate), end="")

    title_idx_map = {}
    for i, p in enumerate(pages):
        title_idx_map[p.title] = i

    for src, dest in redirects.items():
        if dest in title_idx_map and src not in title_idx_map:
            title_idx_map[src] = title_idx_map[dest]

    print("\ndone")

    return pages, title_idx_map

def parse_links(infile, pages, title_idx_map):
    print("reading links...")
    begin_time = time.perf_counter()
    last_output_time = begin_time

    adjacency_list = [[] for _ in range(len(pages))]

    # the first letter of link is not case sensitive
    def normalize_link(link):
        if len(link) == 1: return link
        return link[0].upper() + link[1:]

    with open(infile, "r") as f:
        for n, line in enumerate(f):
            data = json.loads(line)
            if data["type"] == "page":
                title = data["title"]
                if title in title_idx_map:
                    i = title_idx_map[title]

                    links = [normalize_link(l) for l in data["links"]]
                    links = [title_idx_map.get(l, None) for l in links]
                    links = [l for l in links if l is not None]
                    links = sorted(set(links))

                    for j in links:
                        adjacency_list[i].append(j)

            if (time.perf_counter() - last_output_time) > 1.0:
                rate = n / (time.perf_counter() - begin_time)
                last_output_time = time.perf_counter()
                print("\rprocessed {:d} pages ({:0.1f} pages per second)".format(n, rate), end="")

    print("\ndone")

    return adjacency_list

def json2graph(infile):
    pages, title_idx_map = parse_titles(infile)
    adjacency_list = parse_links(infile, pages, title_idx_map)
    return pages, adjacency_list

def write_graph(outfile, pages, adjacency_list):
    assert len(pages) == len(adjacency_list)
    print("writing output...")

    nv = len(adjacency_list)
    ne = sum(len(row) for row in adjacency_list)

    IA = np.zeros((nv + 1,), dtype=np.int32)
    IA[1:] = np.cumsum([len(row) for row in adjacency_list], dtype=np.int32)

    JA = np.zeros((ne,), dtype=np.int32)
    for i in range(nv):
        JA[IA[i]:IA[i+1]] = adjacency_list[i]

    dt = h5py.special_dtype(vlen=str)
    with h5py.File(outfile, "w") as f:
        dset = f.create_dataset("/graph/vertices/titles", (nv,), dt)
        dset[:] = [p.title for p in pages]
        f["/graph/vertices/lengths"] = [p.length for p in pages]
        f["/graph/adjacency/csr/IA"] = IA
        f["/graph/adjacency/csr/JA"] = JA

    print("done")

def main():
    parser = argparse.ArgumentParser(description="parse data emitted by xml2json.py and output adjacency matrix")
    parser.add_argument("infile", help="data to parse")
    parser.add_argument("output", help="output file")
    args = parser.parse_args()

    pages, adjacency_list = json2graph(args.infile)
    write_graph(args.output, pages, adjacency_list)

if __name__ == "__main__":
    main()
