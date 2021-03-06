#! /usr/bin/perl

# eval_xml_refbibs.pl : Evaluation des résultats
#         - sur corpus PM_1943 déjà annoté dans un format NXML
#         - d'une chaine de balisage des références TEI (ex: grobid, bilbo)
# --------------------------------------------------------------------------
#  message /help/ en fin de ce fichier       version: 0.8.5 (05/10/2015)
#  copyright 2014-15 INIST-CNRS    contact: romain dot loth at inist dot fr
# --------------------------------------------------------------------------

# changelog
# ---------
# version 0.8 => 0.8.5: doc_ID (counter simple) remplacé par checkname dans les tables sorties
#                       plus simple à traiter ensuite mais tables plus grosses 
# version 0.7 => 0.8: tout TEI et assiette de précision
# version 0.6 => 0.7: prise en compte d'erreurs OCR courantes
#                     dans clean_compare et @COMPARERS

use warnings ;
use strict ;

use Getopt::Long ;

use File::Basename;            # pour les noms de fichier standards

use XML::LibXML ;              # pour parser les XML
use HTML::HTML5::Entities;     # et enlever les entités

use Unicode::Normalize ;       # pour savoir recoller les accents

use Algorithm::Combinatorics qw(combinations); # pour les combinaisons de fonctions "comparaisons de 2 chaines"

use Data::Dumper ;

use utf8 ;

binmode(STDOUT, ":utf8");
binmode(STDERR, ":utf8");
use Encode ;

############## SWITCHES + ARGS ################
# 2 entrées parallèles :
#  -x dossier/des/xml/à/évaluer/
#      (sortie d'outil)
#  -r dossier/des/xml/de/référence
#      (mêmes noms de fichiers excepté l'extension)

#~ my $debug = $opts->{d} || 0 ;
my $debug = 0 ;

# (option --golddir) Dossier des données de référence, dites "gold"
my $ref_dir = "" ;

# (option --thereflist) Liste des fichiers aux données de référence, dits "gold"
my $ref_list = "" ;

# (option -x) Dossier des données à évaluer, dites "todo"
my $xml_dir = "TEI-back_done" ;

# (option -e) Extension des données à évaluer 
# (TEI avec balisage refbib sorti de Grobid "references.tei.xml" ou de bib-get "refbibs.tei.xml")
my $ext = "references.tei.xml" ;

# limite au nombre de docs à traiter pour les tests
my $maxref = 0 ;

# chemin -l pour le résumé d'éval comme append dans un fichier tabulé
my $eval_log_path = "" ;

# option -r pour le précédent, pour donner un nom à la ligne de résumé d'éval
my $register_id = "";


# booléen: sortir un fichier supplémentaire "lookup_ids.csv"
#           avec une liste à 2 colonnes : identifiant <=> nom de fichier évalué
my $dump_lookup = 0 ;

# booléen (global): plus de détail pour infos d'erreurs telles que champ todo = sous-chaine champ gold
my $SUBSTR_INFO = 0 ;

# booléen (global): activer la désaccentuation avant match des chaînes 
my $UNACCENTS = 0 ;

# booléen activer compteur du défilement des docs en cours sur STDERR
my $numcount = 0 ;

# champs à extraire et traiter pour comparaison micro (variable globale)
# -----------------------------------------------------------------------
my @CANON_KEYS  = ('tit','date','j','vol','iss','fpg','lpg','psher') ;
# NB : 'names' avec les auteurs est traité à part car un degré d'emboîtement supplémentaire

# Fonctions de comparaison
my @COMPARERS = (
	'\&compare_rmhyphen',
	'\&compare_joinhyphen',
	# '\&compare_unligatures',
	'\&compare_normalise_punct',
	'\&compare_normalise_space',
	#~ '\&compare_joinaccent',
	#~ '\&compare_unaccent',
	'\&compare_simple_punctuation',
	'\&compare_ocrerrors',
	'\&compare_little_longer',  # ces 2 là forcément en dernier
	'\&compare_little_shorter', # ces 2 là forcément en dernier
	) ;

# # # # # # # # # # # # # # # # # # # # # # # # # # # # # # #
 GetOptions ("debug"        => \$debug,        # optional bool
			 "extension:s"  => \$ext,          # optional str
			 "xmldir=s"     => \$xml_dir,      # required str
			 "golddir=s"    => \$ref_dir,      # str required unless ref_list
			 "logreport=s"  => \$eval_log_path,# optional str
			 "regreport=s"  => \$register_id,  # optional str
			 "thereflist=s" => \$ref_list,     # str
			 "maxtemp:i"    => \$maxref,       # optional int
			 "iddump"       => \$dump_lookup,  # optional bool
			 "substrinfo"   => \$SUBSTR_INFO,  # optional bool
			 "unaccents"    => \$UNACCENTS,    # optional bool (changes results slightly)
			 "numcount"     => \$numcount,     # optional bool
			 "help"         => \&HELP_MESSAGE,
			 ) ;


###############################################################
#######                    MAIN                      ##########
###############################################################

# Liste des fichiers *à évaluer*

# £TODO lire directement depuis corpusdir/meta ?

my @xml_to_check_list = map {decode('UTF-8', $_)} glob("$xml_dir/*.$ext") ;
my $M = scalar(@xml_to_check_list) ;
warn "RELU_d : $M fichiers $ext dans le dossier à évaluer\n" ;

my @gold_paths_list = () ;
my $N = 0 ;
my $gold_extension = "tei.xml" ;

if ($ref_list) {
	open (REFLIST, "< $ref_list") || die "impossible d'ouvrir le fichier $ref_list" ;
	while (<REFLIST>) {
		chomp ;
		# use Encode ;
		$_ = decode('UTF-8', $_);
		push (@gold_paths_list, $_) ;
	}
	close REFLIST ;
	$N = scalar (@gold_paths_list) ;
	warn "RELU_l : $N fichiers dans la liste étalon\n" ;
}
elsif ($ref_dir) {
	@gold_paths_list = map {decode('UTF-8', $_)} glob("$ref_dir/*.$gold_extension") ;
	$N = scalar (@gold_paths_list) ;
	warn "RELU_d : $N fichiers .$gold_extension dans le dossier étalon\n" ;
}
else {
	warn "Veuillez fournir un dossier gold avec -g (ou une liste de chemins gold avec --thereflist)\n"
}

# REGISTRES avec contenus
# ------------------------
# NB: utilisés seulement en debug et iddump

# table de hash dont les clefs sont les basenames des
# fichiers de réf et les valeurs sont les données d'évaluation
my %docs = () ;

for my $goldpath (@gold_paths_list) {
	# enlève l'extension
	my $checkname_gold = path_to_dockey($goldpath, $gold_extension) ;

	# table de hash pour collecte des informations
	$docs{$checkname_gold} = {
	# niveau docs :
	# -------------
							"goldpath"  => $goldpath ,
							# chemin du doc à évaluer quand (et si) on l'aura
							"todopath"  => undef,
							# id $checkname quand (et si) on l'aura
							"todo_id"   => undef,
	# niveau doc mais stats sur refbibs :
	# -----------------------------------
	# (rempli plus loin)    "goldpairs"    => [liste d'infos sur couples bibs gold/todo alignés] ,
	# (rempli plus loin)    "silence_bibs" => {$k => stockage des $goldbib sans match} ,
	# (rempli plus loin)    "noise_bibs"   => {$l => stockage des $todobib sans match} ,
							} ;
}

# pour debug
#~ warn Dumper \%docs ; 
#~ exit ;

# # ===============================================================
# 1A) Préparation et lancement grande boucle (pour ch. document)
# ===============================================================

# entête du tableau csv
# ---------------------
# sortie 1 ligne :
my $separateur = "\t" ;
print join($separateur,
	('tdoc_id',             # identifiant doc
	 'gbib_id',             # identifiant refbib originale
	 'tbib_id',             # identifiant refbib évaluée
	'match','match_rule',       # alignement {aligné, bruit, silence} et si aligné règle utilisée
	'pubtype','tei_analytic',   # type de l'original (book, journal, etc) en entrée et présence d'une entrée analytique en sortie
	'gfields','tfields',        # nombre de champs de part et d'autre (hormis les noms)
	(map {"F".$_} @CANON_KEYS), # on préfixe 'F' (field) au nom des champs
	'gnames','tnames','oknames',      # nombre de sous-champs auteurs/nom et nb d'entre eux alignés
	))."\n" ;


# VARIABLES
# ---------

# compteurs de boucle doc
my $doc_j = 0 ;         # nb de docs todo lus [1..$M]  (débutera à 1)
my $aligned_docs = 0 ;     # nb de docs todo alignés sur un doc gold
my $matchable_docs = 0 ;   # nb de couples de docs alignés sans erreur XML  
                           # soit: $matchable_docs = $aligned_docs - ||U($gxerrs,$txerrs)||
my $gxerrs = 0 ;           # nb de docs gold à erreurs de lecture XML
my $txerrs = 0 ;           # nb de docs todo à erreurs de lecture XML
my $errs = 0 ;             # nb d'autres erreurs
my $empty_goldbib = 0 ;    # nb de docs originaux sans erreurs XML mais sans refbibs
my $empty_todobib = 0 ;    # nb de docs todo sans erreurs XML mais sans aucune refbib

# ... et de sous-boucles
my $K = 0 ;                   # nb de refbibs gold lues (base de travail)
my $matchable_K = 0 ;         # nb de refbibs gold lues sans errs XML dans le todo d'en face (assiette max pour le silence)
my $L = 0 ;                   # nb de refbibs todo lues (bibs générées) (= base - silence + bruit)
my $matchable_L = 0 ;         # nb de refbibs todo lues sans errs bibl non struct dans le gold d'en face (assiette max pour le bruit)
my $total_found_title = 0 ;   # nb refbibs bien alignées via le titre
my $total_found_issue = 0 ;   # nb refbibs bien alignées via journal+date+vol+fasc
my $total_found_names = 0 ;   # nb refbibs bien alignées via les Noms des auteurs
my $total_found_h_tit_substr = 0 ;  # nb refbibs alignées via heuristique titre + indices

my $semble_bruit = 0 ;    # nb de refbibs todo non alignables sur une refbib gold

# paramètre de l'ID numérique $docnostr
# pour avoir des ID 0001 0002 et non pas 1,2 on prend la longueur max
my $maxdocsdigits = length($M.'') ;

# on boucle sur les FICHIERS A ÉVALUER pour chercher ensuite
# le gold_path des fichiers de référence correspondants


# NB les seules situations où l'ont fait next() sont le non-alignement du fichier
#    (pas de couple gold-todo) et l'erreur goldxml (todo déjà compté, gold rien à compter)
# Par contre l'erreur todoxml (fichier balisé a été renvoyé invalide) doit
# provoquer une continuation avec un ajout aux stats de silence

