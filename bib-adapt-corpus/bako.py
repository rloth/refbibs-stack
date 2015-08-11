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
__version__   = "0.1"
__email__     = "romain.loth@inist.fr"
__status__    = "Dev"

# imports
from os              import path, mkdir, rename
from sys             import stderr, argv
from configparser    import ConfigParser
from site            import addsitedir  # pour imports locaux
from re              import search, match

# imports locaux
addsitedir('lib')

# lib istex-rd "consulte"
import sampler
import api

# Corpus => bnames, cdir, cols, shelfs...
from corpusdirs import Corpus


# ----------------------------------------------------------------------
# lecture de fichier config local
LCONF = ConfigParser()
conf_path = 'local_conf.ini'
conf_file = open(conf_path, 'r')
LCONF.read_file(conf_file)
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

# ----------------------------------------------------------------------
# Fonctions principales

def make_set(corpus_name, tab_path=None, size=None, constraint=None):
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
	my_ko = Corpus(corpus_name, my_tab)
	
	# (3/4) téléchargement des fulltexts ---------------------------------
	
	ids = my_ko.cols['istex_id']
	
	for the_shelf in ['PDF0', 'XMLN']:
		tgt_dir = my_ko.shelf_path(the_shelf)
		print("mkdir: %s" % tgt_dir,
		      file=stderr)
		mkdir(tgt_dir)
	
		for (i, ID) in enumerate(ids):
			the_api_type = BSHELFS[the_shelf]['api']
			the_ext = BSHELFS[the_shelf]['ext']
			
			api.write_fulltexts(
				ID,
				api_conf  = LCONF['istex-api'],
				tgt_dir   = my_ko.shelf_path(the_shelf),
				base_name = my_ko.bnames[i],
				api_types = [the_api_type]
				)
			print("GETDOC: %s" % my_ko.bnames[i]+BSHELFS[the_shelf]['ext'],
			  file=stderr)
	
	my_ko.assert_fulltexts('XMLN')
	my_ko.assert_fulltexts('PDF0')
	
	# (4/4) conversion tei (type gold biblStruct) ------------------------
	
	# copie en changeant les pointeurs dtd
	print("***DTD LINKING***")
	my_ko.dtd_repair()
	
	print("***XML => TEI.XML CONVERSION***")
	
	# créera le dossier C-goldxmltei
	my_ko.pub2tei(bibl_type='biblStruct')      # conversion
	
	my_ko.assert_fulltexts('GTEI')
	
	# we return the new filled corpus for further work or display
	return my_ko


def make_trainers(a_corpus_obj, model_types=None):
	print("NOW TRAINERS")
	# model_types est une liste de modèles parmi les 4 possibles
	# ('bibzone', 'biblines', 'bibfields', 'authornames')
	
	if not model_types:
		model_types = LCONF['training']['model_types'].split(',')
	
	print("cof: model_types", model_types)
	
	for tgt_model in model_types:
		a_corpus_obj.grobid_create_training(tgt_model)

	#~ for tgt_model in model_types:
		#~ # traitement purement par ragréage
		#~ if tgt_model in ['bibzone','biblines']:
			#~ 
		#~ 
		#~ 
		#~ 
		#~ elif tgt_model in ['bibfields','authornames']:
			#~ # pour ces 2 modèles on n'aura pas besoin de 'corpus/raw' 
			#~ #                                           (aka #rawtoks#)
			#~ 
			#~ # de plus pour wiley et nature le ragreage n'est pas
			#~ # nécessaire, il suffit de faire XSLT avec le param 
			#~ # teiBiblType fixé à 'bibl'
			#~ 
			#~ # mais pour les autres lots on veut quand même des #rawtxts#

			#~ #  => on est obligés de mettre les wiley et nature à part 
			#~ #     pour utiliser -dIn sur les autres en corpusTraining
			#~ temp_dir = path.join(a_corpus_obj.cdir,'data', 'D-trainers', 'temp_xsl_in')
			#~ if not path.exists(temp_dir):
				#~ mkdir(temp_dir)
			#~ 
			#~ # puis lors du ragreage (qui est lancé doc par doc)
			#~ # on peut faire un filtre sur le trigramme de lot
			#~ for i, bname in enumerate(a_corpus_obj.bnames):
				#~ lot = a_corpus_obj.cols['corpus'][i]
				#~ if lot in ['wil', 'nat']:
					#~ # ici move TEMP_DIR_TO_REXSLT
					#~ pass
				#~ else:
					#~ ragreage.run(model_type...)
					#~ pass
		
	
	
	pass



########################################################################
if __name__ == '__main__':
	# Ok
	#~ a_corpus_obj = make_set(corpus_name = argv[1], tab_path = argv[2])
	a_corpus_obj = make_set("stest", size = 5)
	
	make_trainers(a_corpus_obj)
	
	# ou lecture de la dir précédente
	#~ a_corpus_obj = Corpus("cent_éval", read_dir="corpora/cent_éval")
	
	# balisage initial d'un sample GOLD
	# mkdir(Z-evalxmltei)
	# grobid -exe processReferences -dIn A-pdfs/ -dOut ZZ-evalxmltei/
	
	# tout de suite une éval => shb grep => meta/mon_sample_gold.vanilla.score
	# ------------------------------------------------------------------------
	# eval_xml_refbibs_multiformat.pl -g elsevier -f tei-grobid -r B-xmlnatifs -x C-goldxmltei/ -e xml > eval_via_B.tab
	# eval_xml_refbibs_tei.pl -x ZZ-evalxmltei/ -r C-goldxmltei/ -e references.tei.xml -n > eval_via_C-tei.tab
	
	print("LOG des sous-dossiers data/.\n%s" % a_corpus_obj.fulltextsh())
	
	print("BAKO: all tasks successful for '%s' corpus" % a_corpus_obj.name)