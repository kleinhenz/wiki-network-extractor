import bz2
import json
import os
import tempfile
import unittest

import h5py

from wiki_network_extractor import json2graph, json2hdf, xml2json


def write_ndjson(path, rows):
    with open(path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


class WikiNetworkExtractorTests(unittest.TestCase):
    def test_redirect_chains_are_resolved(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "wiki.json")
            write_ndjson(
                path,
                [
                    {
                        "type": "page",
                        "title": "Final",
                        "ns": 0,
                        "length": 1,
                        "links": [],
                    },
                    {"type": "redirect", "src": "A", "dest": "B", "ns": 0},
                    {"type": "redirect", "src": "B", "dest": "Final", "ns": 0},
                    {
                        "type": "page",
                        "title": "Source",
                        "ns": 0,
                        "length": 1,
                        "links": ["A"],
                    },
                ],
            )

            pages, adjacency = json2graph(path)

        self.assertEqual([p.title for p in pages], ["Final", "Source"])
        self.assertEqual(adjacency, [[], [0]])

    def test_legacy_redirect_records_still_work(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "wiki.json")
            write_ndjson(
                path,
                [
                    {"type": "page", "title": "Final", "length": 1, "links": []},
                    {"type": "redirect", "src": "Old", "dest": "Final"},
                    {"type": "page", "title": "Source", "length": 1, "links": ["Old"]},
                ],
            )

            pages, adjacency = json2graph(path)

        self.assertEqual([p.title for p in pages], ["Final", "Source"])
        self.assertEqual(adjacency, [[], [0]])

    def test_redirect_cycles_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "wiki.json")
            write_ndjson(
                path,
                [
                    {
                        "type": "page",
                        "title": "Source",
                        "ns": 0,
                        "length": 1,
                        "links": ["A"],
                    },
                    {"type": "redirect", "src": "A", "dest": "B", "ns": 0},
                    {"type": "redirect", "src": "B", "dest": "A", "ns": 0},
                ],
            )

            pages, adjacency = json2graph(path)

        self.assertEqual([p.title for p in pages], ["Source"])
        self.assertEqual(adjacency, [[]])

    def test_links_normalize_underscores_and_case(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "wiki.json")
            write_ndjson(
                path,
                [
                    {
                        "type": "page",
                        "title": "Foo bar",
                        "ns": 0,
                        "length": 1,
                        "links": [],
                    },
                    {
                        "type": "page",
                        "title": "Source",
                        "ns": 0,
                        "length": 1,
                        "links": ["foo_bar"],
                    },
                ],
            )

            pages, adjacency = json2graph(path)

        self.assertEqual([p.title for p in pages], ["Foo bar", "Source"])
        self.assertEqual(adjacency, [[], [0]])

    def test_namespace_filter_uses_xml_namespace_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "wiki.json")
            write_ndjson(
                path,
                [
                    {
                        "type": "page",
                        "title": "Article",
                        "ns": 0,
                        "length": 1,
                        "links": [],
                    },
                    {
                        "type": "page",
                        "title": "Talk:Article",
                        "ns": 1,
                        "length": 1,
                        "links": [],
                    },
                    {
                        "type": "page",
                        "title": "User:Name",
                        "ns": 2,
                        "length": 1,
                        "links": [],
                    },
                ],
            )

            pages, adjacency = json2graph(path)

        self.assertEqual([p.title for p in pages], ["Article"])
        self.assertEqual(adjacency, [[]])

    def test_json2hdf_writes_expected_csr(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            in_path = os.path.join(tmpdir, "wiki.json")
            out_path = os.path.join(tmpdir, "wiki.h5")
            write_ndjson(
                in_path,
                [
                    {
                        "type": "page",
                        "title": "A",
                        "ns": 0,
                        "length": 1,
                        "links": ["B", "B"],
                    },
                    {
                        "type": "page",
                        "title": "B",
                        "ns": 0,
                        "length": 2,
                        "links": ["A"],
                    },
                ],
            )

            json2hdf(in_path, out_path)

            with h5py.File(out_path, "r") as f:
                titles = [title.decode() for title in f["/graph/vertices/titles"][:]]
                lengths = f["/graph/vertices/lengths"][:].tolist()
                ia = f["/graph/adjacency/csr/IA"][:].tolist()
                ja = f["/graph/adjacency/csr/JA"][:].tolist()

        self.assertEqual(titles, ["A", "B"])
        self.assertEqual(lengths, [1, 2])
        self.assertEqual(ia, [0, 1, 2])
        self.assertEqual(ja, [1, 0])

    def test_xml2json_records_namespace(self):
        xml = """<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/">
  <page>
    <title>Article</title>
    <ns>0</ns>
    <revision><text>[[Target|label]]</text></revision>
  </page>
  <page>
    <title>Talk:Article</title>
    <ns>1</ns>
    <revision><text>[[Article]]</text></revision>
  </page>
</mediawiki>"""
        with tempfile.TemporaryDirectory() as tmpdir:
            in_path = os.path.join(tmpdir, "wiki.xml.bz2")
            out_path = os.path.join(tmpdir, "wiki.json")
            with bz2.open(in_path, "wt") as f:
                f.write(xml)

            xml2json(in_path, out_path, None)

            with open(out_path) as f:
                rows = [json.loads(line) for line in f]

        self.assertEqual(rows[0]["ns"], 0)
        self.assertEqual(rows[0]["links"], ["Target"])
        self.assertEqual(rows[1]["ns"], 1)

    def test_xml2json_honors_zero_page_limit(self):
        xml = """<mediawiki xmlns="http://www.mediawiki.org/xml/export-0.11/">
  <page>
    <title>Article</title>
    <ns>0</ns>
    <revision><text>[[Target]]</text></revision>
  </page>
</mediawiki>"""
        with tempfile.TemporaryDirectory() as tmpdir:
            in_path = os.path.join(tmpdir, "wiki.xml.bz2")
            out_path = os.path.join(tmpdir, "wiki.json")
            with bz2.open(in_path, "wt") as f:
                f.write(xml)

            xml2json(in_path, out_path, 0)

            with open(out_path) as f:
                rows = f.readlines()

        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
