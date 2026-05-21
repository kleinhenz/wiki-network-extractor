import json
import re
import bz2

import xml.etree.cElementTree as ET
from xml.sax.saxutils import unescape

from tqdm import tqdm

import os

from collections import namedtuple

import numpy as np
import h5py


filter_title_re = re.compile(
    "(?:Wikipedia:|:?File:|Media:|:?Image:|:?Template:|Draft:|Portal:|Module:|TimedText:|MediaWiki:|Help:)"
)

Page = namedtuple("Page", ["title", "length"])


link_re = re.compile("(?:\\[\\[)(.+?)(?:[\\]|#])")


def parse_page(page, out_f, nsmap):
    title = page.find("./xmlns:title", nsmap).text
    assert title is not None

    redirect = page.find("./xmlns:redirect", nsmap)
    if redirect is not None:
        target = unescape(redirect.attrib["title"])
        out_f.write(
            json.dumps({"type": "redirect", "src": title, "dest": target}) + "\n"
        )
    else:
        text = page.find("./xmlns:revision/xmlns:text", nsmap).text
        if text is not None:
            links = [unescape(m.group(1)) for m in link_re.finditer(text)]
            out_f.write(
                json.dumps(
                    {
                        "type": "page",
                        "title": title,
                        "length": len(text),
                        "links": links,
                    }
                )
                + "\n"
            )


def xml2json(infile, outfile, max_pages):
    print("running xml2json...")
    npages = 0
    with bz2.open(infile, "r") as wiki_f, open(outfile, "x") as out_f:
        tree = ET.iterparse(wiki_f, events=["start", "end"])
        _, root = next(tree)
        ns = re.match("^{(.*?)}", root.tag).group(1)  # extract namespace
        nsmap = {"xmlns": ns}
        page_tag = "{{{xmlns}}}page".format(**nsmap)

        progress = tqdm(unit="pages")

        for event, elem in tree:
            if event == "end" and elem.tag == page_tag:
                parse_page(elem, out_f, nsmap)
                root.remove(elem)
                npages = npages + 1
                progress.update()
            if npages == max_pages:
                break
    progress.close()
    print("done")


def parse_titles(infile):
    print("reading titles...")
    redirects = {}
    pages = []

    progress = tqdm(total=os.path.getsize(infile), unit="bytes")
    with open(infile, "rb") as f:
        for n, line in enumerate(f):
            progress.update(len(line))
            data = json.loads(line.decode())
            if data["type"] == "redirect":
                src, dest = data["src"], data["dest"]
                redirects[src] = dest
            elif data["type"] == "page":
                title, length = data["title"], data["length"]
                if not filter_title_re.match(title):
                    pages.append(Page(title, length))
            else:
                assert False

    progress.close()

    title_idx_map = {}
    for i, p in enumerate(pages):
        title_idx_map[p.title] = i

    for src, dest in redirects.items():
        if dest in title_idx_map and src not in title_idx_map:
            title_idx_map[src] = title_idx_map[dest]

    return pages, title_idx_map


def parse_links(infile, pages, title_idx_map):
    print("reading links...")

    adjacency_list = [[] for _ in range(len(pages))]

    # the first letter of link is not case sensitive
    def normalize_link(link):
        if len(link) == 1:
            return link
        return link[0].upper() + link[1:]

    progress = tqdm(total=os.path.getsize(infile), unit="bytes")
    with open(infile, "rb") as f:
        for n, line in enumerate(f):
            progress.update(len(line))
            data = json.loads(line.decode())
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
    progress.close()

    return adjacency_list


def write_graph(outfile, pages, adjacency_list):
    assert len(pages) == len(adjacency_list)
    print("writing output...")

    nv = len(adjacency_list)
    ne = sum(len(row) for row in adjacency_list)

    IA = np.zeros((nv + 1,), dtype=np.int32)
    IA[1:] = np.cumsum([len(row) for row in adjacency_list], dtype=np.int32)

    JA = np.zeros((ne,), dtype=np.int32)
    for i in range(nv):
        JA[IA[i] : IA[i + 1]] = adjacency_list[i]

    dt = h5py.special_dtype(vlen=str)
    with h5py.File(outfile, "w") as f:
        dset = f.create_dataset("/graph/vertices/titles", (nv,), dt)
        dset[:] = [p.title for p in pages]
        f["/graph/vertices/lengths"] = [p.length for p in pages]
        f["/graph/adjacency/csr/IA"] = IA
        f["/graph/adjacency/csr/JA"] = JA


def json2graph(infile):
    pages, title_idx_map = parse_titles(infile)
    adjacency_list = parse_links(infile, pages, title_idx_map)
    return pages, adjacency_list


def json2hdf(infile, outfile):
    print("running json2hdf...")
    pages, adjacency_list = json2graph(infile)
    write_graph(outfile, pages, adjacency_list)
    print("done")
