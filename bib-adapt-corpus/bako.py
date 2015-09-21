#! /usr/bin/python3
"""
bib-adapt-corpus ou bako
------------------------
5 commands:
 make_set(corpus_name)                    <= sampler, corpus conversion
 make_trainers(corpus, GB, [modeltype])   <= grobid.createTraining, ragreage, install in resources
 
 # à l'avenir commandes suivante dans le cycle (pour l'instant en shell)
 #TODO train_and_store(model, modeltype)  <= grobid-trainer, store in models dir
 #TODO eval_report(model)                 <= eval_xml_refbibs_lite, eval_results_lite.r
 #TODO suggest_install_to_vp(model)       <= juste un echo de la ligne rsync adéquate
"""
__author__    = "Romain Loth"
__copyright__ = "Copyright 2014-5 INIST-CNRS (ISTEX project)"
__license__   = "LGPL"
__version__   = "0.2"
__email__     = "romain.loth@inist.fr"
__status__    = "Dev"

# imports
from os              import path, mkdir, rename
from sys             import stderr, argv
from configparser    import ConfigParser
from site            import addsitedir     # pour imports locaux
from re              import search, match
from subprocess      import PIPE, Popen    # pour l'appel de grobid
                                           # en training proprement dit
from argparse  import ArgumentParser, RawDescriptionHelpFormatter


# imports locaux
addsitedir('lib')

# "libconsulte" istex-rd
import api
import sampler
from corpusdirs import Corpus
                     # Corpus => bnames, cdir, cols, shelfs...

# ----------------------------------------------------------------------
# lecture de fichier config local
CONF = ConfigParser()
conf_path = 'local_conf.ini'
conf_file = open(conf_path, 'r')
CONF.read_file(conf_file)
conf_file.close()

# ----------------------------------------------------------------------
# Structure de base du corpus ("shelf" pour "étagère")
BSHELFS = {
  # basic set ----------------------------------------------------------
  'PDF0': {'d':'A-pdfs',       'ext':'.pdf',      'api':'fulltext/pdf'},
  'XMLN': {'d':'B-xmlnatifs',  'ext':'.xml',      'api':'metadata/xml'},
  'GTEI': {'d':'C-goldxmltei', 'ext':'.tei.xml'},
  # --------------------------------------------------------------------
}
# valeurs sous ['d'] ==> nom des dossiers dans corpora/<nom_corpus>/data

# Noms "humains" des structures de base et de training
SHELF_NAMES = {
	# basic set -------------------------------------
	'PDF0' : "PDFs originaux",
	'XMLN' : "XMLs natifs",
	'GTEI' : "TEI-XMLs gold",
	
	# bibzone = segmentation -------------------------
	'BZRTX': "RAW TEXTS pour bibzone",
	'BZRTK': "RAW TOKENS pour bibzone",
	'BZTEI': "TRAIN TEIs pour bibzone",
	
	# biblines = referenceSegmentation ---------------
	'BLRTX': "RAW TEXTS pour biblines",
	'BLRTK': "RAW TOKENS pour biblines",
	'BLTEI': "TRAIN TEIs pour biblines",
	
	# bibfields = citations --------------------------
	'BFRTX': "RAW TEXTS pour bibfields",
	'BFTEI': "TRAIN TEIs pour bibfields",
	
	# authornames = name/citation ---------------------
	'AURTX': "RAW TEXTS pour authornames",
	'AUTEI': "TRAIN TEIs pour authornames",
	}

# ----------------------------------------------------------------------
# Fonction CLI