for my $path (sort (@xml_to_check_list)) {
	# flag booléen si erreur XML dans doc todo pour ne pas le compter dans l'assiette
	my $got_txerr = 0 ;
	
	# compteur grande boucle [1..$M]
	$doc_j ++ ;
	
	# Obtention du nom de fichier todo simplifié (= clé de classement)
	my $checkname = path_to_dockey($path, $ext) ;

	my $docnostr = sprintf("%0${maxdocsdigits}d", $doc_j) ;
	warn "= DOC $docnostr ============================================\n" if $debug ;

	warn "NEXT file: $checkname\n" if $debug ;

	# hash des infos du document (couple des noms de fichiers + ID)
	my $info = $docs{$checkname} ;

	# Gestion des exceptions
	if (not defined $info) {
		warn "CHECKTODO=>GOLDMIS: nom de fichier '$checkname' non reconnu dans la liste de référence\n";
		next ;
	}
	else {
		$aligned_docs ++ ;    # celui-ci ne sera plus jamais modifié
		$matchable_docs ++ ;   # celui-ci sera décrémenté si une erreur XML du doc todo ou gold
	}

	# enregistrement des infos du doc à évaluer
	$info->{'todopath'} = $path ;
	$info->{'todo_id'} = $docnostr ;

	# ----------------------------------------------------------
	# 1B) parsing + décomptes bibs initiaux (nbbibs gold/todo)
	# ----------------------------------------------------------
	#  NB: attention aux next() même si XMLERR
	#      car risque de décomptes incomplets
	#      pour l'un des 2 fichiers
	
	# parseur XML
	my $parser = XML::LibXML->new() ;
	
	## parsing XML du doc à évaluer # = = = = parse = = = = parse = = = = = = =
	my $tododoc ;
	
	# i) méthode simple
	# eval { $tododoc = $parser->parse_file($path) ; } ;
	
	# ii) méthode avec la main sur chaque ligne
	my @todoxml = () ;
	open (TODO, "< $path") ;
	for my $tline (<TODO>) {
		chomp $tline ;
		# use Encode ;
		$tline = decode('UTF-8', $tline);
		push(@todoxml, $tline)
	}
	close (TODO) ;

	#~ warn Dumper \@todoxml ;

	eval { $tododoc = $parser->parse_string(join("\n",@todoxml)) ; } ;


	# gestion d'erreurs
	# (on *ne* saute *pas* le doc même si on a une erreur parsing xml)
	if ($@) {
		warn "  XMLERR: doc à évaluer no $docnostr ($path)\n" ;
		warn (errlog($@,$path)) ;
		
		$txerrs ++ ;
		$matchable_docs -- ;
		
		# flag on
		$got_txerr = 1 ;
		
		# on garde un doc vide pour le décompte des silences
		$tododoc = $parser->parse_string("<TEI/>") ;
	}

	## Récup liste @refbibs = <tododoc>//listBibl/biblStruct
	my $todoroot = $tododoc->documentElement();
	my $todoxng  = XML::LibXML::XPathContext->new($todoroot);
	$todoxng->registerNs('tei',"http://www.tei-c.org/ns/1.0") ;

	my @todobibs = $todoxng->findnodes('/tei:TEI/tei:text/tei:back//tei:listBibl/tei:biblStruct') ;

	my $nb_todobibs = scalar(@todobibs) ;
	warn "TODO : $nb_todobibs réfbibs\n" if $debug ;
	$L += $nb_todobibs ;
	$matchable_L += $nb_todobibs ;

	# toute todobib est initialement "suspecte d'être du bruit" :
	# (on la décomptera ensuite si alignement)
	$semble_bruit += $nb_todobibs ;

	## idem parsing XML du doc gold # = = = = parse = = = = parse = = = = = =
	my $goldpath = $info->{'goldpath'} ;
	my $golddoc ;

	# on doit lire tout le fichier pour éventuellement corriger les
	# namespaces XML (notamment pour elsevier)

	my @goldxml = () ;
	open (GOLD, "< $goldpath") ;
	for my $gline (<GOLD>) {
		chomp $gline ;
		# use Encode ;
		$gline = decode('UTF-8', $gline);
		push(@goldxml, $gline) ;
	}
	close (GOLD) ;

	eval { $golddoc = $parser->parse_string(join("\n",@goldxml)."\n") ; } ;

	# gestion d'erreurs
	if ($@) {
		$gxerrs ++ ;
		# ne fera pas partie de l'assiette sauf si parmi txerrs (déjà enlevé)
		$matchable_docs -- unless ($got_txerr) ;
		warn "  XMLERR: doc de référence $checkname ($goldpath)\n" ;
		warn (errlog($@,$goldpath)) ;
		
		# il n'ajoutera plus rien aux décomptes et le todobib à déjà été compté
		warn "GOLD : 0 réfbibs erreur parsing\n" if $debug ;
		next()
	}

	### récup liste des nodes
	# # ---------------------
	my @goldbibs = () ;
	
	# gold bibs éventuellement mal positionnées
	my @goldbibs_ubi = () ;
	
	# gold bibs non structurées # TODO influence sur les décomptes
	my @goldbibs_dont_bibl = () ;
	
	## Récup liste @refbibs = <tododoc>//listBibl/biblStruct
	my $goldroot = $golddoc->documentElement();
	my $goldxng  = XML::LibXML::XPathContext->new($goldroot);
	$goldxng->registerNs('tei',"http://www.tei-c.org/ns/1.0") ;
	
	eval {@goldbibs = $goldxng->findnodes('/tei:TEI/tei:text/tei:back//tei:listBibl/tei:biblStruct') ; } ;
	eval {@goldbibs_ubi = $goldxng->findnodes('//tei:listBibl/tei:biblStruct') ; } ;
	eval {@goldbibs_dont_bibl = $goldxng->findnodes('//tei:listBibl/tei:bibl|//tei:listBibl/tei:biblStruct') ; } ;
	#~ eval {@goldbibs_ubi = $goldxng->findnodes('//*[local-name()="listBibl"]/*[local-name()="biblStruct"]') ; } ;
	#~ eval {@goldbibs_dont_bibl = $goldxng->findnodes('//*[local-name()="listBibl"]/*[local-name()="bibl"]') ; } ;
	
	# gestion d'erreurs (on saute le doc si erreur xpath)
	if ($@) {
		$errs ++ ;
		warn "  XP_ERR: XPATH sur doc gold no $doc_j ($path)\n" ;
		warn (errlog($@,$path)) ;

		# il n'ajoutera plus rien aux décomptes et le todobib à déjà été compté
		warn "GOLD : 0 réfbibs erreur xpath\n" if $debug ;
		next() ;
	}
	
	my $nb_goldbibs = scalar(@goldbibs) ;
	my $nb_goldbibs_ubi = scalar(@goldbibs_ubi) ;
	my $nb_goldbibs_dont_bibl = scalar(@goldbibs_dont_bibl) ;

	warn "GOLD : $nb_goldbibs réfbibs struct au bon endroit\n" if $debug ;
	warn "GOLD : $nb_goldbibs_ubi réfbibs struct dans un listBibl\n" if $debug ;
	warn "GOLD : $nb_goldbibs_dont_bibl réfbibs dont non struct dans un listBibl (delta => décomptées assiette P)\n" if $debug ;
	
	# secours gold si besoin est (TEI mal structurée par XSLT mais refbibs présentes)
	if ($nb_goldbibs_ubi > $nb_goldbibs) {
		@goldbibs = @goldbibs_ubi ;
		$nb_goldbibs = $nb_goldbibs_ubi ;
	}
	
	# effet de bord sur l'assiette des todobibl matchable (£TODO les identifier quand on écrit les lignes bruit !)
	my $nb_non_matchable_g_non_struct = $nb_goldbibs_dont_bibl - $nb_goldbibs ;
	
	if ($nb_non_matchable_g_non_struct > 0) {
		warn "SEMISTRU: doc gold $docnostr a $nb_non_matchable_g_non_struct bibl gold non matchables (et $nb_goldbibs matchables)\n" ;
	}
	
	$matchable_L = $matchable_L - $nb_non_matchable_g_non_struct ;
	
	warn "L: $L vs matchable_L: $matchable_L\n" if $debug ;
	
	# début des décomptes d'éval
	$K += $nb_goldbibs ;
	$matchable_K += $nb_goldbibs unless ($got_txerr) ;
	
	# premiers tests de bon sens
	# --------------------------
	# on envoie des warnings mais on continue malgré tout
	# (pour exhaustivité des décomptes bruit/silence et lignes csv sorties)
	if ($nb_goldbibs == 0) {
		$empty_goldbib ++ ;
		warn "EMPTYSRC: doc gold no $docnostr ($checkname)\n" ;
	}
	# ceci n'est pas un else: décompte $empty_todobib distinct
	if ($nb_todobibs == 0 and not($got_txerr)) {
		$empty_todobib ++ ;
		warn "EMPTYTGT: doc à évaluer no $docnostr ($checkname)\n" ;
	}
	
	
	# ------------------------------------------------------------------
	# 1C) appariement todobibs <=> goldbibs
	# ------------------------------------------------------------------

	# décalage des 2 listes pour que les compteurs [0..[ deviennent les identifiants [1..[
	# ------------------------------------------------------------------------------------
	unshift(@goldbibs, undef) ;               # !!!
	unshift(@todobibs, undef) ;               # !!!
	# attention cette méthode affecte par la suite
	# tous les scalar(@liste) , les $liste[$i] ,
	# et les premières itérations des boucles


	# registres d'appariement
	# -----------------------
	# on reportera des infos sur chaque alignement trouvé au format suivant :
	# $goldpairs->[$goldbib_k] = $todobib_l   # matched_id
	my $goldpairs = [] ;
	# on gardera aussi le goldbibs n'ayant pas de match
	my $silence_bibs = {} ;
	# et enfin les todobibs sans alignement (=bruit)
	my $noise_bibs = {} ;


	# stockage des données extraites sur ce doc
	# -----------------------------------------
	# liste de hash des données extraites
	# (rempli en 1B et stocké après la fin du doc ssi bruit)
	my @todobibs_data = (undef) ;
	# NB : l'équivalent $goldbib_data est fait un par un en 1C pendant la boucle


	# ===================================================
	# 1D) Pré-boucle sur les todobibs éléments à évaluer
	# ===================================================
	# Boucle préparative pour stocker une seule fois les infos de comparaison
	# (la comparaison proprement dite sera dans une double boucle suivante,
	#  mais pour optimiser on parsera d'abord le XML des todobibs, une seule fois)

	# indice sur [1..$nb_todobibs]
	my $todobib_l = -1 ;

	for my $todobib (@todobibs) {
		$todobib_l++ ;
		next if ($todobib_l == 0) ;   # on a un cycle vide car [1..[
		
		# récup des champs et ajout de l'ID de la bib
		#~ my $info = retrieve_bibfields($todobib) ;
		
		#~ $info->{"_tb_id"} = $docnostr.sprintf("-tb%03d", $todobib_l),
				
		# enregistrement local (pour la durée du doc ou plus si bruit)
		#~ $todobibs_data[$todobib_l] = $info ;
		# ------------------------8<-----------------------------------------------------------------------
		my $tbxng  = XML::LibXML::XPathContext->new($todobib);
		$tbxng->registerNs('tei',"http://www.tei-c.org/ns/1.0") ;
		my $has_analytic = $tbxng->exists('tei:analytic') ;

		# RECUP du titre à évaluer
		my $todotitl = $tbxng->findvalue('.//tei:title[@level="a"]')
					|| $tbxng->findvalue('.//tei:title[@level="c"]')
					|| $tbxng->findvalue('.//tei:title[@level="m"]')
					|| undef ;

		# date à évaluer
		# TODO prendre un 5ème charactère ssi c'est une lettre [a-e]
		my $tododate = substr($tbxng->findvalue('tei:monogr/tei:imprint/tei:date/@when'),0,4) || undef ;

		# noms d'auteurs
		my @todonames_nodes = $tbxng->findnodes('./tei:analytic/tei:author//tei:surname') ;
		
		# si structure monographique seule
		if (not scalar(@todonames_nodes)) {
			@todonames_nodes = $tbxng->findnodes('./tei:monogr/tei:author//tei:surname') ;
		}

		my @todonames = map {$_->to_literal()} @todonames_nodes ;
		
		# warn Dumper \@todonames ;

		my $todopublisher = $tbxng->findvalue('.//tei:publisher') || undef ;

		my ($todojournal, $todovolume, $todoissue, $todofpage, $todolpage) ;
		if ($has_analytic) {
			# ne marche que pour les refbib analytiques (articles de journaux etc)
			$todojournal   = $tbxng->findvalue('.//tei:title[@level="j"]') || undef ;
			$todovolume    = $tbxng->findvalue('tei:monogr/tei:imprint/tei:biblScope[@unit="vol"]|tei:monogr/tei:imprint/tei:biblScope[@unit="volume"]') || undef ;
			$todoissue     = $tbxng->findvalue('tei:monogr/tei:imprint/tei:biblScope[@unit="issue"]|tei:monogr/tei:imprint/tei:biblScope[@unit="iss"]') || undef ;
			$todofpage     = $tbxng->findvalue('tei:monogr/tei:imprint/tei:biblScope[@unit="page"]/@from|tei:monogr/tei:imprint/tei:biblScope[@unit="pp"]/@from') || undef ;
			$todolpage     = $tbxng->findvalue('tei:monogr/tei:imprint/tei:biblScope[@unit="page"]/@to|tei:monogr/tei:imprint/tei:biblScope[@unit="pp"]/@to') || undef ;
		}

		# enregistrement local (pour la durée du doc, ou plus si bruit)
		$todobibs_data[$todobib_l] = { "tit"   => $todotitl,
									"date"  => $tododate,
									"names" => \@todonames,
									"j"     => $todojournal,
									"vol"   => $todovolume,
									"iss"   => $todoissue,
									"fpg"   => $todofpage,
									"lpg"   => $todolpage,
									"psher" => $todopublisher,
									"_tb_id"   => $docnostr.sprintf("-tb%03d", $todobib_l),
									"_has_analytic"  => $has_analytic ? "an+mo":"mo",
									} ;
		# ------------------------8<-----------------------------------------------------------------------
		
	} ## fin préboucle @todobibs ##
	
	# debug
	#~ warn Dumper \@todobibs_data ;
	#~ exit ;



	# ============================
	#  1E) Apparillage de lignes
	# ============================

	my $local_found = 0 ;

	# compteur sur [1..$nb_goldbibs]
	my $goldbib_k = -1 ;

	# liste bool pour marquage des gagnants (todobibs ayant trouvé leur original)
	# => initialisée à (undef, 0, 0, 0, 0, 0, 0, 0, ... 0)
	my @done = (0) x ($nb_todobibs) ;
	# => comme les indices todobibs commencent à 1, on met bien undef dans $done[0]
	unshift (@done, undef) ;


	# Double sous-boucle : pour chaque goldbib on regarde chaque todobib
	# -------------------------------------------------------------------
	# on fait notre boucle sur les données étalon de @goldbibs et chaque
	# fois on cherche les infos préparées @todobibs correspondantes
	for my $goldbib (@goldbibs) {
		# incrément indice sur [1..$nb_goldbibs]
		$goldbib_k ++ ;
		next if ($goldbib_k == 0) ;  # car [1..[

		# Récup données de référence
		# ---------------------------
		# variables en accès direct pour tests dans la boucle
		#~ my (@goldnames, $goldtitl, $golddate, $goldjournal, $goldvolume,
		    #~ $goldissue, $goldfpage, $goldlpage, $goldpublisher) ;

		# persistence des variables pour stockage des matchs
		my $goldbib_data = {} ;
		
		my $gbxng  = XML::LibXML::XPathContext->new($goldbib);
		$gbxng->registerNs('tei',"http://www.tei-c.org/ns/1.0") ;

	my $has_analytic = $gbxng->exists('tei:analytic') ;

	# RECUP du titre à évaluer
	my $goldtitl = $gbxng->findvalue('.//tei:title[@level="a"]')
				|| $gbxng->findvalue('.//tei:title[@level="c"]')
				|| $gbxng->findvalue('.//tei:title[@level="m"]')
				|| undef ;

	# date à évaluer
	# gold prendre un 5ème charactère ssi c'est une lettre [a-e]
	my $golddate = substr($gbxng->findvalue('.//tei:imprint/tei:date/@when'),0,4) || undef ;

	# noms d'auteurs
	my @goldnames_nodes = $gbxng->findnodes('./tei:analytic/tei:author//tei:surname') ;
	
	# si structure monographique seule
	if (not scalar(@goldnames_nodes)) {
		@goldnames_nodes = $gbxng->findnodes('./tei:monogr/tei:author//tei:surname') ;
	}

	my @goldnames = map {$_->to_literal()} @goldnames_nodes ;
	
	# warn Dumper \@goldnames ;

	my $goldpublisher = $gbxng->findvalue('.//tei:publisher') || undef ;

	my ($goldjournal, $goldvolume, $goldissue, $goldfpage, $goldlpage) ;
	if ($has_analytic) {
		# ne marche que pour les refbib analytiques (articles de journaux etc)
		$goldjournal   = $gbxng->findvalue('.//tei:title[@level="j"]') || undef ;
		$goldvolume    = $gbxng->findvalue('tei:monogr/tei:imprint/tei:biblScope[@unit="vol"]|tei:monogr/tei:imprint/tei:biblScope[@unit="volume"]') || undef ;
		$goldissue     = $gbxng->findvalue('tei:monogr/tei:imprint/tei:biblScope[@unit="issue"]|tei:monogr/tei:imprint/tei:biblScope[@unit="iss"]') || undef ;
		$goldfpage     = $gbxng->findvalue('tei:monogr/tei:imprint/tei:biblScope[@unit="page"]/@from|tei:monogr/tei:imprint/tei:biblScope[@unit="pp"]/@from') || undef ;
		$goldlpage     = $gbxng->findvalue('tei:monogr/tei:imprint/tei:biblScope[@unit="page"]/@to|tei:monogr/tei:imprint/tei:biblScope[@unit="pp"]/@to') || undef ;
	}

			# enregistrement local
			$goldbib_data = { "tit"   => $goldtitl,
							  "date"  => $golddate,
							  "names" => \@goldnames,
							  "j"     => $goldjournal,
							  "vol"   => $goldvolume,
							  "iss"   => $goldissue,
							  "fpg"   => $goldfpage,
							  "lpg"   => $goldlpage,
							  "psher" => $goldpublisher,
							  "_gb_id"   => $docnostr.sprintf("-gb%03d", $goldbib_k),
							  "_has_analytic"  => $has_analytic ? "an+mo":"mo",
							} ;
		# debug
		#~ warn Dumper $goldbib_data ;
		#~ if ($doc_j > 1) {
			#~ exit ;
		#~ }
		
		
		# on court-circuite la suite si on a déjà trouvé $nb_todobibs:
		# (ça veut dire qu'il faut juste stocker les silences mais qu'on ne peut plus espérer de match)
		if ($local_found == $nb_todobibs) {
 			#~ warn Dumper $goldbib_data ;
			$silence_bibs->{$goldbib_k} = $goldbib_data ;
			next ;
		}

		# Boucle la plus intérieure (recherche de $todobib à aligner)
		# ------------------------------------------------------------
		# Cette boucle est un peu optimisée :
		#   - on a préparé les données avant pour ne pas relire le XML à chaque boucle de profondeur 3
		#   - on marque dans une liste @done les todobibs déjà alignées (pour les sauter: gagne ~ 50% du tps)

		# indice sur [1..$nb_todobibs]
		$todobib_l = -1 ;

		for my $todobib_data (@todobibs_data) {
			$todobib_l++ ;
			next if ($todobib_l == 0) ;   # car [1..[
			next if ($done[$todobib_l]) ;

			# debug
			#~ warn Dumper $todobib_data ;
			#~ exit ;

			# Récup données à évaluer (déjà préparées)
			# ----------------------------------------
			my $todotitl = $todobib_data->{'tit'} ;        # titre
			my $tododate = $todobib_data->{'date'} ;       # date préparé (4 chars)

			my @todonames = @{$todobib_data->{'names'}} ;  # noms d'auteurs

			my $todojournal = $todobib_data->{'j'} ;       # journal, volumaison etc
			my $todovolume  = $todobib_data->{'vol'} ;
			my $todofpage   = $todobib_data->{'fpg'} ;


			# 3 tests d'apparillage strict
			# -----------------------------

			# tentative d'alignement par titre exact et date -------------
			if (defined($goldtitl) && defined($todotitl)
				&& defined($golddate) && defined($tododate)
				&& (clean_compare($goldtitl,$todotitl))
				&& ($golddate eq $tododate)) {

				# report des stats
				$done[$todobib_l] = 1 ;
				$local_found ++ ;
				$total_found_title ++ ;
				$semble_bruit -- ;

				# report des infos
				$goldpairs->[$goldbib_k] = $todobib_l ;
				# comparaison micro
				my $csv_line = fields_pair_str(
						{
						 'checkname' => $checkname,
						 'gbib_id' => $goldbib_k,
						 'tbib_id' => $todobib_l,
						 'alignement' => 'aligné',
						 'match_rule'  => 'strict:ti+date',
						 'gbib_fields' => $goldbib_data,
						 'tbib_fields' => $todobib_data,
						} );
				# sortie CSV
				print $csv_line . "\n" ;

				# debg
				if ($csv_line =~ /NON_vide/) {
					warn $todobib_data->{'_str'} ;
				}

				last ;
			}
			
			
			# debug
			#~ warn Dumper join(' ',@goldnames) ;
			#~ warn Dumper join(' ',@todonames) ;
			#~ warn clean_compare(join(' ',@goldnames),join(' ',@todonames))?"mêmes_names\n":"names_diff\n" ;
			
			# tentative d'alignement par auteurs/date --------------------
			# TODO date "2002" --> "2002a"
			if (defined($golddate)
				&& scalar(@goldnames)
				&& defined($tododate)
				&& (clean_compare(join(' ',@goldnames),join(' ',@todonames)))) {
				# report des stats
				$done[$todobib_l] = 1 ;
				$local_found ++ ;
				$total_found_names ++ ;
				$semble_bruit -- ;

				# report des infos
				$goldpairs->[$goldbib_k] = $todobib_l ;
				# comparaison micro
				my $csv_line = fields_pair_str(
						{
						 'checkname' => $checkname,
						 'gbib_id' => $goldbib_k,
						 'tbib_id' => $todobib_l,
						 'alignement' => 'aligné',
						 'match_rule'  => 'strict:au+date',
						 'gbib_fields' => $goldbib_data,
						 'tbib_fields' => $todobib_data,
						} );
				# sortie CSV
				print $csv_line . "\n" ;

				# debg
				if ($csv_line =~ /NON_vide/) {
					warn $todobib_data->{'_str'} ;
				}

				last ;
			}

			# tentative d'alignement par journal/volume/page  ------------
			if (   defined($goldjournal) && defined($goldvolume) && defined($goldfpage)
				&& defined($todojournal) && defined($todovolume) && defined($todofpage) ) {
				
				if (clean_compare($todojournal,$goldjournal)
					&& ($todovolume eq $goldvolume)
					&&  ($todofpage eq $goldfpage)) {
					# report des stats
					$done[$todobib_l] = 1 ;
					$local_found ++ ;
					$total_found_issue ++ ;
					$semble_bruit -- ;


					# report des infos
					$goldpairs->[$goldbib_k] = $todobib_l ;
					
					
					# comparaison micro
					my $csv_line = fields_pair_str(
							{
							'checkname' => $checkname,
							'gbib_id' => $goldbib_k,
							'tbib_id' => $todobib_l,
							'alignement' => 'aligné',
							'match_rule'  => 'strict:j+vol+p',
							'gbib_fields' => $goldbib_data,
							'tbib_fields' => $todobib_data,
							} );
					# sortie CSV
					print $csv_line . "\n" ;

					# debg
					if ($csv_line =~ /NON_vide/) {
						warn $todobib_data->{'_str'} ;
					}

					last ;
				}
			}


			# un test d'apparillage heuristique
			# ----------------------------------
			# Match titre + fort que clean_compare car $todotitl_poor =~ /$goldtitl_poor/
			# TODO transformer (date + un autre indice) en (2 indices convergents mais quelconques)
			
			#~ warn("GOLDTITLE --------------------------------------- $goldtitl");
			#~ warn("TODOTITLE --------------------------------------- $todotitl");
			
			if (defined($goldtitl) && defined($todotitl)
				&& defined($golddate) && defined($tododate)
				&& (scalar(@todonames) || defined($todofpage))) {

				# on appauvrit les titres pour les comparer
				my $goldtitl_poor = lc($goldtitl) ;
				$goldtitl_poor =~ s/\W+//g ;

				my $todotitl_poor = lc($todotitl) ;
				$todotitl_poor =~ s/\W+//g ;

				if ((length($goldtitl_poor) > 6)                   # -> il faut que le titre original ait un peu de teneur,
					&& ($todotitl_poor =~ /$goldtitl_poor/)        # --> titre à évaluer "trop long" mais incluant l'original,
					&& ($golddate eq $tododate)                    # -> on veut quand même la date
					&& (                                           # --> et un autre indice fort (nom ou pagination)
						 (scalar(@goldnames) && scalar(@todonames)  && ($goldnames[0] eq $todonames[0]))
					  || (defined($goldfpage) && defined ($todofpage) && ($goldfpage eq $todofpage)) )
					  ){
					# report des stats
					$done[$todobib_l] = 1 ;
					$local_found ++ ;
					$total_found_h_tit_substr ++ ;
					$semble_bruit -- ;

					# report des infos
					$goldpairs->[$goldbib_k] = $todobib_l ;
					# comparaison micro
					my $csv_line = fields_pair_str(
							{
							'checkname' => $checkname,
							'gbib_id' => $goldbib_k,
							'tbib_id' => $todobib_l,
							'alignement' => 'aligné',
							'match_rule'  => 'heuri:ti+autres',
							'gbib_fields' => $goldbib_data,
							'tbib_fields' => $todobib_data,
							} );
					# sortie CSV
					print $csv_line . "\n" ;

					# debg
					if ($csv_line =~ /NON_vide/) {
						warn $todobib_data->{'_str'} ;
					}

					last ;
				}
			}

			#~ # pour debug taille mémoire des variables
			#~ if (($doc_j == 499) && ($todobib_l == ($nb_todobibs-2))) {
				#~ &Devel::DumpSizes::dump_sizes("./dump_sizes.ls");
			#~ }
		} ## fin boucle @todobibs ##

		# finalement on reporte aussi si rien trouvé (=silence)
		if (not defined($goldpairs->[$goldbib_k])) {
			$silence_bibs->{$goldbib_k} = $goldbib_data ;
		}

	# affiche compteur défilant docno-max(goldbibno)
	print STDERR "doc $docnostr/$M - ".sprintf("bibs [1..%03d] comparées", $goldbib_k)."\r" if ($numcount || $debug) ;

	} ## fin boucle @goldbibs ##

	warn "\n" if ($debug) ;


	# ==================================
	# 1F) a posteriori dans chaque doc
	# ==================================
	# £TODO ici identifier celles qui correspondent aux bibl non struct dans le gold
	# (au moins on les décompte => ces items ne sont pas du vrai gold)
	$semble_bruit -= $nb_non_matchable_g_non_struct ;
	
	
	# on re-passe aussi sur les $todobib pour garder de côté ceux qui n'ont pas d'alignement
	# ---------------------------------------------------------------------------------------
	for my $l_prime (1..$nb_todobibs) {
		if (not $done[$l_prime]) {
			$noise_bibs->{$l_prime} = $todobibs_data[$l_prime] ;
		}
	}

	warn "MATCH: $local_found réfbibs\n" if $debug ;
	warn "==========================================================\n" if $debug ;

	## sorties des lignes csv bruit et silence
	for my $stray_k (sort {$a <=> $b} keys %$silence_bibs) {

		my $print_info = {
							'bname'      => $checkname,
							'bib_id'     => $stray_k,
							'bib_fields' => $silence_bibs->{$stray_k},
							'nature'     => 'silence',
						} ;
		#~ warn Dumper $print_info ;
		print non_aligned_str($print_info) ."\n" ;
	}
	for my $stray_l (sort {$a <=> $b} keys %$noise_bibs) {
		my $print_info = {
							'bname'      => $checkname,
							'bib_id'     => $stray_l,
							'bib_fields' => $noise_bibs->{$stray_l},
							'nature'     => 'bruit',
						} ;
		#~ warn Dumper $print_info ;
		print non_aligned_str($print_info) ."\n" ;
	}

	# possibilité enregistrement des récapitulatifs après chaque document
	# pour toutes sorties complémentaires éventuelles

	# ATTENTION SI ENREGISTREMENT MEMOIRE CUMULÉE
	#£ todo pb info est une copie
	# $info->{'goldpairs'} = $goldpairs ;
	# $info->{'noise_bibs'}   = $noise_bibs ;
	# $info->{'silence_bibs'} = $silence_bibs ;
	if ($dump_lookup) {
		# enregistrement de ce qu'on a mis dans info
		# (au minimum: todopath, goldpath, ID : ces trois essentiels si dump_lookup)
		$docs{$checkname} = $info ;
	}
} ####### fin boucle DOCS todopaths #######


