refbibs_stack
===============

### Synopsis

**Ce dépôt regroupe tous les scripts pour installer/entraîner/utiliser grobid avec les PDF de l'API ISTEX.**  

  - En utilisation "quotidienne", intégrée à une chaîne de production
    * **`bib-install-vp`** pour installer sur un serveur de production une version adaptée à nos besoins.
    * **`bib-get`** pour obtenir des bibs structurées
    * **`bib-checkout`** pour les ré-identifier et les lier
  
  - Pour des nouveaux "profils de documents"  
    * **`bib-adapt-corpus`** pour entraîner grobid "à retrouver les bonnes réponses" sur des corpus PDF + XML gold (c'est-à-dire faire de nouveaux modèles CRF pour des nouveaux "profils de documents") ainsi que stocker, classer et évaluer les différents types de modèles CRF entraînés (bibzone, bibfields, etc.)
  

### Statut
*Après une phase d'un an de développements séparés, la stack arrive à maturité en septembre 2015.*

<table>
<tr><td>MODULE</td>          <td>STATUT</td>  <td>LANG</td>    <td>REMARQUES</td></tr>
<tr><td>bib-get</td>          <td>prod</td> <td>python3</td>   <td>déjà + de 30 Mbibs extraites !</td></tr>
<tr><td>bib-findout-api</td>  <td>dev</td>  <td>python3</td>    <td>proto. résolution par requêtes API</td></tr>
<tr><td>bib-install-vp</td>   <td>prod</td> <td>shell+java</td>  <td>décharge un tarball d'un fork de grobid</td></tr>
<tr><td>bib-eval</td>         <td>prod</td> <td>perl</td>         <td>inclut des matchs souples avancés</td></tr>
<tr><td>bib-adapt-corpus</td> <td>tests</td> <td>python3+XSL</td>  <td>atelier corpus + prépa + training + modèles CRF</td></tr>
</table>


### TODO
 - dockerisations
 - un bib-install-vi avec git pour un grobid utilisé en training
 - paramètrage bako + complet (critères arrêt, params prépas ragréage/Pub2TEI, params éval)
 - readme + complet pour bako !

### Infos
  - Chez Patrice Lopez, l'auteur de Grobid
    * [dépôt grobid officiel](https://github.com/kermitt2/grobid)
    * [manuel du service grobid](http://grobid.readthedocs.org/en/latest/Grobid-service/)
    * [manuel de l'entraînement de grobid](http://grobid.readthedocs.org/en/latest/Training-the-models-of-Grobid/)
  - Chez ISTEX:
    * [wiki enrichissement](http://wiki.istex.fr/enrichissement#refbibs)
    * [dépôt grobid modifié pour ISTEX](https://github.com/rloth/grobid)
    * [dépôt ISTEX pour l'intégration des  "enrichments"](https://git.istex.fr/istex/enrichments/tree/master/refbib)
    * [dépôt Pub2TEI-bibs (avec login seulement)](https://git.istex.fr/loth/Pub2TEI-bibs)
  

Contacts
---------
romain.loth at inist.fr  
istex at inist.fr

© 2014-15 Inist-CNRS (ISTEX)
>>>>>>> 6ce2892e47e1fb6a6c443983d5c97080af48f29c