def bako_sub_args(arglist=None):
	"""
	Preparation du namespace args contenant les  arguments de 
	la ligne de commande pour main()
	"""
	top_parser = ArgumentParser(
		formatter_class=RawDescriptionHelpFormatter,
		description="""
-----------------------------------------------------------
 A corpus manager and training operator for grobid-trainer
-----------------------------------------------------------""",
		#~ usage="""
	#~ bako make_set /corpus_name/ /size/ [/specific api query/]
	#~ bako make_set --from_table chemin/d/une/metatable
	#~ bako take_set /corpus_name/
	#~ 
	#~ bako make_trainers /corpus_name/ --for /model1/ [/model2/ ...]
	#~ bako make_training --corpora /corpus/ [/corpus2/ ...]
	                   #~ --target /model1/ [model2 model3...]
	#~ bako models pick
	#~ bako models eval  /modelname/
	#~ bako models install
		#~ """,
		epilog="""
© 2015 :: romain.loth at inist.fr :: Inist-CNRS (ISTEX)
"""
		)
	
	sub_args = top_parser.add_subparsers(
		title='subcommands',
		help='additional help')
	
	# MAKE_SET ---- sous-commande (1) ----
	args_mkset = sub_args.add_parser(
		'make_set',
		usage="""
  bako make_set corpus_name [--size 20] [--constraint "lucene query"]
  bako make_set corpus_name --from_table infos_table_prealable.tab
		""",
		help="préparer un corpus")
	
	# pour savoir quelle commande ça lance
	args_mkset.set_defaults(func=make_set)
	
	# mode normal
	# argument positionnel (obligatoire) : le nom du corpus
	args_mkset.add_argument(
		'corpus_name',
		type=str,
		help="nom du nouveau corpus à créer"
	)
	
	# option 1: la taille
	args_mkset.add_argument(
		'--size',
		type=int,
		required=False,
		help="taille du nouveau corpus à créer (par déf: 10)"
	)
	
	# option 2: contrainte lucene
	args_mkset.add_argument(
		'--constraint',
		metavar='qualityIndicators.refBibsNative:true',
		type=int,
		help="requête lucene comme contrainte sur le corpus"
	)
	
	# ??? souhaitable ???
	#~ args_mkset.add_argument(
		#~ '--type',
		#~ metavar='gold',
		#~ choices="gold|train",
		#~ help="type du corpus à créer (par défaut = gold) "
		#~ )
	
	# mode "import" avec une table
	args_mkset.add_argument(
		'--from_table',
		type=str,
		help='mode "import": table d\'un corpus préexistant'
	)
	
	# TAKE_SET ---- sous-commande (2) ----
	args_tkset = sub_args.add_parser('take_set', help="lire un corpus")
	
	# pour savoir quelle commande ça lance
	args_tkset.set_defaults(func=take_set)
	
	# un seul argument positionnel : le nom du corpus
	args_tkset.add_argument(
		'corpus_name',
		type=str,
		help="nom du corpus à reprendre"
	)
	
	# def make_trainers(corpus_name, model_types=None, just_rag=False):
	
	# MAKE_TRAINERS ---- sous-commande (3) ----
	args_mktrs = sub_args.add_parser('make_trainers', help="préparer des corpus d'entraînement (dossiers D-*)")
	
	# pour savoir quelle commande ça lance
	args_mktrs.set_defaults(func=make_trainers)
	
	# un seul argument positionnel : le nom du corpus
	args_mktrs.add_argument(
		'corpus_name',
		type=str,
		help="nom du corpus de travail"
	)
	
	args_mktrs.add_argument(
		'--model_types',
		type=str,
		nargs='+',
		metavar="bibfields",
		choices=['bibzone','biblines','bibfields','authornames'],
		help="modèles à préparer (bibzone, biblines...)"
	)
	
	
	####
	
	top_parser.add_argument('-d', '--debug',
		help="niveau de débogage",
		metavar=1,
		type=int,
		default=0,
		action='store')
	
	args = top_parser.parse_args(argv[1:])
	
	# --- checks and pre-propagation --------
	# pass
	# ----------------------------------------
	
	return(args)

# ----------------------------------------------------------------------
# Fonctions principales