# cas particulier si erreur balisage

if ($matchable_L == 0) {
	warn "!!! Aucune refbib à évaluer -- vérifier s'il n'y a pas d'erreur de balisage côté grobid dans grobid.log !!!\n"
}

# ============================================
# 1G) Calcul et affichage stats par documents
# ============================================
my $doc_longest = $N >= $M ? $N : $M ;
my $nbchar1  = length($doc_longest)+1 ;


my $bib_longest = $K >= $L ? $K : $L ;
my $nbchar2  = length($bib_longest)+1 ;

my $total_found = $total_found_title
				+ $total_found_issue
				+ $total_found_names
				+ $total_found_h_tit_substr ;

# rapport affiché
warn "------ stats évaluation corpus nxml ------\n" ;
warn "  #docs dossier gold ..........".sprintf("% ${nbchar1}d",$N)."\n" ;
warn "  #docs dossier todo ..........".sprintf("% ${nbchar1}d",$M)."\n" ;
warn "  #DOCUMENTS ALIGNÉS ..........".sprintf("% ${nbchar1}d",$aligned_docs)."\n" ;
warn "  #documents assiette .........".sprintf("% ${nbchar1}d",$matchable_docs)."\n" ;
warn "  #docs 'gold' à erreurs xml ..".sprintf("% ${nbchar1}d",$gxerrs)."\n" ;
warn "  #docs 'todo' à erreurs xml ..".sprintf("% ${nbchar1}d",$txerrs)."\n" ;
warn "  #docs 'gold' sans refbibs ...".sprintf("% ${nbchar1}d",$empty_goldbib)."\n" ;
warn "  #docs 'todo' sans refbibs ...".sprintf("% ${nbchar1}d",$empty_todobib)."\n" ;
warn "  #autres erreurs (path...). ..".sprintf("% ${nbchar1}d",$errs)."\n" ;
warn "------------------------------------------\n" ;
warn " #refbibs 'gold' ...............".sprintf("% ${nbchar2}d",$K)."\n" ;
warn "  dont #assiette ...............".sprintf("% ${nbchar2}d",$matchable_K)."\n" ;
warn "  dont #trouvés ................".sprintf("% ${nbchar2}d",$total_found)."\n" ;
warn "    ├─ par le titre ............".sprintf("% ${nbchar2}d",$total_found_title)."\n" ;
warn "    ├─ par la volumaison .......".sprintf("% ${nbchar2}d",$total_found_issue)."\n" ;
warn "    ├─ par auteurs+date ........".sprintf("% ${nbchar2}d",$total_found_names)."\n" ;
warn "    └─ par heuristique tit .....".sprintf("% ${nbchar2}d",$total_found_h_tit_substr)."\n" ;
warn "  et #non-trouvés (silence) ....".sprintf("% ${nbchar2}d",$K - $total_found)."\n" ;
warn "           _ _ _ _ _ _ _ _ _ _ \n" ;
warn "          | => Rappel = ".sprintf("%.3f |",$total_found/$K)."\n" if ($K != 0) ;
warn "          | => R_asst = ".sprintf("%.3f |",$total_found/$matchable_K)."\n" if ($matchable_K != 0) ;
warn "------------------------------------------\n" ;
warn " #refbibs 'todo' ...............".sprintf("% ${nbchar2}d",$L)."\n" ;
warn "  dont #assiette ...............".sprintf("% ${nbchar2}d",$matchable_L)."\n" ;
warn "  dont #non-alignées (bruit) ...".sprintf("% ${nbchar2}d",$semble_bruit)."\n" ;
warn "          _ _ _ _ _ _ _ _ _ _ _ _\n" ;
warn "       | => Précision  = ".sprintf("%.3f  |",$total_found/$L)."\n" if ($L != 0) ;
warn "       | => P_assiette = ".sprintf("%.3f  |",$total_found/$matchable_L)."\n" if ($L != 0) ;
warn "------------------------------------------\n" ;

