BAKO.PY (BIB-ADAPT-CORPUS)
==========================

**An ISTEX corpus manager and CRF model workshop for the [grobid](https://github.com/kermitt2/grobid) bibliographical annotator.**

 1. Creates corpus samples from ISTEX API
 2. Prepares annotated gold and training files for 4 CRF models
     - bibzone (document segmentation)
     - biblines (reference segmentation)
     - bibfields (citation tagging)
     - authornames (names in citation tagging)
 3. Runs **grobid-trainer** on selected samples  
 4. Evaluates CRF models on gold samples

Standard usage
---------------
```
bako make_set       corpus_name  [-s size] [-q specific api query]
bako take_set       corpus_name
bako make_trainers  corpus_name  [-m model  [model2...]]
bako run_training   model_type   [-c corpus_name [corpus_name2...]]
bako eval_model     [-m model_name] [-e evalcorpus_name] [-s] [-g]
```


Required packages
------------------
### general
```
sudo apt-get install python3
sudo apt-get install openjdk-7-jdk
sudo apt-get install libsaxonb-java
sudo apt-get install maven
sudo apt-get install git
```

### for the evaluation script
```
sudo apt-get install libxml-libxml-perl
sudo apt-get install libhtml-html5-entities-perl
sudo apt-get install libalgorithm-combinatorics-perl
```

### specific inist settings
```
echo 'export http_proxy="http://proxyout.inist.fr:8080"' >> ~/.bashrc
echo 'export https_proxy="https://proxyout.inist.fr:8080"' >> ~/.bashrc
```

Directory structure
---------------------
```
bib-adapt-corpus
├── bako.py
├── lib ── (all libs)
├── etc ── dtd_mashup
├── local_conf.ini       
├── corpora  ──── (...)  #  T H R E E
├── models  ───── (...)  #   W O R K
└── evaluations ─ (...)  #   D I R S
```

Config
-------
All parameters are set throught the configuration file **`local_conf.ini`**

**Exemple**

```
[grobid]
GROBID_HOME=/home/loth/refbib/grobid
# for tests
# STOP_ITER=500

[istex-api]
HOST=api.istex.fr
ROUTE=document

[workshop]
HOME=/home/loth/refbib/adapt-dir
CORPUS_HOME=corpora
MODELS_HOME=models
PUB2TEI_XSL=lib/Pub2TEI
CORPUS_DTDS=etc/dtd_mashup

[eval]
CORPUS_NAME=centeval4
SCRIPT_PATH=../eval/eval_xml_refbibs.pl
TABLE_PATH="evaluations/all_evals.tab"
```

Contacts
---------
romain.loth at inist.fr  
istex at inist.fr

© 2014-15 Inist-CNRS (ISTEX)
