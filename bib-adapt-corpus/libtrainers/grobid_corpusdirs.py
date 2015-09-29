#! /usr/bin/python3
"""
Grobid-specific corpus management
"""
__author__    = "Romain Loth"
__copyright__ = "Copyright 2014-5 INIST-CNRS (ISTEX project)"
__license__   = "LGPL"
__version__   = "0.1"
__email__     = "romain.loth@inist.fr"
__status__    = "Dev"

# TODOSPLIT update_triggers

from glob            import glob
from os              import mkdir, path
from shutil          import rmtree, move
from re              import match, search, sub
from subprocess      import check_output, STDOUT
from configparser    import ConfigParser

# imports locaux
import libtrainers.ragreage
from libconsulte.corpusdirs import Corpus, BSHELVES


# ----------------------------------------------------------------------
# read-in bib-adapt config values (workshop dirs, api conf, grobid home)
CONF = ConfigParser()

# default location: ../local_conf.ini (relative to this module)
script_dir = path.dirname(path.realpath(__file__))
conf_path = path.join(script_dir, '..', 'local_conf.ini')
conf_file = open(conf_path, 'r')
CONF.read_file(conf_file)
conf_file.close()

MY_CORPUS_HOME = path.join(CONF['workshop']['HOME'],CONF['workshop']['CORPUS_HOME'])

# ----------------------------------------------------------------------
# Globals

# Extension des infos structurelles de corpus
# aux besoins grobid-trainer
# ("shelf" pour "étagère")
GBTRAIN_UPDATED_SHELVES = {
	# bibzone = segmentation -------------------------
	'BZRTX': {'d':  'D.1.a-trainers-bibzone_rawtxt',
			  'ext':'.training.segmentation.rawtxt',
			},
	'BZRTK': {'d':  'D.1.b-trainers-bibzone_rawtok',
			  'ext':'.training.segmentation',
			},
	'BZTEI': {'d':  'D.1.z-trainers-bibzone_tei',
			  'ext':'.training.segmentation.tei.xml',
			},
	
	# biblines = referenceSegmentation ---------------
	'BLRTX': {'d':  'D.2.a-trainers-biblines_rawtxt',
			  'ext':'.training.referenceSegmenter.rawtxt',
			},
	'BLRTK': {'d':  'D.2.b-trainers-biblines_rawtok',
			  'ext':'.training.referenceSegmenter',
			},
	'BLTEI': {'d':  'D.2.z-trainers-biblines_tei',
			  'ext':'.training.referenceSegmenter.tei.xml',
			},
	
	# bibfields = citations --------------------------
	'BFRTX': {'d':  'D.3.a-trainers-bibfields_rawtxt',
			  'ext':'.training.references.rawtxt',
			},
	'BFTEI': {'d':  'D.3.z-trainers-bibfields_tei', 
			  'ext':'.training.references.tei.xml',
			},
	
	# authornames = name/citation ---------------------
	'AURTX': {'d':  'D.4.a-trainers-authornames_rawtxt', 
			  'ext':'.training.citations.authors.rawtxt',
			},
	'AUTEI': {'d':  'D.4.z-trainers-authornames_tei', 
			  'ext':'.training.citations.authors.tei.xml',
			},
	}

# copie de la UPDATED_SHELVES basique depuis corpusdirs
UPDATED_SHELVES = BSHELVES.copy()
UPDATED_SHELVES.update(GBTRAIN_UPDATED_SHELVES)



# PREP_TEI_FROM_TXT
# grobid_create_training implique naturellement un traitement commun
# mais les accès ensuite et l'usage des documents seront distincts..
PREP_TEI_FROM_TXT = {
'bibzone': {'from': 'BZRTX', 'to': 'BZTEI',
			'prep_exe':  'createTrainingSegmentation',
			'tgt_shelves': ['BZRTX','BZRTK'],
			},

'biblines': {
			'from': 'BLRTX', 'to': 'BLTEI',
			'prep_exe': 'createTrainingReferenceSegmentation',
			'tgt_shelves': ['BLRTX','BLRTK'],
			},

# /!\ les sh_tgt pour bibfields et authornames ne donnent pas de txt
#	 on le créera depuis les tei de prépa => £TODO modif grobid
'bibfields': {'from': 'BFRTX', 'to': 'BFTEI',
			'prep_exe': 'createTrainingFulltext',
			# 'tgt_shelves' :   ['BFRTX'], # idéalement modif GB
			
			# autrement "hack" pour obtenir BFRTX
			'tgt_shelves' :   [],
			'sh_mktxt': {'from':'BFTEI', 'to':'BFRTX'},
			},

'authornames': {'from': 'AURTX', 'to': 'AUTEI',
			'prep_exe': 'createTrainingFulltext', 
			# 'tgt_shelves' :   ['AURTX'], # idéalement modif GB
			
			# autrement "hack" pour obtenir AURTX
			'tgt_shelves' :   [],
			'sh_mktxt': {'from':'AUTEI', 'to':'AURTX'},
			},
}