if ($UNACCENTS) {
	warn "[mode --unaccents]\n" ;
}

# Sorties supplémentaires et posttraitements
# ------------------------------------------
# option : rapport ajouté à une table
if($eval_log_path) {
	open (EVAL_REPORT_TO_APPEND, ">>", $eval_log_path)
	 || die "Par contre impossible d'ajouter ce rapport d'éval au fichier $eval_log_path (échec écriture)" ;
	warn "Ajout de ce rapport d'éval dans >> $eval_log_path \n" ;
	if ($register_id) {
		warn "  cols: NDOCS nbibs_gold Rappel_a  Précision_a match_tit match_vol match_au+date match_TOTAL EVAL_ID\n";
	}
	else {
		warn "  cols: NDOCS nbibs_gold Rappel_a  Précision_a match_tit match_vol match_au+date match_TOTAL\n";
	}
	
	print EVAL_REPORT_TO_APPEND sprintf("% ${nbchar1}d",$aligned_docs)."\t" ;
	print EVAL_REPORT_TO_APPEND sprintf("% ${nbchar2}d",$K)."\t" ;
	
	if ($matchable_K == 0) {
		warn "WARNING (EVAL SORTIE) 0 refbibs golds lues sans erreur, (et donc impossible de calculer le rappel)\n" ;
		print EVAL_REPORT_TO_APPEND "err\t" ;
	} else {
		print EVAL_REPORT_TO_APPEND sprintf("%.3f",$total_found/$matchable_K)."\t" ;
	}
	if ($matchable_L == 0) {
		warn "WARNING (EVAL SORTIE) 0 refbibs 'todo' (à évaluer) ! (et donc impossible de calculer la précision)\n" ;
		print EVAL_REPORT_TO_APPEND "err\t" ;
	} else {
		print EVAL_REPORT_TO_APPEND sprintf("%.3f",$total_found/$matchable_L)."\t" ;
	}
	print EVAL_REPORT_TO_APPEND sprintf("% ${nbchar2}d",$total_found_title)."\t" ;
	print EVAL_REPORT_TO_APPEND sprintf("% ${nbchar2}d",$total_found_issue)."\t" ;
	print EVAL_REPORT_TO_APPEND sprintf("% ${nbchar2}d",$total_found_names)."\t" ;
	print EVAL_REPORT_TO_APPEND sprintf("% ${nbchar2}d",$total_found)."\t" ;
	
	if ($register_id) {
		$register_id =~ s/[^a-zA-Z0-9_-]/_/g ;
		print EVAL_REPORT_TO_APPEND $register_id."\t" ;
	}
	
	print EVAL_REPORT_TO_APPEND "\n";
	
	close EVAL_REPORT_TO_APPEND ;
}

