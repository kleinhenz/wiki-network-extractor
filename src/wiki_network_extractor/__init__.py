import bz2
import json
import os
import re
from collections import namedtuple

import xml.etree.cElementTree as ET
from xml.sax.saxutils import unescape

from tqdm import tqdm

import numpy as np
import h5py


filter_title_re = re.compile(
    "(?:Wikipedia:|:?File:|Media:|:?Image:|:?Template:|Draft:|Portal:"
    "|Module:|TimedText:|MediaWiki:|Help:)"
)
ARTICLE_NAMESPACE = 0

Page = namedtuple("Page", ["title", "length"])


link_re = re.compile("(?:\\[\\[)(.+?)(?:[\\]|#])")


def normalize_title(title):
    title = title.replace("_", " ").strip()
    if len(title) <= 1:
        return title
    return title[0].upper() + title[1:]


def is_article_record(data):
    ns = data.get("ns")
    if ns is not None:
        return ns == ARTICLE_NAMESPACE
    title = data.get("title", data.get("src"))
    if title is None:
        raise ValueError("record is missing a title")
    return not filter_title_re.match(title)


def resolve_link_indices(links, title_idx_map):
    indices = [title_idx_map.get(normalize_title(link)) for link in links]
    return sorted({index for index in indices if index is not None})


