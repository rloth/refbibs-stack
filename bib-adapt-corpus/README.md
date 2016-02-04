BAKO.PY (BIB-ADAPT-CORPUS)
==========================

**Gestionnaire de corpus-échantillons ISTEX et atelier d'entraînement pour le baliseur de références bibliographiques [grobid](https://github.com/kermitt2/grobid) (pour améliorer ses scores par apprentissage automatique sur exemples déjà balisés)**

   1. Crée des "set" ou échantillons de docs depuis l'API ISTEX
   2. Prépare à partir d'un set tous les formats annotés gold et entraînement
   3. Lance **grobid-trainer** sur les formats préparés
   4. Obtient des modèles CRF meilleurs et les évalue

Utilisation standard
---------------------
```
bako make_set       corpus_name  [-s size] [-c specific api query]
bako take_set       corpus_name
bako make_trainers  corpus_name  [-m model  [model2...]]
bako run_training   model_type   [-c corpus_name [corpus_name2...]]
bako eval_model     [-m model_name] [-e evalcorpus_name] [-s] [-g]
```

Principes d'utilisation
========================

L'objectif
-----------
Adapter grobid et bib-get à de nouveaux profils de documents

Ce package *bib-adapt-corpus* permet cela en proposant un atelier clés-en-main de génération de modèles par apprentissage automatique à partir  

   - d'échantillonage dans les corpus ISTEX 
   - de pré-traitements créant des fichiers spécifiques pour grobid-trainer
   - de gestion des appels et sorties de grobid-trainer via un modelstore
   - de suivi et d'évaluation de chaque modèle dans une tâche de balisage normal PDF => refbibs

Le dossier corpora
------------------
Le dossier `CORPUS_HOME` (par défaut `corpora`) contient les corpus de travail (échantillons).

Ils ont une forme commune pour toutes les étapes  

   - étapes <=> sous-dossiers dans `mon_corpus/data`  
   - métadonnées communes dans `mon_corpus/meta`  
   - exploration humaine facilitée  
   - possibilité d'intercaler des traitements auto et/ou manuels (filtrage, correction)  


NB: Ces fonctionnalités d'échantillonage/conversion/rangement sont disponibles de façon autonome comme [outils de consultation communs à différentes tâches ISTEX-RD](https://git.istex.fr/loth/libconsulte).


Les types de modèles
----------------------