def make_set(corpus_name,
			from_table=None, 
			size=None, 
			constraint=None,
			# non utilisé encore
			debug=0):
	"""
	Initialisation d'un corpus basique et remplissage de ses fulltexts
	
	3 façons de l'appeler :
	  - soit on fournit une table de métadonnées infos.tab (chemin fs)
	  - soit on fournit une taille (sampling directement avec l'API)
	  - soit on ne fournit rien et il fait un sampling de 10 docs
	
	Métadonnées, rangées dans CORPUS_HOME/<corpus_name>/meta/
	  - basenames.ls
	  - infos.tab
	
	Données: 3 formats, rangés dans CORPUS_HOME/<corpus_name>/data/
	  - .pdf, 
	  - .xml (natif) 
	  - et .tei.xml (pub2tei)
	
	
	
	Position dans le système de fichier
	 cf sous lib/global_conf.ini
	                -> variable CORPUS_HOME 
	                     -> mise par défaut à ./corpora/
	"""
	
	# test de base avant de tout mettre dans le dossier
	# (le seul dossier qu'on n'écrase jamais)
	future_dir = path.join(Corpus.home_dir, corpus_name)
	if path.exists(future_dir):
		print("ERR:'%s'\nLe nom '%s' est déjà pris dans le dossier des corpus." % 
		       (future_dir, corpus_name), file=stderr)
		exit(1)
	
	# (1/4) echantillon initial (juste la table) -------------------------
	
	# soit on a déjà une table
	if from_table and size:
		print("""ERR bako.make_set:
		         fournir au choix 'from_table' ou 'size', mais pas les 2.""",
		         file=stderr)
		exit(1)

	if from_table:
		if path.exists(from_table):
			fic = open(from_table)
			my_tab = fic.readlines()
			fic.close()
		else:
			print("ERR bako.make_set: je ne trouve pas le fichier '%s'" % from_table, file=stderr)
			exit(1)
	
	# sinon sampling
	else:
		if not size:
			size = 10
		
		if not constraint:
			constraint = "qualityIndicators.refBibsNative:true AND NOT(corpusName:bmj)"
		if isinstance(size, int):
			my_tab, my_log = sampler.full_run(
									['-n', str(size), 
									 '--outmode', 'tab', 
									 '--with', constraint]
								)
		else:
			print("ERR bako.make_set: 'size' doit être un entier'%s'" 
			       % from_table, file=stderr)
			exit(1)
	
	# (2/4) notre classe corpus ------------------------------------------
	
	# Corpus
	cobj = Corpus(corpus_name, my_tab)
	
	# (3/4) téléchargement des fulltexts ---------------------------------
	
	ids = cobj.cols['istex_id']
	
	for the_shelf in ['PDF0', 'XMLN']:
		the_api_type = BSHELFS[the_shelf]['api']
		the_ext      = BSHELFS[the_shelf]['ext']
		tgt_dir = cobj.shelf_path(the_shelf)
		
		print("mkdir: %s" % tgt_dir,file=stderr)
		mkdir(tgt_dir)
	
		for (i, ID) in enumerate(ids):
			api.write_fulltexts(
				ID,
				api_conf  = CONF['istex-api'],
				tgt_dir   = cobj.shelf_path(the_shelf),
				base_name = cobj.bnames[i],
				api_types = [the_api_type]
				)
			print("GETDOC: %s" % cobj.bnames[i]+the_ext,
			  file=stderr)
	
	cobj.assert_fulltexts('XMLN')
	cobj.assert_fulltexts('PDF0')
	
	# (4/4) conversion tei (type gold biblStruct) ------------------------
	
	# copie en changeant les pointeurs dtd
	print("***DTD LINKING***")
	cobj.dtd_repair()
	
	print("***XML => TEI.XML CONVERSION***")
	
	# créera le dossier C-goldxmltei
	cobj.pub2goldtei()      # conversion
	
	cobj.assert_fulltexts('GTEI')
	
	# persistence du statut des 3 dossiers créés
	cobj.save_shelves_status()
	
	# we return the new filled corpus for further work or display
	return cobj


def take_set(corpus_name,
			# non utilisé
			debug=0):
	"""
	Reprise d'un corpus créé auparavant
	
	Appel: on fournit le nom d'un corpus déjà sous CORPUS_HOME
	"""
	
	return Corpus(corpus_name, read_dir="corpora/%s" % corpus_name)


PREP_TEI_FROM_TXT = {
					'bibzone' : {'from': 'BZRTX', 'to': 'BZTEI'},
					'biblines' : {'from': 'BLRTX', 'to': 'BLTEI'},
					'bibfields' : {'from': 'BFRTX', 'to': 'BFTEI'},
					'authornames' : {'from': 'AURTX', 'to': 'AUTEI'},
					}

def make_trainers(corpus_name, model_types=None, debug=0):
	"""
	Préparation des corpus d'entraînement => dans dossiers D-*
	
	model_types est une todoliste de modèles parmi les 4 possibles
	     ('bibzone', 'biblines', 'bibfields', 'authornames')
	
	NB: bibzone et biblines ont des fichiers 'rawtoks' supplémentaires
	    qui correspondent à l'input tokenisé vu par un CRF ("features")
	"""
	
	# Récupération du corpus par son nom
	cobj = take_set(corpus_name)
	
	just_rag = True   # <--------- config/expé ?
	
	# on lit la liste des modèles à faire dans le fichier config
	if not model_types:
		model_types = CONF['training']['model_types'].split(',')
	
	
	# (1/2) createTrainingFulltexts ============================
	
	# trainers : RAWTXT pour tous 
	#                      (et RAWTOKS pour bibzone et biblines)
	for tgt_model in model_types:
		
		
		src_shelf = PREP_TEI_FROM_TXT[tgt_model]['from']
		src_shelf_name = SHELF_NAMES[src_shelf]
		
		if src_shelf not in cobj.fulltextsh():
			# raws ++++
			cobj.grobid_create_training(tgt_model)
		
		else:
			print("<= %s (reprise précédemment créés" % src_shelf_name)
		
		# =================(2/2) better training pTEIs =========
		cobj.construct_training_tei(tgt_model, just_rag, debug)
		# ======================================================
	
		# persist. du statut des nvx dossiers "trainers" après ch. étape
		cobj.save_shelves_status()
	
	# nouveau paquet (corpus+model_type) prêt pour make_training
	return cobj


