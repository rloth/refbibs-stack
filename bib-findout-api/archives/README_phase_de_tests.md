BIB-FINDOUT-API
===============
**An ISTEX bibliographical resolver for structured ISTEX-API queries and validated bibref identification.**  

### Phase 1 (actuelle)
Script "test" : prépare une batterie de requêtes de résolution et montre leurs premiers résultats dans l'API
Intérêt : trouver la meilleure requête de résolution


### Usage

```
python3 test_findout.py mes_50.output_bibs.d/ mes_50.resolution.d/
```

### En entrée

L'entrée est toujours un dossier contenant des fichiers TEI avec refbibs:

  - soit en provenance du PDF : fichiers sortis d'un balisage bib-get (testé)
  - soit en provenance des XML natifs : fichiers préparée avec les feuilles MODS2TEI (pas encore testé)

### En sortie 

Pour chaque document en entrée, le script crée dans le dossier de sortie un document `.test_resolution.json`

#### Description du format du json en sortie : 

C'est un tableau d'infos par bibs:

  - chaque bib est renseignée par les champs suivants:
    - `parent_doc` : l'identifiant istex du document source
    - `bib_id` : l'identifiant xml:id de la bib
    - `bib_html` : le xml d'origine de la bib, rendu compatible html
    - `findout_errs` : une liste (souvent vide) de warnings si problèmes rencontrés
    - **`solved_qs`** : le coeur du résultat comme sous-tableau avec chaque test de résolution:
         - champ `lucn_query` : la requête essayée
         - champ `json_answr` : la réponse de l'api (1 hit comme objet json)
  

#### Exemples

Si on veut consulter les infos en ligne de commande, on peut piocher chaque élément facilement avec l'utilitaire `jq`.



```
# tous les id des bibs
jq '.[].bib_id' mondoc.test_resolution.json
  "b0"
  "b1"
  "b2"
  "b3"
  (...)

# le résultat de la requête testée n° [7] pour la bib[29]
jq -r '.[29].solved_qs[7].json_answr' mondoc.test_resolution.json
  {
    "title": "Modeling the effects of ultraviolet radiation on estuarine phytoplankton 
             production: impact of variations in exposure and sensitivity to inhibition",
    "publicationDate": "2001",
    "id": "960D82BA311F26792A83D809A222BFB2EDBE293A",
    "host": {
      "volume": "62",
      "title": "Journal of Photochemistry & Photobiology, B: Biology",
      "pages": {
        "last": "8",
        "first": "1"
      }
    },
    "doi": ["10.1016/S1011-1344(01)00159-2"],
    "corpusName": "elsevier",
    "author": [
      {
        "name": "Patrick J. Neale"
      }
    ]
  }

# ID du doc source de la bib[29]
jq '.[29].parent_doc' mondoc.test_resolution.json
  "A5432A10A0FCD61C74A7224A9183DD077CF09BB1"

# le xml d'origine de la bib[29], rendu compatible html
jq -r '.[29].bib_html' mondoc.test_resolution.json
  <biblStruct xml:id="b29">
   <analytic>
    <author>
     <persName>
      <forename type="first">P</forename>
      <forename type="middle">J</forename>
      <surname>Neale</surname>
     </persName>
    </author>
   </analytic>
   <monogr>
    <title level="j">J. Photochem. Photobiol. B</title>
    <imprint>
     <biblScope unit="volume">62</biblScope>
     <biblScope unit="page" from="1" to="8"></biblScope>
     <date type="published" when="2001"></date>
    </imprint>
   </monogr>
  </biblStruct>


# toutes les requêtes testées pour la bib[29]
jq -r '.[29].solved_qs[].lucn_query'  mondoc.test_resolution.json
  P J Neale J. Photochem. Photobiol. B 62 2001 1 8
  host.volume:"62" AND host.title:"J. Photochem. Photobiol. B" AND 
    author.name:"Neale" AND host.pages.last:"8" AND 
    host.pages.first:"1" AND publicationDate:"2001"
  host.volume:"62" host.title:"J. Photochem. Photobiol. B" author.name:"Neale"
    host.pages.last:"8" host.pages.first:"1" publicationDate:"2001"
  (...)
  host.volume:62 AND publicationDate:2001 AND author.name:Neale AND
    host.pages.last:8 AND host.pages.first:1 AND host.title:(J Photochem Photobiol)
  host.volume:62 AND publicationDate:2001 AND author.name:Neale AND
    host.pages.last:8 AND host.pages.first:1 AND host.title:(journal Photochem* Photobiol*)

# tous les warnings et erreurs éventuelles rencontrés
jq '.[].findout_errs' mondoc.test_resolution.json
  []
  [
    "WARNING: (skip) Refbib = monographie (ne peut exister dans la base)"
  ]
  []
  []
  [
    "ERROR: skip run_queries: 'HTTP Error 400: Bad Request'"
  ]
  []
  []
```

Pour les warnings et erreurs:

  - une liste vide est bon signe, 
  - un **warning n'est pas grave**, il signale juste que la refbib ne remplit pas les prérequis pour la résolution et explique pourquoi.
  - mais une erreur est grave, elle montre que le programme n'a pas su créer une requête valide 
    - c'est très rare
    - ça peut être lié à une incompatibilité de type entre la forme extraite et les formes demandés par l'API, par exemple "Suppl1" extrait pour le fascicule alors que l'API demande uniquement des nombres pour ses champs `host.issue`
    - ou bien à des caractères inhabituels extraits par grobid du pdf et illisibles pour l'API
        - normalement le programme échappe ces caractères avant de les transmettre (cf. les fonctions `prepare_query_frags` et `libconsulte.api.my_url_quoting`)
        - mais parfois il peut y avoir un cas imprévu par ces 2 fonctions