# ---------------------------------------------------------------------
# C O R P U S    A V E C    D E S    E T A G È R E S    E N    P L U S
# ---------------------------------------------------------------------
class TrainingCorpus(Corpus):
	"""
	Un corpus dir avec 
	
	des étagères mises à jour : fulltexts d'entraînement en plus
	
	et quelques fonctions en plus pour bako.make_trainers
	  flux txt et tok              ---> grobid_create_training
	  flux tei + 'bonnes réponses' ---> construct_training_tei
	"""
	
	def __init__(self, corpus_name):
		"""
		Initialisation globalement comme read_dir d'un corpusdir.Corpus normal,
		mais avec vérification qu'on est dans le dossier fixe de la conf de bako
		
		cf. aussi bako.take_set() qui a inspiré ces lignes
		"""
		
		# doit être là
		expected_dir = path.join(MY_CORPUS_HOME, corpus_name)
		try:
			print("=======  %s  =======" % corpus_name)
			# initialisation (mode read_dir)
			# ----------------------------------------------
			seed = Corpus(corpus_name, 
					read_dir = expected_dir,
					corpus_type = 'train',
					verbose  = True,
					new_home = MY_CORPUS_HOME,
					shelves_struct  = UPDATED_SHELVES)
			# ----------------------------------------------
		except FileNotFoundError as fnf_err:
			print("Je ne trouve pas '%s dans le dossier attendu %s\n" % (
						fnf_err.pi_mon_rel_path,
						MY_CORPUS_HOME
						))
			fnf_err.corpus_name = corpus_name
			raise(fnf_err)
		
		# si on est là self contiendra toutes les méthodes de Corpus
		# mais il faut encore transférer les variables
		
		self._home    = seed._home
		self._shtruct = seed._shtruct
		
		self.name   = seed.name
		self.cdir   = seed.cdir
		self.shelfs = seed.shelfs
		self.meta   = seed.meta
		self.cols   = seed.cols
		self.bnames = seed.bnames
		self.size   = seed.size
		
		# et voilà !


	# TRAINING RAWTXT central
	# todo skip if (wiley or nature) and (bibfields ou authornames)
	def grobid_create_training(self, tgt_model):
			"""
			Appel de grobid createTraining (pour les rawtoks et les rawtxts)
			
			Les instructions de traitement sont :
				 - la liste des modèles à faire pour grobid
				 - un dic PREP_TEI_FROM_TXT aux entrées de la forme:
			
			'nom_modele':{'prep_exe': commande grobid,
							 'tgt_shelves' : [étagères à récupérer],
							 },
			
			cf. aussi grobid.readthedocs.org/en/latest/Training-the-models-of-Grobid/
				sous "Generation of training data"
			
			hack : une clé supplémentaire 
					  'sh_mktxt': pointe une étagère permettant de refaire le texte
								si sh_tgt ne peut créer directement le ..RTX
							
			NB: ici seule utilisation de PREP_TEI_FROM_TXT /?\
			"""
			gb_d = CONF['grobid']['GROBID_DIR']
			gb_h = path.join(gb_d,'grobid-home')
			gb_p = path.join(gb_h,'grobid-home','config','grobid.properties')
			
			# todo faire mieux mais si possible rester indep de la version
			my_jar_path = glob(path.join(gb_d, 'grobid-core','target')
										 +"/grobid-core*.one-jar.jar")[0]
			
			# pdfs: unique input dir in any case
			pdf_dir_in =  path.join(self.cdir,self.shelf_path('PDF0'))
			
			
			# commun aux formes rawtxts et aux éventuels rawtoks
			exe_process = PREP_TEI_FROM_TXT[tgt_model]['prep_exe']
			
			# temporary output_dir, elle aussi commune aux deux formes
			temp_dir_out = path.join(self.cdir, "temp_raws_%s" % tgt_model)
			
			if not path.exists(temp_dir_out):
				mkdir(temp_dir_out)
				print("TMP: création dossier %s" % temp_dir_out)
			
			
			grobid_prepare_args = ["java", "-jar",  my_jar_path,
				"-gH",   gb_h,
				"-gP",   gb_p,
				"-exe",  exe_process,
				"-dIn",  pdf_dir_in,
				"-dOut", temp_dir_out]
			
			
			print("******** PREPARATION RAWTXTs pour %s ********" % tgt_model)
			print("Grobid running process '%s' \n -> on dir:%s, please wait..." % 
					(exe_process, pdf_dir_in))
			
			# subprocess.call ++++++++++++++++++++++ appel système
			gb_errs = check_output(grobid_prepare_args, stderr=STDOUT)
			
			print("GB:STDERR", gb_errs)
			
			print("%s ok... storing new docs in trainer dirs:" % tgt_model)
			
			# a posteriori
			for shelf in PREP_TEI_FROM_TXT[tgt_model]['tgt_shelves']:
				shdir = self.shelf_path(shelf)
				shext = UPDATED_SHELVES[shelf]['ext']
				
				if not path.exists(shdir):
					mkdir(shdir)
				
				# vérif et rangement
				for bn in self.bnames:
					just_created = path.join(temp_dir_out, bn+shext)
					tgt_in_shelf = path.join(shdir, bn+shext)
					if not path.exists(just_created):
						print("WARN: doc %s not done for model %s (skip)"
							  % (bn, tgt_model) )
					else:
						move(just_created, tgt_in_shelf)
					
					# on signale qu'on a réussi #£TODO test poussé
					self.assert_docs(shelf)
					
					
			# ---------------------->8----------------------------------
			# hack pour les rawtxt non générables: bibfields authornames
			if 'sh_mktxt' in PREP_TEI_FROM_TXT[tgt_model]:
				shfrom = PREP_TEI_FROM_TXT[tgt_model]['sh_mktxt']['from']
				shto = PREP_TEI_FROM_TXT[tgt_model]['sh_mktxt']['to']
				
				shfrom_ext = UPDATED_SHELVES[shfrom]['ext']
				shto_ext = UPDATED_SHELVES[shto]['ext']
				shtodir = self.shelf_path(shto)
					
				if not path.exists(shtodir):
					mkdir(shtodir)
				
				# lecture "from", transfo vers "to"
				for bn in self.bnames:
					new_shfrom = path.join(temp_dir_out, bn+shfrom_ext)
					tgt_in_shto = path.join(shtodir, bn+shto_ext)
					if not path.exists(new_shfrom):
						print("WARN: doc %s not done for model %s (skip)"
								  % (bn, tgt_model) )
					# sauvegarde >> .shto.rawtxt
					else:
						if tgt_model == "bibfields":
							_strip_tei_save_txt(new_shfrom, tgt_in_shto, start_tag="listBibl")
						elif tgt_model == "authornames":
							_strip_tei_save_txt(new_shfrom, tgt_in_shto, start_tag="biblStruct")
		
				# on signale aussi qu'on a réussi
				self.assert_docs(shto)
			
			# /!\ dans ts les cas on ne conserve pas les tei de prépa (non gold)
			#	 => n'apparaissent pas dans sh_tgt
			# ---------------------->8----------------------------------
			
			# nettoyage
			rmtree(temp_dir_out)
			
			return None
	
	
	# -----------------------------------------------------------------
	#    C O R P U S   P R E - T R A I N I N G   C O N V E R T E R S
	# -----------------------------------------------------------------
	
	# TRAINING TEI ET RAGREAGE
	def construct_training_tei(self, tgt_model, just_rag = False, debug_lvl=0):
		"""
		Generic call to ragreage.py
		or 
		bibl[@type=trainerlike] specific XSLT
		
		Remarque: théoriquement on peut faire 2 procédures:
		
		Procédure just_rag => création des fulltexts depuis les PDF
	                      puis jonction (ragreage) avec les XML
	                      pour l'obtention des exemplaires annotés
	
		Procédure normale  => idem sauf pour Wiley et Nature qui ont
	                      déjà des bibl dans un markup acceptable
	                    (conversion en exemplaires directe, à part)
		"""
		
		print("******** PREPARATION specTEI pour %s ********" % tgt_model)
		
		src_txt_shelf = PREP_TEI_FROM_TXT[tgt_model]['from']
		tgt_tei_shelf = PREP_TEI_FROM_TXT[tgt_model]['to']
		
		print("SRC shelf", src_txt_shelf)
		
		# new folder
		new_dir = self.shelf_path(tgt_tei_shelf)
		if not path.exists(new_dir):
			mkdir(new_dir)
		
		# pour les tei d'entraînement on procède au cas par cas par fichiers
		# ------------------------------------------------------------------
		for i, bname in enumerate(self.bnames):
			lot = self.cols['corpus'][i]
			
			# modèles à traintei seule: selon lot
			if tgt_model in ['bibfields','authornames'] and not(just_rag) and lot in ['wil', 'nat']:
				# (todo) Le cas des feuilles wiley et nature : 
				# le ragreage n'est pas nécessaire si on veut
				# utiliser le flux natif, car le format est précis
				# TODO
				# possibilité: 
				# appel Pub2TEI  param teiBiblType fixé à 'bibl'
				# _tei_trainerlike_substitution(une_tei_lue, modele_visé)
				
				print("TODO cas trainerlike")
				#    c'est possible grace au produit des feuilles trainerlike
				#     => pour le modèle citations
				#         - supprimer tous les sauts de ligne interne
				#         - supprimer @rend='LB et LABEL'
				#         - supprimer @rend='DEL'
				#         - grouper @rend='GRP'
				#         - grouper les pages ET leur délimiteur non parsé
				#         - remplacer @unit par @type dans les biblScope
				#     => pour le modèle authornames
				#         - ne garder que chaque groupe auteur ou éditeur
				#         - garder les DEL
				#     
				#     NB pour le modèle refseg ce serait aussi envisageable
				#         - juste LABELS si présents, et tout le reste groupé 
				#           sauf rend=LB
				#         - mais actuellement pas alignable sur tokens...  
				pass
			
			# ici: modèles à rawtokens et/ou choix just_rag
			# => traitement purement par ragréage <=
			else:
				my_gold_tei_path = self.fileid(bname,'GTEI')
				my_raw_txt_path  = self.fileid(bname, src_txt_shelf)
				
				# générateur ("yield line" dans ragreage)
				line_gen = libtrainers.ragreage.run(
							# modèle
							the_model_type = tgt_model,
							# chemins
							the_txtin  = my_raw_txt_path,
							the_xmlin  = my_gold_tei_path,
							debug_lvl = debug_lvl
						   )
				
				my_train_tei_path = self.fileid(bname, tgt_tei_shelf)
				
				# écriture de chaque ligne ragrégée
				ttei_xml = open(my_train_tei_path, 'w')
				for tline in line_gen:
					ttei_xml.write(tline+"\n")
				ttei_xml.close()
			
			self.assert_docs(tgt_tei_shelf)

		return None