def make_training(a_corpus_obj, model_type):
	""" 
	Entraînement proprement dit
	
	(appel de grobid-trainer)
	  - appel système
	  - commande shell équivalente
	      mvn generate-resources -P train_<model_type>
	      
	  Chaîne d'invocation réelle:
	     bako => shell => maven => grobid-trainer => wapiti
	
	/!\ La commande shell ne renvoit pas le modèle
	    mais va aller l'écrire directement dans grobid-home/models
	    
	    Quant à nous, on le récupère a posteriori pour le ranger.
	
	/!\ Ici un seul model_type"""
	
		# 1) substitution dossiers   SHELF_TRAIN => GB_HOME/grobid-trainer/resources/dataset/$model_name
		
		# 2) _call_grobid_trainer
	
def _call_grobid_trainer():
	"""
	ICI Appel traininf principal
	"""
	model_name = 'train_name_citation'
	
	mon_process = Popen(
	  ['mvn',
	  '-X',
	  'generate-resources',
	  '-P', model_name
	  ], stdout=PIPE, stderr=PIPE, 
	cwd=path.join(CONF['grobid']['GROBID_HOME'],"grobid-trainer")
	)

	for line in mon_process.stderr:
		print(line.decode('UTF-8').rstrip())


def assistant():
	"""
	Séquence standard de commandes lancée si
	l'utilisateur n'a donné aucune commande spécifique...
	
	task 1 sampling et pub2tei (make_set)
	
	task 2 préparation trainers (make_trainers)
	"""
	
	# nom du nouveau corpus
	inname = input("choisissez un nom (si possible sans espaces...) pour initialiser un nouveau dossier corpus sous /corpora :")
	
	if len(inname):
		a_corpus_obj = make_set(
				corpus_name = inname.rstrip(),
				size = 15
			)
	
	input("appuyez sur entrée pour lancer le createTraining puis le ragreage")
	
	# par défaut: avec les modèles de local_conf.ini['training']
	make_trainers(a_corpus_obj.name)
	
	# TODO immédiat
	# ----------------
	# make_training  /model_type/ /sample/ <=> ci-dessus _call_grobid_trainer
	# ----------------
	
	print("BAKO: all tasks DONE for '%s' prepared corpus" % a_corpus_obj.name)
	print("=> Sous-dossiers obtenus dans %s/data/" % a_corpus_obj.cdir)
	for this_shelf in a_corpus_obj.fulltextsh():
		print("  - %s" % SHELF_NAMES[this_shelf])
	print("+  Tableau récapitulatif dans %s/meta/infos.tab" % a_corpus_obj.cdir)
	


########################################################################
if __name__ == '__main__':
	
	# lecture des arguments cli
	# (dont la fonction associée par la sous-commande)
	args = bako_sub_args()
	
	# pour debug cli
	# --------------
	# print("ARGUMENTS LUS: %s " % vars(args))
	# exit()
	
	# APPEL de la sous-commande voulue
	# On déballe les args (c-à-d un Namespace pris comme dict)
	# directement dans la fonction associée (args["func"])
	mes_arguments = vars(args)
	ma_fonction = mes_arguments.pop("func")
	ma_fonction(**mes_arguments)
	# NB: ça nécessite que la fonction appelée (ex: args.func=make_set)
	#   par ch. sous-parseur ait EXACTEMENT le même nombre d'arguments
	#   AVEC les mêmes noms que les options du sous-parseur...
	
	
	
	# ------------------------------
	#     Remarques sur la suite 
	#     ----------------------
	
	# pour models pick | install
	# --------------------------
	# cf. en bash:
	# > cp -p $GB/grobid-home/models/$MODEL_type/model.wapiti $STORE/trained/$CRFTRAINEDID/model/$MODEL_type/.
	# > mkdir -p $CoLTrAnE/run/$CRFTRAINEDID/log
	# > mv -v $MY_NEW_SAMP.$eps.trainer.mvn.log $CoLTrAnE/run/$CRFTRAINEDID/log/.
	# > mv -v $MY_NEW_SAMP.$eps.trainer.crf.log $CoLTrAnE/run/$CRFTRAINEDID/log/.


	# stats et eval proprement dites
	# -------------------------------
	# balisage initial d'un sample GOLD
	# mkdir(Z-evalxmltei)
	# grobid -exe processReferences -dIn A-pdfs/ -dOut ZZ-evalxmltei/
	# ------------------------------------------------------------------------
	# tout de suite une éval => shb grep => meta/mon_sample_gold.vanilla.score    <= baseline
	# ------------------------------------------------------------------------
	# eval_xml_refbibs_multiformat.pl -g elsevier -f tei-grobid -r B-xmlnatifs -x C-goldxmltei/ -e xml > eval_via_B.tab
	# eval_xml_refbibs_tei.pl -x ZZ-evalxmltei/ -r C-goldxmltei/ -e references.tei.xml -n > eval_via_C-tei.tab
	