# Dump lookup table DOCID <=> DOCNAME
if ($dump_lookup) {
	# lignes de couples
	my @table_lines = () ;

	for my $checkname (keys %docs) {
		# on peut avoir plus de docs gold que de fichiers à évaluer
		next unless defined($docs{$checkname}->{'todopath'}) ;

		# (ce qu'on met est une ligne csv ID\tNAME)
		push (@table_lines, $docs{$checkname}->{'todo_id'}."\t$checkname\n") ;
	}

# 	# timestamp pour le nom de fichier
# 	my ($sec,$min,$hour,$mday,$mon,$year) = localtime(time);
# 	$mon += 1;
# 	$year += 1900;
# 	my $timestamp = sprintf("%04d-%02d-%02d-%02dh%02d", $year, $mon, $mday, $hour, $min);

	open (IDDUMP, ">", "./lookup_ids.tab")
	 || die "impossible d'écrire dans un fichier lookup_ids.tab\n" ;

	for my $line (@table_lines) {
		print IDDUMP $line ;
	}
	close IDDUMP ;
}






###############################################################
#######                    SUBS                      ##########
###############################################################


# créatuion d'une string csv sans aucune comparaison
# pour faire état des bibs non alignées (bruit ou silence)
# (mais pas juste les 1ères colonnes car il faut pouvoir
#  inclure des stats par type de champ en présence)
# colonnes
# --------
# 	('tdoc_id','gbib_id','tbib_id',
# 	'match','match_rule',
# 	'pubtype','tei_analytic',
# 	'gfields','tfields',
# 	'tit','date','j','vol','iss','fpg','lpg','psher'
# 	'gnames','tnames','oknames',
# 	'errnames1','errnames2','errnames3','errnames4')
sub non_aligned_str {
	my $params = shift ;

	# identifiant du doc en cours
	my $bname = $params->{'bname'} ;
	# identifiant de la bib (gb_k ou tb_l)
	my $b_id = $params->{'bib_id'} ;
	# hash des données parsées todobib_data ou goldbib_data
	my $b_data = $params->{'bib_fields'} ;
	# str 'bruit' ou 'silence'
	my $nature = $params->{'nature'} ;

	my $nb_names  = scalar(@{$b_data->{'names'}}) ;

	my @csv_values = () ;

	# nombre de champs extraits du xml (les champs ajoutés par ailleurs commencent par _)
	my $nb_def_fields = scalar(grep {($_ !~ /^_/) && defined($b_data->{$_})} keys %$b_data) ;

	# colonnes | doc_id | goldid | -rien- |silence|match_r| pubtype |   -rien-   |nb_gfields| -rien- | gnames | -rien- | oknames (= 0)
	if ($nature eq 'silence') {
		@csv_values = (                              # val?      col:
		               $bname,                       # oui       doc_id
		               $b_id,                        # oui       gold_b_id
		               '___',                        # xxx       todo_b_id
		               'silence',                    # "silence"  match
		               '___',                        # xxx       match rule
		               $b_data->{'_has_analytic'},   # oui       gold_analy
		               '___',                        # xxx       tei_has_analytic
		               $nb_def_fields,               # oui       nb_gfields
		               '___',                        # xxx       nb_tfields
		               ) ;
	}
	# colonnes | doc_id | -rien- | todoid | bruit |match_r| -rien-  |has_analytic|  -rien-  | nb_tfields | -rien- | tnames | oknames (= 0)
	elsif ($nature eq 'bruit') {
		@csv_values = (                              # val?    col:
		               $bname,                       # oui     doc_id
		               '___',                        # xxx     gold_b_id
		               $b_id,                        # oui     todo_b_id
		               'bruit',                      # "bruit"  match
		               '___',                        # xxx     match rule
		               '___',                        # xxx     
		               $b_data->{'_has_analytic'},   # oui     todo_analy
		               '___',                        # xxx     nb_gfields
		               $nb_def_fields,               # oui     nb_tfields
		               ) ;
	}
	else {
		warn $bname."--".$b_id."nature de la bib '$nature' inconnue\n" ;
	}


#   @CANON_KEYS  = ('tit','date','j','vol','iss','fpg','lpg','psher') ;

	# autres colonnes : forcément bruit ou silence
	# comme effet secondaire (captif) du fait que la ligne entière est manquante
	for my $key (@CANON_KEYS) {
		my $field = $b_data->{$key} ;
		if (not defined($field)) {
			push (@csv_values, "___") ;
		}
		else {
			push (@csv_values, "NON_${nature}_captif") ;
		}
	}

	# et enfin colonnes names
	if ($nature eq 'silence') {
		#                   nb_gnames   nb_tnames    nb_oknames
		push (@csv_values, ($nb_names , '___',       '0' )       ) ;
	}
	elsif ($nature eq 'bruit') {
		#                   nb_gnames   nb_tnames    nb_oknames
		push (@csv_values, ('___',      $nb_names ,  '0' )       ) ;
	}
	
	return join("\t", @csv_values) ;
}


# ========================================
# 2) diff sur microstructure => ligne csv
# ========================================
# (diff au niveau de chaque champ des refbibs alignées)
# sortie :
# ligne csv pour décomptes (ex : rappel et précision au niveau des champs)
sub fields_pair_str {
	my $params = shift ;
	
	# mega affichage debug des paires ----------
	#~ warn Dumper $params ;
	# ------------------------------------------
	
	my $bname = $params->{'checkname'};
	my $gb_k  = $params->{'gbib_id'} ;
	my $tb_l  = $params->{'tbib_id'} ;
	my $alignement = $params->{'alignement'} ;
	my $match_rule = $params->{'match_rule'} ;
	my $gb_data    = $params->{'gbib_fields'} ;
	my $tb_data    = $params->{'tbib_fields'} ;

	# nombre de champs extraits du xml gold
	my $nb_def_gf = scalar(grep {($_ !~ /^_/) && defined($gb_data->{$_})} keys %$gb_data) ;

	# idem pour le xml todo
	my $nb_def_tf = scalar(grep {($_ !~ /^_/) && defined($tb_data->{$_})} keys %$tb_data) ;

	# début de ligne 9 colonnes toujours pareilles :
	#   3 cols identifiants,
	#   1 col  devenir de la ligne (alignement, bruit ou silence)
	#   1 col  type d'alignement (aka match_rule)
	#   1 col  le 'publication type' du gold
	#   1 col  le 'has_analytic' du todo
	#   2 cols nombre de champs extraits de part et d'autre
	my @result = ($bname,  $gb_k,  $tb_l,
				  $alignement,  $match_rule,
				  $gb_data->{'_has_analytic'},  $tb_data->{'_has_analytic'},
				  $nb_def_gf,$nb_def_tf) ;

	# colonnes suivantes : comparaison champ par champ (hormis les noms cf. plus loin)
	# @CANON_KEYS  = ('tit','date','j','vol','iss','fpg','lpg','psher') ;
	for my $key (@CANON_KEYS) {
		my $goldfield = $gb_data->{$key} ;
		my $todofield = $tb_data->{$key} ;

		if ((not defined($goldfield)) && (not defined($todofield))) {
			# la donnée n'est pas définie  (ex: journal pour une monographie)
			push (@result, "___") ;
		}
		elsif ((not defined($goldfield)) &&      defined($todofield)) {
			# la donnée n'est pas définie mais l'outil invente qqch
			push (@result, "NON_bruit") ;
		}
		elsif (     defined($goldfield)  && (not defined($todofield))) {
			# la donnée est définie mais l'outil n'a rien vu
			push (@result, "NON_silence") ;
		}
		elsif (not length($todofield)) {
			# n'arrive jamais avec grobid
			push (@result, "NON_silence_vide") ;
		}
		else {
			my $diagnostic_str = "" ;

			my $gold_re = quotemeta($goldfield) ;
			my $todo_re = quotemeta($todofield) ;


			# ----------------------
			# *comparaison stricte*
			# ----------------------
			if ($goldfield eq $todofield) {
				$diagnostic_str = "OUI" ;
			}
			# diagnostics particuliers par champ
			# ----------------------------------
			elsif (($key eq 'tit') && ($todofield =~ /http/)
					&& (length($goldfield) > 7) && ($todofield =~ /$gold_re/)) {
				if  ($SUBSTR_INFO) {
					$diagnostic_str = "NON_+long_tit_http(".length($goldfield)."+".(length($todofield) - length($goldfield)).")"  ;
				}
				else {
					$diagnostic_str = "NON_+long_tit_http"  ;
				}
			}
			# comparaisons élargies génériques
			# --------------------------------
			# cf. toutes les subroutines compare_* recensées dans @COMPARERS
			else {
				# pour debug: flag locale
# 				my $local_debug = (($doc_id == 1) && ($gb_k==24)) ;
				my $local_debug = 0 ;

				# on testera d'abord chaque operation de comparaison seule
				#   puis toutes les combos de 2 opérations
				#   puis toutes les combos de 3
				#   ...
				# jusqu'à la combo de toutes les opérations
				my $compare_success = 0 ;

				my $max_oper = scalar(@COMPARERS) ;

				COMPARE_THIS_FIELD:for (my $k_oper=1; ($k_oper <= $max_oper); $k_oper++) {
				#~ COMPARE_THIS_FIELD:for (my $k_oper=$max_oper; ($k_oper <= $max_oper); $k_oper++) {

					# on liste les k-combinaisons possibles
					# use Algorithm::Combinatorics
					my @k_combos = combinations(\@COMPARERS, $k_oper) ;

					if ($local_debug) {
						warn "================ COMBIS DE $k_oper OPERATIONS ================\n" ;
						warn Dumper \@k_combos ;
					}

					# une séquence possible d'opérations
					for my $combo (@k_combos) {

						# un relevé des opérations effectuées dans cette combinaison
						my $trace_str = "" ;

						# compteur dans une combinaison
						my $nb_oper = 0 ;

						# les valeurs sur lesquelles on travaille
						my $test_goldfield = $goldfield ;
						my $test_todofield = $todofield ;

						# Enfin: application d'une série d'opération en 'pipe'
						for my $operation (@{$combo}) {
							$nb_oper ++ ;

							# £TODO 1 : eval dangereux ?
							# TODO 2 : eval renvoie une ref de ref bien que chaque
							#          fonction renvoie directement l'array ?
							my @send_args = ($test_goldfield, $test_todofield) ;
 							# warn $operation ;
							my $res_arrayref = ${eval("$operation(\@send_args)")};
							die $@ if $@;

							$compare_success  = $res_arrayref->[0] ;
							my $new_goldfield = $res_arrayref->[1] ;
							my $new_todofield = $res_arrayref->[2] ;
							my $stamp         = $res_arrayref->[3] ;

							# traçabilité de la séquence actuelle
							$trace_str .= $stamp ;

							if ($local_debug) {
								warn "=====<$trace_str\n" ;
								warn "\tg:$new_goldfield\n" ;
								warn "\tt:$new_todofield\n" ;
							}

							if ($compare_success) {
								$diagnostic_str = "OUI_avec:${trace_str}OK" ;
								last COMPARE_THIS_FIELD ;
							}
							else {
								# valeurs restaurées ensuite si la combo n'a pas marché
								$test_goldfield = $new_goldfield ;
								$test_todofield = $new_todofield ;
							}
						} # fin combo
					}

					# on a tenté toute les comparaisons possible et toutes leurs combinaisons
					$diagnostic_str = "NON_diff" if (not $compare_success) ;

				} # fin for k

			} # fin else

			warn "(doc-$bname) g:$gb_k, t:$tb_l [".sprintf("%4s",$key)."] => $diagnostic_str\n" if $debug ;
			
			push (@result, $diagnostic_str) ;
		}
	}

	# =================================================================
	# =================================================================
	# TODO isoler la procédure names ci-dessous
	# =================================================================
	# pour les auteurs: comparaison supplémentaire et édition d'une colonne de résumé
	my $nb_g_names = scalar(@{$gb_data->{'names'}}) ;
	my $nb_t_names = scalar(@{$tb_data->{'names'}}) ;
	
	# marqueurs des cas résolus (pas forcément succès strict car match relaché y sera inscrit)
	my @t_names_done = (0) x ($nb_t_names) ;
# 	my @g_names_done = (0) x ($nb_g_names) ; # pour debugA

	# résultats principaux (nb vraiment aligné) pour rappel et précision
	my $nb_ok_names = 0 ;

	# boucle (goldnames)
	for my $gname (@{$gb_data->{'names'}}) {
		# tname précédent pour pouvoir vérifier si le nom n'a pas été cxitoupé en 2
		my $tprevious_clean = "" ;

		# sous-boucle (todonames)
		my $tnid = -1 ;
		for my $tname (@{$tb_data->{'names'}}) {
			
			#debug
			#~ warn("Comparaison: G'$gname' | T'$tname'") ;

			$tnid++ ;
			next if $t_names_done[$tnid] ;
			# comparaison principale : suffit pour rappel et précision
			# ---------------------------------------------------------
			if (clean_compare($gname, $tname)) {
				$t_names_done[$tnid] = 1 ;
				$nb_ok_names ++ ;
				last ;
			}
		}

	}
	# 3 colonnes de diagnostic principal
	push (@result, ($nb_g_names, $nb_t_names, $nb_ok_names)) ;

	# détail du processus pour debug
 	#~ warn "GOLDNAMES: ---------------------------------------------\n" ;
 	#~ warn Dumper $gb_data->{'names'} ;
 	#~ warn Dumper \@g_names_done ;
 	#~ warn "TODONAMES: -----------\n" ;
 	#~ warn Dumper $tb_data->{'names'} ;
 	#~ warn Dumper \@t_names_done ;

	# =================================================================
	
	# détail du résultat pour toute la refbib =========================
	#~ warn Dumper \@result ;  # =========================================

	# join("\t", map {$_ = '' if not(defined($_))} @result) ;
	return join("\t",@result) ; 
}







