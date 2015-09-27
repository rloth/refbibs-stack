BIB-GET.PY
==========
**An ISTEX client for *grobid-service*, the bibliographical annotator.**  

Install
-------

 1. Prerequisites : 
    - a `python3` interpreter
    - a working `grobid-service` (see [the script from **bib-install-vp**](https://git.istex.fr/loth/refbibs-stack/blob/master/bib-install-vp/install_grobid.sh "install_grobid.sh"))
    - a correct proxy + authorization setup to access to api.istex.fr and to the grobid machine 
 2. Get the current package by cloning the git or getting the ZIP: 
    - `git clone https://git.istex.fr/git/loth/bib-get.git`
    - or download [the installation ZIP archive](https://git.istex.fr/loth/bib-get/archive/master.zip) and extract in any chosen directory where future work will take place

That's it! You can run the script on 5 documents for a small test: `python3 bib-get.py -q "agile" --maxi 5`


Standard usage
---------------
**`python3 bib-get.py -q 'corpusName:mon_corpus' [--group_output]`**  

Runtime flow
-------------
 1. Sends a query to the ISTEX-API  
 2. Retrieves a list of documents matching the query  
 3. Feeds each document (as a pdf) to the _grobid_  production server for :  
     - pdf to text preprocessing  
     - cascading identification of the references section, of each reference, and finally of each field in the references  
         -> calls to wapiti CRF tagger with bibzone, biblines and bibfields models
     - TEI XML output  
 4. Returns TEI XML files with all extracted bibliographies  
 5. Optionally groups all result XML files in a large teiCorpus file for API enrichment

Result files
-------------
bib-get creates a result directory named:  
**`<timestamp>-output_bibs.dir`**

In "group_output" mode, the directory is also created and after the process all files are grouped in a teiCorpus file named:  
**`<timestamp>-output_bibs.teiCorpus.xml`**

(These names can be changed in the configuration file)

Timestamps have the following format: YYYY-MM-DD_HHhmm

Detailed usage
---------------
`python3 bib-get.py -q 'any lucene query' [--maxi 100] [--group_output]`  
`python3 bib-get.py --list_in some_ID_list.txt [--group_output]`  
`python3 bib-get.py --print_config`  

### Options
 - **`-h`** or **`--help`**  
   show a help message and exit
 - **`-q`** `"corpusName:nature AND publicationDate:[1970 TO *] AND genre:article"`  
   "normal" input mode: triggers retrieval of bibliographies for all docs matching this query in the API
 -  **`-l`** `some_ID_list.txt`  or   **`--list_in`** `some_ID_list.txt`  
   "prepared" input mode: starts directly with a list of ISTEX IDs of the documents to process
 -  **`-g`**   or   **`--group_output`**
   "teiCorpus" optional output: groups all single TEI output files into one large teiCorpus file at end of run (for return as API enrichment)
 - **`-m`** `10000` or **`--maxi`** `10000`    
   optional maximum limit of processed docs (if the query returned more hits, the remainder will be ignored)
 - **`-c`** `path/to/alternate_config.ini` or **`--config`** `path/to/alternate_config.ini`    
   option to specify an alternate config file (default path is: `<script_dir>/bib-get.ini`)
 - **`-p`** or **`--print_config`**    
   print out the actual configuration file and exit


More information on the lucene query syntax can be found on the [API documentation page](https://api.istex.fr/documentation/300-search.html#syntaxe-des-requetes).  


Advanced config
---------------
All parameters are set throught the configuration file **`bib-get.ini`**

**Exemple**

```INI
[istex-api]
host=api.istex.fr
route=document

[grobid-service]
host=vp-istex-grobid.intra.inist.fr
port=8080
route=processReferencesViaUrl

[output]
dir=output_bibs.dir
tei_ext=.refbibs.tei.xml
corpusfile=output_bibs.teiCorpus.xml

[process]
service-ncpu=9

```

The `[istex-api]` section allows the client **to know the source pdf locations**  
(the pdf url    <=> `https://<host>/<route>/<istex-id>/fulltext/pdf`)

The `[grobid-service]` section allows the client **to retrieve the tei results**  
(the tei url    <=> `http://<host>:<port>/<route>?pdf_url=<see previous>`)

The `[output]` section allows the user to set the name of the saved output files.

The `[process]` section contains the service-ncpu parameter (optimal number of simultaneous queries accepted by the service, to adjust in line with the setting on the server machine at grobid-home/config/grobid.properties => org.grobid.max.connections).

Contacts
---------
romain.loth at inist.fr  
istex at inist.fr

© 2014-15 Inist-CNRS (ISTEX)