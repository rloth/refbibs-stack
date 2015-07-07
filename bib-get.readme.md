BIB-GET.PY
==========
**An ISTEX client for _grobid-service_, the bibliographical annotator.**  
 1. Sends a query to the ISTEX-API  
 2. Retrieves a list of documents  
 3. Feeds each document to _grobid_ for pdftoxml preprocessing, bibzone identification, CRF tagging  
 4. Returns one tei file per document, with all extracted bibliographies  

© 2014-15 Inist-CNRS (ISTEX)  

Usage
------
**`bib-get.py -q 'any lucene query' [--maxi 100]`**  
**`bib-get.py -l some_ID_list.txt`**

### Optional arguments
 - **`-h`** or **`--help`**  
   show a help message and exit
 - **`-q`** `"hawking AND corpusName:nature AND pubdate:[1970 TO *]"`  
   "normal" input mode: triggers retrieval of all bibliographies of all hits of a lucene query passed to the API   
 -  **`-l`** `some_ID_list.txt`  or   **`--list_in`** `some_ID_list.txt`  
   "prepared" input mode: skips the query step and starts directly with a list of ISTEX IDs of the documents to process
 - **`-m`** `10000` or **`--maxi`** `10000`    
   optional maximum limit of processed docs (if the query returned more hits, the remainder will be ignored)
 - **`-c`** `path/to/alternate_config.ini` or **`--config`** `path/to/alternate_config.ini`    
   option to specify an alternate config file (default path is: `<script_dir>/bib-get.ini`)

Config
-------
Here is an example of a configuration file **`bib-get.ini`**
```
[istex-api]
host=api.istex.fr
route=document
[grobid-service]
host=vp-istex-grobid.intra.inist.fr
port=8080
route=processReferencesViaUrl
[output]
dir=mes_sorties_bib_tei
tei_ext=.refbibs.tei.xml
[process]
ncpu=7
```

Install
-------
Install steps are as follows:
  1. Prerequisites
    - a `python3` interpreter
    - a working `grobid-service` (see [the script from **bib-install-vp**](https://git.istex.fr/loth/refbibs_stack/blob/master/bib-install-vp/install_grobid.sh "install_grobid.sh"))
  2. Get the current package
    - `git clone https://git.istex.fr/git/loth/bib-get.git`
  3. Run script!
    - `python bib-get/bib-get.py -q "agile" -m 5`

Contacts
---------
`romain.loth` at `inist.fr`   
`istex` at `inist.fr`