# Fonctions de comparaisons de 2 chaines
# =======================================

# NB: pour pouvoir être mises bout à bout, toutes ces fonctions :
#    - prennent en entrée 2 chaînes et une ligne (chaine de caractère) d'historique aka $trace_str
#    - renvoient le résultat de leur comparaison, les 2 chaînes éventuellement modifiées et ajoutent leur 'tampon' sur la chaîne d'historique



# "erreurs" fréquentes dans cermine qui n'a pas de déhyphénisation comme grobid
# sub dehyphen {
# 	my $string = shift ;
# 	$string =~ s/(?<=\w)- //g ;
# 	return $string ;
# }


# Cumul des fonctions qui suivent (avec lc() en plus) pour comparaison rapide au niveau macro
# (retourne simplement un booléen)
sub clean_compare {
	my $gold_str = shift ;
	my $todo_str = shift ;

	# $success doit être False par défaut !
	my $success = 0 ;
	
	my $glen = length($gold_str) ;
	my $tlen = length($todo_str) ;
	
	# incomparable
	return $success if ($glen == 0 or $tlen == 0) ;
	# trop différents
	return $success if ($glen > 2 * $tlen or $tlen > 2 * $glen) ;
	
	
	# tampon du dernier opérateur effectué (pour debug, a priori non affiché)
	my $log_stamp = "" ;
	
	#~ warn "G0=".$gold_str ;
	#~ warn "T0=".$todo_str ;
	
	# séquence d'opérateurs de simplification de la chaîne avant comparaison
	# ---------------------------------------------------------------------------------
	# 3 simplifications canoniques : OCeeRs..unlig..punct
	($success, $gold_str, $todo_str, $log_stamp) = @{compare_ocrerrors($gold_str, $todo_str)} ;
	return $success if ($success) ;
	($success, $gold_str, $todo_str, $log_stamp) = @{compare_unligatures($gold_str, $todo_str)} ;
	return $success if ($success) ;
	($success, $gold_str, $todo_str, $log_stamp) = @{compare_simple_punctuation($gold_str, $todo_str)} ;
	return $success if ($success) ;
	
	my $new_gold_str = "" ;
	my $new_todo_str = "" ;
	# Opérateurs (optionnels) sur les accents 
	if ($UNACCENTS) {
		# joinacc..unacc (/!\ lents surtout compare_unaccent)
		($success, $new_gold_str, $new_todo_str, $log_stamp) = @{compare_joinaccent($gold_str, $todo_str)} ;
		return $success if ($success) ;
		($success, $new_gold_str, $new_todo_str, $log_stamp) = @{compare_unaccent($new_gold_str, $new_todo_str)} ;
		return $success if ($success) ;
	}
	else {
		$new_gold_str = $gold_str ;
		$new_todo_str = $todo_str ;
	}
	
	#~ warn "G1=".$new_gold_str ;
	#~ warn "T1=".$new_todo_str ;
	
	# opérations supplémentaires pour comparaison radicale
	# -----------------------------------------------------
	$new_gold_str = lc($new_gold_str) ;
	$new_todo_str = lc($new_todo_str) ;
	# [^a-z0-9] au lieu de \W pour éviter les caras non-ascii quelque soit la locale de \W
	# (car les caras non-ascii sont plus souvent mal transcrits à l'ocr ou conversion)
	$new_gold_str =~ s/[^a-z0-9]+//g ;
	$new_todo_str =~ s/[^a-z0-9]+//g ;
	
	#~ warn "G2=".$new_gold_str ;
	#~ warn "T2=".$new_todo_str ;
	
	$success = ($new_gold_str eq $new_todo_str) ;
	return $success if $success ;

	# enfin match regexp si les champs sont de longueurs suffisantes et comparables
	# ------------------------------------------------------------------------------
	# on autorise 30% de chaîne en plus ou en moins sur les chaînes de plus de 5 caractères
	if (($glen > 5) && ($tlen > 5) && ($glen/$tlen > 0.7) && ($glen/$tlen < 1.3)) {
		$success = (($new_gold_str =~ /$new_todo_str/) || ($new_todo_str =~ /$new_gold_str/)) ;
# 		if ($success) {
# 			warn "MATCH: sb_longueur_proche todo avant: '$todo_str'\n" ;
# 			warn "MATCH: sb_longueur_proche gold avant: '$gold_str'\n" ;
# 			warn "MATCH: sb_longueur_proche todo après: '$new_todo_str'\n" ;
# 			warn "MATCH: sb_longueur_proche gold après: '$new_gold_str'\n" ;
# 			warn "success = '$success'\n" ;
# 		}
	}

	return $success ;
}


sub compare_little_shorter {
	my $gstr = shift ;
	my $tstr = shift ;

	my @ret_vals = () ;

	# TODO on pourrait éventuellement faire un test de longueurs comparables mais on est déjà au sein d'une refbib alignée donc ce n'est pas nécessaire

	# la sous-chaine ne sera pas un indice assez fort si elle est trop courte
	if (length($tstr) <= 5) {
		@ret_vals = (0, $gstr,$tstr,"mt(5-).") ;
	}
	else {
		my $todo_re = quotemeta($tstr) ;

		# TEST proportionnel : on autorise un caractère en plus pour chaque 5 caractères de longueur totale
		my $success = ((length($gstr) <= (length($tstr) + int(length($tstr)/5))) && ($gstr =~ /$todo_re/)) ;

		my $stamp = $SUBSTR_INFO ? "raccourci(".length($gstr)."-".(length($gstr) - length($tstr)).")." : "raccourci." ;

		if ($success && $debug) {
			warn "gold : $gstr\n" ;
			warn "todo : $tstr\n" ;
		}

		@ret_vals = ($success, $gstr, $tstr, $stamp) ;
	}
	return \@ret_vals ;
}

sub compare_little_longer {
	my $gstr = shift ;
	my $tstr = shift ;

	my @ret_vals = () ;
	# la sous-chaine ne sera pas un indice assez fort si elle est trop courte
	if (length($gstr) <= 5) {
		@ret_vals = (0, $gstr,$tstr,"mg(5-).") ;
	}
	else {
		my $gold_re = quotemeta($gstr) ;

		# TEST proportionnel : on autorise un caractère en plus pour chaque 5 caractères de longueur totale
		my $success = ((length($tstr) <= (length($gstr) + int(length($gstr)/5)   )) && ($tstr =~ /$gold_re/)) ;


		my $stamp = $SUBSTR_INFO ? "allongé(".length($gstr)."+".(length($tstr) - length($gstr)).")." : "allongé." ;

		@ret_vals = ($success, $gstr, $tstr, $stamp) ;
	}
	return \@ret_vals ;
}

# 
sub compare_simple_punctuation {
	my $gstr = shift ;
	my $tstr = shift ;

	for my $string ($gstr, $tstr) {
		# tous les espaces alternatifs --> espace
		$string =~tr/\x{00A0}\x{1680}\x{180E}\x{2000}\x{2001}\x{2002}\x{2003}\x{2004}\x{2005}\x{2006}\x{2007}\x{2008}\x{2009}\x{200A}\x{200B}\x{202F}\x{205F}\x{3000}\x{FEFF}/ / ;
		
		# la plupart des tirets alternatifs --> tiret normal (dit "du 6")
		# (dans l'ordre U+002D U+2010 U+2011 U+2012 U+2013 U+2014 U+2015 U+2212 U+FE63)
		$string =~ s/[‐‑‒–—―−﹣]/-/go ;
		
		# Guillemets
		# ----------
		# la plupart des quotes doubles --> "
		$string =~ tr/“”„‟/"/ ;   # U+201C U+201D U+201E U+201F
		$string =~ s/« ?/"/go ;    # U+20AB plus espace éventuel après
		$string =~ s/ ?»/"/go ;    # U+20AB plus espace éventuel avant
		
		# la plupart des quotes simples --> "
		$string =~ tr/‘’‚‛/"/ ;   # U+2018 U+2019 U+201a U+201b
		$string =~ s/‹ ?/"/go ;    # U+2039 plus espace éventuel après
		$string =~ s/ ?›/"/go ;    # U+203A plus espace éventuel avant
	}

	my $success = $gstr eq $tstr ;
	my $stamp = "punct." ;
	my @ret_vals = ($success, $gstr, $tstr, $stamp) ;
	return \@ret_vals ;
}

