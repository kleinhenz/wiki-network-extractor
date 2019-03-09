# wiki-network-extractor
wiki-network-extractor (`wikinet`) is a python module for extracting link networks from [wikimedia xml dumps](https://dumps.wikimedia.org).

## Installation
`pip install git+https://github.com/kleinhenz/wiki-network-extractor.git`

## Usage
The following commands download and parse the latest xml dump of [simple english wikipedia](https://simple.wikipedia.org/wiki/Main_Page).
This takes ~300MB of disk space and ~1 minute to parse.
```
curl -L "https://dumps.wikimedia.org/simplewiki/latest/simplewiki-latest-pages-articles.xml.bz2" > simplewiki.xml.bz2
python -m wikinet xml2json simplewiki.xml.bz2 simplewiki.json
python -m wikinet json2hdf simplewiki.json simplewiki.h5
```
This creates a hdf5 archive (`simplewiki.h5`) containing page titles, lengths (in characters) and the adjacency matrix of the link network in [CSR](https://en.wikipedia.org/wiki/Sparse_matrix#Compressed_sparse_row_(CSR,_CRS_or_Yale_format)) format.
The structure of the hdf5 archive is shown below (obtained from `h5dump -n 1 simplewiki.h5`).
```
HDF5 "simplewiki.h5" {
FILE_CONTENTS {
 group      /
 group      /graph
 group      /graph/adjacency
 group      /graph/adjacency/csr
 dataset    /graph/adjacency/csr/IA
 dataset    /graph/adjacency/csr/JA
 group      /graph/vertices
 dataset    /graph/vertices/lengths
 dataset    /graph/vertices/titles
 }
}
```

## Inspiration
* [six degrees of wikipedia](http://mu.netsoc.ie/wiki/)
* [sdow](https://github.com/jwngr/sdow)

## Implementation Notes

### Two Stage Parsing
Network extraction is done in two stages to optimize speed, memory, and disk space requirements.
In the first, and slowest stage `xml2json` incrementally reads a (bzip2 compressed) xml dump, extracts all links from the text of each page using regex and produces a [newline delimited json](http://ndjson.org/) file where each line is a json object containing the title, length and links for a single page/redirect.
In the second stage `json2hdf` reads the json file, applies filters, resolves all links and saves the results in a hdf5 archive.

This two stage approach is used because in order to resolve links a complete list of all page titles and redirects must be available.
Therefore, either all links must be held in memory as text until the entire wiki has been read or else the wiki must be read twice (once to collect all titles and redirects and once to resolve links).
For large wikis, e.g. [english wikipedia](https://en.wikipedia.org/wiki/Main_Page), holding all links as text requires a prohibitive amount of memory for typical machines so it is necessary to use the second approach and take two passes.
However, reading the xml dump twice would be slow because of its size and compression (and it is desirable keep it compressed in order to save disk space).
The intermediate ndjson representation solves these problems since it can be written on the fly requiring only one pass through the xml dump, and can be read quickly making the two pass approach feasible in the second stage.

### Link Extraction
[Wikitext links](https://en.wikipedia.org/wiki/Help:Link) have the general form `[[Page name#Section name|displayed text]]`.
The target for each link is extracted in `xml2json` using the following python regex: `re.compile("(?:\\[\\[)(.+?)(?:[\\]|#])")`.

### Link Resolution
Resolving links is a mostly straightforward process except for two details.
First links can point to redirects that must be followed.
Second the first letter of a link is case insensitive unless the link is only a single letter.
`wikinet` takes care to handle both these details correctly by keeping track of all redirects and normalizing links.

### Page Filtering
The xml dumps contain many pages that are not normal articles such as files and help pages.
These are filtered in `json2hdf` by checking page titles against the following python regex:
```
re.compile("(?:Wikipedia:|:?Category:|:?File:|Media:|:?Image:|:?Template:|Draft:|Portal:|Module:|TimedText:|MediaWiki:|Help:)")
```

### Storage Format
The output is stored as a hdf5 archive rather than as GraphML or some other text based format because the data can be large enough to make these formats inconvenient in terms of both disk space and parsing time.
For example the link network of [simple english wikipedia](https://simple.wikipedia.org/wiki/Main_Page) takes up ~125MB as a GraphML file but only ~16MB as a hdf5 archive.
These savings become more important for larger wikis such as [english wikipedia](https://en.wikipedia.org/wiki/Main_Page) which takes up about 1GB as a hdf5 archive.
