# Installation de Grobid sur une VP
*romain.loth@inist.fr*  : 15/06/2015

Le script d'installation **`./install_grobid.sh`** est à lancer une fois sur toute nouvelle machine.

Il installe et lance un **[grobid](http://grobid.readthedocs.org/en/latest/)** entraîné particulièrement au balisage de références bibliographiques dans les documents PDF.

Cette application tourne ensuite en mode service REST, qu'on peut interroger sur le port 8080.


## Redirection NAT
Attention ce script *ne gère pas* l'ouverture du port 8080 à faire ou demander séparément par l'installateur, via les règles NAT de VMware.

## Synopsis
En revanche le script gère tout le reste :
   1. l'installation de `maven` et d'une `jdk` (nécessite `sudo`)
   2. la mise en place des variables d'environnement pour le proxy (modification de `.bashrc`)
   3. le téléchargement de [l'archive grobid avec ses patchs istex](https://github.com/rloth/grobid/commits/master)
   4. son installation et compilation maven
   5. le lancement du service


Une fois **grobid** installé, on peut l'interroger de 2 façons pour les refbibs :
  - en fournissant des documents PDF en PJ d'une requête multipart
  
    exemple: `curl $ma_nouvelle_machine:8080/processReferences --form input=@pdf/$mon_chemin_local`

  - ou bien en fournissant en GET une url de document PDF extérieur
    
    exemple: `curl $ma_nouvelle_machine:8080/processReferencesViaUrl?pdf_url=https://api.istex.fr/document/1BF4605DEFB7A48FAEDF56D10E8321F169CBA42F/fulltext/pdf`