Il y a dans le balisage grobid l'intervention de 4 baliseurs en cascade :  

  - **bibzone** (segmentation du document)
    (aka *segmentation*)  
  - **biblines** (segmentation de la zone biblio en items)
    (aka *reference-segmenter*)  
  - **bibfields** (étiquetage des champs dans une ref. biblio.)  
    (aka *citations*)  
  - **authornames** (balisage nom/prénoms dans les listes d'auteurs)  
    (aka *names_citation*)  

Ces 4 baliseurs peuvent chacun être entraînés => il y a donc 4 types de modèles, avec pour chacun deux ou trois types de fichiers d'entraînement alignés à préparer.

Ces cascades à modèles différents sont décrites par Patrice Lopez dans [la documentation d'entraînement de grobid](grobid.readthedocs.org/en/latest/Training-the-models-of-Grobid/).


Installation
=============

Paquets requis
---------------
### général (pour le script ou pour grobid)
```
sudo apt-get install python3
sudo apt-get install openjdk-7-jdk
sudo apt-get install libsaxonb-java
sudo apt-get install maven
sudo apt-get install git
```

### pour le suivis d'évaluations seulement
```
sudo apt-get install libxml-libxml-perl
sudo apt-get install libhtml-html5-entities-perl
sudo apt-get install libalgorithm-combinatorics-perl
sudo apt-get install r-base
```

### réglages de proxy de l'INIST
```
echo 'export http_proxy="http://proxyout.inist.fr:8080"' >> ~/.bashrc
echo 'export https_proxy="https://proxyout.inist.fr:8080"' >> ~/.bashrc
```

### ajout au PATH
(optionnel mais utile !)  

```
cd dossier/ou/j/ai/mis/bib-adapt-corpus
echo -e "export PATH=$PWD:\$PATH" >> ~/.bashrc
```

### Pour installer un nouveau projet dans un dossier

Créera 3 dossiers `corpora`, `modelstore` et `evaluations`

```
cd mon/nouveau/dossier/de/travail
bako.py new_workshop
```

Configuration
--------------
All parameters are set throught the configuration file **`local_conf.ini`**

**Minimal exemple**

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


Arborescences obtenues
======================

Installation
-------------
**Dossier où l'on installe bako.py (à ajouter au PATH)**

```
bib-adapt-corpus
├── bako.py
├── libconsulte ── # pour les liens à l'API, l'échantillonnage, le stockage/conversion des formats
├── libtrainers ── # pour les formats spécifiques à l'entraînement, les runs d'entraînement et le modelstore
└── bako_config.ini
```


Travail
--------

**Dossier de travail (à choisir n'importe où)**

```
my_workshop
├── corpora  ──── (...)  #  T R O I S
├── models  ───── (...)  #  D O S S I E R S
└── evaluations ─ (...)  #  D E    T R A V A I L
```

**Structure d'un corpus de 6 docs dans corpora**

```
corpora/mon_corpus/
   ├── data
   │   ├── A-pdfs
   │   │   ├── els-BD881D3F098A64F3EC19F69BB874B535DD54E63D.pdf
   │   │   ├── els-C71674F4C0CC54423F9773ACACA9F6B407345546.pdf
   │   │   ├── oup-310F2D4E822645C1CDCBD3B72C1D2512FFA27A63.pdf
   │   │   ├── wil-75CAE2ADF845BBF006AFFB989A62E777194596F9.pdf
   │   │   ├── wil-E9646538FA913983C399657F26593815B7930B5F.pdf
   │   │   └── wil-F50350EE6E30A7EE442F60112B9EEE5BE4FE235A.pdf
   │   ├── B-xmlnatifs
   │   │   ├── els-BD881D3F098A64F3EC19F69BB874B535DD54E63D.xml
   │   │   ├── els-C71674F4C0CC54423F9773ACACA9F6B407345546.xml
   │   │   ├── oup-310F2D4E822645C1CDCBD3B72C1D2512FFA27A63.xml
   │   │   ├── wil-75CAE2ADF845BBF006AFFB989A62E777194596F9.xml
   │   │   ├── wil-E9646538FA913983C399657F26593815B7930B5F.xml
   │   │   └── wil-F50350EE6E30A7EE442F60112B9EEE5BE4FE235A.xml
   │   ├── C-goldxmltei
   │   │   ├── els-BD881D3F098A64F3EC19F69BB874B535DD54E63D.tei.xml
   │   │   ├── els-C71674F4C0CC54423F9773ACACA9F6B407345546.tei.xml
   │   │   ├── oup-310F2D4E822645C1CDCBD3B72C1D2512FFA27A63.tei.xml
   │   │   ├── wil-75CAE2ADF845BBF006AFFB989A62E777194596F9.tei.xml
   │   │   ├── wil-E9646538FA913983C399657F26593815B7930B5F.tei.xml
   │   │   └── wil-F50350EE6E30A7EE442F60112B9EEE5BE4FE235A.tei.xml
   │   ├── format suivant
   │   │   ├── etc.
   │   │   └── etc.
   │   └── format suivant
   │       ├── etc.
   │       └── etc.
   └── meta
      ├── infos.tab          # tableau TSV résumé (date, titre, auteur 1, ID,  corpus...)
      ├── corpus_type.txt     # type de corpus (gold ou à sous-dossiers supplémentaires)
      ├── basenames.ls         # liste des noms de fichiers
      ├── shelves_map.json      # liste des sous-dossiers possibles ("étagères")
      └── shelf_triggers.json    # liste des sous-dossiers remplis
```


**Structure du modelstore**  


```
modelstore/
├── models_situation.json        # relevé des modèles actifs 
│                                # et modèles originaux importés
│
├── biblines-vanilla # ici un modèle original (importé depuis grobid)
│   ├── log
│   │   └── vanilla.import.log
│   ├── model
│   │   └── name
│   │       └── citation
│   │           └── model.wapiti # <= le fichier CRF modèle proprement dit
│   └── recipy.json
│
│
└── biblines-srca_srcb-42  # ici modèle entraîné sur 2 corpus srca et srcb
    ├── log
    │   ├── training.crf.log
    │   └── training.mvn.log
    ├── model
    │   └── reference-segmenter
    │       └── model.wapiti     # <= le fichier CRF modèle proprement dit
    └── recipy.json
```

Pour chaque modèle, un fichier `recipy.json` contiendra toujours les infos du grobid source et des éventuels corpus sources. À la racine du store, un fichier `models_situation.json` assure en plus la persistance des infos pour l'ensemble des modèles (relevé des modèles actifs et des modèles d'origine).

Un modèle est considéré comme actif si le ou les sous-dossiers sous model/ sont copiés ou symlinkés dans le dossier grobid/grobid-home/models (il est alors utilisé pour tout balisage)

**Concernant les évaluations**
Une évaluation revient à lancer un balisage sur l'étagère PDF avec le modèle évalué et de comparer la sortie avec l'étagère des TEI golds obtenus par conversion des refbibs natives. Cela donne un score de rappel et précision. Il ne vaut mieux pas entraîner et évaluer sur le même corpus, cela donnerait des résultats complètement biaisés...


Contacts
---------
romain.loth at inist.fr  
istex at inist.fr

© 2014-15 Inist-CNRS (ISTEX)
