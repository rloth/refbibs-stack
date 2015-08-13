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
from argparse  import ArgumentParser, RawTextHelpFormatter


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
# Fonctions principales

def make_set(corpus_name, ttype="train", tab_path=None, size=None, constraint=None):
	"""
	Initialisation d'un corpus basique et remplissage de ses fulltexts
	
	3 façons de l'appeler :
	  - soit on fournit un tab (chemin fs)
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
	if tab_path and size:
		print("""ERR bako.make_set:
		         fournir au choix 'tab_path' ou 'size', mais pas les 2.""",
		         file=stderr)
		exit(1)

	if tab_path:
		if path.exists(tab_path):
			fic = open(tab_path)
			my_tab = fic.readlines()
			fic.close()
		else:
			print("ERR bako.make_set: je ne trouve pas le fichier '%s'" % tab_path, file=stderr)
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
			       % tab_path, file=stderr)
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
	
	# we return the new filled corpus for further work or display
	return cobj





PREP_TEI_FROM_TXT = {
					'bibzone' : {'from': 'BZRTX', 'to': 'BZTEI'},
					'biblines' : {'from': 'BLRTX', 'to': 'BLTEI'},
					'bibfields' : {'from': 'BFRTX', 'to': 'BFTEI'},
					'authornames' : {'from': 'AURTX', 'to': 'AUTEI'},
					}

def make_trainers(cobj, model_types=None, just_rag=False):
	"""
	Préparation des corpus d'entraînement => dans dossiers D-*
	
	model_types est une todoliste de modèles parmi les 4 possibles
	     ('bibzone', 'biblines', 'bibfields', 'authornames')
	
	NB: bibzone et biblines ont des fichiers 'rawtoks' supplémentaires
	    qui correspondent à l'input tokenisé vu par un CRF ("features")
	"""
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
		cobj.construct_training_tei(tgt_model)
		# ======================================================
	
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



########################################################################
if __name__ == '__main__':
	
	#~ print(vars(args))  # <== après réintégration argparse
	
	# -------------
	# SIMPLES TESTS  : task 1 sampling et pub2tei (make_set)  
	#                  task 2 préparation trainers (make_trainers)
	
	# si lecture d'une dir pré-existante
	# 
	
	inname = input("choisissez un nom (si possible sans espaces...) pour initialiser un nouveau dossier corpus sous /corpora :")
	
	if len(inname):
		# todo ttype="gold" (défaut) ou "train" ?
		a_corpus_obj = make_set(corpus_name = inname.rstrip() , size = 10)
	
	else:
		print("mode lecture ==> futur take_set() sur %s")
		a_corpus_obj = Corpus("truc", read_dir="corpora/truc")

	input("appuyez sur entrée pour lancer le createTraining puis le ragreage")
	
	# par défaut: avec les modèles de local_conf.ini['training']
	make_trainers(a_corpus_obj)

	# make_trainers(a_corpus_obj, ['bibfields', 'bibzone'])
	
	
	# TODO immédiat
	# ----------------
	# make_training  /model_type/ /sample/ <=> ci-dessus _call_grobid_trainer
	# ----------------
	
	print("BAKO: all tasks successful for '%s' corpus" % a_corpus_obj.name)
	print("=> Sous-dossiers obtenus dans %s/data/" % a_corpus_obj.cdir)
	for this_shelf in a_corpus_obj.fulltextsh():
		print("  - %s" % SHELF_NAMES[this_shelf])
	print("+  Tableau récapitulatif dans %s/meta/infos.tab" % a_corpus_obj.cdir)
	
	
	
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
	
