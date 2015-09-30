#! /usr/bin/python3
"""
bib-adapt-corpus ou bako
------------------------
5 commands:
  bako make_set       corpus_name  [-s size] [-q specific api query]
  bako take_set       corpus_name
  bako make_trainers  corpus_name  [-m model  [model2...]]
  bako run_training   model_type   [-c corpus_name [corpus_name2...]]
  bako eval_model     [-m model_name] [-e evalcorpus_name] [-s] [-g]
  
TODO : éval de plusieurs modèles => eval_id
       avec une sorte de modèles_triggers => substitutionsles
  
"""
__author__    = "Romain Loth"
__copyright__ = "Copyright 2014-5 INIST-CNRS (ISTEX project)"
__license__   = "LGPL"
__version__   = "0.5"
__email__     = "romain.loth@inist.fr"
__status__    = "Dev"

# imports
from os              import path, makedirs, symlink, stat
from shutil          import rmtree, copytree
from sys             import stderr, argv
from configparser    import ConfigParser
from re              import search, match
from argparse        import ArgumentParser, RawDescriptionHelpFormatter
from collections     import defaultdict
from subprocess      import call, check_output

# "libconsulte" istex-rd
from libconsulte import api
from libconsulte import sampler

# Corpus => bnames, cdir, cols, shelfs...
from libconsulte.corpusdirs import Corpus, BSHELVES

# CRFModel => mid, recipy, storing_path
from libtrainers.grobid_corpusdirs import TrainingCorpus, PREP_TEI_FROM_TXT
from libtrainers.grobid_models import CRFModel, GB_RAW_VERSION, gb_model_import, GB_MODEL_MAP

# ----------------------------------------------------------------------
# lecture de fichier config local
# v 0.5 : dépend dorénavant de l'installation bako
#         (=> devient *indépendant* des dossiers de travail 
#             sur les contenus: corpus, modèles, évals)
script_dir = path.dirname(path.realpath(__file__))
CONF = ConfigParser()
conf_path = path.join(script_dir, 'bako_config.ini')
conf_file = open(conf_path, 'r')
CONF.read_file(conf_file)
conf_file.close()

MY_CORPUS_HOME = path.join(CONF['workshop']['HOME'],CONF['workshop']['CORPUS_HOME'])

# -----------------------------------------------------------------------------
# Noms "humains" des étagères de base (Corpus) et pour grobid (TrainingCorpus)
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

# dossiers nécessaires pour constituer un dataset grobid
# dans _prepare_dirs()
PREP_DATASET = {
	'bibzone' : {'raw': 'BZRTK', 'tei': 'BZTEI'},
	'biblines' : {'raw': 'BLRTK', 'tei': 'BLTEI'},
	'bibfields' : {'tei': 'BFTEI'},
	'authornames' : {'tei': 'AUTEI'},
	}

# ----------------------------------------------------------------------
# Fonction CLI