# remplace les variantes OCR courantes par une des variantes (tj la même)
# ex: s/m|rn|nn/m/g    (en fait simplifié en s/rn|nn/m/g)
# ex: s/6|ö|é/6/g
sub compare_ocrerrors {
	my $gstr = shift ;
	my $tstr = shift ;

	for my $string ($gstr, $tstr) {
		# c'est visuel... on écrase le niveau de détail des cara 
		
		# attention à ne pas trop écraser tout de même !
		# par exemple G0=Munier  T0=Muller doivent rester différents
		
		
		# ex: y|v -> v
		$string =~ s/nn|rn/m/g ; # /!\ 'nn' à traiter avant 'n'
		$string =~ s/ü|ti|fi/ii/g ; # /!\ '*i' à traiter avant 'i'
		
		$string =~ s/O|o|ø|C\)/0/g ;
		$string =~ s/1|I|l|i/1/g ;
		$string =~ s/f|t|e/c/g ;    # f|c|e ?
		$string =~ s/y/v/g ;
		$string =~ s/S/5/g ;
		#~ $string =~ s/c/e/g ;
		$string =~ s/E/B/g ;
		$string =~ s/R/K/g ;
		$string =~ s/n|u/a/g ;
		$string =~ s/\]/J/g ;
		
		# diacritiques et cara "spéciaux"
		$string =~ s/\[3/β/g ;
		$string =~ s/é|ö/6/g ;
		
		$string =~ s/ç/q/g ;
	}

	my $success = $gstr eq $tstr ;
	my $stamp = "OCeeRs." ;
	my @ret_vals = ($success, $gstr, $tstr, $stamp) ;
	return \@ret_vals ;
}

sub compare_rmhyphen {
	my $gstr = shift ;
	my $tstr = shift ;

	for my $string ($gstr, $tstr) {
		$string =~ s/(?<=\w)- ?(?=\w)//g ;
	}

	my $success = $gstr eq $tstr ;
	my $stamp = "rmhyph." ;
	my @ret_vals = ($success, $gstr, $tstr, $stamp) ;
	return \@ret_vals ;
}


sub compare_joinhyphen {
	my $gstr = shift ;
	my $tstr = shift ;

	for my $string ($gstr, $tstr) {
		$string =~ s/(?<=\w)- /-/g ;
	}

	my $success = $gstr eq $tstr ;
	my $stamp = "joinhyph." ;
	my @ret_vals = ($success, $gstr, $tstr, $stamp) ;
	return \@ret_vals ;
}


sub compare_unligatures {
	my $gstr = shift ;
	my $tstr = shift ;

	for my $string ($gstr, $tstr) {
		$string =~ s/Ꜳ/AA/g ;
		$string =~ s/ꜳ/aa/g ;
		$string =~ s/Æ/AE/g ;
		$string =~ s/æ/ae/g ;
		$string =~ s/Ǳ/DZ/g ;
		$string =~ s/ǲ/Dz/g ;
		$string =~ s/ǳ/dz/g ;
		$string =~ s/ﬃ/ffi/g ;
		$string =~ s/ﬀ/ff/g ;
		$string =~ s/ﬁ/fi/g ;
		$string =~ s/ﬄ/ffl/g ;
		$string =~ s/ﬂ/fl/g ;
		$string =~ s/ﬅ/ft/g ;
		$string =~ s/Ĳ/IJ/g ;
		$string =~ s/ĳ/ij/g ;
		$string =~ s/Ǉ/LJ/g ;
		$string =~ s/ǉ/lj/g ;
		$string =~ s/Ǌ/NJ/g ;
		$string =~ s/ǌ/nj/g ;
		$string =~ s/Œ/OE/g ;
		$string =~ s/œ/oe/g ;
		$string =~ s//oe/g ;   # U+009C (cara contrôle vu comme oe)
		$string =~ s/ﬆ/st/g ;
		$string =~ s/Ꜩ/Tz/g ;
		$string =~ s/ꜩ/tz/g ;

	}

	my $success = $gstr eq $tstr ;
	my $stamp = "unlig." ;

	my @ret_vals = ($success, $gstr, $tstr, $stamp) ;

	return \@ret_vals ;
}


sub compare_normalise_punct {
	my $gstr = shift ;
	my $tstr = shift ;

	for my $string ($gstr, $tstr) {
		# la plupart des tirets alternatifs --> tiret normal (dit "du 6")
		# (dans l'ordre U+002D U+2010 U+2011 U+2012 U+2013 U+2014 U+2015 U+2212 U+FE63)
		$string =~ s/[‐‑‒–—―−﹣]/-/g ;

		# le macron aussi parfois comme tiret
		# (mais compatibilité avec desaccent ?)
		$string =~ s/\x{00af}/-/g ;

		# Guillemets
		# ----------
		# la plupart des quotes doubles --> " QUOTATION MARK
		$string =~ tr/“”„‟/"/ ;   # U+201C U+201D U+201E U+201F
		$string =~ s/« ?/"/g ;    # U+20AB plus espace éventuel après
		$string =~ s/ ?»/"/g ;    # U+20AB plus espace éventuel avant

		# la plupart des quotes simples --> ' APOSTROPHE
		$string =~ tr/‘’‚`‛/'/ ;   # U+2018 U+2019 U+201a U+201b
		$string =~ s/‹ ?/'/g ;    # U+2039 plus espace éventuel après
		$string =~ s/ ?›/'/g ;    # U+203A plus espace éventuel avant

		# deux quotes simples (préparées ci-dessus) => une double
		$string =~ s/''/"/g ;
	}

	my $success = $gstr eq $tstr ;
	my $stamp = "norpun." ;
	my @ret_vals = ($success, $gstr, $tstr, $stamp) ;

	return \@ret_vals ;
}


sub compare_normalise_space {
	my $gstr = shift ;
	my $tstr = shift ;

	for my $string ($gstr, $tstr) {
		# tous les caractères de contrôle (dont \t = \x{0009}, \n = \x{000A} et \r = \x{000D}) --> espace
		$string =~ tr/\x{0000}\x{0001}\x{0002}\x{0003}\x{0004}\x{0005}\x{0006}\x{0007}\x{0008}\x{0009}\x{000A}\x{000B}\x{000C}\x{000D}\x{000E}\x{000F}\x{0010}\x{0011}\x{0012}\x{0013}\x{0014}\x{0015}\x{0016}\x{0017}\x{0018}\x{0019}\x{001A}\x{001B}\x{001C}\x{001D}\x{001E}\x{001F}\x{007F}/ / ;

		# Line separator
		$string =~ tr/\x{2028}/ / ;

		# parfois quote parfois caractère de contrôle
		$string =~ tr/\x{0092}/ / ;
		## tr/\x{0092}/'/ ;

		# tous les espaces alternatifs --> espace
		$string =~ tr/\x{00A0}\x{1680}\x{180E}\x{2000}\x{2001}\x{2002}\x{2003}\x{2004}\x{2005}\x{2006}\x{2007}\x{2008}\x{2009}\x{200A}\x{200B}\x{202F}\x{205F}\x{3000}\x{FEFF}/ / ;

		# "supprespaces" : pour finir on enlève les espaces en trop
		$string =~ s/\s+/ /g ;
		$string =~ s/^\s//g ;
		$string =~ s/\s$//g ;
	}

	my $success = $gstr eq $tstr ;
	my $stamp = "norspa." ;
	my @ret_vals = ($success, $gstr, $tstr, $stamp) ;
	return \@ret_vals ;
}

# en l'état c'est la fonction qui prend le plus de temps 
# cf. analyse/soft/dprofpp_out.eval_xml_refbibs.tab
sub compare_unaccent {
	my $gstr = shift ;
	my $tstr = shift ;

	for my $string ($gstr, $tstr) {
		# toutes les accentuées possibles sur leur équivalent ASCII
		# NB : on utilise s/// car tr/// est plus difficile à utiliser avec l'utf8
		$string =~ s/[ÀÁÂÃÄÅĄĀĂ]/A/go ;
		$string =~ s/[àáâãäåąāă]/a/go ;
		$string =~ s/[ÇĆĈĊČ]/C/go ;
		$string =~ s/[çćĉċč]/c/go ;
		$string =~ s/[ĎĐ]/D/go ;
		$string =~ s/[ďđ]/d/go ;
		$string =~ s/[ÈÉÊËĘĒĔĖĚ]/E/go ;
		$string =~ s/[èéêëęēĕėě]/e/go ;
		$string =~ s/[ĜĞĠĢ]/G/go ;
		$string =~ s/[ĝğġģ]/g/go ;
		$string =~ s/[ĤĦ]/H/go ;
		$string =~ s/[ĥħ]/h/go ;
		$string =~ s/[ÌÍÎÏĨĪĬĮİ]/I/go ;
		$string =~ s/[ìíîïĩīĭįı]/i/go ;
		$string =~ s/[Ĵ]/J/go ;
		$string =~ s/[ĵ]/j/go ;
		$string =~ s/[Ķ]/K/go ;
		$string =~ s/[ķ]/k/go ;
		$string =~ s/[ŁĹĻĽĿ]/L/go ;
		$string =~ s/[łĺļľŀ]/l/go ;
		$string =~ s/[ÑŃŅŇ]/N/go ;
		$string =~ s/[ñńņň]/n/go ;
		$string =~ s/[ÒÓÔÕÖØŌŎŐ]/O/go ;
		$string =~ s/[òóôõöøōŏő]/o/go ;
		$string =~ s/[ŔŖŘ]/R/go ;
		$string =~ s/[ŕŗř]/r/go ;
		$string =~ s/[ŚŜŞŠ]/S/go ;
		$string =~ s/[śŝşš]/s/go ;
		$string =~ s/[ŢŤŦ]/T/go ;
		$string =~ s/[ţťŧ]/t/go ;
		$string =~ s/[ÙÚÛÜŨŪŬŮŰŲ]/U/go ;
		$string =~ s/[ùúûüũūŭůűų]/u/go ;
		$string =~ s/[Ŵ]/W/go ;
		$string =~ s/[ŵ]/w/go ;
		$string =~ s/[ŸÝŶ]/Y/go ;
		$string =~ s/[ÿýŷ]/y/go ;
		$string =~ s/[ŹŻŽ]/Z/go ;
		$string =~ s/[źżž]/z/go ;
	}

	my $success = $gstr eq $tstr ;
	my $stamp = "unacc." ;
	my @ret_vals = ($success, $gstr, $tstr, $stamp) ;
	return \@ret_vals ;
}


sub compare_joinaccent {
	my $gstr = shift ;
	my $tstr = shift ;

	for my $string ($gstr, $tstr) {
		# match sur les fragments /lettre + accent/
		# avec la substitution appelant une fonction
		# ------------------------------------------
		$string =~ s/([A-Za-z])([\x{0300}-\x{036F}`¨¯´¸ˇ˘˙˚\x{02db}˜˝^\x{ff3e}\x{ff40}\x{ffe3}])/combine_accent($1,$2)/eg ;
	}

	my $success = $gstr eq $tstr ;
	my $stamp = "joinacc.." ;
	my @ret_vals = ($success, $gstr, $tstr, $stamp) ;
	return \@ret_vals ;
}

