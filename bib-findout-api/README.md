BIB-FINDOUT-API
===============
**An ISTEX bibliographical resolver for structured ISTEX-API queries and validated bibref identification.**  

### Phase 1 (actuelle)
Script "test" : prépare une batterie de requêtes de résolution et montre leurs premiers résultats dans l'API
Intérêt : trouver la meilleure requête de résolution


### Usage

```
python3 test_findout.py mes_50.output_bibs.d/ > recette.json
```

### La sortie 

#### Description du format du json en sortie : 

  - tableau d'infos par bibs
  - chaque info contient les champs suivants:
    - `parent_doc` : l'identifiant istex du document source
    - `bib_id` : l'identifiant xml:id de la bib
    - `bib_html` : le xml d'origine de la bib, rendu compatible html
    - `findout_errs` : une liste (souvent vide) de warnings si problèmes rencontrés
    - `solved_qs` : le coeur du résultat avec
      - un nouveau tableau : n tests de résolution (plusieurs méthodes essayées), soit n x 2 champs
         - champ `lucn_query` : la requête envoyée
         - champ `json_answr` : la réponse de l'api (1 hit comme objet json)
  

#### Exemples


```
# ID du doc source de la bib[3]
jq '.[3].parent_doc' recette.json
  "1A40CCA0EEB4D02A02F90A138D1F46467D971309"

# le xml d'origine de la bib[3] rendu compatible html
jq '.[3].bib_html' recette.json 
  "<biblStruct xml:id=\"b3\">\n <analytic>\n  <title></title>\n </analytic>\n <monogr>\n  <title level=\"m\">Water Deficits and Plant Growth</title>\n  <editor>T. T. KOZLOWSKI</editor>\n  <meeting><address><addrLine>New York, London</addrLine></address></meeting>\n  <imprint>\n   <publisher>Academic Press</publisher>\n   <date type=\"published\" when=\"1968\"></date>\n   <biblScope unit=\"page\" from=\"85\" to=\"133\"></biblScope>\n  </imprint>\n </monogr>\n</biblStruct>\n\n"


# tous les ID des docs source
jq '.[].parent_doc' recette.json 
  "1A40CCA0EEB4D02A02F90A138D1F46467D971309"
  "1A40CCA0EEB4D02A02F90A138D1F46467D971309"
  "1A40CCA0EEB4D02A02F90A138D1F46467D971309"
  "1A40CCA0EEB4D02A02F90A138D1F46467D971309"


# tous les id des bibs
jq '.[].bib_id' recette.json 
  "b0"
  "b1"
  "b2"
  "b3"

# toutes les requêtes testées pour la bib[3]
jq '.[3].solved_qs[].lucn_query' recette.json
  "Water Deficits and Plant Growth T. T. KOZLOWSKI New York, London Academic Press 1968 85 133"
  "\"New York, London\" AND publicationDate:\"1968\" AND host.pages.first:\"85\" AND host.editor:\"Academic Press\" AND host.editor:\"T. T. KOZLOWSKI\" AND host.pages.last:\"133\" AND host.title:\"Water Deficits and Plant Growth\""
  "\"New York, London\" publicationDate:\"1968\" host.pages.first:\"85\" host.editor:\"Academic Press\" host.editor:\"T. T. KOZLOWSKI\" host.pages.last:\"133\" host.title:\"Water Deficits and Plant Growth\""
  "York London publicationDate:1968 host.pages.first:85 host.editor:(Academic Press KOZLOWSKI) host.pages.last:133 host.title:(Water Deficits and Plant Growth)"
  "(publicationDate:1968) AND (York London host.pages.first:85 host.editor:(Academic Press KOZLOWSKI) host.pages.last:133 host.title:(Water Deficits and Plant Growth))"
  "(publicationDate:1968) AND (York London host.pages.first:85 host.editor:(Academic Press KOZLOWSKI) host.pages.last:133 host.title:(Water* Deficits* and* Plant* Growth*))"
  "York AND London AND publicationDate:1968 AND host.pages.first:85 AND host.editor:(Academic Press KOZLOWSKI) AND host.pages.last:133 AND host.title:(Water Deficits and Plant Growth)"
  "York AND London AND publicationDate:1968 AND host.pages.first:85 AND host.editor:(Academic Press KOZLOWSKI) AND host.pages.last:133 AND host.title:(Water* Deficits* and* Plant* Growth*)


# le résultat de la requête[0] pour la bib[3]
jq '.[3].solved_qs[0].json_answr' recette.json 
{
  "author": [
    {
      "name": "T. T. Kozlowski"
    }
  ],
  "corpusName": "springer",
  "id": "BB92A134FD1FD10092C7EEA177A6A534626AB294",
  "doi": [
    "10.1007/BF02858600"
  ],
  "host": {
    "pages": {
      "first": "107",
      "last": "222"
    },
    "title": "The Botanical Review",
    "volume": "58"
  },
  "title": "Carbohydrate sources and sinks in woody plants"
}
```