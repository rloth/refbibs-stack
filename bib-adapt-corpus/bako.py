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
__version__   = "0.4"
__email__     = "romain.loth@inist.fr"
__status__    = "Dev"

# imports
from os              import path, makedirs, rename, symlink, stat
from shutil          import rmtree, copytree
from sys             import stderr, argv
from configparser    import ConfigParser
from site            import addsitedir     # pour imports locaux
from re              import search, match
from argparse        import ArgumentParser, RawDescriptionHelpFormatter
from collections     import defaultdict
from subprocess      import PIPE, Popen, call


# pour les 4 imports locaux + field_values
# (tel quel: dépendant du lieu de lancement de bako !)
addsitedir('lib')

# "libconsulte" istex-rd
import api
import sampler

# Corpus => bnames, cdir, cols, shelfs...
from corpusdirs import Corpus

# CRFModel => mid, recipy, storing_path
from grobid_models import CRFModel, FULL_GB_VERSION

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

def bako_sub_args(arglist=None):
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
	
	# def make_trainers(corpus_name, model_types=None, just_rag=False):
	
	
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
		
		print("mkdir -p: %s" % tgt_dir,file=stderr)
		makedirs(tgt_dir)
	
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
	
	expected_dir = path.join(Corpus.home_dir, corpus_name)
	
	try:
		print("=======  %s  =======" % corpus_name)
		cobj = Corpus(corpus_name, read_dir=expected_dir, verbose=True)
	except FileNotFoundError as fnf_err:
		print("Je ne trouve pas '%s dans le dossier attendu %s\n  (peut-être avez-vous changé de dossier corpusHome ?)" % (fnf_err.pi_mon_rel_path, Corpus.home_dir),
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
	
	# nouveau paquet (corpus+model_type) prêt pour run_training
	return cobj


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
				corpora_objs.append(take_set(c_name))
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
	
	new_model.ran = True
	
	# 3) pick_n_store : récupération du modèle
	stored_location = new_model.pick_n_store(mvnlog, crflog)
	print("new model %s stored into dir %s" % (new_model.mid, stored_location), file=stderr)


def _prepare_dirs(new_model, corpora, debug_lvl = 0):
	"""
	symlinks dans GB_HOME/grobid-trainer/
	pour chaque corpus source, avant training
	
	n X SHELF_TRAIN 
	n X SHELF_TRAIN } => resources/dataset/$model_name
	n X SHELF_TRAIN
	"""
	
	# modèle central
	gb_model = new_model.gb_mdltype_long()
	
	base_resrc_elts = [CONF['grobid']['GROBID_HOME'],
						'grobid-trainer','resources','dataset']
	model_path_elts = CRFModel.model_map[new_model.mtype]['gbpath'].split('/')
	
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
					cobj.filext(filename, src_shelf)
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
	tagged_path = path.join("evaluations","output_bibs.dir")
	if not path.isdir(tagged_path):
		makedirs(tagged_path)
	jarfile = 'grobid-core-'+FULL_GB_VERSION+'.one-jar.jar'
	print ('vvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvvv', file = stderr)
	print ('--- Balisage en cours sur %s ---' % eval_corpus.name , file = stderr)
	baliseur = call(
		  ['java',
		  '-Xmx1024m',
		  '-jar', path.join(CONF['grobid']['GROBID_HOME'], 'grobid-core','target', jarfile),
		  '-gH', path.join(CONF['grobid']['GROBID_HOME'],'grobid-home'),
		  '-gP', path.join(CONF['grobid']['GROBID_HOME'],'grobid-home','config','grobid.properties'),
		  '-exe', 'processReferences',
		  '-dIn',eval_corpus.shelf_path('PDF0'),
		  '-dOut',path.join("evaluations","output_bibs.dir")
		  ]
		  )
	print ('--- Balisage terminé ---', file = stderr)
	print ('^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^', file = stderr)
	
	# (2) évaluer
	which_eval_script = CONF['eval']['SCRIPT_PATH']
	
	# cas où l'on évalue les modèles courants
	# dont initialement vanilla: modèles pré-existants
	if model_name is None:
		# use case courant: une eval vanilla qui est fréquente
		#                   pour "calibrer" les attentes
		print("/!\\ EVALUATING CURRENT MODELS /!\\", file=stderr)
		# juste modèles courants
		
		debug_flag = ""
		if debug > 0:
			debug_flag = "-d"
		
		mon_process = call(
		  ['perl', which_eval_script,
		   debug_flag,
		  '-r',  eval_corpus.shelf_path('GTEI'),
		  '-x', tagged_path,
		  '-e', 'references.tei.xml'
		  ], 
		  # stdout=PIPE, stderr=PIPE,
		  #~ cwd=work_dir
		)
		
		for line in mon_process.stderr:
			print(line.decode('UTF-8').rstrip())
	
	# cas avec un modèle donné
	else:
		model_object = CRFModel(existing_mid=model_name)
		# TODO
		raise NotImplementedError()


def assistant_installation():
	"""
	Séquence standard de commandes lancées à la mise en place
	
	task 1 initialisation des dossiers corpora, models, evals
	task 2 import des modèles grobid courants
	task 3 sampling d'un premier corpus eval (+ make_set)
	task 4 première évaluation "vanilla"
	"""
	
	# --- initialisation des dossiers --------------------------
	choix1 = input(
	"""
Vos paramètres de configuration ont le dossier '%s'
comme lieu de stockage de tous les corpus... mais il n'existe pas encore (nécessaire pour continuer)).
  => Voulez-vous le créer maintenant ? (y/n) """ % Corpus.home_dir)
	if choix1[0] in ['Y','y','O','o']:
		mkdir(Corpus.home_dir)
	else:
		exit(1)
	
	if not path.exists(CRFModel.home_dir):
		choix2 = input(
	"""
De même, nous aurons besoin du dossier '%s' pour les modèles CRF ("CRF Store")
  => Voulez-vous aussi le créer maintenant ? (y/n) """ % CRFModel.home_dir)
	if choix2[0] in ['Y','y','O','o']:
		makedirs(CRFModel.home_dir)
	else:
		exit(1)
	
	# --- import des modèles grobid courants (aka 'vanilla') ---
	
	
	
	# --- premier corpus d'évaluation --------------------------
	# nom du nouveau corpus
	eval_c_name = CONF['eval']['CORPUS_NAME']
	# taille
	eval_size = input("choisissez la taille du corpus d'évaluation par défaut pour initialiser un nouveau dossier corpus '%s' sous /corpora [défaut:100]: " % eval_c_name).rstrip()
	
	if not match(r'[0-9]*', eval_size):
		exit(1)
	else:
		if len(eval_size):
			the_size = int(eval_size)
		else:
			the_size = 100
		# >> initialisation <<
		a_corpus_obj = make_set(
					corpus_name = eval_c_name,
					size = the_size
				)
		print("=> Sous-dossiers obtenus dans %s/data/" % a_corpus_obj.cdir)
		for this_shelf in a_corpus_obj.fulltextsh():
			print("  - %s" % SHELF_NAMES[this_shelf])
		print("+  Tableau récapitulatif dans %s/meta/infos.tab" % a_corpus_obj.cdir)
	
	print("BAKO: all tasks DONE for '%s' prepared corpus" % a_corpus_obj.name)
	
	
	# --- première évaluation ----------------------------------
	input('appuyez sur entrée pour lancer la première évaluation (avec juste les modèles grobid courants, dits aussi "vanilla")')


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
	
	#£TODO lancement assistant la 1ère fois
	