def parse_page(page, out_f, nsmap):
    title_elem = page.find("./xmlns:title", nsmap)
    if title_elem is None or title_elem.text is None:
        raise ValueError("page is missing a title")

    title = title_elem.text
    ns_elem = page.find("./xmlns:ns", nsmap)
    ns = int(ns_elem.text) if ns_elem is not None and ns_elem.text is not None else None

    redirect = page.find("./xmlns:redirect", nsmap)
    if redirect is not None:
        target = unescape(redirect.attrib["title"])
        out_f.write(
            json.dumps({"type": "redirect", "src": title, "dest": target, "ns": ns})
            + "\n"
        )
    else:
        text_elem = page.find("./xmlns:revision/xmlns:text", nsmap)
        text = text_elem.text if text_elem is not None else None
        if text is not None:
            links = [unescape(m.group(1)) for m in link_re.finditer(text)]
            out_f.write(
                json.dumps(
                    {
                        "type": "page",
                        "title": title,
                        "ns": ns,
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
        ns_match = re.match("^{(.*?)}", root.tag)
        if ns_match is None:
            raise ValueError("XML root tag is missing a namespace")
        ns = ns_match.group(1)
        nsmap = {"xmlns": ns}
        page_tag = "{{{xmlns}}}page".format(**nsmap)

        progress = tqdm(unit="pages")

        for event, elem in tree:
            if event == "end" and elem.tag == page_tag:
                if max_pages is not None and npages >= max_pages:
                    break
                parse_page(elem, out_f, nsmap)
                root.remove(elem)
                npages = npages + 1
                progress.update()
    progress.close()
    print("done")


def parse_titles(infile):
    print("reading titles...")
    redirects = {}
    pages = []

    progress = tqdm(total=os.path.getsize(infile), unit="bytes")
    with open(infile, "rb") as f:
        for line in f:
            progress.update(len(line))
            data = json.loads(line.decode())
            if data["type"] == "redirect":
                if is_article_record(data):
                    src, dest = data["src"], data["dest"]
                    redirects[normalize_title(src)] = normalize_title(dest)
            elif data["type"] == "page":
                title, length = data["title"], data["length"]
                if is_article_record(data):
                    pages.append(Page(title, length))
            else:
                raise ValueError(f"unknown record type: {data['type']!r}")

    progress.close()

    title_idx_map = {}
    for i, p in enumerate(pages):
        title_idx_map[normalize_title(p.title)] = i

    def resolve_redirect(title, seen=None):
        if title in title_idx_map:
            return title_idx_map[title]
        if title not in redirects:
            return None
        if seen is None:
            seen = set()
        if title in seen:
            return None
        seen.add(title)
        return resolve_redirect(redirects[title], seen)

    for src in redirects:
        resolved = resolve_redirect(src)
        if resolved is not None and src not in title_idx_map:
            title_idx_map[src] = resolved

    return pages, title_idx_map


def parse_links(infile, pages, title_idx_map):
    print("reading links...")

    adjacency_list = [[] for _ in range(len(pages))]

    progress = tqdm(total=os.path.getsize(infile), unit="bytes")
    with open(infile, "rb") as f:
        for line in f:
            progress.update(len(line))
            data = json.loads(line.decode())
            if data["type"] == "page":
                title = data["title"]
                i = title_idx_map.get(normalize_title(title))
                if i is not None:
                    for j in resolve_link_indices(data["links"], title_idx_map):
                        adjacency_list[i].append(j)
    progress.close()

    return adjacency_list


def _count_links(infile, title_idx_map, nv):
    counts = np.zeros((nv,), dtype=np.int64)

    progress = tqdm(total=os.path.getsize(infile), unit="bytes")
    with open(infile, "rb") as f:
        for line in f:
            progress.update(len(line))
            data = json.loads(line.decode())
            if data["type"] != "page":
                continue
            i = title_idx_map.get(normalize_title(data["title"]))
            if i is None:
                continue
            counts[i] = len(resolve_link_indices(data["links"], title_idx_map))
    progress.close()

    return counts


def _fill_links(infile, title_idx_map, IA, JA):
    offsets = IA[:-1].copy()

    progress = tqdm(total=os.path.getsize(infile), unit="bytes")
    with open(infile, "rb") as f:
        for line in f:
            progress.update(len(line))
            data = json.loads(line.decode())
            if data["type"] != "page":
                continue
            i = title_idx_map.get(normalize_title(data["title"]))
            if i is None:
                continue
            links = resolve_link_indices(data["links"], title_idx_map)
            start = offsets[i]
            end = start + len(links)
            JA[start:end] = links
            offsets[i] = end
    progress.close()


def _csr_dtype(n):
    return np.int64 if n > np.iinfo(np.int32).max else np.int32


def write_graph_csr(outfile, pages, IA, JA):
    print("writing output...")

    nv = len(pages)
    dt = h5py.special_dtype(vlen=str)
    with h5py.File(outfile, "w") as f:
        dset = f.create_dataset("/graph/vertices/titles", (nv,), dt)
        dset[:] = [p.title for p in pages]
        f["/graph/vertices/lengths"] = [p.length for p in pages]
        f["/graph/adjacency/csr/IA"] = IA
        f["/graph/adjacency/csr/JA"] = JA


def write_graph_from_json(outfile, infile, pages, title_idx_map):
    print("counting links...")

    nv = len(pages)
    counts = _count_links(infile, title_idx_map, nv)
    ne = int(counts.sum())
    dtype = _csr_dtype(max(nv + 1, ne))

    IA = np.zeros((nv + 1,), dtype=dtype)
    IA[1:] = np.cumsum(counts, dtype=dtype)
    JA = np.zeros((ne,), dtype=dtype)

    print("resolving links...")
    _fill_links(infile, title_idx_map, IA, JA)
    write_graph_csr(outfile, pages, IA, JA)


def write_graph(outfile, pages, adjacency_list):
    if len(pages) != len(adjacency_list):
        raise ValueError("pages and adjacency_list must have the same length")

    nv = len(adjacency_list)
    ne = sum(len(row) for row in adjacency_list)
    dtype = _csr_dtype(max(nv + 1, ne))

    IA = np.zeros((nv + 1,), dtype=dtype)
    IA[1:] = np.cumsum([len(row) for row in adjacency_list], dtype=dtype)

    JA = np.zeros((ne,), dtype=dtype)
    for i in range(nv):
        JA[IA[i] : IA[i + 1]] = adjacency_list[i]

    write_graph_csr(outfile, pages, IA, JA)


def json2graph(infile):
    pages, title_idx_map = parse_titles(infile)
    adjacency_list = parse_links(infile, pages, title_idx_map)
    return pages, adjacency_list


def json2hdf(infile, outfile):
    print("running json2hdf...")
    pages, title_idx_map = parse_titles(infile)
    write_graph_from_json(outfile, infile, pages, title_idx_map)
    print("done")
