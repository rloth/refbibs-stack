#! /usr/bin/python3
"""
Simple CRF model fs management
"""
__author__    = "Romain Loth"
__copyright__ = "Copyright 2014-5 INIST-CNRS (ISTEX project)"
__license__   = "LGPL"
__version__   = "0.1"
__email__     = "romain.loth@inist.fr"
__status__    = "Dev"

from os              import makedirs, path, symlink, stat, listdir
from shutil          import copy
from re              import sub
from sys             import stderr
from configparser    import ConfigParser

# pour l'appel de grobid en training
from subprocess      import check_output, PIPE, Popen
from locale  import getlocale, setlocale, LC_TIME, LC_NUMERIC

# pour lire la version grobid
from lxml            import etree

# pour informer sur la date de création d'un modèle
from time            import localtime, strftime

# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
# read-in bib-adapt config values (model home dir, grobid home)

# NB la conf n'est essentielle *que* pour CRFModel.home_dir
#    (tout le reste pourrait être passé come arg)

CONF = ConfigParser()

# default location: ./global_conf.ini (relative to corpus.py)
script_dir = path.dirname(path.realpath(__file__))
conf_path = path.join(script_dir, '..', 'local_conf.ini')
conf_file = open(conf_path, 'r')
CONF.read_file(conf_file)
conf_file.close()

# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
# Global constants
# ----------------

# G R O B I D    I N F O S
# Valeurs stables de l'installation grobid 
#  | GB_HOME    (exemple: "/home/jeanpaul/grobid")
#  | GB_VERSION (exemple: "GB_0.3.4")
#  | GB_GIT_ID  (exemple: "4116965")
# (pour rangement/suivi des modèles entraînés avec)

GB_HOME = CONF['grobid']['GROBID_HOME']

try:
	gb_pom = [CONF['grobid']['GROBID_HOME'],'grobid-trainer','pom.xml']
	# print("CHEMIN POM de GB",path.join(*gb_pom))
	pom_xml = etree.parse(path.join(*gb_pom))
	version_elt = pom_xml.xpath('/*[local-name()="project"]/*[local-name()="version"]')[0]
	version_elt.text = sub("-SNAPSHOT","",version_elt.text)
	GB_VERSION = "GB_"+version_elt.text
except Exception as e:
	print("Problem while parsing %s: grobid version UNKNOWN" % gb_pom)
	GB_VERSION = 'GB_UNKNOWN'

try:
	GB_GIT_ID = 'git_'+check_output(['git','--git-dir',GB_HOME+"/.git", 'log', '--pretty=format:%h', '-n1']).decode('UTF-8')
except Exception as e:
	print("Problem while looking for grobid git commit id in %s: UNKNOWN" % GB_HOME)
	GB_GIT_ID = 'git_unknown'



# S T R U C T U R E    D E    R A N G E M E N T 
# (à la coltrane)
TIDY_STRUCT = {
	# échantillon de travail
	'SAMP': {
		'_id' : "<mdltype>-<name>-<nfiles>",
		'data': "<mdltype_long>",
		'meta': "<_id.readme>"
		},
	
	# resultat d'un run d'entraînement
	'MODL': {
		'_id'  : "<gb_name>[.<eps>]-<samp_id>",
		'log'  : ["<_id>.crf.log", "<_id>.mvn.log"],
		'model': {"<mdltype_long>":'model.wapiti'}
		},
	
	# résultat d'une évaluation
	'EVAL': {
		'_id' : "<corpus_shortname>-<gb_name>_<samp_id>+",
		'version.log':None,
		'gb_eval_<_id>.log':None,
		'gb_eval_<_id>.tab':None,
		'gb_eval_<_id>.shb':None,
		'TEI-back_done': "%res_tei%"
		},
	}

