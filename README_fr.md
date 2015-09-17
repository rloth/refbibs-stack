BIB-GET.PY
==========
**Un client ISTEX pour interroger *grobid-service*, l'annotateur de références bibliographiques.**  

Installation
-------------

 1. Prérequis : 
    - un interpréteur `python3`  
    - un `grobid-service` fonctionnel (cf. [le script d'installation  **bib-install-vp**](https://git.istex.fr/loth/refbibs-stack/blob/master/bib-install-vp/install_grobid.sh "install_grobid.sh"))
    - un paramétrage correct des proxy et des autorisations permettant d'accéder à l'api.istex.fr et au serveur grobid.
 2. Récupérer le package bib-get courant en faisant au choix:
    - `git clone https://git.istex.fr/git/loth/bib-get.git`
    - ou récupérer [l'archive ZIP d'installation](https://git.istex.fr/loth/bib-get/archive/master.zip) et l'extraire dans le dossier où l'on voudra travailler

C'est tout! On peut lancer le script sur 5 documents pour faire un petit test: `python3 bib-get.py -q "agile" --maxi 5`


Utilisation standard
---------------------
**`python3 bib-get.py -q 'corpusName:mon_corpus' [--group_output]`**  

Déroulement du traitement
--------------------------
 1. La requête -q est envoyée à l'API ISTEX  
 2. Le client récupère la liste des documents correspondants  
 3. Il fournit chaque document (sous sa forme pdf) au serveur de production de  _grobid_  pour:  
     - pré-conversion du pdf en texte  
     - identification en cascade de la zone des biblios, de chaque biblio et de chaque champ qu'elle contient  
         -> appels à l'étiqueteur CRF wapiti et aux modèles bibzone, biblines et bibfields
     - sortie en TEI XML  
 4. Enregistre les fichiers TEI XML comportant les bibliographies extraites  
 5. Optionnel : groupe les fichiers TEI en un grand fichier teiCorpus (pour enrichissement API)

Fichiers résultats
--------------------
bib-get crée un dossier pour les résultats nommé:  
**<timestamp>-output_bibs.dir**

En mode "group_output", le dossier est aussi créé, puis après le traitement tous les fichiers sont regroupés dans un fichier teiCorpus nommé:  
**<timestamp>-output_bibs.teiCorpus.xml**

(Ces noms peuvent être changés dans le fichier de configuration)

Les <timestamp> sont de la forme : YYYY-MM-DD_HHhmm

Utilisation détaillée
-----------------------
`python3 bib-get.py -q 'any lucene query' [--maxi 100] [--group_output]`  
`python3 bib-get.py --list_in some_ID_list.txt [--group_output]`  
`python3 bib-get.py --print_config`  

### Options
 - **`-h`** or **`--help`**  
   affiche un message d'aide
 - **`-q`** `"corpusName:nature AND publicationDate:[1970 TO *] AND genre:article"`  
   mode d'entrée "normal" par requête lucene: déclenche l'extraction des biblios pour tous les documents correspondant à cette requête dans l'API
 -  **`-l`** `some_ID_list.txt`  ou   **`--list_in`** `some_ID_list.txt`  
   mode d'entrée "preparé": débute directement avec une liste d'identifiants ISTEX des documents à traiter
 -  **`-g`**   ou   **`--group_output`**
   sortie "teiCorpus" optionnelle: groupe chaque fichier TEI individuel dans un grand fichier teiCorpus à la fin du traitement (utile pour l'enrichissement de l'API)
 - **`-m`** `10000` or **`--maxi`** `10000`    
   limite maxi optionnelle du nombre de documents traités (si la requête renvoie plus de résultats, les suivants seront ignorés)
 - **`-c`** `fichier/de/config.ini` or **`--config`** `fichier/de/config.ini`    
   option permettant de specifié un chemin alternatif vers le fichier de config (par défaut, il est pris dans : `<script_dir>/bib-get.ini`)
 - **`-p`** or **`--print_config`**    
   affiche seulement le ficher de configuration et quitte


Pour plus d'informations sur la syntaxe des requêtes lucene, se reporter à la [page de documentation correspondante de l'API](https://api.istex.fr/documentation/300-search.html#syntaxe-des-requetes).


Configuration avancée
----------------------
Les paramètres peuvent être fixés via le petit fichier de configuration **`bib-get.ini`**

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
# if grouped output
corpusfile=output_bibs.teiCorpus.xml

[process]
# max = ncpu of grobid-service
ncpu=9

```

La section `[istex-api]` permet au client **d'accéder aux PDF sources**  
(l'url PDF obtenue sera: `https://<host>/<route>/<istex-id>/fulltext/pdf`)

La section `[grobid-service]` permet au client **de récupérer les résultats TEI**  
(l'url TEI interrogée sera: `http://<host>:<port>/<route>?pdf_url=<cf précédent>`)

La section `[output]` permet à l'utilisateur de changer le nom des fichiers sauvegardés en sortie.

La section `[process]` contient le paramètre ncpu (nombre de requêtes simultanées envoyées par le client).

Contacts
---------
romain.loth at inist.fr  
istex at inist.fr

© 2014-15 Inist-CNRS (ISTEX)
