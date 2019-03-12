import json
import re
import time
import bz2

import xml.etree.cElementTree as ET
from xml.sax.saxutils import unescape

from tqdm import tqdm

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
    print("running xml2json...")
    npages = 0
    with bz2.open(infile, "r") as wiki_f, open(outfile, "x") as out_f:
        tree = ET.iterparse(wiki_f, events=["start", "end"])
        _, root = next(tree)

        progress = tqdm(unit="pages")

        page_tag = "{{{xmlns}}}page".format(**nsmap)
        for (event, elem) in tree:
            if event == "end" and elem.tag == page_tag:
                parse_page(elem, out_f)
                root.remove(elem)
                npages = npages + 1
                progress.update()
            if npages == max_pages: break
    progress.close()
    print("done")