def bako_sub_args(next_sys_args=None):
	"""
	Preparation du namespace args contenant les  arguments de 
	la ligne de commande pour main()
	"""
	top_parser = ArgumentParser(
		formatter_class=RawDescriptionHelpFormatter,
		description="""
----------------------------------------------------------------------
      A corpus manager and training operator for grobid-trainer
----------------------------------------------------------------------""",
		usage="""
  bako make_set       corpus_name  [-s size] [-q specific api query]
  bako take_set       corpus_name
  bako make_trainers  corpus_name  [-m model  [model2...]]
  bako run_training   model_type   [-c corpus_name [corpus_name2...]]
  bako eval_model     [-m model_name] [-e evalcorpus_name] [-s] [-g]
""",
		epilog="""
------- (c) 2015 :: romain.loth@inist.fr :: Inist-CNRS (ISTEX) -------
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
		'-s', '--size',
		type=int,
		required=False,
		help="taille du nouveau corpus à créer (par déf: 10)"
	)
	
	# option 2: contrainte lucene
	args_mkset.add_argument(
		'-q', '--constraint',
		metavar='refBibsNative:true',
		type=str,
		help="requête lucene comme contrainte sur le corpus"
	)
	
	# NB type: écrit en dur lors de l'initialisation ou cast
	
	# mode "import" avec une table
	args_mkset.add_argument(
		'--from_table',
		type=str,
		help="""mode "import": table d\'un corpus préexistant
		.....colonnes attendues: istex_id	corpus
		4D0BA8757489B4B057B12BFACC797E9A7864B661	els"""
	)
	
	
	# TAKE_SET ---- sous-commande (2) ----
	args_tkset = sub_args.add_parser(
		'take_set',
		usage="""
  bako.py take_set corpus_name""",
		help="lire un corpus"
	)
	
	# pour savoir quelle commande ça lance
	args_tkset.set_defaults(func=take_set)
	
	# un seul argument positionnel : le nom du corpus
	args_tkset.add_argument(
		'corpus_name',
		type=str,
		help="nom du corpus à reprendre"
	)
	
	
	# MAKE_TRAINERS ---- sous-commande (3) ----
	args_mktrs = sub_args.add_parser(
		'make_trainers',
		usage="""
  bako make_trainers corpus_name --model_types model1 [model2 ...]""",
		help="préparer un jeu d'entraînement pour un corpus"
		)
	
	# pour savoir quelle commande ça lance
	args_mktrs.set_defaults(func=make_trainers)
	
	# un seul argument positionnel : le nom du corpus
	args_mktrs.add_argument(
		'corpus_name',
		type=str,
		help="nom du corpus de travail"
	)
	
	args_mktrs.add_argument(
		'-m', '--model_types',
		type=str,
		nargs='+',
		metavar="model",
		choices=['bibzone','biblines','bibfields','authornames'],
		help="modèles à préparer (bibzone, biblines...)"
	)
	
	
	# MAKE_TRAINING ---- sous-commande (4) ----
	args_mktrg = sub_args.add_parser(
		'run_training',
		usage="""
  bako run_training mon_modèle --corpora corpus1 [corpus2...]""",
		help="créer un modèle depuis un ou plusieurs corpus"
		)
	
	# pour savoir quelle commande ça lance
	args_mktrg.set_defaults(func=run_training)
	
	# un seul argument positionnel : le type du modèle
	args_mktrg.add_argument(
		'model_type',
		type=str,
		choices=['bibzone','biblines','bibfields','authornames'],
		help="modèle à entraîner (mon_modèle)"
	)
	
	args_mktrg.add_argument(
		'-c', '--corpora',
		type=str,
		nargs='+',
		required=False,  # sans rien mode vanilla...
		metavar="corpus_name",
		help="un ou plusieurs corpus d'entraînement"
	)
	
	# EVAL_MODEL ---- sous-commande (5) ----
	args_evalm = sub_args.add_parser(
		'eval_model',
		usage="""
  bako.py eval_model [-m model_name]  [-e evalcorpus_name] [-s] [-g]
""",
		help="évaluer le dernier modèle (ou autre selon -m)"
	)
	
	# pour savoir quelle commande ça lance
	args_evalm.set_defaults(func=eval_model)
	
	# aucun argument obligatoire
	args_evalm.add_argument(
		'-m','--model_name',
		required=False,
		type=str,
		help="nom du modèle à reprendre"
	)
	# option: un autre jeu d'évaluation que dans la config
	args_evalm.add_argument(
		'-e', '--eval_set',
		metavar='cent_eval5',
		required=False,
		type=str,
		help="nom d'un corpus comme jeu d'évaluation alternatif"
	)
	
	args_evalm.add_argument('-s', '--save_tab',
		help="enregistrer une ligne d'éval dans le tableau de suivi",
		required=False,
		default=False,
		action='store_true')
	
	args_evalm.add_argument('-g', '--do_graphs',
		help="générer les graphiques d'évaluation",
		required=False,
		default=False,
		action='store_true')
	
	####
	
	# commun à tous
	top_parser.add_argument('-d', '--debug',
		help="niveau de débogage",
		metavar=1,
		type=int,
		default=0,
		action='store')
	
	# cas où aucune de ces sous-commandes n'est présente
	if not search(r'make_set|take_set|make_trainers|run_training|eval_model', " ".join(next_sys_args)):
		print(""" ===================================================================
  /!\\  Vous avez lancé bako sans aucune de ses sous-commandes  /!\\
 ===================================================================

En temps normal il faut écrire par exemple 'bako make_set mon_corpus'
""", file=stderr)
		top_parser.print_usage()
		choix = input("""
 ===================================================================
   Voulez-vous lancer l'assistant d'installation ?
      -> vérifiera les dossiers de travail
      -> importera les modèles actuels de grobid (dits "vanilla")
      -> créera un premier corpus d'évaluation
      -> lancera une première évaluation (dite "vanilla baseline")
(Y/[N]) """)
		if len(choix) and choix[0] in ['Y','y','O','o']:
			assistant_installation()
		else:
			exit(1)
	
	# cas normal avec sous-commandes
	else:
		args = top_parser.parse_args(next_sys_args)
		return(args)

# ----------------------------------------------------------------------
# Fonctions principales

def make_set(corpus_name,
			from_table=None, 
			size=None, 
			constraint=None,
			type='gold',
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
	future_dir = path.join(MY_CORPUS_HOME, corpus_name)
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
	# initialisation (mode tab seul, éventuellement ajouter verbose ?)
	cobj = Corpus(corpus_name,
					new_infos = my_tab, 
					new_home  = MY_CORPUS_HOME,
					verbose = (debug>0),
					type=type)
	
	# (3/4) téléchargement des fulltexts ---------------------------------
	
	ids = cobj.cols['istex_id']
	
	for the_shelf in ['PDF0', 'XMLN']:
		the_api_type = cobj.origin(the_shelf)
		the_ext      = cobj.filext(the_shelf)
		tgt_dir      = cobj.shelf_path(the_shelf)
		
		print("mkdir -p: %s" % tgt_dir,file=stderr)
		makedirs(tgt_dir)
	
		for (i, ID) in enumerate(ids):
			new_name_i = cobj.bnames[i]
			api.write_fulltexts(
				ID,
				api_conf  = CONF['istex-api'],
				tgt_dir   = tgt_dir,
				base_name = new_name_i,
				api_types = [the_api_type]
				)
			print("GETDOC: %s" % new_name_i+the_ext,
			  file=stderr)
		
		# NB: il doit y avoir la même extension dans cobj.filext(the_shelf) que chez l'API
		#  ou alors api.write_fulltexts doit autoriser à changer (renommer) les extensions
	
	cobj.assert_docs('PDF0')
	cobj.assert_docs('XMLN')
	
	# persistance du statut des 2 dossiers créés
	cobj.save_shelves_status()

	
	# (4/4) conversion tei (type gold biblStruct) ------------------------
	
	# copie en changeant les pointeurs dtd
	print("***DTD LINKING***")
	cobj.dtd_repair(debug_lvl = debug)
	
	print("***XML => TEI.XML CONVERSION***")
	
	# créera le dossier C-goldxmltei
	cobj.pub2goldtei(debug_lvl = debug)      # conversion
	
	cobj.assert_docs('GTEI')
	
	# persistence du statut du dossier créé
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
	
	# todo si signale corpus étendu => cast en TrainingCorpus
	
	expected_dir = path.join(MY_CORPUS_HOME, corpus_name)
	
	try:
		# initialisation (mode read_dir et avec verbose)
		print("=======  %s  =======" % corpus_name)
		cobj = Corpus(corpus_name, 
						read_dir = expected_dir,
						new_home = MY_CORPUS_HOME,
						verbose  = True)
	except FileNotFoundError as fnf_err:
		print("Je ne trouve pas '%s dans le dossier attendu %s\n  (peut-être avez-vous changé de dossier corpusHome ?)" % (fnf_err.pi_mon_rel_path, MY_CORPUS_HOME),
		file=stderr)
		fnf_err.corpus_name = corpus_name
		raise(fnf_err)
	
	return cobj


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
	# (comme un take_set avec cast Corpus => TrainingCorpus)
	gcobj = TrainingCorpus(corpus_name)
	
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
		
		if src_shelf not in gcobj.got_shelves():
			# raws ++++
			gcobj.create_raw_streams(tgt_model)
		
		else:
			print("<= %s (reprise précédemment créés" % src_shelf_name)
		
		# =================(2/2) better training pTEIs =========
		gcobj.construct_training_tei(tgt_model, just_rag, debug)
		# ======================================================
	
		# persist. du statut des nvx dossiers "trainers" après ch. étape
		gcobj.save_shelves_status()
	
	# nouveau paquet (grobid_corpus+model_type) prêt pour run_training
	return gcobj


def run_training(model_type, corpora, debug=0):
	""" 
	Entraînement proprement dit
	
	/!\ Ici un seul model_type, plusieurs corpus potentiels /!\
	
	(appel de grobid-trainer)
	  - appel système
	  - commande shell équivalente
	      mvn generate-resources -P train_<model_type>
	      
	  Chaîne d'invocation réelle:
	     bako => shell => maven => grobid-trainer => wapiti
	
	/!\ La commande shell ne renvoit pas le modèle
	    mais va aller l'écrire directement dans grobid-home/models
	    
	    Quant à nous, on le récupère a posteriori pour le ranger.
	
	"""
	
	# cas vanilla: on entraîne sur les dataset existants
	if corpora is None:
		# use case rare (ex: pour comparer avec repository)
		# (contrairement à une eval vanilla qui est fréquente)
		print("/!\\ RE-TRAINING VANILLA MODEL /!\\", file=stderr)
		# juste modèle
		new_model = CRFModel(model_type,debug_lvl=debug)
	
	# cas normal avec liste de corpus à reprendre
	else:
		corpora_objs = []
		# (1) vérif existence
		for c_name in corpora:
			try:
				corpora_objs.append(TrainingCorpus(c_name))
			except FileNotFoundError as e:
				print("ERR: Le corpus '%s' n'existe pas." % e.corpus_name,file=stderr)
				exit(1)
		
		# (2) vérif étagère(s) requise(s)
		for c_obj in corpora_objs:
			for tgtdir in PREP_DATASET[model_type]:
				needed_sh = PREP_DATASET[model_type][tgtdir]
				if not c_obj.shelfs[needed_sh]:
					print("ERR: Le corpus '%s' n'a pas d'étagère %s pour %s" % (c_obj.name,needed_sh,model_type) ,file=stderr)
					exit(1)
		
		# (3) vérif doublons
		# dict de vérification local
		dedup_check = dict()
		for cobj in corpora_objs:
			# liste rattachée par objet
			cobj.temp_ignore = defaultdict(lambda: False)
			for filename in cobj.bnames:
				if filename not in dedup_check:
					# le premier arrivé à gagné
					dedup_check[filename] = cobj.name
				else:
					print("DOUBLON entre %s et %s: %s" % (
							dedup_check[filename],
							cobj.name,
							filename
							)
						)
					# stockage temporaire
					cobj.temp_ignore[filename] = True
		
		# --- initialisation modele -----------------------------
		new_model = CRFModel(
			model_type,
			# NB ce sont juste les noms mais à présent vérifiés
			the_samples=corpora,
			debug_lvl=debug
			)
		# !! symlinks de substitution dossiers !!
		_prepare_dirs(new_model, corpora_objs, debug_lvl=debug)
	
	
	# 2) train_params = _call_grobid_trainer()
	
	# lancement grobid-trainer
	print("training new model %s" % new_model.mid)
	
	# ==================================================#
	#  E N T R A I N E M E N T    G R O B I D    C R F  #
	# ==================================================#
	(mvnlog, crflog) = new_model.call_grobid_trainer()  #
	# ==================================================#
	
	# vérification simple
	# si le CRF n'a pas été lancé c'est que le maven a planté
	if not len(crflog.lines):
		print("!!!--------- ERREUR GROBID-TRAINER ---------!!!", file=stderr)
		print("\n".join(mvnlog.lines), file=stderr)
		exit(1)
	# cas normal ------------------------------------------------------
	else:
		new_model.ran = True
	
	# 3) pick_n_store : récupération du modèle
	stored_location = new_model.pick_n_store(logs = [mvnlog, crflog])
	print("new model %s stored into dir %s" % (new_model.mid, stored_location), file=stderr)


def _prepare_dirs(new_model, corpora, debug_lvl = 0):
	"""
	symlinks dans GB_DIR/grobid-trainer/
	pour chaque corpus source, avant training
	
	n X SHELF_TRAIN 
	n X SHELF_TRAIN } => resources/dataset/$model_name
	n X SHELF_TRAIN
	"""
	
	# modèle central
	gb_model = new_model.gb_mdltype_long()
	
	base_resrc_elts = [CONF['grobid']['GROBID_DIR'], 'grobid-trainer','resources','dataset']
	model_path_elts = GB_MODEL_MAP[new_model.mtype]['gbpath'].split('/')
	
	full_resrc_elts = base_resrc_elts + model_path_elts + ['corpus']
	resrc_corpusdir = path.join(*full_resrc_elts)
	
	# |#### S U B S T I T U T I O N S  ####|
	# |corpora trainers                    |
	# |corpora trainers }~~> grobid dataset|
	# |corpora trainers                    |
	# |####################################|
	
	# --- dossiers cibles -----------------------------------------
	# stockage model_type s'il n'y en a pas déjà
	if not path.isdir(resrc_corpusdir +'.bak'):
		copytree(resrc_corpusdir, resrc_corpusdir +'.bak')
	
	# suppression anciens dataset 
	# (corpus uniquement: les templates et eval peuvent rester)
	rmtree(resrc_corpusdir)
	
	# nouveau(x) dossier(s) (corpus et eventuels sous-dirs)
	makedirs(resrc_corpusdir)
	
	# --- modèles à rawtokens ET tei spécifiques ------------------
	if new_model.mtype in ['bibzone', 'biblines']:
		# 'tei' et 'raw' (tokens)
		for subdir in PREP_DATASET[new_model.mtype]:
			# ici tgt_subdirs à créer
			tgt_dataset_dir = path.join(resrc_corpusdir,subdir)
			makedirs(tgt_dataset_dir)
			# src_shelf: exemple BZRTK ou BZTEI
			src_shelf = PREP_DATASET[new_model.mtype][subdir]
			for cobj in corpora:
				_lns(cobj, src_shelf, tgt_dataset_dir, subdir, debug_lvl)
	
	# --- modèles citation et authornames: juste tei spécifiques --
	else:
		# les tei sources sont à mettre
		# directement sous <model>/corpus
		src_subdir = 'tei'
		# src_shelf: exemple BFTEI
		src_shelf = PREP_DATASET[new_model.mtype][src_subdir]
		for cobj in corpora:
			_lns(cobj, src_shelf, resrc_corpusdir, src_subdir, debug_lvl)


def _lns(cobj, src_shelf, tgt_dataset_dir, subdir, debug_lvl):
	"""
	Création de symlink depuis une shelf
	vers un dossier extérieur (ex: dataset)
	avec vérifications fichier tei vides
	"""
	
	# stats
	linked_docs = 0
	null_trainer_tei = 0
	null_duplicated = 0
	null_absent = 0
	
	print("---( corpus %s : étagère %s )---" % (cobj.name, src_shelf), file=stderr)
	
	# ex: ".tei.xml"
	src_ext = cobj.filext(src_shelf)
	
	# boucle par fichier à lier
	for filename in cobj.bnames:
		# ---
		# mini filtre selon notre liste de dédoublonnage précédente
		if cobj.temp_ignore[filename]:
			if debug_lvl >= 2:
				print("     doublon ignoré: %s" % filename,file=stderr)
			null_duplicated += 1
		# ---
		# cas normal
		else:
			src = cobj.fileid(filename, src_shelf)
			# ---
			# mini filtre fichiers absents
			if not path.exists(src):
				if debug_lvl >= 2:
					print("     fichier absent ignoré: %s dans %s" % (filename, src_shelf),file=stderr)
			# ---
			# ---
			# mini filtre fichiers vides
			elif subdir == 'tei' and (stat(src).st_size == 0):
				if debug_lvl >= 2:
					print("     training.tei vide ignoré: %s" % filename,file=stderr)
				null_trainer_tei += 1
			# ---
			else:
				tgt = path.join(
					tgt_dataset_dir,
					filename+src_ext
					)
				symlink(src, tgt)
				linked_docs += 1
			# print("symlink %s -> %s" % (src, tgt),file=stderr)
	if debug_lvl >= 1:
		print(" => %s docs ignorés (%s absents, %s vides, %s doublons)" % (
									null_absent+null_trainer_tei+null_duplicated,
									null_absent ,null_trainer_tei ,null_duplicated
									),
											file=stderr)
	print(" => %s documents liés" % linked_docs, file=stderr)


def eval_model(model_name=None, eval_set=None, 
               save_tab=True, do_graphs=False, debug = 0):
	"""
	Stats et eval proprement dites
	1 - balisage initial d'un sample GOLD
	2 - lancement indirect de eval_xml_refbibs.pl
	(si pas de model_name, on évalue le dernier modèle)
	"""
	
	# récupération du corpus
	if eval_set is None:
		eval_set = CONF['eval']['CORPUS_NAME']
	
	eval_corpus = take_set(eval_set)
	
	# (1) lancer balisage
	evals_dir = path.join(CONF['workshop']['HOME'], CONF['workshop']['EVALS_HOME'])
	newbibs_path = path.join(evals_dir,"output_bibs.dir")
	if not path.isdir(newbibs_path):
		makedirs(newbibs_path)
	jarfile = 'grobid-core-'+GB_RAW_VERSION+'.one-jar.jar'
	print ('vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv', file = stderr)
	print ('--- Balisage en cours sur %s ---' % eval_corpus.name , file = stderr)
	baliseur = call(
		  ['java',
		  '-Xmx1024m',
		  '-jar', path.join(CONF['grobid']['GROBID_DIR'], 'grobid-core','target', jarfile),
		  '-gH', path.join(CONF['grobid']['GROBID_DIR'],'grobid-home'),
		  '-gP', path.join(CONF['grobid']['GROBID_DIR'],'grobid-home','config','grobid.properties'),
		  '-exe', 'processReferences',
		  '-dIn',eval_corpus.shelf_path('PDF0'),
		  '-dOut',newbibs_path
		  ]
		  )
	print ('--- Balisage terminé ---', file = stderr)
	print ('^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^', file = stderr)
	
	# (2) évaluer
	which_eval_script = CONF['eval']['SCRIPT_PATH']
	# NB si existe >> append
	report_table = CONF['eval']['TABLE_PATH']
	
	resultat_eval = bytes()
	
	# cas où l'on évalue les modèles courants
	# dont initialement vanilla: modèles pré-existants
	if model_name is None:
		# use case courant: une eval vanilla qui est fréquente
		#                   pour "calibrer" les attentes
		print("/!\\ EVALUATING CURRENT MODELS /!\\", file=stderr)
		
		
		# juste modèles courants
		mon_eval_id = 'vanilla-'+eval_corpus.name
		
		debug_flag = ""
		if debug > 0:
			debug_flag = "-d"
		
		resultat_eval = check_output(
		  ['perl', which_eval_script,
		   debug_flag,
		  '-x', newbibs_path,
		  '-g',  eval_corpus.shelf_path('GTEI'),
		  '-e', 'references.tei.xml',
		  '--logreport', report_table,
		  '--regreport', mon_eval_id
		  ],
		)
		#£TODO IF résumé d'éval à écrire à part 
		#   si save_tab => dans eval_xml option --logline )
		#   sinon       => s'affichera d'elle-même sur STDERR
	
	# cas avec un modèle donné
	else:
		model_object = CRFModel(existing_mid=model_name)
		# £TODO substitutions dossier
		raise NotImplementedError()
	
	resultat_eval.decode("UTF-8")


def assistant_installation():
	"""
	Séquence standard de commandes lancées à la mise en place
	
	task 1 initialisation des dossiers corpora, models, evals
	task 2 import des modèles grobid courants "vanilla"
	task 3 sampling d'un premier corpus eval (+ make_set)
	task 4 première évaluation "baseline vanilla"
	"""
	
	# --- initialisation des dossiers --------------------------
	corpora_dir = MY_CORPUS_HOME
	models_dir = CRFModel.home_dir
	evals_dir = path.join(CONF['workshop']['HOME'], CONF['workshop']['EVALS_HOME'])
	if not path.isdir(corpora_dir):
		choix1 = input("""Vos paramètres de configuration ont le dossier '%s'
