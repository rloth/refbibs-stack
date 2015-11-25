BIB-FINDOUT-API
===============
**An ISTEX bibliographical resolver for structured ISTEX-API queries and validated bibref identification.** 

Installation
-------------

 Prérequis
 
  - un interpréteur `python3`
  - Le package `python3-lxml`
  - Récupérer ce package `git clone https://git.istex.fr/git/loth/refbibs-stack.git`
  - remplacer le lien libconsulte sous `bib-findout-api` par un vrai lien vers le package libconsulte pour les méthodes d'accès API  
  - la mise en place éventuelle de la variable d'environnement http_proxy pour accéder à l'API
  


Usage standard
---------------
**`python3 resolver.py -I mes_TEI_avec_bibs/ -O mes_TEI_enrichies/ > tableau_recap.tsv`**

Description
-------------
Resolver fonctionne autour de 3 étapes clés:

 1. Transformation de chaque tei:biblStruct en une requête structurée lucene
    - fonctions dédiées dans resolver.py:
      - `BiblStruct.bib_subvalues()`
      - `BiblStruct.prepare_query_frags()`
 2. Interrogation de l'API
    - objectif : avoir le plus grand *rappel*, même avec des faux positifs)
    - type de requête lancée : série de fragments champ:(mot1 mot2)
    - fonctions dédiées dans resolver.py:
      - `get_top_match_or_None()`
 3. validation par des règles de comparaison intelligentes
   - objectif : avoir une *précision* parfaite tout en gardant le plus de résultats
   - fonctions dédiées dans resolver.py:
     - `BiblStruct.test_hit()`
       - qui fait des tests sur des infos nécessaires et suffisantes à valider
       - elle utilise pour les abréviations de revues la liste sous `etc/issn_abrevs.tsv`
       - et utilise pour les valeurs texte une fonction de comparaison de 2 chaînes de cara : `soft_compare(str_extrait_PDF, str_réponse_API)`

Entrée/sortie
-------------

L'entrée se fait par un dossier de documents TEI

  - soit issus des xml natifs via MODS2TEI
  - soit issues de l'extraction grobid à partir des PDF

**Quelque soit la provenance, l'essentiel est que les documents TEI contiennent des éléments `/TEI/text/back//biblStruct`.**

Dans l'idéal ils devraient être précisément sous `/TEI/text/back/div/listBibl/biblStruct` et comporter chacun un xml:id.

Le dossier de sortie contiendra les mêmes documents, avec un petit ajout dans chaque bib qui aura pu être résolue:


```
 ...
 <biblStruct>
  <analytic>
   ...
  </analytic>
  <monogr>
   ...
  </monogr>
  <!-- ici ref ajoutée par resolver.py -->
  <ref type="istex-url">
    https://api.istex.fr/document/44F3E0BD4B9D7C39BEC3C43EE65D77CEAE8345E8
  </ref>
 </biblStruct>
 ... 
 (suite du doc)
 
```

Pour plus d'infos
-----------------
Une aide est disponible avec `python3 resolver.py -h`

Concernant la liste des abréviations par revues, cf. aussi doc/infos_revues_abrégées.pdf

Pour la phase 1 de tests sur la constitution de requêtes cf. archive

Contacts
---------
romain.loth at inist.fr  
istex at inist.fr

© 2015 Inist-CNRS (ISTEX)