# -----------------------------------------------------------------------------------
# TRAINING RAWTXT helper externe strip gb ptei
def _strip_tei_save_txt(tei_path_in, txt_path_out, start_tag="listBibl"):
	"""
	Helper function for rawtxt generation
	Opens, strips XML markup and saves.
	
	We start the rendering only at listBibl because this 
	function is only used in bibfields and authornames models
	(they wouldn't need what precedes)
	
	
	# dans notre contexte, c'est SEMI-SATISFAISANT
		> prendre dans le training.tei c'est un listBibl incertain
		> mais tout de même le gros des bibl est majoritairement là
		> et c'est bien le listBibl tel que la cascade l'aurait eu
	"""
	tei_in = open(tei_path_in, 'r')
	all_lines = []
	on = False
	
	# first : diagnosis
	for line in tei_in.readlines():
					# trigger: a lone listBibl
					if match(r'^\s*<%s>$' % start_tag, line):
							on = True
					if match(r'^\s*</%s>$' % start_tag, line):
							on = False
					if on:
							# one or more sub-lines
							sublines = line.split('<lb/>')
							# (rather one but for the rare cases are interesting)
							for sline in sublines:
									# strip fixed indent
									sline = sub(r'^\t+', '', sline)
									
									# >> strip all xml tags <<
									sline = sub(r'<[^>]+>', '', sline)
									
									# convert 5 entities back to text
									sline = sub(r'&amp;', '&', sline)
									sline = sub(r'&lt;',  '<', sline)
									sline = sub(r'&gt;',  '>', sline)
									sline = sub(r'&quot;', '"', sline)
									sline = sub(r'&apos;', "'", sline)
									
									all_lines.append(sline)
	tei_in.close()
	txt_fh = open(txt_path_out, 'w')
	# lines still have their newlines
	txt_fh.write('\n'.join(all_lines)+'\n')   # todo vérifier les newlines
	txt_fh.close()
