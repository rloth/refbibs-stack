BAKO.PY (BIB-ADAPT-CORPUS)
==========================

**Gestionnaire de corpus-échantillons ISTEX et atelier d'entraînement pour le baliseur de références bibliographiques [grobid](https://github.com/kermitt2/grobid) (pour améliorer ses scores par apprentissage automatique sur exemples déjà balisés)**

   1. Crée des "set" ou échantillons de docs depuis l'API ISTEX
   2. Prépare à partir d'un set tous les formats annotés gold et entraînement
   3. Lance **grobid-trainer** sur les formats préparés
   4. Obtient des modèles CRF et évalue s'il sont meilleurs en balisage

Il s'agit de grobid en mode *entraînement*. Pour le mode *balisage* seul utiliser bib-get ou grobid directement. 
L'utilisation de bako est seulement dans le cas où l'on veut modifier les modèles CRF de grobid (par exemple pour améliorer son balisage et l'adapter à de nouveaux profils de documents). Bako permet notamment d'éviter de passer son temps à déplacer les corpus d'entraînement dans grobid et de récupérer les modèles créés, et facilite le test de chaque modèle en isolation sur des corpus faciles à préparer.

Utilisation standard
---------------------
```
bako.py new_workshop
bako.py make_set       corpus_name  [-s size] [-c specific api query]
bako.py take_set       corpus_name
bako.py make_trainers  corpus_name  [-m model  [model2...]]
bako.py run_training   model_type   [-c corpus_name [corpus_name2...]]
bako.py eval_model     [-m model_name] [-e evalcorpus_name] [-s] [-g]
```

Principes d'utilisation
========================

L'objectif
-----------
Adapter grobid et bib-get à de nouveaux profils de documents.

Ce package *bib-adapt-corpus* tente de proposer un atelier clés-en-main de génération de modèles par apprentissage automatique à partir :

   - d'échantillonage dans les corpus ISTEX (commande **make_set**)
   - de pré-traitements créant des fichiers spécifiques pour grobid-trainer (commande **make_trainers**)
   - de gestion des appels et sorties de grobid-trainer via un modelstore (commande **run_training**)
   - de suivi et d'évaluation de chaque modèle dans une tâche de balisage normal PDF => refbibs (commande **eval_model**)

Le dossier corpora
------------------
Le dossier `CORPUS_HOME` (par défaut `corpora`) contiendra les corpus de travail (échantillons).

On va créer ces corpus de travail à partir de la commande make_set qui fait un échantillonage de documents de l'API.
On peut aussi reprendre des corpus précédents créés de la même manière.

Ils auront une forme commune pour toutes les étapes  

   - étapes <=> sous-dossiers dans `mon_corpus/data`  
   - métadonnées communes dans `mon_corpus/meta`  
   - exploration humaine facilitée  
   - possibilité d'intercaler des traitements auto et/ou manuels (filtrage, correction)  

NB: Les fonctionnalités d'échantillonage/conversion/rangement sont disponibles de façon autonome comme [outils de consultation communs à différentes tâches ISTEX-RD](https://git.istex.fr/loth/libconsulte).


Les types de modèles
----------------------

Il y a dans le balisage grobid l'intervention de 4 baliseurs en cascade :  

  - **bibzone** (segmentation du document)
    (nom d'origine dans grobid: *segmentation*)  
  - **biblines** (segmentation de la zone biblio en items)
    (nom d'origine dans grobid: *reference-segmenter*)  
  - **bibfields** (étiquetage des champs dans une ref. biblio.)  
    (nom d'origine dans grobid: *citations*)  
  - **authornames** (balisage nom/prénoms dans les listes d'auteurs)  
    (nom d'origine dans grobid: *names_citation*)  

Ces 4 baliseurs peuvent chacun être entraînés => il y a donc 4 types de modèles, avec pour chacun deux ou trois types de fichiers d'entraînement alignés à préparer.

Ces cascades à modèles différents sont décrites par Patrice Lopez dans [la documentation d'entraînement de grobid](grobid.readthedocs.org/en/latest/Training-the-models-of-Grobid/).


Installation
=============

Paquets requis
---------------
### général (pour le script ou pour grobid)
```
sudo apt-get install python3
sudo apt-get install openjdk-7-jdk     # ou une version > 7
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

### réglages de proxy quand on est à l'INIST
```
echo 'export http_proxy="http://proxyout.inist.fr:8080"' >> ~/.bashrc
echo 'export https_proxy="https://proxyout.inist.fr:8080"' >> ~/.bashrc
```

### ajout au PATH
(optionnel mais utile pour lancer de n'importe où en écrivant juste `bako.py mescommandes` au lieu de `python3 dossier/ou/j/ai/mis/bib-adapt-corpus/bako.py mescommandes`!)  

```
cd dossier/ou/j/ai/mis/bib-adapt-corpus
echo -e "export PATH=$PWD:\$PATH" >> ~/.bashrc
```

### Installer grobid !
Il y a deux sources d'installations possibles de grobid.

 1. *Conseillé*: Pour repartir de la version en production à l'API Istex (début 2016), il faut utiliser le lien [http://github.com/rloth/grobid].  
    Dans ce cas on peut utiliser le script `install_grobid.sh` sous [bib-install-vp](https://git.istex.fr/loth/refbibs-stack/tree/master/bib-install-vp)

 2. *Avancé*: On peut aussi utiliser (la version actuelle de grobid)[http://github.com/kermitt2/grobid]. Cette version est plus récente, mais elle ne contient pas les modèles entraînés par istexRD2015. Cela peut être utile si on veut créer une nouvelle version de production.

Pour les 2, on peut télécharger un zip du master git ou faire une commande `git clone`

Dans tous les cas, on peut mettre le dossier grobid où l'on veut.
Parmi les commandes du script install_grobid, la plus importante est la compilation grobid (pour obtenir l'application cible `grobid-core/target/grobid-core-...-SNAPSHOT.one-jar.jar`.

Il n'est pas nécessaire de lancer le service grobid à la fin.

### Indiquer le chemin de grobid à bako
 1. ouvrir `bako_config.ini` dans un éditeur texte
 2. changer la variable `GROBID_DIR` pour mettre le chemin du grobid qu'on a installé

### Créer un nouveau dossier de travail

On crée juste un nouveau dossier vide où l'on veut.

```
mkdir mon/nouveau/dossier/de/travail
```

Et on indique aussi ce dossier dans la config
 1. ouvrir `bako_config.ini` dans un éditeur texte
 2. changer la variable `HOME` pour mettre le chemin du grobid qu'on a installé


### Pour installer un nouveau dossier projet

On doit créer ce nouveau dossier de travail (`mkdir`) puis le plus simple est d'utiliser les commandes bako.py new_workshop ci-dessous.

Cela créera 3 sous-dossiers `corpora`, `modelstore` et `evaluations`
Ensuite elle vont copier les modèles d'origine de notre installation grobid (sous GROBID_DIR) dans `modelstore`.
Puis elle vont échantillonner et télécharger un premier corpus d'évaluation via l'API ISTEX.
Enfin elle vont lancer une première évaluation, qui servira de baseline pour comparer la qualité des refbibs obtenues quand on créera des modèles ré-entraînés.

```
cd mon/nouveau/dossier/de/travail
bako.py new_workshop --dirs
bako.py new_workshop --import_models
bako.py new_workshop --make_eval_set
bako.py new_workshop --baseline
```

Si il y a eu un problème ou qu'on veut changer de corpus d'évaluation, chacune de ces 4 étapes peut être relancée à part ultérieurement.

Pour `bako.py new_workshop --import_models`, si les modèles importés ont déjà un nom dans grobid.properties, il sera repris dans le modelstore, et sinon on mettra le mot "vanilla".

Configuration
--------------
Tous les paramètres de bib-adapt-corpus sont dans **`bako_config.ini`**

Parmi ces paramètres, il y en a 3 que l'utilisateur doit modifier régulièrement:

**les 3 paramètres les plus importants**

```
[grobid]
GROBID_HOME=/mon/chemin/vers/grobid

[workshop]
HOME=/mon/nouveau/dossier/de/travail

[eval]
CORPUS_NAME=nom_du_corpus_eval_choisi
```


Déroulement des entraînements
==============================

`run_training`
--------------

La commande `bako.py run_training` constitue le coeur du travail.

*Concrètement il suffit de la lancer avec le plus de corpus préparés possible, de regarder les itérations du CRF défiler et de revenir après quelques heures pour constater qu'un nouveau modèle est apparu dans le dossier `modelstore`.*

Pour info, voilà ce qui se passe "sous le capot" durant la commande:  

  1. Elle met temporairement les corpus choisis dans l'endroit attendu par grobid pour ses corpus d'entraînement.
     (c'est-à-dire `GROBID_DIR/grobid-trainer/resources/dataset/<NOM_MODELE>/corpus`)
  2. Ensuite elle lance un sous-processus `mvn generate-resources -P train_<NOM_MODELE> -e` dans le dossier `GROBID_DIR/grobid-trainer`.
     La première fois, ce processus peut prendre jusqu'à 2 minutes pour se lancer, si maven cherche à télécharger des dépendances.
     En général, il se lance immédiatement
  3. On voit alors les itérations du CRF qui défilent (prend jusqu'à 20h, mais plutôt autour de 2 ou 3h)
     (cf. copie d'affichage ci-dessous)
  4. A la fin de l'entraînement, grobid enregistre le modèle sous `GROBID_DIR/grobid-home/models/<NOM_MODELE>/model.wapiti`
     Puis notre fonction libtrainers.grobid_models.CRFModel.pick_n_store va recopier le modèle et les logs de sa création dans le dossier `modelstore` et rétablir l'état d'origine du dossier `GROBID_DIR`



A l'étape 3, voilà l'affichage qu'on peut lire par exemple pour un entraînement *bibzone*:

```
=======  mon_corpus  =======
.rawinfos << /mon/nouveau/dossier/de/travail/corpora/mon_corpus/meta/infos.tab
.cols:
  ├──['pub_year'] --> ['1941', '1980', '1991']..
  ├──['title']    --> ['OPERATION ..', 'The modern..', 'Flavimonas..']..
  └──['pub_period', 'pdfwc', 'bibnat', 'lang', 'corpus', 'pdfver', 'cat_sci', 'doctype_1', 'istex_id', 'author_1'] --> ...
======= CORPUSDIRS  [essai_10]  =======
  >  ON  --- A-pdfs
  >  ON  --- B-xmlnatifs
  >  ON  --- C-goldxmltei
  >  ON  --- D.1.a-trainers-bibzone_rawtxt
  >  ON  --- D.1.b-trainers-bibzone_rawtok
  >  ON  --- D.1.z-trainers-bibzone_tei

=====( SIZE: 10 docs x 6 format-shelfs )=====

---( corpus essai_10 : étagère BZRTK )---
 => 10 documents liés
---( corpus essai_10 : étagère BZTEI )---
 => 10 documents liés
training new model bibzone-GBv0.3.4-essai_10-2
Lancement ENTRAINEMENT
(commande:mvn generate-resources -P train_segmentation -e)
* Load patterns
* Load training data
* Initialize the model
* Summary
    nb train:    10        <= nb de documents
    nb labels:   4         <= nb d'étiquettes différentes à prédire
    nb blocks:   51258     <= instances à classer
    nb features: 205044    <= indices utilisés pour classer
* Train the model with l-bfgs
  [   1] obj=1064,16    act=74412    err= 3,40%/100,00% time=0,09s/0,09s
  [   2] obj=1006,60    act=39616    err= 3,40%/100,00% time=0,06s/0,15s
  [   3] obj=640,03     act=8800     err= 3,40%/100,00% time=0,06s/0,21s
  [   4] obj=499,63     act=9539     err= 3,25%/90,00% time=0,16s/0,37s
  [   5] obj=429,63     act=9912     err= 3,12%/80,00% time=0,08s/0,45s
  ...
  ...       (quelques heures)
  ...
  [36000] obj=94,63     act=127     err= 0.00%/3,02% time=8024s/0,45s
  ^^^^^^^                  ^^^^^^          ^^^^^^^           ^^^^^^
n° d'itération           nb de règles     taux d'erreur    temps écoulé total/dernière itération
             ^^^^^^^^
       valeur de la fonction
    "objectif" que l'entraînement
      wapiti veut faire baisser
```

*Remarque si interruption du traitement*
Si on interrompt le traitement avant la fin, les liens du corpus testé
vont rester dans le dossier des corpus d'entraînement de grobid au lieu
de ceux qui s'y trouvent dans le dépôt normal.

Si jamais ça arrive, pour les restaurer il suffit de faire:

```
rm -rf DOSSIER_GROBID/grobid-trainer/resources/dataset/segmentation/corpus  
mv DOSSIER_GROBID/grobid-trainer/resources/dataset/segmentation/corpus.bak DOSSIER_GROBID/grobid-trainer/resources/dataset/segmentation/corpus
```

Et pour restaurer le modèle d'avant entraînement:

```
mv grobid-home/models/segmentation/model.wapiti.old grobid-home/models/segmentation/model.wapiti
```


Concernant les évaluations
--------------------------

L'évaluation d'un modèle se lance par `bako.py eval_model`.

Une évaluation revient à lancer un balisage sur l'étagère PDF avec le modèle évalué et de comparer la sortie avec l'étagère des TEI golds obtenus par conversion des refbibs natives. Cela donne un score de rappel et précision. 

Il ne vaut mieux pas entraîner et évaluer sur le même corpus, cela donnerait des résultats complètement biaisés...
Le nom du corpus d'évaluation par défaut peut être changé dans le fichier `bako_config.ini` dans `CORPUS_NAME` sous la section `[eval]`.

Après le balisage test, l'évaluation proprement dite sera effectuée par un script perl extérieur à bako appelé eval_xml_refbibs.pl. Si on a installé toute la refbib-stack, il se trouve normalement dans `refbib-stack/bib-eval/eval_xml_refbibs.pl`.

Il y a aussi un fichier de rapports d'éval automatiques enregistré dans HOME. A chaque évaluation, il sera mis à jour par le script. Il contient une ligne par évaluation avec le nombre de documents, le nombre de refbibs, les scores obtenus et un identifiant 'nom_du_corpus_eval_choisi--nom_du_modèle_évalué'.

Par exemple:

```
NDOCS	nbibs_gold	Rappel	Précision	EVAL_ID
200	 4232	58.3	61.5	minieval-BASELINE-GBv0_3_4_avec_vanilla
200	 4232	62.2	64.1	minieval-biblines-GBv0.3.4-srca.srcb-42
```



Arborescences obtenues
======================

Installation
-------------
**Dossier où l'on installe bako.py (et à ajouter au PATH)**

```
bib-adapt-corpus
├── bako.py
├── libconsulte ── # pour les liens à l'API, l'échantillonnage, le stockage/conversion des formats
├── libtrainers ── # pour les formats spécifiques à l'entraînement, les runs d'entraînement et le modelstore
└── bako_config.ini
```


Dossier grobid
--------------

**Lieu d'installation de grobid (à choisir n'importe où et renseigner dans `bako_config.grobid.GROBID_DIR`)**

```
/mon/installation/grobid
   ├── grobid-core  ───── (...)  #  (contient l'appli java et le jar)
   ├── grobid-home  ───── (...)  #  (contient les modèles et propriétés)
   ├── grobid-trainer  ── (...)  #  (contient les corpus d'entraînement)
   └── grobid-service ─── (...)  #  N E    S E R T    P A S    I C I
```

Travail
--------

**Dossier de travail (à choisir n'importe où et renseigner dans `bako_config.workshop.HOME`**)

```
/mon/nouveau/dossier/de/travail
   ├── corpora  ──── (...)  #  L E S    T R O I S
   ├── models  ───── (...)  #  S O U S  -  D O S S I E R S
   └── evaluations ─ (...)  #  D E    T R A V A I L
```


**Structure d'un corpus de 5 docs dans corpora**

```
corpora/mon_corpus/
   ├── data
   │   ├── A-pdfs
   │   │   ├── els-BD881D3F098A64F3EC19F69BB874B535DD54E63D.pdf
   │   │   ├── els-C71674F4C0CC54423F9773ACACA9F6B407345546.pdf
   │   │   ├── oup-310F2D4E822645C1CDCBD3B72C1D2512FFA27A63.pdf
   │   │   ├── wil-75CAE2ADF845BBF006AFFB989A62E777194596F9.pdf
   │   │   └── wil-F50350EE6E30A7EE442F60112B9EEE5BE4FE235A.pdf
   │   ├── B-xmlnatifs
   │   │   ├── els-BD881D3F098A64F3EC19F69BB874B535DD54E63D.xml
   │   │   ├── els-C71674F4C0CC54423F9773ACACA9F6B407345546.xml
   │   │   ├── oup-310F2D4E822645C1CDCBD3B72C1D2512FFA27A63.xml
   │   │   ├── wil-75CAE2ADF845BBF006AFFB989A62E777194596F9.xml
   │   │   └── wil-F50350EE6E30A7EE442F60112B9EEE5BE4FE235A.xml
   │   ├── C-goldxmltei
   │   │   ├── els-BD881D3F098A64F3EC19F69BB874B535DD54E63D.tei.xml
   │   │   ├── els-C71674F4C0CC54423F9773ACACA9F6B407345546.tei.xml
   │   │   ├── oup-310F2D4E822645C1CDCBD3B72C1D2512FFA27A63.tei.xml
   │   │   ├── wil-75CAE2ADF845BBF006AFFB989A62E777194596F9.tei.xml
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


Structure du modelstore  
--------------------------

Le dossier `modelstore` contiendra un dossier par modèle, avec des noms comme `bibfields-modele27` et avec à l'interieur les logs de sa création, le modèle lui-même (rangé suivant exactement les mêmes sous-dossiers que si il résidait dans grobid-home/models).

```
modelstore/
├── models_situation.json        # relevé des modèles actifs 
│                                # et modèles originaux importés
│
├── biblines-vanilla # ici un modèle original (importé depuis grobid)
│   ├── log
│   │   └── vanilla.import.log
│   ├── model
│   │   └── reference-segmenter
│   │       └── model.wapiti     # <= le fichier CRF modèle proprement dit
│   └── recipy.json
│
└── biblines-GBv0.3.4-srca.srcb-42    # nom d'un modèle entraîné sur 2 corpus srca et srcb
    ├── log
    │   ├── training.crf.log
    │   └── training.mvn.log
    ├── model
    │   └── reference-segmenter
    │       └── model.wapiti     # <= le fichier CRF modèle proprement dit
    └── recipy.json
```

Pour chaque modèle, un fichier `recipy.json` contiendra toujours les infos du grobid source et des éventuels corpus sources. À la racine du store, un fichier `models_situation.json` assure en plus la persistance des infos pour l'ensemble des modèles (relevé des modèles actifs et des modèles d'origine).

*Un modèle est considéré comme actif si le ou les sous-dossiers sous model/ sont copiés ou symlinkés dans le dossier grobid/grobid-home/models (il est alors utilisé par grobid pour tout balisage)*

Contacts
---------
romain.loth at inist.fr  
romain.loth at iscpif.fr  
istex at inist.fr  
rd-team at listes.istex.fr  

© 2014-16 Inist-CNRS (ISTEX)