comme lieu de stockage de tous les corpus... mais il n'existe pas encore (nécessaire pour continuer)).
  => Voulez-vous le créer maintenant ? (y/n) """ % corpora_dir)
		if choix1[0] in ['Y','y','O','o']:
			makedirs(corpora_dir)
		else:
			print('Assistant "baseline" interrompu. Vous pouvez ajuster la configuration CORPUS_HOME et relancer l\'assistant.', file=stderr)
			exit(1)
	
	if not path.isdir(models_dir):
		choix2 = input("""Vos paramètres de configuration ont le dossier '%s'
comme lieu de stockage pour les modèles CRF ("CRF Store")
  => Voulez-vous le créer maintenant ? (y/n) """ % models_dir)
		if choix2[0] in ['Y','y','O','o']:
			makedirs(models_dir)
		else:
			print('Assistant "baseline" interrompu. Vous pouvez ajuster la configuration MODELS_HOME et relancer l\'assistant.', file=stderr)
			exit(1)
	
	if not path.isdir(evals_dir):
		choix3 = input("""Vos paramètres de configuration ont le dossier '%s'
comme lieu de stockage pour les évaluations
  => Voulez-vous le créer maintenant ? (y/n) """ % models_dir)
		if choix3[0] in ['Y','y','O','o']:
			makedirs(evals_dir)
		else:
			print('Assistant "baseline" interrompu. Vous pouvez ajuster la configuration EVALS_HOME et relancer l\'assistant.', file=stderr)
			exit(1)
	
	# --- import des modèles grobid courants (aka 'vanilla') ---
	
	gb_model_import(model_type = 'bibzone', to = models_dir)
	gb_model_import(model_type = 'biblines', to = models_dir)
	gb_model_import(model_type = 'bibfields', to = models_dir)
	gb_model_import(model_type = 'authornames', to = models_dir)
	
	# --- premier corpus d'évaluation --------------------------
	# nom du nouveau corpus
	eval_c_name = CONF['eval']['CORPUS_NAME']
	
	if path.isdir(path.join(MY_CORPUS_HOME,eval_c_name)):
		print("== Reprise du corpus d'évaluation existant déjà sous %s ==" % MY_CORPUS_HOME, file=stderr)
	
	else:
		# taille nouveau corpus
		eval_size = input("choisissez la taille du corpus d'évaluation par défaut pour initialiser un nouveau dossier corpus '%s' sous /corpora [défaut:100]: " % eval_c_name).rstrip()
		
		if not match(r'[0-9]*', eval_size):
			print('taille incorrecte: veuillez relancer et entrer un nombre', file=stderr)
			exit(1)
		else:
			if len(eval_size):
				the_size = int(eval_size)
			else:
				the_size = 100
			# >> initialisation <<
			make_set(corpus_name = eval_c_name, size = the_size)
			print("=> Sous-dossiers obtenus dans %s/data/" % a_corpus_obj.cdir)
			for this_shelf in a_corpus_obj.got_shelves():
				print("  - %s" % SHELF_NAMES[this_shelf])
			print("+  Tableau récapitulatif dans %s/meta/infos.tab" % a_corpus_obj.cdir)
	
	
	# --- première évaluation ----------(aka 'baseline vanilla') ---
	input('BASELINE VANILLA:\nappuyez sur entrée pour lancer la première évaluation (avec juste les modèles grobid courants, dits aussi "vanilla")')
	
	# --- evaluation des modèles courants 
	
	eval_model(model_name=None, eval_set=eval_c_name)
	
	print("L'assistant d'installation bako a fini l'évaluation initiale baseline", file=stderr)


########################################################################
if __name__ == '__main__':
	
	# lecture des arguments cli
	# (dont la fonction associée par la sous-commande)
	args_namespace = bako_sub_args(next_sys_args=argv[1:])
	
	# pour debug cli
	# --------------
	# print("ARGUMENTS LUS: %s " % vars(args))
	# exit()
	
	# APPEL de la sous-commande voulue
	# On déballe les args (c-à-d un Namespace pris comme dict)
	# directement dans la fonction associée (args["func"])
	mes_arguments = vars(args_namespace)
	
	# lancement d'une sous-commande
	ma_fonction = mes_arguments.pop("func")
	ma_fonction(**mes_arguments)
	# NB: ça nécessite que la fonction appelée (ex: args.func=make_set)
	#   par ch. sous-parseur ait EXACTEMENT le même nombre d'arguments
	#   AVEC les mêmes noms que les options du sous-parseur...