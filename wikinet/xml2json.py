import json
import re
import time
import bz2

import xml.etree.cElementTree as ET
from xml.sax.saxutils import unescape

nsmap = {"xmlns" : "http://www.mediawiki.org/xml/export-0.10/"}
link_re = re.compile("(?:\\[\\[)(.+?)(?:[\\]|#])")

def parse_page(page, out_f):
    title = page.find("./xmlns:title", nsmap).text
    assert title is not None

    redirect = page.find("./xmlns:redirect", nsmap)
    if redirect is not None:
        target = unescape(redirect.attrib["title"])
        out_f.write(json.dumps({"type" : "redirect", "src" : title, "dest" : target}) + "\n")
    else:
        text = page.find("./xmlns:revision/xmlns:text", nsmap).text
        if text is not None:
            links = [unescape(m.group(1)) for m in link_re.finditer(text)]
            out_f.write(json.dumps({"type" : "page", "title" : title, "length" : len(text), "links" : links}) + "\n")

def xml2json(infile, outfile, max_pages):
    npages = 0

    begin_time = time.perf_counter()
    last_output_time = time.perf_counter()

    with bz2.open(infile, "r") as wiki_f, open(outfile, "x") as out_f:
        tree = ET.iterparse(wiki_f, events=["start", "end"])
        _, root = next(tree)

        page_tag = "{{{xmlns}}}page".format(**nsmap)
        for (event, elem) in tree:
            if event == "end" and elem.tag == page_tag:
                parse_page(elem, out_f)
                root.remove(elem)
                npages = npages + 1
            if (time.perf_counter() - last_output_time) > 1.0:
                rate = npages / (time.perf_counter() - begin_time)
                last_output_time = time.perf_counter()
                print("\rprocessed {:d} pages ({:0.1f} pages per second)".format(npages, rate), end="")
            if npages == max_pages: break

    print("\r" + " "*100, end="") # clear line
    print("\rprocessed {:d} pages in {:0.1f} seconds".format(npages, time.perf_counter() - begin_time))