# ----------------------------------------------------------------------
# ----------------------------------------------------------------------
# our Model class
# ----------------
class CRFModel:
	"""
	A wapiti CRF model with its locatation
	and standard operations/methods
	
	Usual slots:
	 -self.id
	 -self.model_type
	 -self.storing_path
	"""
	
	home_dir = path.join(CONF['workshop']['HOME'],CONF['workshop']['MODELS_HOME'])
	
	# pour compter les instances => model ID
	
	# valeur par défaut
	model_idno = 0
	
	# s'il y a déjà des dossier modèles
	existing_mds = listdir(home_dir)
	
	if existing_mds:
		# alors on prendra plutôt la plus grande des valeurs existantes
		model_idno = int(max([sub(r".*-([0-9]+)$",r"\1",md) for md in existing_mds]))
	
	model_map = {
			'bibzone' : { 
				'gbpath': 'segmentation',
				'gbcmd' : 'train_segmentation',
				'short' : 'seg',
				},
			'biblines' : { 
				'gbpath': 'reference-segmenter',
				'gbcmd' : 'train_reference-segmentation',
				'short' : 'refseg',
				},
			'bibfields' : { 
				'gbpath': 'citation',
				'gbcmd' : 'train_citation',
				'short' : 'cit',
				},
			'authornames' : { 
				'gbpath': 'name/citation',
				'gbcmd' : 'train_name_citation',
				'short' : 'au',
				}
			}
	
	# ------------------------------------------------------------
	#             C O R P U S    I N I T
	# ------------------------------------------------------------

	def __init__(self, the_model_type, samples_list, gb_name="g03test", eps="10^-3", debug_lvl = 0):
		"""
		IN: SAMPLE(S) + grobid infos
		
		OUT: Model instance with:
			self.mid
			--------
			   =  <gb_name>[.<eps>]-<samp_id>
			
			self.recipy
			------------
			   =  {
			       samples_list (??? corpusdirs)
			       train_params
			       }
			
			self.model_type
			----------------
			   =  bibzone|biblines|bibfields|authornames
				 - traduction 1 => self.gb_mdltype_long()
				 - ? traduction 2 => self.gb_mdltype_short()
			
			self.storing_path
			-----------------
			   =  path.join(home_dir, 'run', model_id, 'model', 'model_type_long')
		"""
		
		if not path.exists(CRFModel.home_dir):
			user_reply = input(
"""
PAUSE: Vos paramètres de config ont le dossier '%s'
comme lieu de stockage de tous les modèles CRF ("CRF Store")... mais il n'existe pas encore (nécessaire pour continuer)).

  => Voulez-vous le créer maintenant ? (y/n) """ % CRFModel.home_dir)
			
			if user_reply[0] in ['Y','y','O','o']:
				makedirs(CRFModel.home_dir)
			else:
				exit(1)
		
		# VAR 1: id
		# solution incrément TEMPORAIRE => TODO mieux
		self.model_idno += 1
		# exemple authornames-0.3.4-411696A-42
		self.mid = "-".join([the_model_type,GB_VERSION,GB_GIT_ID,str(self.model_idno)])
		
		# VAR 2: model_type
		self.model_type = the_model_type
		
		# VAR 3: storing_path
		# exemple: /home/jeanpaul/models/authornames-0.3.4-411696A-42
		self.storing_path = path.join(CRFModel.home_dir, self.mid)
		
		# VAR 4: recipy
		self.recipy = None
		
		# flags de statut
		self.ran = False
		self.picked = False
		self.evaluated = False
		
	
	# ------------------------------------------------------
	#         M O D E L    I N F O    M E T H O D S
	# ------------------------------------------------------
	def gb_mdltype_long(self):
		"""
		Returns the grobid long name of a model (str)
		exemple:
		  "segmentation"
		"""
		return CRFModel.model_map[self.model_type]['gbstd']
	
	
	# ------------------------------------------------------
	#         M A I N    M O D E L    T R A I N I N G
	# ------------------------------------------------------
	def call_grobid_trainer(self):
		"""
		ICI Appel training principal
		!!! Ne vérifie pas que les fichiers src sont au bon endroit !!!
		"""
		
		return None
		
		# exemple: "train_name_citation"
		model_cmd = CRFModel.model_map[self.model_type]['gbcmd']
		
		# on travaillera directement là-bas
		work_dir = path.join(CONF['grobid']['GROBID_HOME'],"grobid-trainer")
		
		
		# !!! locale = C !!!
		lc_time_backup = getlocale(LC_TIME)
		lc_numeric_backup = getlocale(LC_NUMERIC)
		setlocale(LC_TIME, 'C')
		setlocale(LC_NUMERIC, 'C')
		
		mon_process = Popen(
			  ['mvn',
			  '-X',
			  'generate-resources',
			  '-P', model_cmd
			  ], 
			  stdout=PIPE, stderr=PIPE,
			  cwd=work_dir
		)
		
		self.ran = True

		for line in mon_process.stderr:
			print(line.decode('UTF-8').rstrip())
		
		# on remet la locale comme avant
		setlocale(LC_TIME, lc_time_backup)
		setlocale(LC_NUMERIC, lc_numeric_backup)
	
	# ------------------------------------------------------
	#         M O D E L   < = >   F I L E S Y S T E M
	# ------------------------------------------------------
	# filesystem interaction: prepare pick, store, install_to_prod
	
	def pick_n_store(self, debug_lvl = 1):
		"""
		Recovers the new model from its standard grobid location and
		stores it in the structured models home_dir with ID and creation info.
		"""
		# WHERE DO WE PICK FROM ?
		# the standard place for models created by grobid
		# ------------------------------------------------
		base_path_elts = [CONF['grobid']['GROBID_HOME'],'grobid-home','models']
		model_path_elts = CRFModel.model_map[self.model_type]['gbpath'].split('/')
		
		full_path_elts = base_path_elts + model_path_elts + ['model.wapiti']
		the_path = path.join(*full_path_elts)
		
		if debug_lvl >= 1:
			# infos complémentaires : taille et date de création
			statinfo = stat(the_path)
			MB_size = statinfo.st_size/1048576
			ctime = strftime("%Y-%m-%d %H:%M:%S", localtime(statinfo.st_ctime))
			print("WILL PICK MODEL:\n  %s\n  (%.1f MB) (created %s)" % (the_path, MB_size, ctime), file=stderr)
		
		
		print("SSP", self.storing_path)
		
		# exemple: /home/jeanpaul/models/authornames-0.3.4-411696A-42
		new_base_dir = self.storing_path
		new_log_dir = path.join(new_base_dir, 'log')
		
		model_dir_elts = [new_base_dir, 'model'] + model_path_elts
		new_model_dir = path.join(*model_dir_elts)
		
		# exemples
		# /home/jeanpaul/models/authornames-0.3.4-411696A-42
		# /home/jeanpaul/models/authornames-0.3.4-411696A-42/log
		# /home/jeanpaul/models/authornames-0.3.4-411696A-42/model/name/citation
		
		makedirs(new_base_dir)
		makedirs(new_log_dir)
		makedirs(new_model_dir)
		
		copy(the_path, path.join(new_model_dir, 'model.wapiti'))
 
		#~ # logs
		#~ mkdir -p $CoLTrAnE/run/$CRFTRAINEDID/log
		#~ mv -v $MY_NEW_SAMP.$eps.trainer.mvn.log $CoLTrAnE/run/$CRFTRAINEDID/log/.
		#~ mv -v $MY_NEW_SAMP.$eps.trainer.crf.log $CoLTrAnE/run/$CRFTRAINEDID/log/.
		
		
		self.picked = True


	# ------------------------------------------------------
	#            M O D E L    E V A L U A T I O N
	# ------------------------------------------------------