# letter + combining accent ==> accented letter
# par exemple : n (U+006E) +  ́(U+0301) ==> ń (U+0144)
# NB on suppose que l'entrée a été decode et la sortie devra être encode(UTF-8)
sub combine_accent {
	my $letter = shift ;
	my $accent = shift ;

	# debug
# 	warn Dumper [$letter,$accent] ;

	# valeur à retourner
	my $combined_result = "" ;

	# lettre et caractère d'accentuation directement combinable dit 'combining accent'
	# --------------------------------------------------------------------------------
	if ($accent =~ /^[\x{0300}-\x{036F}]$/) {
# 		warn "comb" ;
		# lettre + combining accent
		$combined_result = Unicode::Normalize::NFC($letter.$accent) ;
	}
	# lettre et caractère d'accentuation séparé dit 'spacing accent'
	# ----------------------------------------------------------
	else {
# 		warn "spac" ;
		my $combining_equivalent = spacing_to_combining_accent($accent) ;

		if ($combining_equivalent eq 'UNKNOWN_ACCENT') {
			warn "combine_accent():unknown acct removed" ;
			$combined_result = $letter ;
		}
		else {
			$combined_result = Unicode::Normalize::NFC($letter.$combining_equivalent) ;
		}
	}

# 	warn "\ncombined_result= '$combined_result'\n" ;

	# a single accented char
	return $combined_result ;
}


# on cherche le 'combining accent' équivalent au 'spacing accent'
#
# par exemple
# \x{00B4} (class [Sk]) => \x{0301} (class [Mn])
# "ACUTE ACCENT"        => "COMBINING ACUTE ACCENT"
#
# NB on suppose que l'entrée a été decode et la sortie devra être encode(UTF-8)
sub spacing_to_combining_accent {
	# spacing accent = (any element from Unicode [Sk] category
	#                   that has an equivalent combining accent char)
	# --- avec 'compatibility decomposition' ---
	# 00A8   DIAERESIS
	# 00AF   MACRON
	# 00B4   ACUTE ACCENT
	# 00B8   CEDILLA
	# 02D8   BREVE
	# 02D9   DOT ABOVE
	# 02DA   RING ABOVE
	# 02DB   OGONEK
	# 02DC   SMALL TILDE
	# 02DD   DOUBLE ACUTE ACCENT
	# --- sans 'compatibility decomposition' ---
	# 005E   CIRCUMFLEX ACCENT
	# 0060   GRAVE ACCENT
	# 02C7   CARON
	# FF3E   FULLWIDTH CIRCUMFLEX ACCENT
	# FF40   FULLWIDTH GRAVE ACCENT
	# FFE3   FULLWIDTH MACRON
	my $accent_char = shift ;

# 	warn "inside s2ca with '$accent_char'\n" ;

	# caractère cherché
	my $combining_accent = "" ;

	my $decomp = "" ;

	# pour plusieurs spacing accents, Unicode::Normalize::NFKD donne la
	# "compatibility decomposition" en un espace et l'accent combining
	$decomp = Unicode::Normalize::NFKD($accent_char);

	my @one_two = split(//, $decomp) ;

	# si c'est le cas :
	if ((scalar(@one_two) == 2) && ($one_two[0] eq ' ')) {
		$combining_accent = $one_two[1] ;
	}
	# sinon on le fait nous-mêmes sur liste empirique
	else {
		# 0060 GRAVE ACCENT  -------------------------> 0300 COMBINING GRAVE ACCENT
		# 005E CIRCUMFLEX ACCENT  --------------------> 0302 COMBINING CIRCUMFLEX ACCENT
		# 02C7 CARON  (hacek)  -----------------------> 030C COMBINING CARON
		# FF40 FULLWIDTH GRAVE ACCENT  ---------------> 0300 COMBINING GRAVE ACCENT
		# FF3E FULLWIDTH CIRCUMFLEX ACCENT  ----------> 0302 COMBINING CIRCUMFLEX ACCENT
		# FFE3 FULLWIDTH MACRON  ---------------------> 0304 COMBINING MACRON
		$combining_accent = $accent_char ;
		$combining_accent =~ tr/\x{0060}\x{005e}\x{02c7}\x{ff40}\x{ff3e}\x{ffe3}/\x{0300}\x{0302}\x{030c}\x{0300}\x{0302}\x{0304}/ ;
	}

	# vérification du combining accent
	# il devrait être dans range [768-879] = hex range [300-36F]
	my $decimal_cp = unpack('U*', $combining_accent) ;
	if ($decimal_cp < 768 || $decimal_cp > 879) {
		warn "found no equivalent in hex [0300-036F] for second char, codepoint '".sprintf("%x",$decimal_cp)."'\n" ;
		return "UNKNOWN_ACCENT" ;
	}
	else {
		# a single *non-spacing* char
		return $combining_accent ;
	}
}

############### utilitaires ############################################

# transformer le chemin d'input en clé unique
# NB le chemin du doc à évaluer reflète le chemin du pdf originel
# alors que le chemin du doc de ref celui du XML de la base
# donc ATTENTION lorqu'ils ne sont pas faits pareils (ex: corpus OUP)

# pensé pour tous les docs sont dans un même dossier (structure 'flat')
# ==> le basename suffira.
sub path_to_dockey {
	my $path   = shift ;
	my $ext    = shift ;

	# document key for hashes and ID
	my $kname = $path ;

	# use File::Basename
	$kname = fileparse($path,(".$ext")) ;

	return $kname ;
}

# Sélectionne une info à loguer à l'intérieur de $@
# --------------------------------------------------
# On cherche l'info la plus pertinente parmi plusieurs
# lignes d'un log hérité en favorisant les lignes longues
# et les lignes vers la fin du log
sub errlog {
	my $at = shift || "=inco=" ;      # lignes d'erreur $@ héritées
	my $path = shift || "" ;          # nom du fichier
	my $off = shift || 8 ;            # offset en nb d'espaces

	my $to_replace = quotemeta($path) ;

	$at =~ s/$to_replace/<INFILE>/g ;

	my @errors = split(/\n/,$at) ;
	my $best_line = "" ;
	my $best_score = 0 ;
	my $i = 0 ;
	for my $line (@errors) {
		# warn "orig >> $line\n" ;
		$i++ ;
		my $test = $line ;
		$test =~ s/\s+/ /g ;

		# warn "--> $test\n" ;
		my $score = log(length($test)+1) * sqrt($i) ;
		# warn "$i score = $score\n" ;
		if ($score >= $best_score) {
			$best_score = $score ;
			$best_line = $line ;
		}
	}
	return " "x$off."[$best_line]\n" ;   # message mis en forme pr warn
}

########################################################################


# renvoie le message d'aide
sub HELP_MESSAGE {
	print <<EOT;
--------------------------------------------------------------------
|  Évaluation de refbibs obtenues TEI sur un corpus gold TEI aussi |
|------------------------------------------------------------------|
| Usage                                                            |
| =====                                                            |
|   eval_xml_refbibs.pl -x TEI-XMLs/à/évaluer/                     |
|                       -g TEI-XMLs/de/référence/ > resultats.tab  |
|                                                                  |
|  NB: il faut les mêmes noms de fichiers (sauf .ext) des 2 côtés  |
|                                                                  |
| Options et arguments                                             |
| ====================                                             |
|   -h  --help            afficher cet écran                       |
|   -x  --xmldir path/    dossier des XML à évaluer (sortie outil) |
|   -g  --golddir path/   dossier du corpus de référence           |
|   -e  --extension       extension dans xmldir [refbibs.tei.xml]  |
|                                                                  |
|   -d  --debug           infos de debogage au cours du traitement |
|   -l  --logreport fic   ajouter 1 ligne de rapport-éval dans fic |
|   -r  --regreport eID   si logreport, mentionner un identifiant  |
|   -i  --iddump          sortir à part une table IDS <=> FICHIERS |
|   -s  --substrinfo      infos supplémentaires si match substr    |
|   -u  --unaccents       activer la désaccentuation préalable aux |
|                         comparaisons de chaînes (+ ~.1 R & ~.3 P)|
|                         mais temps de traitement x 2             |
|   -n  --numcount        afficher un compteur durant traitement   |
|                                                                  |
| Sortie:                                                          |
|      STDERR : statistiques sur le parsing (et log d'erreurs)     |
|      STDOUT : tableau csv de la comparaison par champs           |
                pour chaque paires de refbibs alignées             |
|------------------------------------------------------------------|
|  © 2014 Inist-CNRS (ISTEX)          romain.loth at inist dot fr  |
--------------------------------------------------------------------
EOT
	exit 0 ;
}


# STOCK

# $pub_type : contenus rencontrés (et leur fréquence) :
# -----------------------------------------------------
#   79184 journal         9 other-ref        3 weblink
#    6076 book            8 undeclared       1 msds
#    3105 other           6 report           1 inbook
#     106 webpage         6 patent           1 discussion
#      84 confproc        6 gov              1 computer-program
#      11 web             5 thesis           1 commun

# pour mémoire quelques correspondances au niveau des champs
# ----------------------------------------------------------
# my %correspondances = (
#
# 	'article_title' => { 'gold' => ['article-title'],
# 						 'eval' => ['tei:analytic/tei:title[@level="a"]'] },
# 	'journal_title' => { 'gold' => ['source'] ,
# 						 'eval' => ['tei:monogr/tei:title[@level="j"]'] },
#
# 	'vol'           => { 'gold' => ['volume'],
# 						 'eval' => ['tei:monogr/tei:imprint/tei:biblScope[@unit="volume"]'] },
#
# 	'issue'         => { 'gold' => ['issue'],
# 						 'eval' => ['tei:monogr/tei:imprint/tei:biblScope[@unit="issue"]'] },
#
# 	'fpage'         => { 'gold' => ['fpage'],
# 						 'eval' => ['tei:monogr/tei:imprint/tei:biblScope[@unit="fpage"]'] },
#
# 	'lpage'         => { 'gold' => ['lpage'],
# 						 'eval' => ['tei:monogr/tei:imprint/tei:biblScope[@unit="lpage"]'] },
#
# 	'publisher'     => { 'gold' => ['publisher-name'],
# 						 'eval' => ['tei:monogr/tei:imprint/tei:publisher'] },
# 	'publisher-loc' => { 'gold' => ['publisher-loc'],
# 						 'eval' => ['tei:monogr/tei:imprint/tei:pubPlace'] },
#
# 	'year'          => { 'gold' => ['year'],                     # todo substr($year,0,4 ou 5 si 2010a)
# 						 'eval' => ['tei:monogr/tei:imprint/tei:date/@when'] },  # idem
#
# 	'weblink'       => { 'gold' => ['.//ext-link[@ext-link-type=uri]'],
# 						 'eval' => [undef] },      # les liens se retrouvent souvent dans la fin du tei:title!
# ) ;
